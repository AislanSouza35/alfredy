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


# ============================================================
# O limiar acompanha o barulho da sala
# ============================================================
#
# O usuário usa alto-falante. Um limiar fixo de 0,045 serve para sala
# quieta; com o alto-falante ligado, ventilador ou rua aberta, ele
# deixa passar barulho -- e barulho que sobe vira "o usuário falou",
# que é o que faz o servidor cortar a fala do ALF.


def test_sem_medida_usa_o_limiar_de_fabrica():
    assert GeminiLiveWorker().limiar_de_voz() == live_client.LIMIAR_VOZ_MICROFONE


def test_sala_barulhenta_sobe_o_limiar():
    worker = GeminiLiveWorker()
    worker.ruido_ambiente = 0.04

    assert worker.limiar_de_voz() > live_client.LIMIAR_VOZ_MICROFONE
    assert worker.limiar_de_voz() == 0.04 * live_client.FATOR_ACIMA_DO_RUIDO


def test_sala_quieta_nao_abaixa_o_limiar():
    """Abaixar deixaria qualquer respiração virar fala."""
    worker = GeminiLiveWorker()
    worker.ruido_ambiente = 0.001

    assert worker.limiar_de_voz() == live_client.LIMIAR_VOZ_MICROFONE


def test_o_limiar_tem_teto():
    """Sem teto, sala muito barulhenta acabaria exigindo grito."""
    worker = GeminiLiveWorker()
    worker.ruido_ambiente = 0.9

    assert worker.limiar_de_voz() == live_client.LIMIAR_MAXIMO


def test_a_medida_do_ruido_nao_pula_com_uma_porta_batendo():
    worker = GeminiLiveWorker()
    for _ in range(50):
        worker.medir_ruido(0.01)
    calmo = worker.ruido_ambiente

    worker.medir_ruido(0.9)

    assert worker.ruido_ambiente < calmo + 0.1


def test_so_o_silencio_antes_da_fala_vira_amostra():
    """Pausa no meio de uma frase é pausa, não sala."""
    worker = GeminiLiveWorker()

    worker.decidir_envio_do_microfone(ALTO, agora=100.0)
    worker.decidir_envio_do_microfone(0.001, agora=100.2)

    assert worker.ruido_ambiente is None


def test_barulho_forte_e_constante_deixa_de_passar_por_voz():
    """O caso do alto-falante: o barulho da sala sobe junto."""
    worker = GeminiLiveWorker()
    barulho = 0.05

    assert worker.decidir_envio_do_microfone(barulho, agora=100.0) == "enviar"

    outro = GeminiLiveWorker()
    for _ in range(200):
        outro.medir_ruido(barulho)

    assert outro.decidir_envio_do_microfone(barulho, agora=100.0) == "guardar"
