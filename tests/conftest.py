"""Fixtures compartilhadas pelos testes. Nenhum teste deve tocar os
arquivos reais em memory/memory.json ou memory/agenda.json."""



import pytest as _pytest


@_pytest.fixture(autouse=True)
def _comentarios_em_arquivo_temporario(tmp_path, monkeypatch):
    """Nenhum teste grava comentário de aluno no memory/ de verdade."""
    from actions import devolucao_comentada

    monkeypatch.setattr(
        devolucao_comentada, "ARQUIVO", tmp_path / "comentarios_pendentes.json"
    )



@_pytest.fixture(autouse=True)
def _log_em_arquivo_temporario(tmp_path, monkeypatch):
    """
    Os testes escreviam no log do ALF de verdade. Linhas falsas, como o
    "socket caiu" de um teste, apareciam misturadas ao uso real e
    atrapalhavam justamente o diagnóstico que depende desse log.
    """
    from gemini.live_client import GeminiLiveWorker

    monkeypatch.setattr(
        GeminiLiveWorker,
        "caminho_log_diagnostico",
        staticmethod(lambda: tmp_path / "alf_runtime_debug.log"),
    )
