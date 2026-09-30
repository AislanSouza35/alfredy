"""
A cadeia de voz: Gemini Live, OpenAI Realtime e o modo simples.

Em 18/09/2026 a cota do Gemini esgotou no meio da manhã e o ALF parou de
vez: um provedor só, sem para onde ir. O JARVIS, na mesma máquina,
atravessa isso porque mantém uma cadeia de alternativas.

A cadeia só desce. O que esgotou foi a cota do degrau anterior, e voltar
a ele gastaria o que não tem.
"""

from pathlib import Path

import pytest

import gemini.live_client as live_client
from gemini.live_client import GeminiLiveWorker


CODIGO = Path("gemini/live_client.py").read_text(encoding="utf-8")


@pytest.fixture
def chaves(monkeypatch):
    """Cada teste diz quais chaves existem."""

    def definir(openai="sk-openai", groq="gsk", mistral="", cerebras=""):
        monkeypatch.setattr(live_client, "OPENAI_API_KEY", openai)
        monkeypatch.setattr(live_client, "GROQ_API_KEY", groq)
        monkeypatch.setattr(live_client, "MISTRAL_API_KEY", mistral)
        monkeypatch.setattr(live_client, "CEREBRAS_API_KEY", cerebras)

    return definir


def test_do_gemini_desce_para_a_openai(chaves):
    chaves()

    assert GeminiLiveWorker().proximo_provedor() == "openai"


def test_sem_openai_pula_direto_para_o_modo_simples(chaves):
    """Faltar um degrau não pode quebrar a cadeia."""
    chaves(openai="")

    assert GeminiLiveWorker().proximo_provedor() == "simples"


def test_da_openai_desce_para_o_modo_simples(chaves):
    chaves()
    worker = GeminiLiveWorker()
    worker.provedor = "openai"

    assert worker.proximo_provedor() == "simples"


def test_do_modo_simples_nao_ha_mais_para_onde_ir(chaves):
    chaves()
    worker = GeminiLiveWorker()
    worker.provedor = "simples"

    assert worker.proximo_provedor() is None


def test_sem_nenhuma_chave_extra_o_alf_encerra_explicando(chaves):
    chaves(openai="", groq="")

    assert GeminiLiveWorker().proximo_provedor() is None


def test_qualquer_provedor_de_texto_habilita_o_modo_simples(chaves):
    """Groq, Mistral ou Cerebras: basta um."""
    chaves(openai="", groq="", mistral="chave-mistral")
    assert GeminiLiveWorker().proximo_provedor() == "simples"

    chaves(openai="", groq="", mistral="", cerebras="chave-cerebras")
    assert GeminiLiveWorker().proximo_provedor() == "simples"


def test_a_chamada_comeca_sempre_pelo_gemini():
    assert GeminiLiveWorker().provedor == "gemini"


# ============================================================
# O que o professor ouve
# ============================================================

def test_o_aviso_da_openai_diz_o_que_deixa_de_funcionar():
    aviso = GeminiLiveWorker.aviso_do_provedor("openai")

    assert "não enxergo a tela" in aviso
    assert "clique visual" in aviso


def test_o_aviso_do_modo_simples_avisa_do_que_muda():
    """É mais devagar e não dá para interromper: melhor saber antes."""
    aviso = GeminiLiveWorker.aviso_do_provedor("simples")

    assert "modo simples" in aviso
    assert "devagar" in aviso
    assert "interromper" in aviso
    assert "demais funções seguem funcionando" in aviso


# ============================================================
# A ligação com o laço de conexão
# ============================================================

def test_a_troca_acontece_na_primeira_recusa():
    """
    Esperar em silêncio por uma cota que acabou, com outro provedor
    pronto ao lado, é tempo de aula jogado fora.
    """
    trecho = CODIGO.split("if self.parece_cota_esgotada(erro):", 1)[1][:2500]

    assert trecho.index("proximo_provedor()") < trecho.index(
        "decidir_apos_cota(duracao_sessao)"
    )


def test_sem_alternativa_continua_esperando_antes_de_encerrar():
    """Sem para onde ir, o tempo é o único remédio."""
    trecho = CODIGO.split("if self.parece_cota_esgotada(erro):", 1)[1][:2500]

    assert 'if decisao == "parar":' in trecho
    assert "raise RuntimeError(detalhe)" in trecho


def test_a_conexao_abre_o_degrau_da_vez():
    assert 'if self.provedor == "simples":' in CODIGO
    assert 'elif self.provedor == "openai":' in CODIGO
    assert "conectar_simples(" in CODIGO
    assert "conectar_alternativa(" in CODIGO


# ============================================================
# O log precisa dizer de qual provedor fala
# ============================================================

def test_o_log_nomeia_o_provedor_da_vez():
    """
    O log dizia "Sessao Gemini Live aberta" mesmo quando a sessão era da
    OpenAI. Isso mandou o professor investigar a cota do Gemini por
    causa de um erro que era da OpenAI.
    """
    worker = GeminiLiveWorker()

    assert worker.nome_do_provedor() == "Gemini Live"

    worker.provedor = "openai"
    assert worker.nome_do_provedor() == "OpenAI Realtime"

    worker.provedor = "simples"
    assert worker.nome_do_provedor() == "modo simples"


def test_nenhuma_mensagem_fixa_fala_em_gemini():
    """Mensagem de conexão com provedor fixo no texto é armadilha."""
    assert "Abrindo sessao Gemini Live" not in CODIGO
    assert "Reabrindo sessao Gemini Live" not in CODIGO
    assert "Sessao Gemini Live aberta com sucesso" not in CODIGO
