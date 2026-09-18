"""
O que o ensaio de 10/09 mostrou, travado em teste.

Ensaio numa página falsa igual ao Classroom: 0 de 6 notas. O localizador
sozinho achava a aluna com confiança 1,0; o que falhou foi o entorno:

- 503 do Google em cinco de sete buscas, e três tentativas curtas não
  passavam do pico;
- sem âncora, a roda rolou a lista de turmas, com o ponteiro parado em
  cima dela, e a lista de alunos nunca se mexeu;
- uma ferramenta que estoura o prazo continua rodando por trás, e a
  chamada seguinte mexeria no mouse junto com ela.
"""

from types import SimpleNamespace

import pytest

from actions import devolucao_comentada as dc
from actions import transporte_notas as tn
from vision import click_locator as cl


@pytest.fixture(autouse=True)
def estado_limpo():
    tn._transporte.update(pendentes=[], concluidos=[], todas=[], nomes=[], ancora=None)
    dc._devolucao.update(fila=[], feitos=[], nomes=[], contexto=None, ancora=None)
    yield
    tn._transporte.update(pendentes=[], concluidos=[], todas=[], nomes=[], ancora=None)
    dc._devolucao.update(fila=[], feitos=[], nomes=[], contexto=None, ancora=None)


# ============================================================
# 503
# ============================================================

class _Modelos:
    def __init__(self, falhas):
        self.falhas = falhas
        self.chamadas = 0

    def generate_content(self, **kwargs):
        self.chamadas += 1
        if self.chamadas <= self.falhas:
            raise RuntimeError("503 UNAVAILABLE")
        return SimpleNamespace(
            text='{"encontrado": true, "x": 1, "y": 2, "confianca": 0.9, "descricao": "ok"}'
        )


def test_localizador_aguenta_um_pico_de_503(monkeypatch):
    esperas = []
    monkeypatch.setattr(cl.time, "sleep", esperas.append)
    modelos = _Modelos(falhas=4)

    resposta = cl._perguntar_coordenada(SimpleNamespace(models=modelos), b"img", "alvo")

    assert resposta["encontrado"]
    assert modelos.chamadas == 5
    # A espera dobra: um pico dura segundos, não um segundo e meio.
    assert esperas == [1.5, 3.0, 6.0, 12.0]


def test_localizador_desiste_depois_do_limite(monkeypatch):
    monkeypatch.setattr(cl.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="503"):
        cl._perguntar_coordenada(
            SimpleNamespace(models=_Modelos(falhas=99)), b"img", "alvo"
        )


# ============================================================
# Rolar onde a lista está, não onde o ponteiro está
# ============================================================

@pytest.fixture
def tela(monkeypatch):
    acoes = {"ponteiro": [], "rolagens": [], "digitado": []}

    monkeypatch.setattr(
        "actions.mouse_actions.mover_mouse_para",
        lambda x, y, duracao=0.35: acoes["ponteiro"].append((x, y)),
    )
    monkeypatch.setattr(
        "actions.mouse_actions.rolar_pagina",
        lambda direcao, quantidade=3: acoes["rolagens"].append(direcao),
    )
    monkeypatch.setattr(
        "actions.mouse_actions.mover_e_clicar", lambda x, y, duracao=0.35: None
    )
    monkeypatch.setattr(
        "actions.text_actions.escrever_no_campo_ativo",
        lambda texto: acoes["digitado"].append(texto),
    )
    monkeypatch.setattr(tn, "ESPERA_APOS_ROLAR", 0)
    monkeypatch.setattr(tn, "ESPERA_ANTES_DE_CONFERIR", 0)
    return acoes


def test_sem_ancora_acha_a_lista_antes_de_rolar(tela, monkeypatch):
    """No ensaio a roda rolou a lista de turmas, e os alunos nem se mexeram."""

    def localizar(alvo):
        if "lista de nomes" in alvo:
            return {"sucesso": True, "x": 400, "y": 450, "confianca": 0.95}
        return {"sucesso": False, "mensagem": "fora da tela"}

    monkeypatch.setattr("vision.click_locator.localizar_elemento_na_tela", localizar)

    tn.procurar_na_lista("campo do Bruno", ancora=None)

    # Antes da primeira rolagem o ponteiro já foi para dentro da lista.
    assert tela["ponteiro"]
    assert set(tela["ponteiro"]) == {(400, 450)}


def test_com_ancora_nao_gasta_busca_pela_lista(tela, monkeypatch):
    pedidos = []

    def localizar(alvo):
        pedidos.append(alvo)
        return {"sucesso": False, "mensagem": "fora da tela"}

    monkeypatch.setattr("vision.click_locator.localizar_elemento_na_tela", localizar)

    tn.procurar_na_lista("campo do Bruno", ancora=(10, 20))

    assert not any("lista de nomes" in p for p in pedidos)


# ============================================================
# Uma execução por vez
# ============================================================

def test_transporte_recusa_segunda_execucao_simultanea(tela):
    tn._transporte["pendentes"] = [{"aluno": "Ana", "nota": "0.5"}]

    tn._EM_ANDAMENTO.acquire()
    try:
        resultado = tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))
    finally:
        tn._EM_ANDAMENTO.release()

    assert tela["digitado"] == []
    assert "Ainda estou digitando" in resultado
    # A fila continua intacta para a execução que está rodando.
    assert tn._transporte["pendentes"] == [{"aluno": "Ana", "nota": "0.5"}]


def test_trava_e_solta_depois_de_cada_nota(tela, monkeypatch):
    monkeypatch.setattr(
        "vision.click_locator.localizar_elemento_na_tela",
        lambda alvo: {"sucesso": True, "x": 1, "y": 1, "confianca": 0.95},
    )
    tn._transporte["pendentes"] = [{"aluno": "Ana", "nota": "0.5"}]

    tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    assert not tn._EM_ANDAMENTO.locked()


def test_devolucao_recusa_segunda_execucao_simultanea():
    dc._devolucao["fila"] = [
        {"uid": "u1", "aluno": "Ana", "nota": 1.0, "texto": "", "id_entrega": "e1"}
    ]
    devolvidos = []

    dc._EM_ANDAMENTO.acquire()
    try:
        resultado = dc.devolver_proximo_aluno(devolver=devolvidos.append)
    finally:
        dc._EM_ANDAMENTO.release()

    assert devolvidos == []
    assert "Ainda estou devolvendo" in resultado


def test_prazo_da_ferramenta_cabe_numa_busca_com_503():
    import re
    from pathlib import Path

    codigo = Path("gemini/live_client.py").read_text(encoding="utf-8")

    # A chamada que roda a ferramenta, não a linha do import.
    achado = re.search(
        r"executar_funcao_local\(\s*lancar_proxima_nota,\s*timeout=(\d+)", codigo
    )

    assert achado is not None
    assert int(achado.group(1)) >= 240
