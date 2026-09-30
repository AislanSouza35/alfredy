"""
O último degrau da cadeia: sem API de voz em tempo real.

Groq, Mistral e Cerebras são APIs de texto. Aqui o ALF ouve até o
silêncio, transcreve, responde e fala pela voz do Windows. É mais lento
e não dá para interromper a fala dele -- mas funciona quando os dois
primeiros degraus recusam, e a fala não depende de cota nenhuma.

Como os outros degraus, tem a mesma cara da sessão do Gemini. Estes
testes travam isso, e travam também a decisão de quando a fala acabou:
cortar o professor no meio de uma pausa seria pior que demorar.

Nenhum teste toca a rede nem o sintetizador de verdade.
"""

import asyncio
from array import array

import pytest
from google.genai import types

from voz import modo_simples as simples


def _bloco(amplitude, amostras=1600):
    """Um bloco de 100 ms a 16 kHz."""
    return array("h", [amplitude] * amostras).tobytes()


SILENCIO = _bloco(0)
VOZ = _bloco(9000)


def _sessao(**ajustes):
    padroes = dict(
        provedores=[simples.Provedor("groq", "https://x", "chave", "modelo")],
        chave_groq="chave",
        modelo_whisper="whisper-large-v3",
        instrucao="Você é o ALF.",
        ferramentas=[],
        voz_windows="Microsoft Maria Desktop",
        cliente=None,
        sintetizador=lambda texto: b"\x01\x02" * 100,
    )
    padroes.update(ajustes)
    return simples.SessaoModoSimples(**padroes)


# ============================================================
# Ouvir até o silêncio
# ============================================================

def test_nivel_separa_voz_de_silencio():
    assert simples.nivel_do_bloco(SILENCIO) == 0.0
    assert simples.nivel_do_bloco(VOZ) > simples.NIVEL_DE_VOZ


def test_silencio_sozinho_nao_vira_turno():
    async def executar():
        sessao = _sessao()

        for _ in range(20):
            await sessao.send_realtime_input(
                audio=types.Blob(data=SILENCIO, mime_type="audio/pcm")
            )

        assert sessao._turnos.empty()

    asyncio.run(executar())


def test_fala_seguida_de_silencio_fecha_o_turno(monkeypatch):
    """A fala termina quando o silêncio passa do limite."""

    async def executar():
        sessao = _sessao()
        relogio = {"agora": 1000.0}
        monkeypatch.setattr(simples.time, "monotonic", lambda: relogio["agora"])

        for _ in range(10):  # 1 s de fala
            await sessao.send_realtime_input(
                audio=types.Blob(data=VOZ, mime_type="audio/pcm")
            )
            relogio["agora"] += 0.1

        assert sessao._turnos.empty()

        relogio["agora"] += simples.SILENCIO_PARA_ENCERRAR + 0.1
        await sessao.send_realtime_input(
            audio=types.Blob(data=SILENCIO, mime_type="audio/pcm")
        )

        assert not sessao._turnos.empty()

    asyncio.run(executar())


def test_barulho_curto_demais_e_ignorado(monkeypatch):
    """Tosse, porta batendo e clique de mouse não são perguntas."""

    async def executar():
        sessao = _sessao()
        relogio = {"agora": 1000.0}
        monkeypatch.setattr(simples.time, "monotonic", lambda: relogio["agora"])

        await sessao.send_realtime_input(
            audio=types.Blob(data=VOZ, mime_type="audio/pcm")
        )
        relogio["agora"] += simples.SILENCIO_PARA_ENCERRAR + 0.1
        await sessao.send_realtime_input(
            audio=types.Blob(data=SILENCIO, mime_type="audio/pcm")
        )

        assert sessao._turnos.empty()

    asyncio.run(executar())


# ============================================================
# A cadeia de provedores
# ============================================================

class _ClienteFalso:
    def __init__(self, respostas):
        self._respostas = list(respostas)
        self.pedidos = []

    async def post(self, url, **kwargs):
        self.pedidos.append(url)
        resposta = self._respostas.pop(0)
        return resposta


class _Resposta:
    def __init__(self, status, dados=None, texto=""):
        self.status_code = status
        self._dados = dados or {}
        self.text = texto

    def json(self):
        return self._dados


def _mensagem(conteudo):
    return {"choices": [{"message": {"role": "assistant", "content": conteudo}}]}


def test_cai_para_o_proximo_provedor_quando_o_primeiro_recusa():
    """O motivo de estar aqui é cota acabando: insistir repetiria isso."""

    async def executar():
        provedores = [
            simples.Provedor("groq", "https://groq", "k1", "m1"),
            simples.Provedor("mistral", "https://mistral", "k2", "m2"),
        ]
        cliente = _ClienteFalso(
            [_Resposta(429, texto="cota"), _Resposta(200, _mensagem("oi"))]
        )

        mensagem, provedor, erro = await simples.conversar_com_provedores(
            provedores, [{"role": "user", "content": "oi"}], [], cliente
        )

        assert erro is None
        assert provedor.nome == "mistral"
        assert mensagem["content"] == "oi"
        assert len(cliente.pedidos) == 2

    asyncio.run(executar())


def test_provedor_sem_chave_e_pulado():
    async def executar():
        provedores = [
            simples.Provedor("groq", "https://groq", "", "m1"),
            simples.Provedor("mistral", "https://mistral", "k2", "m2"),
        ]
        cliente = _ClienteFalso([_Resposta(200, _mensagem("oi"))])

        _, provedor, erro = await simples.conversar_com_provedores(
            provedores, [], [], cliente
        )

        assert erro is None
        assert provedor.nome == "mistral"
        assert len(cliente.pedidos) == 1

    asyncio.run(executar())


def test_todos_recusando_devolve_o_motivo():
    async def executar():
        provedores = [simples.Provedor("groq", "https://groq", "k", "m")]
        cliente = _ClienteFalso([_Resposta(500, texto="fora do ar")])

        mensagem, _, erro = await simples.conversar_com_provedores(
            provedores, [], [], cliente
        )

        assert mensagem is None
        assert "groq" in erro

    asyncio.run(executar())


# ============================================================
# A mesma cara da sessão do Gemini
# ============================================================

def test_a_resposta_sai_como_audio_em_pedacos():
    async def executar():
        sessao = _sessao(
            sintetizador=lambda texto: b"\x01\x02" * 5000,
            cliente=_ClienteFalso([_Resposta(200, _mensagem("bom dia"))]),
        )

        await sessao.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text="oi")]),
        )

        eventos = []
        async for evento in sessao.receive():
            eventos.append(evento)
            if evento.server_content is not None:
                break

        audio = [e for e in eventos if e.data]
        assert len(audio) > 1
        assert eventos[-1].server_content.turn_complete is True

    asyncio.run(executar())


def test_ferramenta_e_pedida_e_respondida():
    """O ciclo de ferramenta precisa funcionar igual ao dos outros degraus."""

    async def executar():
        chamada = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {
                                    "name": "estado_do_transporte",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ]
        }
        cliente = _ClienteFalso(
            [_Resposta(200, chamada), _Resposta(200, _mensagem("nada em andamento"))]
        )
        sessao = _sessao(cliente=cliente)

        await sessao.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text="e o transporte?")]),
        )

        eventos = []

        async def conversar():
            async for evento in sessao.receive():
                eventos.append(evento)

                if evento.tool_call is not None:
                    await sessao.send_tool_response(
                        function_responses=[
                            types.FunctionResponse(
                                id="c1",
                                name="estado_do_transporte",
                                response={"result": "nada"},
                            )
                        ]
                    )

                if evento.server_content is not None:
                    return

        await asyncio.wait_for(conversar(), timeout=5)

        pedidos = [e for e in eventos if e.tool_call is not None]
        assert len(pedidos) == 1
        assert pedidos[0].tool_call.function_calls[0].name == "estado_do_transporte"
        assert any(e.data for e in eventos)

    asyncio.run(executar())


def test_imagem_vira_aviso_de_que_ele_nao_enxerga():
    async def executar():
        sessao = _sessao()

        await sessao.send_client_content(
            turns=types.Content(
                role="user",
                parts=[
                    types.Part(
                        inline_data=types.Blob(data=b"jpeg", mime_type="image/jpeg")
                    )
                ],
            ),
        )

        assert "NÃO enxerga a tela" in await sessao._turnos.get()

    asyncio.run(executar())


def test_sem_nenhuma_chave_o_modo_simples_avisa():
    async def executar():
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            async with simples.conectar_simples(
                "oi", [], [simples.Provedor("groq", "https://x", "", "m")], "", "w", "voz"
            ):
                pass

    asyncio.run(executar())


def test_wav_sai_no_formato_que_a_transcricao_aceita(tmp_path, monkeypatch):
    import wave

    monkeypatch.setattr(simples.tempfile, "gettempdir", lambda: str(tmp_path))

    caminho = simples.montar_wav(VOZ)

    with wave.open(str(caminho), "rb") as arquivo:
        assert arquivo.getnchannels() == 1
        assert arquivo.getsampwidth() == 2
        assert arquivo.getframerate() == simples.TAXA_MICROFONE
