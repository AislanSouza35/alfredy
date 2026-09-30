"""
Alternativa de voz quando a cota do Gemini acaba.

Em 18/09/2026 a cota da chave do Gemini esgotou no meio da manhã e o
ALF simplesmente parou: um provedor só, sem para onde ir. O JARVIS, no
mesmo computador, atravessa isso porque tem uma cadeia de alternativas.

Este módulo é a alternativa do ALF. Ele conversa com a API Realtime da
OpenAI, mas oferece para o resto do programa a MESMA superfície que a
sessão do Gemini oferece: send_realtime_input, send_client_content,
send_tool_response e receive(). Assim o microfone, a reprodução, as
ferramentas e o laço de recebimento continuam exatamente como estão --
só muda quem está do outro lado do fio.

Duas diferenças que não dá para esconder, e que o ALF avisa em voz alta:

1. Imagem não vai. A Realtime da OpenAI trata texto e áudio; a análise
   de tela do ALF depende do Gemini. Em vez de fingir que olhou, ele
   recebe um aviso escrito de que está sem visão.
2. O clique visual também usa o Gemini. Se a cota que acabou for a do
   Gemini, ele continua indisponível mesmo nesta alternativa.

Sem SDK novo de propósito: websockets já está no projeto, e a Realtime
é um WebSocket com mensagens JSON.
"""

import asyncio
import base64
import json
from array import array
from contextlib import asynccontextmanager

import websockets

from core.gemini_ssl import criar_contexto_ssl_gemini


ENDERECO = "wss://api.openai.com/v1/realtime"

# Taxa que a Realtime usa nos dois sentidos. A saída do ALF já é 24 kHz;
# a entrada é 16 kHz e precisa ser reamostrada.
TAXA_OPENAI = 24000
TAXA_MICROFONE = 16000

TEMPO_LIMITE_CONEXAO = 30

AVISO_SEM_VISAO = (
    "[A alternativa de voz está ativa porque a cota do Gemini acabou. "
    "Nesta alternativa você NÃO enxerga a tela nem a câmera: diga isso "
    "ao usuário em uma frase, sem inventar o que estaria na imagem.]"
)


# ============================================================
# ÁUDIO
# ============================================================

def reamostrar_para_24k(pcm16, sobra=None):
    """
    Converte áudio de 16 kHz para 24 kHz.

    São três amostras de saída para cada duas de entrada. A amostra
    ímpar que sobra no fim do bloco volta como 'sobra' e entra no bloco
    seguinte: descartá-la a cada bloco produziria um estalo regular.

    Devolve (bytes_em_24k, sobra).
    """

    amostras = array("h")
    if sobra:
        amostras.extend(sobra)
    amostras.frombytes(bytes(pcm16))

    saida = array("h")
    indice = 0

    while indice + 1 < len(amostras):
        primeira = amostras[indice]
        segunda = amostras[indice + 1]

        saida.append(primeira)
        saida.append((primeira + segunda) // 2)
        saida.append(segunda)

        indice += 2

    resto = array("h", amostras[indice:]) if indice < len(amostras) else None

    return saida.tobytes(), resto


# ============================================================
# FERRAMENTAS
# ============================================================

def _schema_para_dicionario(schema):
    """Traduz um types.Schema do Gemini para JSON Schema comum."""

    if schema is None:
        return None

    tipo = getattr(schema, "type", None)
    tipo = str(getattr(tipo, "value", tipo) or "object").lower()

    convertido = {"type": tipo}

    descricao = getattr(schema, "description", None)
    if descricao:
        convertido["description"] = descricao

    propriedades = getattr(schema, "properties", None) or {}
    if propriedades:
        convertido["properties"] = {
            nome: _schema_para_dicionario(valor)
            for nome, valor in propriedades.items()
        }

    itens = getattr(schema, "items", None)
    if itens is not None:
        convertido["items"] = _schema_para_dicionario(itens)

    obrigatorios = getattr(schema, "required", None)
    if obrigatorios:
        convertido["required"] = list(obrigatorios)

    return convertido


def converter_ferramentas(ferramentas):
    """
    Traduz as declarações de função do Gemini para o formato da OpenAI.

    As 67 ferramentas do ALF são declaradas uma única vez, no formato do
    Gemini. Traduzir aqui evita manter duas listas que iriam divergir na
    primeira pressa.
    """

    convertidas = []

    for ferramenta in ferramentas or []:
        declaracoes = getattr(ferramenta, "function_declarations", None) or []

        for declaracao in declaracoes:
            parametros = _schema_para_dicionario(
                getattr(declaracao, "parameters", None)
            ) or {"type": "object", "properties": {}}

            convertidas.append(
                {
                    "type": "function",
                    "name": declaracao.name,
                    "description": getattr(declaracao, "description", "") or "",
                    "parameters": parametros,
                }
            )

    return convertidas


# ============================================================
# EVENTOS DEVOLVIDOS AO LAÇO DE RECEBIMENTO
# ============================================================

class _TurnoTerminou:
    turn_complete = True


class _ChamadaDeFuncao:
    def __init__(self, id_chamada, nome, argumentos):
        self.id = id_chamada
        self.name = nome
        self.args = argumentos


class _ListaDeChamadas:
    def __init__(self, chamadas):
        self.function_calls = chamadas


class Evento:
    """
    Imita a resposta do Gemini Live, campo por campo.

    O laço de recebimento do ALF lê .data, .tool_call, .server_content,
    .session_resumption_update e .go_away. Manter os mesmos nomes é o
    que permite trocar o provedor sem tocar no laço.
    """

    def __init__(self, data=None, tool_call=None, server_content=None):
        self.data = data
        self.tool_call = tool_call
        self.server_content = server_content
        self.session_resumption_update = None
        self.go_away = None


# ============================================================
# A SESSÃO
# ============================================================

class SessaoOpenAIRealtime:
    """Fala com a Realtime da OpenAI com a cara da sessão do Gemini."""

    def __init__(self, websocket):
        self._ws = websocket
        self._sobra_audio = None
        # call_id de cada função, para devolver o resultado no lugar certo.
        self._chamadas = {}

    # ---------- envio ----------

    async def _enviar(self, mensagem):
        await self._ws.send(json.dumps(mensagem))

    async def send_realtime_input(self, audio=None, audio_stream_end=False):
        if audio_stream_end:
            # Com detecção de fala no servidor, o fim do turno é decidido
            # lá. Não há o que enviar, e forçar um commit aqui cortaria
            # a frase do usuário pela metade.
            return

        if audio is None:
            return

        dados, self._sobra_audio = reamostrar_para_24k(
            audio.data, self._sobra_audio
        )

        await self._enviar(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(dados).decode("ascii"),
            }
        )

    async def send_client_content(self, turns=None, turn_complete=True):
        """
        Manda um turno do usuário. Imagem vira aviso escrito.

        O ALF usa isto para a abertura da conversa e para análise de
        tela. Fingir que a imagem foi enviada faria o modelo descrever
        uma tela que ele nunca viu.
        """

        textos = []
        tinha_imagem = False

        for parte in getattr(turns, "parts", None) or []:
            texto = getattr(parte, "text", None)
            if texto:
                textos.append(texto)
            if getattr(parte, "inline_data", None) is not None:
                tinha_imagem = True

        if tinha_imagem:
            textos.append(AVISO_SEM_VISAO)

        if not textos:
            return

        await self._enviar(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": " ".join(textos)}],
                },
            }
        )

        if turn_complete:
            await self._enviar({"type": "response.create"})

    async def send_tool_response(self, function_responses=None):
        for resposta in function_responses or []:
            nome = getattr(resposta, "name", "")
            id_chamada = self._chamadas.pop(nome, None) or getattr(
                resposta, "id", ""
            )

            conteudo = getattr(resposta, "response", None) or {}
            saida = conteudo.get("result", conteudo)

            await self._enviar(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": id_chamada,
                        "output": str(saida),
                    },
                }
            )

        await self._enviar({"type": "response.create"})

    # ---------- recebimento ----------

    async def receive(self):
        async for bruto in self._ws:
            evento = json.loads(bruto)
            tipo = evento.get("type", "")

            if tipo == "response.audio.delta" or tipo == "response.output_audio.delta":
                yield Evento(data=base64.b64decode(evento.get("delta", "")))

            elif tipo in (
                "response.function_call_arguments.done",
                "response.output_item.done",
            ):
                chamada = self._ler_chamada(evento)
                if chamada is not None:
                    yield Evento(tool_call=_ListaDeChamadas([chamada]))

            elif tipo == "response.done":
                yield Evento(server_content=_TurnoTerminou())

            elif tipo == "error":
                detalhe = evento.get("error", {}) or {}
                raise RuntimeError(
                    f"OpenAI Realtime: {detalhe.get('message', 'erro sem descrição')}"
                )

    def _ler_chamada(self, evento):
        """Monta a chamada de função, venha ela em qual evento vier."""

        item = evento.get("item") or {}
        if item and item.get("type") != "function_call":
            return None

        nome = evento.get("name") or item.get("name")
        if not nome:
            return None

        id_chamada = evento.get("call_id") or item.get("call_id") or ""
        argumentos = evento.get("arguments") or item.get("arguments") or "{}"

        try:
            argumentos = json.loads(argumentos)
        except (TypeError, ValueError):
            argumentos = {}

        self._chamadas[nome] = id_chamada

        return _ChamadaDeFuncao(id_chamada, nome, argumentos)


# ============================================================
# CONEXÃO
# ============================================================

def montar_configuracao(instrucao, ferramentas, voz):
    """
    Configuração no formato definitivo da Realtime.

    A primeira versão usava o formato beta, com o cabeçalho
    OpenAI-Beta e os campos soltos na raiz da sessão. Esta conta
    recusou com "beta_api_shape_disabled": o formato beta está
    desligado. No definitivo, áudio de entrada e de saída ficam
    aninhados, cada um com a sua taxa.
    """

    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "instructions": instrucao,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": TAXA_OPENAI},
                    "turn_detection": {"type": "server_vad"},
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": TAXA_OPENAI},
                    "voice": voz,
                },
            },
            "tools": converter_ferramentas(ferramentas),
            "tool_choice": "auto",
        },
    }


@asynccontextmanager
async def conectar(api_key, modelo, instrucao, ferramentas, voz, abrir=None):
    """
    Abre a sessão alternativa. abrir existe para os testes.

    Devolve algo com a mesma cara da sessão do Gemini, para o laço de
    recebimento do ALF não precisar saber de nada disto.
    """

    if not api_key:
        raise RuntimeError(
            "A alternativa de voz precisa de OPENAI_API_KEY no arquivo .env."
        )

    if abrir is None:
        abrir = websockets.connect

    conexao = await asyncio.wait_for(
        abrir(
            f"{ENDERECO}?model={modelo}",
            # Sem cabeçalho beta: esta conta só aceita o formato
            # definitivo, e o beta responde beta_api_shape_disabled.
            additional_headers={"Authorization": f"Bearer {api_key}"},
            ssl=criar_contexto_ssl_gemini(),
            max_size=None,
        ),
        timeout=TEMPO_LIMITE_CONEXAO,
    )

    sessao = SessaoOpenAIRealtime(conexao)

    try:
        await sessao._enviar(montar_configuracao(instrucao, ferramentas, voz))
        yield sessao
    finally:
        await conexao.close()
