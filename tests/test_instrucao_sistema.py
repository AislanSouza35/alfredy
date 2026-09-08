"""
Testes da atualização da instrução do sistema.

A instrução era montada uma única vez, antes do laço de conexão. Com
isso uma memória salva durante a chamada só valia na chamada seguinte,
e a data embutida na instrução envelhecia numa chamada longa, fazendo o
ALF errar "hoje" e "amanhã" ao mexer na agenda.
"""

from datetime import datetime

import gemini.live_client as live_client
from gemini.live_client import GeminiLiveWorker


def _instrucao_base(memorias="MEMÓRIA PERSISTENTE:\nNenhuma memória salva."):
    return (
        "Você é o ALF. "
        "Data e hora local atual: 01/01/2020 03:00. "
        "Continue ajudando o usuário."
        "\n\n"
        + memorias
    )


def test_data_da_instrucao_e_atualizada():
    atualizada = GeminiLiveWorker.atualizar_instrucao_sistema(_instrucao_base())

    assert "01/01/2020 03:00" not in atualizada
    assert datetime.now().strftime("%d/%m/%Y") in atualizada


def test_memorias_novas_entram_na_instrucao(monkeypatch):
    monkeypatch.setattr(
        live_client,
        "contexto_memorias",
        lambda: "MEMÓRIA PERSISTENTE DO USUÁRIO:\n- O usuário se chama Aislan.",
    )

    atualizada = GeminiLiveWorker.atualizar_instrucao_sistema(_instrucao_base())

    assert "O usuário se chama Aislan." in atualizada
    assert "Nenhuma memória salva." not in atualizada


def test_memoria_antiga_e_substituida_e_nao_acumulada(monkeypatch):
    base = _instrucao_base(
        "MEMÓRIA PERSISTENTE DO USUÁRIO:\n- Memória antiga."
    )

    monkeypatch.setattr(
        live_client,
        "contexto_memorias",
        lambda: "MEMÓRIA PERSISTENTE DO USUÁRIO:\n- Memória nova.",
    )

    atualizada = GeminiLiveWorker.atualizar_instrucao_sistema(base)

    assert "Memória nova." in atualizada
    assert "Memória antiga." not in atualizada
    assert atualizada.count("MEMÓRIA PERSISTENTE DO USUÁRIO:") == 1


def test_restante_da_instrucao_e_preservado(monkeypatch):
    monkeypatch.setattr(
        live_client,
        "contexto_memorias",
        lambda: "MEMÓRIA PERSISTENTE:\nNenhuma memória salva.",
    )

    atualizada = GeminiLiveWorker.atualizar_instrucao_sistema(_instrucao_base())

    assert "Você é o ALF." in atualizada
    assert "Continue ajudando o usuário." in atualizada
