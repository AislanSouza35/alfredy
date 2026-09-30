"""
Último recurso: o ALF funcionando sem nenhuma API de voz em tempo real.

A cadeia do ALF tem três degraus. Gemini Live e OpenAI Realtime são voz
de verdade: áudio nos dois sentidos, interrupção no meio da fala. Este
terceiro degrau é outra coisa, porque Groq, Mistral e Cerebras não têm
voz em tempo real -- são APIs de texto.

Aqui o caminho é: ouvir até o silêncio, transcrever, responder em texto,
falar. Mais lento, sem poder interromper no meio da fala, e com a voz do
Windows em vez de uma voz neural. Em compensação, funciona quando as
duas primeiras estão fora, e a fala não depende de cota nenhuma: é o
sintetizador do próprio computador.

Como os outros degraus, oferece a MESMA superfície da sessão do Gemini,
para o microfone, a reprodução e as 72 ferramentas seguirem sem mudança.

O que ele mantém: conversa, memória da conversa e as ferramentas.
O que ele perde: interromper a fala do ALF, e enxergar a tela.
"""

import asyncio
import json
import subprocess
import tempfile
import time
import wave
from array import array
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from voz.openai_realtime import (
    AVISO_SEM_VISAO,
    Evento,
    _ChamadaDeFuncao,
    _ListaDeChamadas,
    _TurnoTerminou,
    converter_ferramentas,
)


TAXA_MICROFONE = 16000
TAXA_SAIDA = 24000

# Acima disto é voz; abaixo é ruído de sala.
NIVEL_DE_VOZ = 0.04

# Silêncio que encerra a fala. Curto demais corta o usuário no meio de
# uma pausa; longo demais faz a resposta parecer travada.
SILENCIO_PARA_ENCERRAR = 0.9

# Fala curta demais é tosse, porta batendo, clique de mouse.
DURACAO_MINIMA_DA_FALA = 0.4

# Pedaços em que o áudio falado é entregue, para a reprodução começar
# antes de a frase inteira estar pronta.
BLOCO_DE_SAIDA = 4800

TEMPO_LIMITE_HTTP = 60


def nivel_do_bloco(pcm16):
    """Pico do bloco, de 0 a 1."""

    amostras = array("h")
    amostras.frombytes(bytes(pcm16))

    if not amostras:
        return 0.0

    return max(abs(amostra) for amostra in amostras) / 32768.0


def montar_wav(pcm16, taxa=TAXA_MICROFONE):
    """Embrulha o PCM num WAV, que é o que a transcrição aceita."""

    caminho = Path(tempfile.gettempdir()) / f"alf_fala_{int(time.time()*1000)}.wav"

    with wave.open(str(caminho), "wb") as arquivo:
        arquivo.setnchannels(1)
        arquivo.setsampwidth(2)
        arquivo.setframerate(taxa)
        arquivo.writeframes(bytes(pcm16))

    return caminho


# ============================================================
# FALAR — pelo sintetizador do Windows
# ============================================================

def sintetizar(texto, voz=""):
    """
    Devolve o PCM de 24 kHz da frase falada, ou b"" se não der.

    Usa o sintetizador do próprio Windows. É a única parte desta cadeia
    que não depende de rede nem de cota: se tudo mais falhar, o ALF
    ainda tem voz.
    """

    texto = " ".join(str(texto or "").split())
    if not texto:
        return b""

    pasta = Path(tempfile.gettempdir())
    marca = int(time.time() * 1000)
    arquivo_texto = pasta / f"alf_tts_{marca}.txt"
    arquivo_wav = pasta / f"alf_tts_{marca}.wav"

    try:
        arquivo_texto.write_text(texto, encoding="utf-8")

        escolher_voz = (
            f"try {{ $s.SelectVoice('{voz}') }} catch {{}}" if voz else ""
        )

        script = f"""
Add-Type -AssemblyName System.Speech
$t = Get-Content -Raw -Encoding UTF8 '{arquivo_texto}'
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
{escolher_voz}
$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo({TAXA_SAIDA}, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile('{arquivo_wav}', $f)
$s.Speak($t)
$s.Dispose()
"""

        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if not arquivo_wav.exists():
            return b""

        with wave.open(str(arquivo_wav), "rb") as som:
            return som.readframes(som.getnframes())

    except Exception:
        return b""

    finally:
        for descartavel in (arquivo_texto, arquivo_wav):
            try:
                descartavel.unlink(missing_ok=True)
            except OSError:
                pass


# ============================================================
# OS PROVEDORES DE TEXTO
# ============================================================

class Provedor:
    """Um serviço de texto compatível com o formato da OpenAI."""

    def __init__(self, nome, endereco, chave, modelo):
        self.nome = nome
        self.endereco = endereco
        self.chave = chave
        self.modelo = modelo

    def disponivel(self):
        return bool(self.chave)


async def conversar_com_provedores(provedores, mensagens, ferramentas, cliente):
    """
    Tenta os provedores em ordem e devolve (mensagem, provedor, erro).

    A cadeia existe porque o motivo de estar aqui é justamente cota
    acabando: insistir num provedor só repetiria o problema.
    """

    ultimo_erro = "nenhum provedor configurado"

    for provedor in provedores:
        if not provedor.disponivel():
            continue

        corpo = {
            "model": provedor.modelo,
            "messages": mensagens,
            "temperature": 0.6,
        }

        if ferramentas:
            corpo["tools"] = [
                {"type": "function", "function": f} for f in ferramentas
            ]
            corpo["tool_choice"] = "auto"

        try:
            resposta = await cliente.post(
                f"{provedor.endereco}/chat/completions",
                headers={"Authorization": f"Bearer {provedor.chave}"},
                json=corpo,
                timeout=TEMPO_LIMITE_HTTP,
            )

            if resposta.status_code >= 400:
                ultimo_erro = f"{provedor.nome}: {resposta.status_code} {resposta.text[:160]}"
                continue

            dados = resposta.json()
            return dados["choices"][0]["message"], provedor, None

        except Exception as falha:
            ultimo_erro = f"{provedor.nome}: {falha}"

    return None, None, ultimo_erro


async def transcrever(pcm16, chave, modelo, cliente):
    """Devolve (texto, erro). Whisper no Groq: é o mais rápido que há."""

    if not chave:
        return "", "sem GROQ_API_KEY para transcrever"

    caminho = montar_wav(pcm16)

    try:
        with caminho.open("rb") as arquivo:
            resposta = await cliente.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {chave}"},
                files={"file": (caminho.name, arquivo, "audio/wav")},
                data={"model": modelo, "language": "pt"},
                timeout=TEMPO_LIMITE_HTTP,
            )

        if resposta.status_code >= 400:
            return "", f"{resposta.status_code} {resposta.text[:160]}"

        return resposta.json().get("text", "").strip(), None

    except Exception as falha:
        return "", str(falha)

    finally:
        try:
            caminho.unlink(missing_ok=True)
        except OSError:
            pass


# ============================================================
# A SESSÃO
# ============================================================

class SessaoModoSimples:
    """Ouvir, transcrever, responder, falar -- com cara de sessão Live."""

    def __init__(self, provedores, chave_groq, modelo_whisper, instrucao,
                 ferramentas, voz_windows, cliente, sintetizador=None,
                 transcritor=None):
        self._provedores = provedores
        self._chave_groq = chave_groq
        self._modelo_whisper = modelo_whisper
        self._ferramentas = converter_ferramentas(ferramentas)
        self._voz = voz_windows
        self._cliente = cliente
        self._sintetizar = sintetizador or (lambda texto: sintetizar(texto, voz_windows))
        self._transcrever = transcritor

        self._historico = [{"role": "system", "content": instrucao}]

        self._falando = bytearray()
        self._tem_voz = False
        self._ultimo_som = None

        self._turnos = asyncio.Queue()
        self._resultados = asyncio.Queue()

    # ---------- entrada ----------

    async def send_realtime_input(self, audio=None, audio_stream_end=False):
        """
        Junta o áudio e decide sozinho quando a fala terminou.

        Aqui não há detecção de fala no servidor: quem decide é este
        laço, pelo nível do som.
        """

        if audio_stream_end or audio is None:
            return

        dados = bytes(audio.data)
        agora = time.monotonic()

        if nivel_do_bloco(dados) >= NIVEL_DE_VOZ:
            self._tem_voz = True
            self._ultimo_som = agora

        if self._tem_voz:
            self._falando.extend(dados)

            silencio = agora - (self._ultimo_som or agora)
            duracao = len(self._falando) / (TAXA_MICROFONE * 2)

            if silencio >= SILENCIO_PARA_ENCERRAR:
                fala = bytes(self._falando)
                self._falando.clear()
                self._tem_voz = False
                self._ultimo_som = None

                if duracao >= DURACAO_MINIMA_DA_FALA:
                    await self._turnos.put(fala)

    async def send_client_content(self, turns=None, turn_complete=True):
        textos = []
        tinha_imagem = False

        for parte in getattr(turns, "parts", None) or []:
            if getattr(parte, "text", None):
                textos.append(parte.text)
            if getattr(parte, "inline_data", None) is not None:
                tinha_imagem = True

        if tinha_imagem:
            textos.append(AVISO_SEM_VISAO)

        if textos:
            await self._turnos.put(" ".join(textos))

    async def send_tool_response(self, function_responses=None):
        for resposta in function_responses or []:
            conteudo = getattr(resposta, "response", None) or {}
            await self._resultados.put(
                {
                    "role": "tool",
                    "tool_call_id": getattr(resposta, "id", "") or "",
                    "content": str(conteudo.get("result", conteudo)),
                }
            )

    # ---------- saída ----------

    async def receive(self):
        while True:
            entrada = await self._turnos.get()

            if isinstance(entrada, bytes):
                texto, erro = await self._ouvir(entrada)
                if erro or not texto:
                    continue
            else:
                texto = entrada

            self._historico.append({"role": "user", "content": texto})

            async for evento in self._responder():
                yield evento

    async def _ouvir(self, fala):
        if self._transcrever is not None:
            return await self._transcrever(fala)

        return await transcrever(
            fala, self._chave_groq, self._modelo_whisper, self._cliente
        )

    async def _responder(self):
        """Conversa até chegar numa fala, executando ferramentas no meio."""

        for _ in range(5):  # uma conversa não deveria precisar de mais voltas
            mensagem, _provedor, erro = await conversar_com_provedores(
                self._provedores, self._historico, self._ferramentas, self._cliente
            )

            if erro:
                async for evento in self._falar(
                    "Não consegui responder agora: todos os serviços de texto "
                    "recusaram. Tente de novo em alguns minutos."
                ):
                    yield evento
                return

            self._historico.append(mensagem)

            chamadas = mensagem.get("tool_calls") or []

            if not chamadas:
                async for evento in self._falar(mensagem.get("content") or ""):
                    yield evento
                return

            convertidas = []
            for chamada in chamadas:
                funcao = chamada.get("function", {})
                try:
                    argumentos = json.loads(funcao.get("arguments") or "{}")
                except (TypeError, ValueError):
                    argumentos = {}

                convertidas.append(
                    _ChamadaDeFuncao(
                        chamada.get("id", ""), funcao.get("name", ""), argumentos
                    )
                )

            yield Evento(tool_call=_ListaDeChamadas(convertidas))

            # O ALF executa e devolve por send_tool_response.
            for _ in convertidas:
                self._historico.append(await self._resultados.get())

    async def _falar(self, texto):
        if not str(texto or "").strip():
            yield Evento(server_content=_TurnoTerminou())
            return

        pcm = await asyncio.to_thread(self._sintetizar, texto)

        for inicio in range(0, len(pcm), BLOCO_DE_SAIDA):
            yield Evento(data=pcm[inicio:inicio + BLOCO_DE_SAIDA])

        yield Evento(server_content=_TurnoTerminou())


@asynccontextmanager
async def conectar_simples(
    instrucao,
    ferramentas,
    provedores,
    chave_groq,
    modelo_whisper,
    voz_windows,
    cliente=None,
):
    """Abre o modo simples. cliente existe para os testes."""

    if not any(p.disponivel() for p in provedores):
        raise RuntimeError(
            "O modo simples precisa de GROQ_API_KEY, MISTRAL_API_KEY ou "
            "CEREBRAS_API_KEY no arquivo .env."
        )

    meu_cliente = cliente is None
    cliente = cliente or httpx.AsyncClient()

    try:
        yield SessaoModoSimples(
            provedores,
            chave_groq,
            modelo_whisper,
            instrucao,
            ferramentas,
            voz_windows,
            cliente,
        )
    finally:
        if meu_cliente:
            await cliente.aclose()
