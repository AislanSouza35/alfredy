"""Testes unitários para helpers puros de gemini/live_client.py.

Não abre conexão real com o Gemini Live; testa apenas os métodos
estáticos e utilitários que não dependem de rede ou áudio real.
"""

import asyncio
import time
from types import SimpleNamespace

from gemini.live_client import GeminiLiveWorker


def test_calcular_nivel_audio_silencio():
    assert GeminiLiveWorker.calcular_nivel_audio(b"") == 0.0


def test_calcular_nivel_audio_com_amostras():
    import struct

    # Amostras int16 com pico conhecido (metade da amplitude máxima).
    amostras = struct.pack("<4h", 0, 16384, -16384, 0)
    nivel = GeminiLiveWorker.calcular_nivel_audio(amostras)
    assert 0.0 < nivel < 1.0


def test_calcular_nivel_audio_dados_invalidos():
    # Quantidade ímpar de bytes não forma amostras válidas de 16 bits.
    assert GeminiLiveWorker.calcular_nivel_audio(b"\x01") == 0.0


def test_limpar_fila_microfone_esvazia_a_fila():
    fila = asyncio.Queue()
    fila.put_nowait(b"bloco1")
    fila.put_nowait(b"bloco2")

    GeminiLiveWorker.limpar_fila_microfone(fila)

    assert fila.empty()


def test_worker_inicia_com_estado_limpo():
    worker = GeminiLiveWorker()
    assert worker.ativo is True
    assert worker.historico_cliques_padrao == []
    assert worker.processando_ferramenta is False
    assert worker._forcar_reconexao is False
    assert worker.fluxo_audio_em_andamento is False
    assert worker.usuario_falando_detectado is False
    assert worker.ultimo_audio_com_voz is None


def test_vad_cliente_finaliza_fluxo_apos_fala_e_silencio():
    worker = GeminiLiveWorker()

    assert worker.deve_finalizar_fluxo_por_silencio(0.20, agora=10.0) is False
    assert worker.usuario_falando_detectado is True
    assert worker.ultimo_audio_com_voz == 10.0

    assert worker.deve_finalizar_fluxo_por_silencio(0.0, agora=10.4) is False
    assert worker.usuario_falando_detectado is True

    assert worker.deve_finalizar_fluxo_por_silencio(0.0, agora=11.0) is True
    assert worker.usuario_falando_detectado is False
    assert worker.ultimo_audio_com_voz is None


def test_vad_cliente_nao_finaliza_quando_so_existe_silencio():
    worker = GeminiLiveWorker()

    assert worker.deve_finalizar_fluxo_por_silencio(0.0, agora=10.0) is False
    assert worker.deve_finalizar_fluxo_por_silencio(0.0, agora=20.0) is False


def test_config_live_usa_pensamento_minimo_para_reduzir_latencia():
    config = GeminiLiveWorker.criar_config_live(
        instrucao_sistema="instrucao",
        tools=[],
        session_handle=None,
    )

    assert config.thinking_config.thinking_level.value == "MINIMAL"


def test_reconexao_rapida_nao_reseta_contador_de_tentativas():
    assert GeminiLiveWorker.calcular_tentativas_apos_queda(
        tentativas_atual=1,
        duracao_sessao=15.0,
    ) == 2


def test_reconexao_apos_sessao_estavel_recomeca_contador():
    assert GeminiLiveWorker.calcular_tentativas_apos_queda(
        tentativas_atual=4,
        duracao_sessao=90.0,
    ) == 1


def test_finalizar_fluxo_audio_pendente_envia_audio_stream_end_quando_necessario():
    class SessaoFake:
        def __init__(self):
            self.chamadas = []

        async def send_realtime_input(self, **kwargs):
            self.chamadas.append(kwargs)

    async def executar():
        worker = GeminiLiveWorker()
        worker.lock_envio = asyncio.Lock()
        worker.fluxo_audio_em_andamento = True
        sessao = SessaoFake()

        await worker.finalizar_fluxo_audio_pendente(sessao)

        assert sessao.chamadas == [{"audio_stream_end": True}]
        assert worker.fluxo_audio_em_andamento is False

    asyncio.run(executar())


def test_finalizar_fluxo_audio_pendente_nao_duplica_audio_stream_end():
    class SessaoFake:
        def __init__(self):
            self.chamadas = []

        async def send_realtime_input(self, **kwargs):
            self.chamadas.append(kwargs)

    async def executar():
        worker = GeminiLiveWorker()
        worker.lock_envio = asyncio.Lock()
        worker.fluxo_audio_em_andamento = False
        sessao = SessaoFake()

        await worker.finalizar_fluxo_audio_pendente(sessao)

        assert sessao.chamadas == []

    asyncio.run(executar())


def test_preparar_pausa_microfone_bloqueia_limpa_fila_e_finaliza_fluxo():
    class SessaoFake:
        def __init__(self):
            self.chamadas = []

        async def send_realtime_input(self, **kwargs):
            self.chamadas.append(kwargs)

    async def executar():
        worker = GeminiLiveWorker()
        worker.lock_envio = asyncio.Lock()
        worker.fluxo_audio_em_andamento = True
        fila = asyncio.Queue()
        fila.put_nowait(b"audio-antigo")
        sessao = SessaoFake()

        await worker.preparar_pausa_microfone(sessao, fila)

        assert worker.alfred_falando is True
        assert fila.empty()
        assert sessao.chamadas == [{"audio_stream_end": True}]

    asyncio.run(executar())


def test_agendar_liberacao_microfone_cria_tarefa_de_liberacao():
    async def executar():
        worker = GeminiLiveWorker()
        worker.alfred_falando = True

        worker.agendar_liberacao_microfone()

        assert worker.tarefa_liberar_microfone is not None
        assert not worker.tarefa_liberar_microfone.done()
        worker.tarefa_liberar_microfone.cancel()

    asyncio.run(executar())


def test_receber_audio_nao_bloqueia_leitura_enquanto_ferramenta_roda():
    """
    Uma ferramenta demorada não pode travar a leitura do WebSocket.

    Enquanto o laço ficava parado esperando a ferramenta, o aviso GoAway
    do servidor não era lido, a sessão não era renovada e a conexão caía
    com o código 1006 -- a origem dos reinícios em sequência.
    """

    async def executar():
        worker = GeminiLiveWorker()
        worker.lock_envio = asyncio.Lock()
        fila_saida = asyncio.Queue()
        fila_microfone = asyncio.Queue()
        ordem = []
        ferramenta_iniciada = asyncio.Event()
        liberar_ferramenta = asyncio.Event()

        resposta_tool = SimpleNamespace(
            data=None,
            tool_call=SimpleNamespace(function_calls=[]),
            session_resumption_update=None,
            go_away=None,
            server_content=None,
        )
        resposta_final = SimpleNamespace(
            data=None,
            tool_call=None,
            session_resumption_update=None,
            go_away=None,
            server_content=None,
        )

        class SessaoFake:
            async def receive(self):
                yield resposta_tool
                ordem.append("segunda_resposta_lida")
                worker.ativo = False
                yield resposta_final

        async def preparar_pausa_microfone(sessao, fila):
            ordem.append("microfone_pausado")

        async def processar_chamada_de_funcao(sessao, tool_call, fila):
            ordem.append("ferramenta_iniciada")
            ferramenta_iniciada.set()
            await liberar_ferramenta.wait()
            ordem.append("ferramenta_finalizada")

        worker.preparar_pausa_microfone = preparar_pausa_microfone
        worker.processar_chamada_de_funcao = processar_chamada_de_funcao

        tarefa = asyncio.create_task(
            worker.receber_audio(SessaoFake(), fila_saida, fila_microfone)
        )
        await asyncio.wait_for(ferramenta_iniciada.wait(), timeout=1)
        await asyncio.wait_for(tarefa, timeout=1)

        # A leitura seguiu adiante com a ferramenta ainda em execução.
        assert "segunda_resposta_lida" in ordem
        assert "ferramenta_finalizada" not in ordem

        liberar_ferramenta.set()
        await asyncio.wait_for(
            worker.tarefa_ferramenta_atual,
            timeout=1,
        )
        assert ordem[-1] == "ferramenta_finalizada"

    asyncio.run(executar())


def test_ferramentas_seguidas_mantem_a_ordem_de_execucao():
    """Duas ferramentas em sequência não podem rodar sobrepostas."""

    async def executar():
        worker = GeminiLiveWorker()
        ordem = []
        liberar_primeira = asyncio.Event()

        async def processar_chamada_de_funcao(sessao, tool_call, fila):
            ordem.append(f"inicio-{tool_call}")
            if tool_call == "A":
                await liberar_primeira.wait()
            ordem.append(f"fim-{tool_call}")

        worker.processar_chamada_de_funcao = processar_chamada_de_funcao

        worker.agendar_chamada_de_funcao(None, "A", None)
        segunda = worker.agendar_chamada_de_funcao(None, "B", None)

        await asyncio.sleep(0)
        assert ordem == ["inicio-A"]

        liberar_primeira.set()
        await asyncio.wait_for(segunda, timeout=1)

        assert ordem == ["inicio-A", "fim-A", "inicio-B", "fim-B"]

    asyncio.run(executar())


def test_imagem_vai_como_turno_do_usuario_e_nao_como_video():
    """
    A imagem precisa chegar como turno do usuário (send_client_content),
    não como quadro de vídeo ao vivo (send_realtime_input).

    Medido contra a API real, mandando duas imagens diferentes em
    sequência e perguntando o que o modelo via:

      send_realtime_input -> 1a: "não vejo imagem alguma"
                             2a: descrevia a PRIMEIRA imagem
      send_client_content -> 1a e 2a corretas

    O caminho de vídeo deixava o modelo sempre um turno atrasado, que
    era o motivo de o ALF comentar abas já fechadas pelo usuário.
    """

    class SessaoFake:
        def __init__(self):
            self.chamadas = []

        async def send_realtime_input(self, **kwargs):
            self.chamadas.append(("realtime", kwargs))

        async def send_client_content(self, **kwargs):
            self.chamadas.append(("client_content", kwargs))

    async def executar():
        worker = GeminiLiveWorker()
        worker.lock_envio = asyncio.Lock()
        worker.imagem_visual_pendente = ("tela", b"jpeg")
        worker.momento_captura_visual = time.monotonic()
        sessao = SessaoFake()

        await worker.enviar_imagem_visual_pendente(sessao)

        tipos = [tipo for tipo, _ in sessao.chamadas]
        assert tipos == ["client_content"]
        assert "realtime" not in tipos

        argumentos = sessao.chamadas[0][1]
        assert argumentos["turn_complete"] is True

        partes = argumentos["turns"].parts
        assert argumentos["turns"].role == "user"
        assert partes[0].inline_data.data == b"jpeg"
        assert partes[0].inline_data.mime_type == "image/jpeg"

        texto = partes[1].text
        assert "MAIS RECENTE" in texto
        assert "Ignore completamente qualquer imagem" in texto

    asyncio.run(executar())


def test_enviar_imagem_visual_fecha_audio_pendente_antes_da_imagem():
    class SessaoFake:
        def __init__(self):
            self.chamadas = []

        async def send_realtime_input(self, **kwargs):
            self.chamadas.append(("realtime", kwargs))

        async def send_client_content(self, **kwargs):
            self.chamadas.append(("client_content", kwargs))

    async def executar():
        worker = GeminiLiveWorker()
        worker.lock_envio = asyncio.Lock()
        worker.fluxo_audio_em_andamento = True
        worker.imagem_visual_pendente = ("camera", b"jpeg")
        worker.momento_captura_visual = time.monotonic()
        sessao = SessaoFake()

        await worker.enviar_imagem_visual_pendente(sessao)

        # O fluxo de áudio do microfone precisa ser encerrado antes,
        # senão a imagem entra no meio de um turno de fala aberto.
        assert sessao.chamadas[0] == ("realtime", {"audio_stream_end": True})

        tipo, argumentos = sessao.chamadas[1]
        assert tipo == "client_content"
        assert "câmera" in argumentos["turns"].parts[1].text

    asyncio.run(executar())


def test_criar_contexto_ssl_websocket_remove_validacao_estrita():
    import ssl

    contexto = GeminiLiveWorker.criar_contexto_ssl_websocket()

    assert isinstance(contexto, ssl.SSLContext)
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        assert not contexto.verify_flags & ssl.VERIFY_X509_STRICT


def test_registrar_diagnostico_grava_mensagem_em_arquivo(tmp_path):
    caminho = tmp_path / "alf_runtime_debug.log"

    GeminiLiveWorker.registrar_diagnostico(
        "mensagem de teste",
        caminho=caminho,
    )

    conteudo = caminho.read_text(encoding="utf-8")
    assert "mensagem de teste" in conteudo


def test_registrar_diagnostico_nao_interrompe_quando_nao_consegue_gravar(tmp_path):
    caminho_invalido = tmp_path / "pasta_no_lugar_do_arquivo"
    caminho_invalido.mkdir()

    GeminiLiveWorker.registrar_diagnostico(
        "mensagem que nao deve quebrar",
        caminho=caminho_invalido,
    )


def test_captura_visual_antiga_nao_e_enviada():
    """
    Uma captura que envelheceu entre a resposta da ferramenta e o envio
    não pode ser analisada: a tela do usuário já mudou. Era assim que o
    ALF acabava descrevendo algo antigo.
    """

    import gemini.live_client as live_client

    class SessaoFake:
        def __init__(self):
            self.chamadas = []

        async def send_client_content(self, **kwargs):
            self.chamadas.append(kwargs)

    async def executar():
        worker = GeminiLiveWorker()
        worker.lock_envio = asyncio.Lock()
        worker.imagem_visual_pendente = ("tela", b"jpeg")
        worker.momento_captura_visual = (
            time.monotonic() - live_client.VALIDADE_CAPTURA_VISUAL - 1
        )
        sessao = SessaoFake()

        await worker.enviar_imagem_visual_pendente(sessao)

        assert sessao.chamadas == []
        assert worker.imagem_visual_pendente is None

    asyncio.run(executar())


def test_captura_visual_recente_e_enviada():
    class SessaoFake:
        def __init__(self):
            self.chamadas = []

        async def send_client_content(self, **kwargs):
            self.chamadas.append(kwargs)

    async def executar():
        worker = GeminiLiveWorker()
        worker.lock_envio = asyncio.Lock()
        worker.imagem_visual_pendente = ("tela", b"jpeg")
        worker.momento_captura_visual = time.monotonic()
        sessao = SessaoFake()

        await worker.enviar_imagem_visual_pendente(sessao)

        partes = sessao.chamadas[0]["turns"].parts
        assert partes[0].inline_data.data == b"jpeg"


def test_chamada_visual_repetida_recaptura_quando_nada_esta_pendente():
    """
    A versão anterior devolvia "use a última imagem recebida" por oito
    segundos, fazendo o ALF responder sobre uma tela antiga quando o
    usuário pedia para olhar de novo.
    """

    async def executar():
        worker = GeminiLiveWorker()
        worker.ultima_funcao_visual = "analisar_tela"
        worker.tempo_ultima_funcao_visual = time.monotonic()
        worker.imagem_visual_pendente = None

        capturas = []

        def capturar_falso():
            capturas.append("nova")
            return b"jpeg-novo"

        import gemini.live_client as live_client

        original = live_client.capturar_tela_bytes
        live_client.capturar_tela_bytes = capturar_falso
        try:
            resultado = await worker.processar_funcao_visual("analisar_tela")
        finally:
            live_client.capturar_tela_bytes = original

        assert capturas == ["nova"]
        assert worker.imagem_visual_pendente == ("tela", b"jpeg-novo")
        assert "acabou de ser capturada" in resultado

    asyncio.run(executar())


def test_chamada_visual_duplicada_no_mesmo_pedido_e_ignorada():
    """Chamadas repetidas do mesmo turno continuam sendo agrupadas."""

    async def executar():
        worker = GeminiLiveWorker()
        worker.ultima_funcao_visual = "analisar_tela"
        worker.tempo_ultima_funcao_visual = time.monotonic()
        worker.imagem_visual_pendente = ("tela", b"ja-capturada")

        resultado = await worker.processar_funcao_visual("analisar_tela")

        assert "já está a caminho" in resultado
        assert worker.imagem_visual_pendente == ("tela", b"ja-capturada")

    asyncio.run(executar())


def test_microfone_so_reabre_depois_que_a_fila_de_audio_esvazia():
    """
    O servidor manda turn_complete quando termina de gerar a resposta,
    não quando o áudio termina de tocar. Reabrir o microfone naquele
    momento fazia o ALF escutar a própria voz e se interromper.
    """

    async def executar():
        worker = GeminiLiveWorker()
        worker.alfred_falando = True
        worker.fila_saida = asyncio.Queue()
        worker.fila_saida.put_nowait(b"bloco-ainda-tocando")

        worker.agendar_liberacao_microfone()

        await asyncio.sleep(0.2)
        assert worker.alfred_falando is True

        worker.fila_saida.get_nowait()

        await asyncio.wait_for(
            worker.tarefa_liberar_microfone,
            timeout=5,
        )
        assert worker.alfred_falando is False

    asyncio.run(executar())


def test_aguardar_fim_da_reproducao_respeita_o_limite():
    """Uma placa de som travada não pode deixar o microfone fechado."""

    async def executar():
        worker = GeminiLiveWorker()
        worker.fila_saida = asyncio.Queue()
        worker.fila_saida.put_nowait(b"bloco-preso")

        concluiu = await worker.aguardar_fim_da_reproducao(limite=0.2)

        assert concluiu is False

    asyncio.run(executar())
