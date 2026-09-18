"""
O nome encurtado precisa ser único na TURMA, não só entre quem tem nota.

O Classroom corta nomes longos, então a busca na tela usa o menor
pedaço que distingue o aluno. Esse pedaço era calculado só entre os
alunos com nota na planilha. Com "Ana Beatriz Santos da Silva" com nota
e "Ana Beatriz Costa Lima" sem nota, o pedaço virava "Ana Beatriz" --
único na fila, ambíguo na tela. A conferência procurava o mesmo pedaço
e podia aprovar a linha errada: nota na aluna errada, aprovada.
"""

import pytest

from actions import devolucao_comentada as dc
from actions import transporte_notas as tn


@pytest.fixture(autouse=True)
def estado_limpo():
    tn._transporte.update(pendentes=[], concluidos=[], todas=[], nomes=[], ancora=None)
    dc._devolucao.update(fila=[], feitos=[], nomes=[], contexto=None, ancora=None)
    yield
    tn._transporte.update(pendentes=[], concluidos=[], todas=[], nomes=[], ancora=None)
    dc._devolucao.update(fila=[], feitos=[], nomes=[], contexto=None, ancora=None)


@pytest.fixture
def localizador(monkeypatch):
    """Guarda o que foi pedido ao localizador visual."""
    alvos = []

    def localizar(alvo):
        alvos.append(alvo)
        return {"sucesso": True, "x": 1, "y": 1, "confianca": 0.95, "descricao": alvo}

    monkeypatch.setattr("vision.click_locator.localizar_elemento_na_tela", localizar)
    monkeypatch.setattr(
        "actions.mouse_actions.mover_e_clicar", lambda x, y, duracao=0.35: None
    )
    monkeypatch.setattr(
        "actions.mouse_actions.mover_mouse_para", lambda x, y, duracao=0.35: None
    )
    monkeypatch.setattr(
        "actions.mouse_actions.rolar_pagina", lambda direcao, quantidade=3: None
    )
    monkeypatch.setattr(
        "actions.text_actions.escrever_no_campo_ativo", lambda texto: None
    )
    monkeypatch.setattr(tn, "ESPERA_ANTES_DE_CONFERIR", 0)
    monkeypatch.setattr(tn, "ESPERA_APOS_ROLAR", 0)
    return alvos


def test_transporte_desempata_com_aluno_sem_nota(localizador, monkeypatch):
    linhas = [
        ["Aluno", "Nota sugerida (de 1)"],
        ["Ana Beatriz Costa Lima", ""],
        ["Ana Beatriz Santos da Silva", "0.7"],
    ]
    monkeypatch.setattr(tn, "_ler_planilha_local", lambda caminho: linhas)
    monkeypatch.setattr(
        "actions.email_actions.localizar_arquivo",
        lambda nome: [tn.Path("notas.xlsx")],
    )

    tn.preparar_transporte("notas")
    tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    assert "Ana Beatriz Santos" in localizador[0]


def test_conferencia_usa_o_mesmo_nome_desempatado(localizador, monkeypatch):
    """Desempatar só a busca e não a conferência deixaria o furo aberto."""
    linhas = [
        ["Aluno", "Nota sugerida (de 1)"],
        ["Ana Beatriz Costa Lima", ""],
        ["Ana Beatriz Santos da Silva", "0.7"],
    ]
    monkeypatch.setattr(tn, "_ler_planilha_local", lambda caminho: linhas)
    monkeypatch.setattr(
        "actions.email_actions.localizar_arquivo",
        lambda nome: [tn.Path("notas.xlsx")],
    )
    conferidos = []

    tn.preparar_transporte("notas")
    tn.lancar_proxima_nota(
        conferir=lambda nome, nota: conferidos.append(nome) or (True, "")
    )

    assert conferidos == ["Ana Beatriz Santos"]


def test_nomes_da_planilha_inclui_quem_ficou_sem_nota():
    linhas = [
        ["Aluno", "Nota"],
        ["Ana", "8"],
        ["Bruno", ""],
        ["", ""],
    ]

    assert tn._nomes_da_planilha(linhas) == ["Ana", "Bruno"]


def test_nomes_da_turma_vem_da_api(monkeypatch):
    """Planilha feita à mão pode não ter a turma inteira; a tela tem."""
    import actions.classroom_actions as ca

    monkeypatch.setattr(
        ca,
        "_encontrar_turma",
        lambda turma: (("p@e.com", object(), None, {"id": "t1", "name": "3A"}, ""), None),
    )
    monkeypatch.setattr(
        ca,
        "_mapa_de_alunos",
        lambda servico, id_turma: ({"u1": "Ana Beatriz Costa Lima"}, None),
    )

    assert tn._nomes_da_turma("3A") == ["Ana Beatriz Costa Lima"]


def test_nomes_da_turma_sem_turma_nao_consulta_nada():
    assert tn._nomes_da_turma("") == []


def test_devolucao_desempata_com_a_turma_inteira(localizador, monkeypatch):
    """Na devolução o furo era o mesmo: só contava quem ia ser devolvido."""
    monkeypatch.setattr(
        "vision.click_locator.localizar_elemento_na_tela",
        lambda alvo: localizador.append(alvo) or {"sucesso": False, "mensagem": "x"},
    )
    dc._devolucao["fila"] = [
        {"uid": "u2", "aluno": "Ana Beatriz Santos da Silva", "nota": 0.7,
         "texto": "Parabéns pelo fluxograma.", "id_entrega": "e2"},
    ]
    dc._devolucao["nomes"] = ["Ana Beatriz Costa Lima", "Ana Beatriz Santos da Silva"]

    dc.devolver_proximo_aluno(ler_painel=lambda: ({}, None), devolver=lambda item: None)

    assert "Ana Beatriz Santos" in localizador[0]
