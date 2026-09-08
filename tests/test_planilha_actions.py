"""Testes de integração para actions/planilha_actions.py.

Gera planilhas .xlsx reais em um diretório temporário com openpyxl
e valida a leitura completa (sem mocks, é um teste de integração real).
"""

import openpyxl
import pytest

from actions import planilha_actions


@pytest.fixture
def desktop_falso(tmp_path, monkeypatch):
    monkeypatch.setattr(planilha_actions, "_pastas_busca", lambda: [tmp_path])
    return tmp_path


def _criar_planilha(caminho, cabecalho, linhas, nome_aba="Notas"):
    pasta_trabalho = openpyxl.Workbook()
    planilha = pasta_trabalho.active
    planilha.title = nome_aba
    planilha.append(cabecalho)
    for linha in linhas:
        planilha.append(linha)
    pasta_trabalho.save(caminho)


def test_ler_planilha_notas_com_sucesso(desktop_falso):
    caminho = desktop_falso / "notas_turma_a.xlsx"
    _criar_planilha(
        caminho,
        ["Aluno", "NOTA (0-6)"],
        [
            ["Ana Souza", 5.5],
            ["Bruno Lima", 4.0],
        ],
    )

    resultado = planilha_actions.ler_planilha_notas("notas_turma_a")

    assert "lida com sucesso" in resultado
    assert "Ana Souza" in resultado
    assert "5.5" in resultado
    assert "Bruno Lima" in resultado
    assert "2 alunos encontrados" in resultado


def test_ler_planilha_notas_arquivo_inexistente(desktop_falso):
    resultado = planilha_actions.ler_planilha_notas("nao_existe")
    assert "Não encontrei nenhuma planilha" in resultado


def test_ler_planilha_notas_nome_ambiguo(desktop_falso):
    _criar_planilha(desktop_falso / "notas_1a.xlsx", ["Aluno", "Nota"], [["A", 1]])
    _criar_planilha(desktop_falso / "notas_1b.xlsx", ["Aluno", "Nota"], [["B", 2]])

    resultado = planilha_actions.ler_planilha_notas("notas")
    assert "mais de uma planilha parecida" in resultado


def test_ler_planilha_notas_sem_coluna_de_nome(desktop_falso):
    _criar_planilha(desktop_falso / "dados.xlsx", ["Coluna1", "Coluna2"], [[1, 2]])
    resultado = planilha_actions.ler_planilha_notas("dados")
    assert "Não consegui identificar a coluna" in resultado


def test_ler_planilha_notas_aba_especifica(desktop_falso):
    caminho = desktop_falso / "notas_multi_aba.xlsx"
    pasta_trabalho = openpyxl.Workbook()
    aba1 = pasta_trabalho.active
    aba1.title = "1a Unidade"
    aba1.append(["Aluno", "Nota"])
    aba1.append(["Ana", 5])
    aba2 = pasta_trabalho.create_sheet("2a Unidade")
    aba2.append(["Aluno", "Nota"])
    aba2.append(["Bruno", 7])
    pasta_trabalho.save(caminho)

    resultado = planilha_actions.ler_planilha_notas("notas_multi_aba", aba="2a Unidade")
    assert "Bruno" in resultado
    assert "Ana" not in resultado


def test_ler_planilha_notas_aba_inexistente(desktop_falso):
    _criar_planilha(desktop_falso / "notas.xlsx", ["Aluno", "Nota"], [["A", 1]])
    resultado = planilha_actions.ler_planilha_notas("notas", aba="Aba Fantasma")
    assert "Não encontrei a aba" in resultado


def test_ler_planilha_notas_ignora_linhas_sem_nome(desktop_falso):
    _criar_planilha(
        desktop_falso / "notas.xlsx",
        ["Aluno", "Nota"],
        [["Ana", 5], ["", 8], [None, 9]],
    )
    resultado = planilha_actions.ler_planilha_notas("notas")
    assert "1 alunos encontrados" in resultado


def test_normalizar_remove_acentos_e_caixa():
    assert planilha_actions._normalizar("São Paulo") == "SAO PAULO"
