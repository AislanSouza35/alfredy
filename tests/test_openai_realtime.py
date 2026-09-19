"""
A alternativa de voz, para quando a cota do Gemini acabar.

Em 18/09/2026 a cota esgotou no meio da manhã e o ALF parou: um
provedor só, sem para onde ir.

O que estes testes travam é a promessa central do módulo: ele tem a
MESMA cara da sessão do Gemini. Se essa cara mudar, o laço de
recebimento do ALF quebra sem aviso.

Nenhum teste toca a rede.
"""

import asyncio
import json
from array import array

import pytest
from google.genai import types

from voz import openai_realtime as alt


class _WebSocketFalso:
    def __init__(self, eventos=None):
        self.enviados = []
        self._eventos = [json.dumps(e) for e in (eventos or [])]
        self.fechado = False

    async def send(self, texto):
        self.enviados.append(json.loads(texto))

    async def close(self):
        self.fechado = True

    def __aiter__(self):
        async def gerar():
            for evento in self._eventos:
                yield evento

        return gerar()

    def tipos(self):
        return [m["type"] for m in self.enviados]


# ============================================================
# Áudio
# ============================================================

def test_reamostra_de_16k_para_24k():
    """Três amostras de saída para cada duas de entrada."""
    entrada = array("h", [0, 100, 200, 300]).tobytes()

    saida, sobra = alt.reamostrar_para_24k(entrada)

    assert len(array("h", saida)) == 6
    assert sobra is None


def test_amostra_impar_nao_e_jogada_fora():
    """Descartar a sobra a cada bloco daria um estalo regular."""
    primeiro, sobra = alt.reamostrar_para_24k(array("h", [0, 100, 200]).tobytes())

    assert len(array("h", primeiro)) == 3
    assert sobra is not None

    segundo, _ = alt.reamostrar_para_24k(array("h", [300]).tobytes(), sobra)

    assert len(array("h", segundo)) == 3


# ============================================================
# Ferramentas
# ============================================================

def _ferramenta():
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="lancar_notas_em_lote",
                description="Lança notas.",
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "turma": types.Schema(type="STRING", description="Turma."),
                        "notas": types.Schema(
                            type="ARRAY", items=types.Schema(type="STRING")
                        ),
                    },
                    required=["turma"],
                ),
            )
        ]
    )


def test_traduz_as_ferramentas_do_gemini():
    """As 67 ferramentas são declaradas uma vez só, no formato do Gemini."""
    convertidas = alt.converter_ferramentas([_ferramenta()])

    assert len(convertidas) == 1
    ferramenta = convertidas[0]
    assert ferramenta["type"] == "function"
    assert ferramenta["name"] == "lancar_notas_em_lote"
    assert ferramenta["parameters"]["type"] == "object"
    assert ferramenta["parameters"]["properties"]["turma"]["type"] == "string"
    assert ferramenta["parameters"]["properties"]["notas"]["items"]["type"] == "string"
    assert ferramenta["parameters"]["required"] == ["turma"]


def test_ferramenta_sem_parametros_nao_quebra():
    sem_parametros = types.Tool(
        function_declarations=[
            types.FunctionDeclaration(name="encerrar_chamada", description="Encerra.")
        ]
    )

    convertidas = alt.converter_ferramentas([sem_parametros])

    assert convertidas[0]["parameters"] == {"type": "object", "properties": {}}


# ============================================================
# A mesma cara da sessão do Gemini
# ============================================================

def test_audio_do_microfone_vira_append():
    async def executar():
        ws = _WebSocketFalso()
        sessao = alt.SessaoOpenAIRealtime(ws)

        await sessao.send_realtime_input(
            audio=types.Blob(
                data=array("h", [1, 2, 3, 4]).tobytes(),
                mime_type="audio/pcm;rate=16000",
            )
        )

        assert ws.tipos() == ["input_audio_buffer.append"]

    asyncio.run(executar())


def test_fim_do_fluxo_nao_manda_nada():
    """Com detecção no servidor, forçar o fim cortaria a frase no meio."""

    async def executar():
        ws = _WebSocketFalso()
        sessao = alt.SessaoOpenAIRealtime(ws)

        await sessao.send_realtime_input(audio_stream_end=True)

        assert ws.enviados == []

    asyncio.run(executar())


def test_audio_da_resposta_vira_data():
    async def executar():
        import base64

        ws = _WebSocketFalso(
            [{"type": "response.audio.delta", "delta": base64.b64encode(b"som").decode()}]
        )
        sessao = alt.SessaoOpenAIRealtime(ws)

        eventos = [e async for e in sessao.receive()]

        assert [e.data for e in eventos] == [b"som"]

    asyncio.run(executar())


def test_chamada_de_funcao_tem_a_forma_do_gemini():
    """O laço do ALF lê .tool_call.function_calls[].name/.args/.id."""

    async def executar():
        ws = _WebSocketFalso(
            [
                {
                    "type": "response.function_call_arguments.done",
                    "call_id": "c1",
                    "name": "listar_turmas",
                    "arguments": '{"turma": "3A"}',
                }
            ]
        )
        sessao = alt.SessaoOpenAIRealtime(ws)

        eventos = [e async for e in sessao.receive()]
        chamada = eventos[0].tool_call.function_calls[0]

        assert chamada.name == "listar_turmas"
        assert chamada.args == {"turma": "3A"}
        assert chamada.id == "c1"

    asyncio.run(executar())


def test_fim_de_turno_tem_a_forma_do_gemini():
    async def executar():
        ws = _WebSocketFalso([{"type": "response.done"}])
        sessao = alt.SessaoOpenAIRealtime(ws)

        eventos = [e async for e in sessao.receive()]

        assert eventos[0].server_content.turn_complete is True

    asyncio.run(executar())


def test_erro_da_api_interrompe_o_laco():
    async def executar():
        ws = _WebSocketFalso(
            [{"type": "error", "error": {"message": "cota da OpenAI acabou"}}]
        )
        sessao = alt.SessaoOpenAIRealtime(ws)

        with pytest.raises(RuntimeError, match="cota da OpenAI"):
            [e async for e in sessao.receive()]

    asyncio.run(executar())


def test_resultado_da_ferramenta_volta_no_call_id_certo():
    async def executar():
        ws = _WebSocketFalso(
            [
                {
                    "type": "response.function_call_arguments.done",
                    "call_id": "c9",
                    "name": "listar_turmas",
                    "arguments": "{}",
                }
            ]
        )
        sessao = alt.SessaoOpenAIRealtime(ws)

        [e async for e in sessao.receive()]

        await sessao.send_tool_response(
            function_responses=[
                types.FunctionResponse(
                    id="ignorado", name="listar_turmas", response={"result": "51 turmas"}
                )
            ]
        )

        item = ws.enviados[0]["item"]
        assert item["type"] == "function_call_output"
        assert item["call_id"] == "c9"
        assert "51 turmas" in item["output"]
        assert ws.tipos()[-1] == "response.create"

    asyncio.run(executar())


# ============================================================
# O que a alternativa não faz
# ============================================================

def test_imagem_vira_aviso_de_que_ele_nao_enxerga():
    """Fingir que viu a tela faria o ALF descrever o que nunca viu."""

    async def executar():
        ws = _WebSocketFalso()
        sessao = alt.SessaoOpenAIRealtime(ws)

        await sessao.send_client_content(
            turns=types.Content(
                role="user",
                parts=[
                    types.Part(
                        inline_data=types.Blob(data=b"jpeg", mime_type="image/jpeg")
                    ),
                    types.Part(text="o que tem na tela?"),
                ],
            ),
            turn_complete=True,
        )

        texto = ws.enviados[0]["item"]["content"][0]["text"]

        assert "NÃO enxerga a tela" in texto
        assert "sem inventar" in texto

    asyncio.run(executar())


def test_texto_simples_vai_inteiro():
    async def executar():
        ws = _WebSocketFalso()
        sessao = alt.SessaoOpenAIRealtime(ws)

        await sessao.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text="bom dia")]),
            turn_complete=True,
        )

        assert ws.enviados[0]["item"]["content"][0]["text"] == "bom dia"
        assert ws.tipos() == ["conversation.item.create", "response.create"]

    asyncio.run(executar())


def test_sem_chave_a_alternativa_avisa_em_vez_de_travar():
    async def executar():
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            async with alt.conectar("", "gpt-realtime", "oi", [], "alloy"):
                pass

    asyncio.run(executar())


def test_configuracao_pede_deteccao_de_fala_no_servidor():
    config = alt.montar_configuracao("instrução", [_ferramenta()], "alloy")["session"]

    assert config["turn_detection"] == {"type": "server_vad"}
    assert config["input_audio_format"] == "pcm16"
    assert config["output_audio_format"] == "pcm16"
    assert config["instructions"] == "instrução"
    assert config["voice"] == "alloy"
    assert len(config["tools"]) == 1
