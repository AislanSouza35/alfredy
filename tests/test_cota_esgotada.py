"""
Cota esgotada da chave do Gemini.

Em 18/09/2026 o ALF ficou mudo e travado a manhã inteira. O log tinha
cinco recusas do Google com 1011 "Resource has been exhausted" e 27
sessões abertas: ele tratava isso como queda de rede, reabria em poucos
segundos, era recusado de novo, e nunca dizia o motivo. Cada reabertura
gastava mais da cota que já tinha acabado.
"""

import pytest

import gemini.live_client as live_client
from gemini.live_client import GeminiLiveWorker


@pytest.mark.parametrize(
    "erro",
    [
        "1011 None. Resource has been exhausted (e.g. check quota).",
        "received 1011 (internal error) Resource has been exhausted",
        "429 Too Many Requests",
        "RESOURCE_EXHAUSTED",
        "You exceeded your current quota",
    ],
)
def test_reconhece_recusa_por_cota(erro):
    assert GeminiLiveWorker.parece_cota_esgotada(erro)


@pytest.mark.parametrize(
    "erro",
    [
        "1008 None. The operation was aborted.",
        # Mesmo código 1011, outro problema: falha passageira do
        # servidor, que se resolve reconectando. Metade das quedas 1011
        # desta máquina eram assim.
        "received 1011 (internal error) Internal error encountered.",
        "1011 None. Internal error encountered.",
        "no close frame received or sent",
        "1006 abnormal closure",
        "received 1000 (OK) The operation was cancelled.",
    ],
)
def test_queda_comum_nao_e_confundida_com_cota(erro):
    """Tratar queda de rede como cota faria o ALF esperar um minuto à toa."""
    assert not GeminiLiveWorker.parece_cota_esgotada(erro)


def test_primeiras_recusas_esperam_em_vez_de_insistir():
    worker = GeminiLiveWorker()

    assert worker.decidir_apos_cota(0.0) == ("esperar", live_client.ESPERA_APOS_COTA)
    assert worker.decidir_apos_cota(0.0) == ("esperar", live_client.ESPERA_APOS_COTA)


def test_insistindo_ele_para_e_explica():
    worker = GeminiLiveWorker()

    for _ in range(live_client.MAX_QUEDAS_POR_COTA):
        worker.decidir_apos_cota(0.0)

    decisao, mensagem = worker.decidir_apos_cota(0.0)

    assert decisao == "parar"
    # A mensagem precisa dizer o que houve, o que ele fez e o que fazer.
    assert "cota" in mensagem.lower()
    assert "Encerrei a chamada" in mensagem
    assert "reabrir agora só gasta" in mensagem


def test_sessao_que_durou_bem_recomeca_a_contagem():
    """Uma queda por cota hoje de manhã não pode derrubar a aula da tarde."""
    worker = GeminiLiveWorker()

    for _ in range(live_client.MAX_QUEDAS_POR_COTA + 1):
        worker.decidir_apos_cota(0.0)

    decisao, _ = worker.decidir_apos_cota(live_client.TEMPO_SESSAO_ESTAVEL + 1)

    assert decisao == "esperar"
    assert worker.quedas_por_cota == 1


def test_espera_por_cota_e_bem_maior_que_a_de_rede():
    assert live_client.ESPERA_APOS_COTA >= 10 * live_client.ESPERA_BASE_RECONEXAO
