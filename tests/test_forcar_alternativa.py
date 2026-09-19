"""
Ligar a alternativa de voz à força, para poder testá-la.

O caminho alternativo só entrava em cena quando a cota do Gemini
acabava -- ou seja, o primeiro uso de verdade aconteceria no meio de
uma aula, justamente quando tudo já deu errado. Com
ALF_VOZ_ALTERNATIVA=1 no .env, a chamada já começa pela OpenAI.
"""

from pathlib import Path

import gemini.live_client as live_client
from gemini.live_client import GeminiLiveWorker


CODIGO = Path("gemini/live_client.py").read_text(encoding="utf-8")


def test_sem_a_variavel_comeca_pelo_gemini(monkeypatch):
    monkeypatch.setattr(live_client, "FORCAR_VOZ_ALTERNATIVA", False)
    monkeypatch.setattr(live_client, "OPENAI_API_KEY", "sk-exemplo")

    assert GeminiLiveWorker.decidir_provedor_inicial() == (False, "")


def test_com_a_variavel_comeca_pela_alternativa(monkeypatch):
    monkeypatch.setattr(live_client, "FORCAR_VOZ_ALTERNATIVA", True)
    monkeypatch.setattr(live_client, "OPENAI_API_KEY", "sk-exemplo")

    usar, mensagem = GeminiLiveWorker.decidir_provedor_inicial()

    assert usar
    # Ninguém deveria descobrir por acaso que está falando com outro
    # provedor, nem esquecer a variável ligada.
    assert "ALF_VOZ_ALTERNATIVA" in mensagem
    assert "não enxergo a tela" in mensagem
    assert "apague essa linha" in mensagem


def test_forcada_sem_chave_avisa_e_segue_no_gemini(monkeypatch):
    """Forçar sem chave não pode virar erro no meio da chamada."""
    monkeypatch.setattr(live_client, "FORCAR_VOZ_ALTERNATIVA", True)
    monkeypatch.setattr(live_client, "OPENAI_API_KEY", None)

    usar, mensagem = GeminiLiveWorker.decidir_provedor_inicial()

    assert not usar
    assert "falta OPENAI_API_KEY" in mensagem
    assert "Continuando pelo Gemini" in mensagem


def test_a_variavel_aceita_as_formas_comuns():
    import importlib
    import os

    import core.config

    for valor, esperado in [
        ("1", True), ("sim", True), ("true", True), ("ON", True),
        ("0", False), ("", False), ("nao", False),
    ]:
        os.environ["ALF_VOZ_ALTERNATIVA"] = valor
        recarregado = importlib.reload(core.config)
        assert recarregado.FORCAR_VOZ_ALTERNATIVA is esperado, valor

    os.environ.pop("ALF_VOZ_ALTERNATIVA", None)
    importlib.reload(core.config)


def test_a_decisao_acontece_na_abertura_da_chamada():
    assert "self.usando_alternativa, aviso_provedor = self.decidir_provedor_inicial()" in CODIGO
