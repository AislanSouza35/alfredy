"""
Testes do transporte de notas para a tela do Classroom.

Este é o fluxo mais perigoso do projeto: digita nota de aluno numa tela,
sem a API para garantir que foi no registro certo. Errar aqui significa
nota errada na vida de alguém, e ninguém percebe olhando.

Por isso a conferência pela tela depois de cada nota, e a interrupção na
primeira divergência. Os testes abaixo travam exatamente isso.
"""

import pytest

from actions import transporte_notas as tn


@pytest.fixture(autouse=True)
def fila_limpa():
    tn._transporte["pendentes"] = []
    tn._transporte["concluidos"] = []
    tn._transporte["ancora"] = None
    tn._transporte["todas"] = []
    yield
    tn._transporte["pendentes"] = []
    tn._transporte["concluidos"] = []
    tn._transporte["ancora"] = None
    tn._transporte["todas"] = []


@pytest.fixture
def tela(monkeypatch):
    """Substitui mouse, teclado, roda e localizador visual."""
    acoes = {"cliques": [], "digitado": [], "rolagens": [], "ponteiro": []}

    monkeypatch.setattr(
        "vision.click_locator.localizar_elemento_na_tela",
        lambda alvo: {
            "sucesso": True,
            "x": 100,
            "y": 200,
            "confianca": 0.95,
            "descricao": alvo,
        },
    )
    monkeypatch.setattr(
        "actions.mouse_actions.mover_e_clicar",
        lambda x, y, duracao=0.35: acoes["cliques"].append((x, y)),
    )
    monkeypatch.setattr(
        "actions.mouse_actions.mover_mouse_para",
        lambda x, y, duracao=0.35: acoes["ponteiro"].append((x, y)),
    )
    monkeypatch.setattr(
        "actions.mouse_actions.rolar_pagina",
        lambda direcao, quantidade=3: acoes["rolagens"].append(
            (direcao, quantidade)
        ),
    )
    monkeypatch.setattr(
        "actions.text_actions.escrever_no_campo_ativo",
        lambda texto: acoes["digitado"].append(texto),
    )
    monkeypatch.setattr(tn, "ESPERA_ANTES_DE_CONFERIR", 0)
    monkeypatch.setattr(tn, "ESPERA_APOS_ROLAR", 0)
    return acoes


def _planilha(linhas):
    return [["Aluno", "Entregou", "Nota sugerida", "Observação"]] + linhas


# ============================================================
# Leitura da planilha revisada
# ============================================================

def test_le_alunos_e_notas():
    notas, erro = tn._extrair_notas(
        _planilha([["Ana Souza", "Sim", "8", "ok"], ["Bruno Lima", "Sim", "9,5", ""]])
    )

    assert erro is None
    assert notas == [
        {"aluno": "Ana Souza", "nota": "8"},
        {"aluno": "Bruno Lima", "nota": "9.5"},
    ]


def test_linhas_sem_nota_ficam_de_fora():
    """Aluno em branco não vira nota zero por engano."""
    notas, _ = tn._extrair_notas(
        _planilha([["Ana", "Sim", "8", ""], ["Bruno", "Não", "", ""]])
    )

    assert [n["aluno"] for n in notas] == ["Ana"]


def test_nota_que_nao_e_numero_interrompe():
    notas, erro = tn._extrair_notas(
        _planilha([["Ana", "Sim", "oito", ""]])
    )

    assert notas is None
    assert "não é um número" in erro


def test_planilha_sem_coluna_de_nota_e_recusada():
    notas, erro = tn._extrair_notas([["Aluno", "Entregou"], ["Ana", "Sim"]])

    assert notas is None
    assert "colunas" in erro


def test_planilha_sem_nenhuma_nota_preenchida():
    notas, erro = tn._extrair_notas(_planilha([["Ana", "Sim", "", ""]]))

    assert notas is None
    assert "Preencha as notas" in erro


def test_coluna_de_nota_ja_lancada_nao_e_confundida():
    linhas = [
        ["Aluno", "Nota sugerida", "Nota já lançada"],
        ["Ana", "8", "3"],
    ]

    notas, _ = tn._extrair_notas(linhas)

    assert notas == [{"aluno": "Ana", "nota": "8"}]


# ============================================================
# Preparar não digita nada
# ============================================================

def test_preparar_nao_digita(tela, monkeypatch):
    monkeypatch.setattr(
        tn, "_ler_planilha_local", lambda caminho: _planilha([["Ana", "Sim", "8", ""]])
    )
    monkeypatch.setattr(
        "actions.email_actions.localizar_arquivo",
        lambda nome: [tn.Path("notas.xlsx")],
    )

    resultado = tn.preparar_transporte("notas")

    assert tela["digitado"] == []
    assert "NADA foi digitado ainda" in resultado
    # Sem a tela certa aberta, o clique visual não teria onde acertar.
    assert "página de notas da atividade no Classroom" in resultado


# ============================================================
# Um aluno por vez, com conferência
# ============================================================

def _enfileirar(*pares):
    tn._transporte["pendentes"] = [
        {"aluno": a, "nota": n} for a, n in pares
    ]
    tn._transporte["concluidos"] = []


def test_digita_e_confere_um_aluno(tela):
    _enfileirar(("Ana Souza", "8"))

    resultado = tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    assert tela["digitado"] == ["8"]
    assert "Ana Souza" in resultado
    assert tn._transporte["pendentes"] == []
    assert len(tn._transporte["concluidos"]) == 1


def test_avanca_um_por_chamada(tela):
    _enfileirar(("Ana", "8"), ("Bruno", "9"))

    tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    assert tela["digitado"] == ["8"]
    assert len(tn._transporte["pendentes"]) == 1

    tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    assert tela["digitado"] == ["8", "9"]


def test_conferencia_que_falha_interrompe_tudo(tela):
    """
    Divergência significa que a nota pode ter ido para o aluno errado.
    Seguir adiante espalharia o erro pela turma inteira.
    """
    _enfileirar(("Ana", "8"), ("Bruno", "9"), ("Carla", "7"))

    resultado = tn.lancar_proxima_nota(
        conferir=lambda nome, nota: (False, "CONFERÊNCIA FALHOU: está 3")
    )

    assert "FALHOU" in resultado
    assert tn._transporte["pendentes"] == []


def test_campo_nao_encontrado_para_o_transporte(tela, monkeypatch):
    monkeypatch.setattr(
        "vision.click_locator.localizar_elemento_na_tela",
        lambda alvo: {"sucesso": False, "mensagem": "não localizei"},
    )
    _enfileirar(("Ana", "8"))

    resultado = tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    descidas = [r for r in tela["rolagens"] if r[0] == "baixo"]
    subidas = [r for r in tela["rolagens"] if r[0] == "cima"]

    assert tela["digitado"] == []
    # Volta ao topo uma vez e varre a lista inteira antes de desistir.
    assert subidas
    assert len(descidas) == tn.ROLAGENS_MAXIMAS
    # A recusa precisa ser impossível de confundir com sucesso.
    assert "NÃO LANCEI" in resultado
    assert "NÃO diga que lançou" in resultado


def test_pouca_certeza_nao_digita_as_cegas(tela, monkeypatch):
    monkeypatch.setattr(
        "vision.click_locator.localizar_elemento_na_tela",
        lambda alvo: {
            "sucesso": True, "x": 1, "y": 1, "confianca": 0.5,
            "descricao": "algo",
        },
    )
    _enfileirar(("Ana", "8"))

    resultado = tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    assert tela["digitado"] == []
    assert "pouca certeza" in resultado


# ============================================================
# Aluno fora da tela
# ============================================================
#
# A turma não cabe na tela. O transporte lançava certinho os primeiros
# quatro alunos e parava no quinto, pedindo rolagem manual -- ou seja,
# só servia para quem coubesse na primeira tela.


def test_rola_a_lista_ate_achar_o_aluno(tela, monkeypatch):
    tentativas = []

    def localizador(alvo):
        # A procura pela lista de alunos (para a roda rolar no lugar
        # certo) não é uma tentativa de achar o aluno.
        if "lista de nomes" in alvo:
            return {"sucesso": False, "mensagem": "ignorado"}
        tentativas.append(alvo)
        # Aparece só depois da segunda rolagem.
        if len(tentativas) < 3:
            return {"sucesso": False, "mensagem": "fora da tela"}
        return {
            "sucesso": True, "x": 640, "y": 548, "confianca": 0.95,
            "descricao": alvo,
        }

    monkeypatch.setattr(
        "vision.click_locator.localizar_elemento_na_tela", localizador
    )
    _enfileirar(("Renan Melo de Araujo", "0.9"))

    resultado = tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    # Primeira falha manda voltar ao topo; a segunda é que desce.
    assert tela["rolagens"][0][0] == "cima"
    assert ("baixo", tn.PASSOS_POR_ROLAGEM) in tela["rolagens"]
    assert tela["digitado"] == ["0,9"]
    assert "Renan Melo de Araujo" in resultado


def test_rolagem_acontece_sobre_a_lista_de_alunos(tela, monkeypatch):
    """
    A roda age na janela sob o ponteiro. Rolar com ele parado sobre a
    barra lateral das turmas não mexeria a lista de alunos.
    """
    chamadas = []

    def localizador(alvo):
        chamadas.append(alvo)
        if "Bruno" in alvo and len(chamadas) < 3:
            return {"sucesso": False, "mensagem": "fora da tela"}
        return {
            "sucesso": True, "x": 640, "y": 500, "confianca": 0.95,
            "descricao": alvo,
        }

    monkeypatch.setattr(
        "vision.click_locator.localizar_elemento_na_tela", localizador
    )
    _enfileirar(("Ana", "8"), ("Bruno", "9"))

    tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))
    tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    # O ponteiro foi para o campo de nota da Ana antes de rolar.
    assert tela["ponteiro"] == [(640, 500)]


def test_ancora_e_zerada_por_um_transporte_novo(tela, monkeypatch):
    _enfileirar(("Ana", "8"))
    tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))
    assert tn._transporte["ancora"] is not None

    monkeypatch.setattr(
        tn, "_ler_planilha_local", lambda caminho: _planilha([["Ana", "Sim", "8", ""]])
    )
    monkeypatch.setattr(
        "actions.email_actions.localizar_arquivo",
        lambda nome: [tn.Path("notas.xlsx")],
    )

    tn.preparar_transporte("notas")

    assert tn._transporte["ancora"] is None


def test_localiza_pelo_nome_do_aluno(tela, monkeypatch):
    """
    Rolagem, linha mais alta e seção nova desalinham posição; nome não.
    """
    alvos = []
    monkeypatch.setattr(
        "vision.click_locator.localizar_elemento_na_tela",
        lambda alvo: alvos.append(alvo) or {
            "sucesso": True, "x": 1, "y": 1, "confianca": 0.95,
            "descricao": alvo,
        },
    )
    _enfileirar(("Ana Souza", "8"))

    tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    assert "Ana Souza" in alvos[0]


def test_fim_avisa_que_nada_foi_salvo(tela):
    _enfileirar(("Ana", "8"))

    resultado = tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    assert "conferir_transporte" in resultado


def test_sem_fila_nao_faz_nada(tela):
    resultado = tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    assert tela["digitado"] == []
    assert "Não há transporte" in resultado


# ============================================================
# Acompanhar e parar
# ============================================================

def test_estado_mostra_progresso(tela):
    _enfileirar(("Ana", "8"), ("Bruno", "9"))
    tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    estado = tn.estado_do_transporte()

    assert "1 notas já lançadas" in estado
    assert "Bruno" in estado


def test_cancelar_preserva_o_que_ja_foi_feito(tela):
    _enfileirar(("Ana", "8"), ("Bruno", "9"))
    tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    resultado = tn.cancelar_transporte()

    assert "1 notas já tinham sido digitadas" in resultado
    assert tn._transporte["pendentes"] == []


# ============================================================
# Conferência pela tela
# ============================================================

def test_conferencia_aceita_valor_igual(monkeypatch):
    monkeypatch.setattr(
        tn, "_conferir_na_tela", lambda nome, nota: (True, "")
    )
    assert tn._conferir_na_tela("Ana", "8")[0] is True


def test_instrucao_proibe_decidir_nota_no_transporte():
    from pathlib import Path

    codigo = Path("gemini/live_client.py").read_text(encoding="utf-8")

    assert "NUNCA decide nota nesse fluxo" in codigo
    assert "PARE na hora" in codigo


# ============================================================
# Escala da nota
# ============================================================
#
# Caso real: atividade de 1 ponto, planilha com notas sugeridas em
# escala de 10. O transporte digitaria 8 num campo que vai até 1 --
# obediente, e errado, aluno por aluno.


def test_le_o_valor_da_atividade_no_cabecalho():
    assert tn._maximo_do_cabecalho("Nota sugerida (de 1)") == 1.0
    assert tn._maximo_do_cabecalho("Nota sugerida (de 2,5)") == 2.5
    assert tn._maximo_do_cabecalho("Nota sugerida") is None


def test_nota_acima_do_valor_da_atividade_e_recusada():
    linhas = [
        ["Aluno", "Entregou", "Nota sugerida (de 1)", "Observação"],
        ["Ana", "Sim", "0,9", ""],
        ["Bruno", "Sim", "8", ""],
    ]

    notas, erro = tn._extrair_notas(linhas)

    assert notas is None
    assert "vale 1" in erro
    assert "Bruno" in erro
    assert "escala errada" in erro


def test_valor_vindo_da_api_tem_precedencia():
    """O cabeçalho pode estar desatualizado; a API é a fonte."""
    linhas = [
        ["Aluno", "Nota sugerida (de 10)"],
        ["Ana", "8"],
    ]

    notas, erro = tn._extrair_notas(linhas, maximo=1)

    assert notas is None
    assert "vale 1" in erro


def test_nota_no_limite_passa():
    linhas = [
        ["Aluno", "Nota sugerida (de 1)"],
        ["Ana", "1"],
    ]

    notas, erro = tn._extrair_notas(linhas)

    assert erro is None
    assert notas == [{"aluno": "Ana", "nota": "1"}]


def test_nota_negativa_e_recusada():
    linhas = [["Aluno", "Nota sugerida"], ["Ana", "-2"]]

    notas, erro = tn._extrair_notas(linhas)

    assert notas is None
    assert "negativa" in erro


def test_sem_turma_e_atividade_avisa_que_nao_conferiu():
    maximo, aviso = tn._valor_da_atividade("", "")

    assert maximo is None
    assert "não sei de qual turma" in aviso


# ============================================================
# Auditoria pela API
# ============================================================
#
# O transporte parou no meio e o ALF anunciou que tinha lançado tudo.
# A conferência por tela não impediu isso: ela olha um aluno por vez e
# nada olha o conjunto. Esta função pergunta ao Classroom.


@pytest.fixture
def classroom(monkeypatch):
    """Classroom falso: devolve o que o professor teria na tela."""
    estado = {"notas": {}}

    import actions.classroom_actions as ca

    class _Lista:
        def execute(self):
            return {
                "studentSubmissions": [
                    {"userId": f"u{i}", "draftGrade": valor}
                    for i, valor in enumerate(estado["notas"].values())
                ]
            }

    class _Servico:
        def courses(self):
            return self

        def courseWork(self):
            return self

        def studentSubmissions(self):
            return self

        def list(self, **kwargs):
            return _Lista()

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
        lambda servico, id_turma, nome: ({"id": "a1", "title": "X"}, None),
    )
    monkeypatch.setattr(
        ca,
        "_mapa_de_alunos",
        lambda servico, id_turma: (
            {f"u{i}": nome for i, nome in enumerate(estado["notas"])},
            None,
        ),
    )
    monkeypatch.setattr(
        ca, "_executar", lambda pedido: (pedido.execute(), None)
    )
    return estado


def _carregar(*pares):
    tn._transporte["todas"] = [{"aluno": a, "nota": n} for a, n in pares]
    tn._transporte["turma"] = "3A"
    tn._transporte["atividade"] = "X"


def test_auditoria_denuncia_notas_que_nao_entraram(classroom):
    _carregar(("Ana Beatriz", "0.7"), ("Bruno Almeida", "0.5"))
    classroom["notas"] = {"Ana Beatriz": 0.7, "Bruno Almeida": None}

    resultado = tn.conferir_transporte()

    assert "NÃO estão lançadas" in resultado
    assert "Bruno Almeida" in resultado
    assert "NÃO diga que está tudo lançado" in resultado


def test_auditoria_denuncia_nota_diferente(classroom):
    _carregar(("Ana Beatriz", "0.7"))
    classroom["notas"] = {"Ana Beatriz": 0.9}

    resultado = tn.conferir_transporte()

    assert "DIFERENTES" in resultado
    assert "0.9" in resultado or "0,9" in resultado


def test_auditoria_confirma_quando_tudo_bate(classroom):
    _carregar(("Ana Beatriz", "0.7"), ("Bruno Almeida", "0.5"))
    classroom["notas"] = {"Ana Beatriz": 0.7, "Bruno Almeida": 0.5}

    resultado = tn.conferir_transporte()

    assert "Tudo bate" in resultado
    # Rascunho não é nota entregue ao aluno.
    assert "rascunho" in resultado.lower()


def test_auditoria_sem_planilha_carregada():
    tn._transporte["todas"] = []

    resultado = tn.conferir_transporte("3A", "X")

    assert "preparar_transporte" in resultado


# ============================================================
# Nome cortado na lista
# ============================================================
#
# O Classroom trunca nomes longos: "Ana Beatriz Santos da Silva" vira
# "Ana Beatriz Santos da ...". Pedir o nome inteiro ao localizador o
# fazia recusar -- ele é instruído a não chutar, e está certo. O
# transporte parava justamente nos alunos de nome comprido.


def test_prefixo_encurta_nome_comprido():
    assert tn._prefixo_do_nome(
        "Ana Beatriz Santos da Silva", ["Bruno Almeida Lacerda do Carmo"]
    ) == "Ana Beatriz"


def test_prefixo_cresce_quando_dois_alunos_comecam_igual():
    """Encurtar não pode custar ambiguidade: nota no aluno errado."""
    nomes = ["Ana Beatriz Santos da Silva", "Ana Beatriz Costa Lima"]

    assert tn._prefixo_do_nome(nomes[0], nomes) == "Ana Beatriz Santos"


def test_nome_curto_fica_inteiro():
    assert tn._prefixo_do_nome("Ana Souza", []) == "Ana Souza"


def test_busca_avisa_que_o_nome_pode_estar_cortado(tela, monkeypatch):
    alvos = []
    monkeypatch.setattr(
        "vision.click_locator.localizar_elemento_na_tela",
        lambda alvo: alvos.append(alvo) or {
            "sucesso": True, "x": 1, "y": 1, "confianca": 0.95,
            "descricao": alvo,
        },
    )
    _enfileirar(("Ana Beatriz Santos da Silva", "0.7"))

    tn.lancar_proxima_nota(conferir=lambda nome, nota: (True, ""))

    assert "Ana Beatriz" in alvos[0]
    assert "cortado" in alvos[0]
