"""
O portão da palavra-chave não pode virar silêncio.

Sintoma de 18/09/2026: "ele começa perguntando a palavra-chave, eu
respondo, depois ele para de conversar". A instrução mandava parar de
falar, não preencher o silêncio e não executar funções antes da
autenticação -- mas não dizia o que fazer quando a palavra não fosse
reconhecida. Reconhecimento de voz erra, e 'Arlan' é curto. Ele cumpria
a parte do silêncio e sumia.

Aqui também fica o medidor de demora: "demora muito para responder" não
se investiga sem número.
"""

import time
from pathlib import Path

from gemini.live_client import GeminiLiveWorker


CODIGO = Path("gemini/live_client.py").read_text(encoding="utf-8")


# ============================================================
# O portão
# ============================================================

def test_portao_manda_responder_quando_a_palavra_nao_bate():
    assert "NÃO for a palavra-chave, responda em UMA" in CODIGO


def test_portao_proibe_silencio_depois_de_uma_fala():
    assert "NUNCA fique calado depois de uma fala dele" in CODIGO
    assert "silêncio parece" in CODIGO


def test_portao_aceita_variacoes_do_reconhecimento_de_voz():
    """'Arlan' vira 'Arlã', 'Harlan', 'Alan' na transcrição."""
    assert "Aceite variações próximas no som" in CODIGO


def test_portao_termina_depois_de_autorizado():
    """Ele voltava a emudecer no meio da conversa, já autenticado."""
    assert "O PORTÃO ACABOU nesta chamada" in CODIGO


def test_portao_continua_exigindo_a_palavra_chave():
    """A correção não pode ter derrubado a autenticação."""
    assert "Não execute funções nem prossiga com uma conversa completa" in CODIGO
    assert "Nunca revele, pronuncie, escreva, repita" in CODIGO


# ============================================================
# A demora
# ============================================================

def test_conta_a_partir_da_voz_do_usuario_e_nao_do_turno_anterior():
    """
    A primeira versão media do fim do turno anterior. Silêncio do
    usuário virava lentidão do ALF: apareceram "demoras" de 38 s e 94 s
    que eram só ele pensando antes de falar.
    """
    import gemini.live_client as live_client

    worker = GeminiLiveWorker()

    # Silêncio não mexe no relógio; voz mexe.
    worker.decidir_envio_do_microfone(
        live_client.LIMIAR_VOZ_MICROFONE - 0.02, agora=500.0
    )
    assert worker.momento_ultima_voz is None

    worker.decidir_envio_do_microfone(
        live_client.LIMIAR_VOZ_MICROFONE + 0.05, agora=500.0
    )
    assert worker.momento_ultima_voz == 500.0


def test_mede_quanto_tempo_levou_para_responder():
    worker = GeminiLiveWorker()
    worker.momento_ultima_voz = time.monotonic() - 2.0

    atraso = worker.registrar_atraso_da_resposta()

    assert 1.9 <= atraso <= 2.5


def test_so_o_primeiro_pedaco_do_turno_conta():
    """A resposta chega em muitos pedaços; a demora é até o primeiro."""
    worker = GeminiLiveWorker()
    worker.momento_ultima_voz = time.monotonic()

    assert worker.registrar_atraso_da_resposta() is not None
    assert worker.registrar_atraso_da_resposta() is None


def test_sem_fala_esperando_nao_mede_nada():
    worker = GeminiLiveWorker()

    assert worker.registrar_atraso_da_resposta() is None


def test_a_medicao_esta_ligada_na_chegada_do_audio():
    trecho = CODIGO.split("if resposta.data:", 1)[1][:200]

    assert "registrar_atraso_da_resposta()" in trecho
