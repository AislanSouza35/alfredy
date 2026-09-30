"""
A troca de provedor quando a cota do Gemini acaba.

Em 18/09/2026 a cota esgotou no meio da manhã e o ALF parou de vez: um
provedor só, sem para onde ir. O JARVIS, na mesma máquina, atravessa
isso porque tem uma cadeia de alternativas.

Aqui fica travado o comportamento da troca -- inclusive o caso de não
haver alternativa configurada, que continua encerrando com explicação.
"""

from pathlib import Path

import gemini.live_client as live_client
from gemini.live_client import GeminiLiveWorker


CODIGO = Path("gemini/live_client.py").read_text(encoding="utf-8")


def test_com_chave_da_openai_existe_para_onde_ir(monkeypatch):
    monkeypatch.setattr(live_client, "OPENAI_API_KEY", "sk-exemplo")
    worker = GeminiLiveWorker()

    assert worker.pode_trocar_para_alternativa()


def test_sem_chave_nao_ha_alternativa(monkeypatch):
    """Sem OPENAI_API_KEY ele encerra com a explicação de sempre."""
    monkeypatch.setattr(live_client, "OPENAI_API_KEY", None)
    worker = GeminiLiveWorker()

    assert not worker.pode_trocar_para_alternativa()


def test_nao_troca_duas_vezes(monkeypatch):
    """O que esgotou foi a cota do Gemini: voltar só gastaria de novo."""
    monkeypatch.setattr(live_client, "OPENAI_API_KEY", "sk-exemplo")
    worker = GeminiLiveWorker()
    worker.usando_alternativa = True

    assert not worker.pode_trocar_para_alternativa()


def test_a_chamada_comeca_sempre_pelo_gemini():
    assert GeminiLiveWorker().usando_alternativa is False


def test_a_troca_acontece_na_primeira_recusa():
    """
    Esperar dois minutos em silêncio por uma cota que acabou, com outro
    provedor pronto ao lado, é tempo de aula jogado fora. A checagem da
    alternativa vem ANTES da decisão de esperar.
    """
    trecho = CODIGO.split("if self.parece_cota_esgotada(erro):", 1)[1][:2500]

    posicao_troca = trecho.index("pode_trocar_para_alternativa()")
    posicao_espera = trecho.index("decidir_apos_cota(duracao_sessao)")

    assert posicao_troca < posicao_espera
    assert "usando_alternativa = True" in trecho


def test_sem_alternativa_continua_esperando_antes_de_encerrar():
    """Sem para onde ir, o tempo é o único remédio."""
    trecho = CODIGO.split("if self.parece_cota_esgotada(erro):", 1)[1][:2500]

    assert 'if decisao == "parar":' in trecho
    assert "raise RuntimeError(detalhe)" in trecho


def test_o_usuario_e_avisado_do_que_deixa_de_funcionar():
    """Na alternativa ele não enxerga a tela; fingir seria pior."""
    assert "não enxergo a tela" in CODIGO
    assert "clique visual" in CODIGO


def test_a_conexao_escolhe_o_provedor_da_vez():
    assert "if self.usando_alternativa:" in CODIGO
    assert "conectar_alternativa(" in CODIGO


def test_a_instrucao_vai_para_os_dois_provedores():
    """A alternativa recebe a mesma instrução, com memórias e data."""
    assert "instrucao_agora = self.atualizar_instrucao_sistema(" in CODIGO
    assert "instrucao_agora," in CODIGO
