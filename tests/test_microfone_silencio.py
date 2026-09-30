"""
O microfone para de mandar ruído de sala para o servidor.

Em 30/09/2026 o log registrou uma interrupção dois segundos depois da
saudação de abertura, com ninguém falando -- e zero faltas de áudio. O
ALF mandava ao servidor tudo o que o microfone captava desde o instante
em que conectava: ventilador, teclado, a rua. Quando ele começava a
falar e o programa fechava o fluxo, o servidor tratava aquele ruído
acumulado como fala do usuário e cortava a própria resposta.

O silêncio do FIM da fala continua subindo: é nele que o servidor
percebe que a frase acabou.
"""

from pathlib import Path

import gemini.live_client as live_client
from gemini.live_client import GeminiLiveWorker


ALTO = live_client.LIMIAR_VOZ_MICROFONE + 0.05
BAIXO = live_client.LIMIAR_VOZ_MICROFONE - 0.02


def test_silencio_antes_da_fala_fica_guardado():
    """Ruído de sala não pode virar uma fala aos olhos do servidor."""
    worker = GeminiLiveWorker()

    assert worker.decidir_envio_do_microfone(BAIXO, agora=100.0) == "guardar"


def test_voz_sobe():
    worker = GeminiLiveWorker()

    assert worker.decidir_envio_do_microfone(ALTO, agora=100.0) == "enviar"


def test_silencio_curto_no_meio_da_fala_sobe():
    """Pausa entre palavras não é fim de frase."""
    worker = GeminiLiveWorker()

    worker.decidir_envio_do_microfone(ALTO, agora=100.0)

    assert worker.decidir_envio_do_microfone(BAIXO, agora=100.3) == "enviar"


def test_silencio_longo_encerra_a_fala():
    worker = GeminiLiveWorker()

    worker.decidir_envio_do_microfone(ALTO, agora=100.0)
    tarde = 100.0 + live_client.TEMPO_SILENCIO_FINALIZAR_AUDIO + 0.1

    assert worker.decidir_envio_do_microfone(BAIXO, agora=tarde) == "encerrar"


def test_depois_de_encerrar_volta_a_guardar():
    worker = GeminiLiveWorker()

    worker.decidir_envio_do_microfone(ALTO, agora=100.0)
    tarde = 100.0 + live_client.TEMPO_SILENCIO_FINALIZAR_AUDIO + 0.1
    worker.decidir_envio_do_microfone(BAIXO, agora=tarde)

    assert worker.decidir_envio_do_microfone(BAIXO, agora=tarde + 1) == "guardar"


def test_a_voz_marca_o_relogio_da_medida_de_demora():
    worker = GeminiLiveWorker()

    worker.decidir_envio_do_microfone(ALTO, agora=555.0)

    assert worker.momento_ultima_voz == 555.0


def test_o_comeco_da_palavra_vai_junto():
    """
    O nível só passa do limiar depois que a voz já saiu. Sem o pré-rolo,
    a primeira sílaba se perde.
    """
    codigo = Path("gemini/live_client.py").read_text(encoding="utf-8")

    assert "pre_rolo = deque(" in codigo
    assert "blocos = list(pre_rolo) + [audio_bytes]" in codigo
    assert live_client.PRE_ROLO_SEGUNDOS >= 0.3
