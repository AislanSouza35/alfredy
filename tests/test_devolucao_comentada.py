"""
Testes da devolução com comentário particular.

Comentário no aluno errado é vazamento de informação particular: pior
que nota errada, e não se desfaz na cabeça de quem leu. Por isso o
painel é conferido antes de digitar, antes de enviar e depois de
enviar, e qualquer divergência para tudo. Os testes travam isso.

Nenhum teste toca tela, teclado ou API de verdade.
"""

import pytest

from actions import devolucao_comentada as dc
from actions import transporte_notas as tn


@pytest.fixture(autouse=True)
def fila_limpa():
    dc._devolucao.update(fila=[], feitos=[], contexto=None, ancora=None)
    yield
    dc._devolucao.update(fila=[], feitos=[], contexto=None, ancora=None)


@pytest.fixture
def tela(monkeypatch):
    """
    Substitui mouse, teclado e localizador. Um clique depois de digitar
    é o clique em enviar -- é assim que o painel falso sabe que enviou.
    """
    estado = {
        "cliques": [],
        "digitado": [],
        "enviou": False,
        "painel_nome": "Ana Souza",
    }

    def clicar(x, y, duracao=0.35):
        estado["cliques"].append((x, y))
        if estado["digitado"]:
            estado["enviou"] = True

    monkeypatch.setattr(
        "vision.click_locator.localizar_elemento_na_tela",
        lambda alvo: {
            "sucesso": True, "x": 10, "y": 20, "confianca": 0.95,
            "descricao": alvo,
        },
    )
    monkeypatch.setattr("actions.mouse_actions.mover_e_clicar", clicar)
    monkeypatch.setattr(
        "actions.mouse_actions.mover_mouse_para", lambda x, y, duracao=0.35: None
    )
    monkeypatch.setattr(
        "actions.mouse_actions.rolar_pagina", lambda direcao, quantidade=3: None
    )
    monkeypatch.setattr(
        "actions.text_actions.escrever_no_campo_ativo",
        lambda texto: estado["digitado"].append(texto),
    )
    monkeypatch.setattr(dc, "ESPERA_TELA", 0)
    monkeypatch.setattr(tn, "ESPERA_APOS_ROLAR", 0)

    def painel():
        ultimo = estado["digitado"][-1] if estado["digitado"] else ""
        return {
            "nome_no_painel": estado["painel_nome"],
            "texto_no_campo": "" if estado["enviou"] else ultimo,
            "comentario_enviado": ultimo if estado["enviou"] else "",
        }, None

    estado["ler_painel"] = painel
    return estado


COMENTARIO = "Seu fluxograma ficou claro e bem organizado. Da próxima vez, detalhe o treinamento."


def _fila(*itens):
    dc._devolucao["fila"] = [
        {"uid": f"u{i}", "aluno": nome, "nota": 0.8, "texto": texto,
         "id_entrega": f"e{i}"}
        for i, (nome, texto) in enumerate(itens)
    ]


# ============================================================
# O caminho feliz
# ============================================================

def test_envia_o_comentario_e_depois_devolve(tela):
    _fila(("Ana Souza", COMENTARIO))
    devolvidos = []

    resultado = dc.devolver_proximo_aluno(
        ler_painel=tela["ler_painel"],
        devolver=lambda item: devolvidos.append(item["id_entrega"]),
    )

    assert tela["digitado"] == [COMENTARIO]
    assert tela["enviou"]
    assert devolvidos == ["e0"]
    assert "comentário enviado e atividade devolvida" in resultado
    assert dc._devolucao["fila"] == []


def test_aluno_sem_comentario_so_e_devolvido(tela):
    """Sem comentário não há o que digitar: nem toca na tela."""
    _fila(("Ana Souza", ""))
    devolvidos = []

    dc.devolver_proximo_aluno(
        ler_painel=tela["ler_painel"],
        devolver=lambda item: devolvidos.append(item["id_entrega"]),
    )

    assert tela["cliques"] == []
    assert tela["digitado"] == []
    assert devolvidos == ["e0"]


# ============================================================
# Conferências que param tudo
# ============================================================

def test_painel_de_outro_aluno_nao_recebe_comentario(tela):
    """O caso que mais importa: o comentário da Ana na conversa do Bruno."""
    tela["painel_nome"] = "Bruno Lima"
    _fila(("Ana Souza", COMENTARIO), ("Carla Dias", COMENTARIO))
    devolvidos = []

    resultado = dc.devolver_proximo_aluno(
        ler_painel=tela["ler_painel"],
        devolver=lambda item: devolvidos.append(item),
    )

    assert tela["digitado"] == []
    assert devolvidos == []
    assert "Bruno Lima" in resultado
    assert "Não digitei nada" in resultado
    # Para tudo, não só este aluno.
    assert dc._devolucao["fila"] == []


def test_texto_errado_no_campo_nao_e_enviado(tela):
    _fila(("Ana Souza", COMENTARIO))
    devolvidos = []

    def painel_com_outro_texto():
        return {
            "nome_no_painel": "Ana Souza",
            "texto_no_campo": "outra coisa qualquer",
            "comentario_enviado": "",
        }, None

    resultado = dc.devolver_proximo_aluno(
        ler_painel=painel_com_outro_texto,
        devolver=lambda item: devolvidos.append(item),
    )

    assert not tela["enviou"]
    assert devolvidos == []
    assert "NÃO foi enviado" in resultado
    assert "apagar" in resultado


def test_envio_nao_confirmado_nao_devolve(tela):
    _fila(("Ana Souza", COMENTARIO))
    devolvidos = []

    def painel_que_nunca_mostra_o_enviado():
        ultimo = tela["digitado"][-1] if tela["digitado"] else ""
        return {
            "nome_no_painel": "Ana Souza",
            "texto_no_campo": ultimo,
            "comentario_enviado": "",
        }, None

    resultado = dc.devolver_proximo_aluno(
        ler_painel=painel_que_nunca_mostra_o_enviado,
        devolver=lambda item: devolvidos.append(item),
    )

    assert devolvidos == []
    assert "NÃO devolvi" in resultado


def test_falha_na_devolucao_avisa_que_o_comentario_ja_foi(tela):
    """O aluno já lê o comentário; o professor precisa saber disso."""
    _fila(("Ana Souza", COMENTARIO))

    resultado = dc.devolver_proximo_aluno(
        ler_painel=tela["ler_painel"],
        devolver=lambda item: "servidor fora do ar",
    )

    assert "JÁ FOI enviado" in resultado
    assert "servidor fora do ar" in resultado


def test_aluno_fora_da_tela_nao_esvazia_a_fila(tela, monkeypatch):
    """Nada saiu: dá para tentar de novo depois de arrumar a tela."""
    monkeypatch.setattr(
        "vision.click_locator.localizar_elemento_na_tela",
        lambda alvo: {"sucesso": False, "mensagem": "não achei"},
    )
    _fila(("Ana Souza", COMENTARIO))

    resultado = dc.devolver_proximo_aluno(
        ler_painel=tela["ler_painel"], devolver=lambda item: None
    )

    assert tela["digitado"] == []
    assert "NÃO devolvi" in resultado
    assert len(dc._devolucao["fila"]) == 1


# ============================================================
# Nome no painel
# ============================================================

def test_nome_do_painel_precisa_ser_o_mesmo():
    assert dc._mesmo_aluno("Ana Souza", "Ana Souza")
    assert dc._mesmo_aluno("ANA SOUZA", "Ana Souza")
    assert not dc._mesmo_aluno("Ana Lima", "Ana Souza")
    assert not dc._mesmo_aluno("", "Ana Souza")


def test_nome_cortado_so_passa_com_duas_palavras():
    assert dc._mesmo_aluno("Ana Beatriz Santos...", "Ana Beatriz Santos da Silva")
    # "Ana..." serviria para qualquer Ana da turma.
    assert not dc._mesmo_aluno("Ana...", "Ana Beatriz Santos da Silva")


# ============================================================
# Guardar e preparar
# ============================================================

def test_comentarios_guardados_em_disco():
    """O professor revisa no dia seguinte, com o ALF reiniciado."""
    dc.guardar_comentarios(
        "p@e.com",
        {"id": "t1", "name": "3A"},
        {"id": "a1", "title": "X"},
        {"u1": {"aluno": "Ana Souza", "texto": COMENTARIO}},
    )

    assert dc.ARQUIVO.exists()
    assert dc.comentarios_da_atividade("t1", "a1")["u1"]["texto"] == COMENTARIO


def test_comentario_enviado_e_esquecido(tela):
    """Para nunca sair duas vezes."""
    dc.guardar_comentarios(
        "p@e.com",
        {"id": "t1", "name": "3A"},
        {"id": "a1", "title": "X"},
        {"u0": {"aluno": "Ana Souza", "texto": COMENTARIO}},
    )
    _fila(("Ana Souza", COMENTARIO))
    dc._devolucao["contexto"] = {"servico": None, "id_turma": "t1", "id_atividade": "a1"}

    dc.devolver_proximo_aluno(
        ler_painel=tela["ler_painel"], devolver=lambda item: None
    )

    assert dc.comentarios_da_atividade("t1", "a1") == {}


@pytest.fixture
def classroom(monkeypatch):
    import actions.classroom_actions as ca

    entregas = [
        {"id": "e1", "userId": "u1", "state": "TURNED_IN",
         "draftGrade": 0.8, "associatedWithDeveloper": True},
        {"id": "e2", "userId": "u2", "state": "RETURNED",
         "assignedGrade": 1, "associatedWithDeveloper": True},
        {"id": "e3", "userId": "u3", "state": "TURNED_IN",
         "associatedWithDeveloper": True},
    ]

    class _Servico:
        def courses(self):
            return self

        def courseWork(self):
            return self

        def studentSubmissions(self):
            return self

        def list(self, **kwargs):
            return {"studentSubmissions": entregas}

    monkeypatch.setattr(ca, "servicos", lambda: [("p@e.com", _Servico(), None)])
    monkeypatch.setattr(
        ca,
        "_encontrar_turma",
        lambda turma: (
            ("p@e.com", _Servico(), None, {"id": "t1", "name": "3A"}, ""),
            None,
        ),
    )
    monkeypatch.setattr(
        ca,
        "_encontrar_atividade",
        lambda servico, id_turma, nome: ({"id": "a1", "title": "Fluxograma"}, None),
    )
    monkeypatch.setattr(
        ca,
        "_mapa_de_alunos",
        lambda servico, id_turma: (
            {"u1": "Ana Souza", "u2": "Bruno Lima", "u3": "Carla Dias"},
            None,
        ),
    )
    monkeypatch.setattr(ca, "_executar", lambda resposta: (resposta, None))
    return entregas


def test_preparar_nao_devolve_nada(classroom):
    dc.guardar_comentarios(
        "p@e.com",
        {"id": "t1", "name": "3A"},
        {"id": "a1", "title": "Fluxograma"},
        {"u1": {"aluno": "Ana Souza", "texto": COMENTARIO}},
    )

    resultado = dc.preparar_devolucao("3A", "Fluxograma")

    # Só a Ana: Bruno já foi devolvido, Carla não tem nota.
    assert [item["aluno"] for item in dc._devolucao["fila"]] == ["Ana Souza"]
    assert dc._devolucao["fila"][0]["texto"] == COMENTARIO
    assert "NADA foi devolvido" in resultado
    assert "1 com comentário" in resultado
    assert "confirme UMA" in resultado


def test_preparar_recusa_atividade_de_fora(classroom):
    for entrega in classroom:
        entrega["associatedWithDeveloper"] = False

    resultado = dc.preparar_devolucao("3A", "Fluxograma")

    assert "criadas por mim" in resultado
    assert dc._devolucao["fila"] == []


def test_instrucao_so_comenta_na_devolucao():
    from pathlib import Path

    codigo = Path("gemini/live_client.py").read_text(encoding="utf-8")

    assert "na DEVOLUÇÃO -- nunca antes" in codigo
    assert "confirme UMA vez só" in codigo
    assert "NUNCA diga que enviou um comentário" in codigo
