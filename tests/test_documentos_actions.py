"""
Testes de criar apresentação, documento e planilha.

Nenhum escopo novo foi preciso: as três APIs aceitam o drive.file, que
o Forms já trouxe. Isso importa e está travado num teste: drive.file
alcança apenas os arquivos criados por este app.

Nenhum teste toca a API real.
"""

from pathlib import Path

import pytest

from actions import documentos_actions as doc


CODIGO_CLIENTE = Path("gemini/live_client.py").read_text(encoding="utf-8")


class _Exec:
    def __init__(self, resposta, erro=None):
        self._resposta = resposta
        self._erro = erro

    def execute(self):
        if self._erro:
            raise self._erro
        return self._resposta


class _ApiFalsa:
    """Serve para Slides, Docs e Sheets: o encadeamento é parecido."""

    def __init__(self, criar, falhar_no_batch=False):
        self._criar = criar
        self._falhar = falhar_no_batch
        self.criados = []
        self.batches = []
        self.valores = []

    # Slides
    def presentations(self):
        return self

    # Docs
    def documents(self):
        return self

    # Sheets
    def spreadsheets(self):
        return self

    def values(self):
        return _Valores(self)

    def create(self, body=None):
        self.criados.append(body)
        return _Exec(self._criar)

    def batchUpdate(self, body=None, **kwargs):
        if self._falhar:
            return _Exec(None, erro=Exception("500 erro do servidor"))
        self.batches.append(body)
        return _Exec({})


class _Valores:
    def __init__(self, api):
        self._api = api

    def update(self, **kwargs):
        self._api.valores.append(kwargs)
        return _Exec({})


@pytest.fixture
def api(monkeypatch):
    def instalar(criar, falhar_no_batch=False):
        falsa = _ApiFalsa(criar, falhar_no_batch)
        monkeypatch.setattr(
            doc,
            "_servico",
            lambda nome, versao, conta="": (
                falsa,
                "professor@escola.com",
                None,
            ),
        )
        return falsa

    return instalar


# ============================================================
# Apresentação
# ============================================================

RESPOSTA_SLIDES = {
    "presentationId": "p1",
    "slides": [{"objectId": "slide_em_branco"}],
}


def test_apresentacao_cria_um_slide_por_item(api):
    falsa = api(RESPOSTA_SLIDES)

    resultado = doc.criar_apresentacao(
        "Modelo Relacional",
        [
            {"titulo": "O que é", "topicos": ["Tabelas", "Relações"]},
            {"titulo": "Chaves", "topicos": ["Primária", "Estrangeira"]},
        ],
    )

    pedidos = falsa.batches[0]["requests"]
    criacoes = [p for p in pedidos if "createSlide" in p]

    assert len(criacoes) == 2
    assert "2 slides" in resultado


def test_slide_em_branco_inicial_e_removido_por_ultimo(api):
    """
    Apagar antes deixaria a apresentação sem nenhum slide por um
    instante, o que a API recusa.
    """
    falsa = api(RESPOSTA_SLIDES)

    doc.criar_apresentacao("Aula", [{"titulo": "Introdução"}])

    pedidos = falsa.batches[0]["requests"]

    assert pedidos[-1] == {
        "deleteObject": {"objectId": "slide_em_branco"}
    }


def test_slide_sem_topicos_usa_layout_so_de_titulo(api):
    falsa = api(RESPOSTA_SLIDES)

    doc.criar_apresentacao("Aula", [{"titulo": "Capa"}])

    criacao = [p for p in falsa.batches[0]["requests"] if "createSlide" in p][0]
    layout = criacao["createSlide"]["slideLayoutReference"]["predefinedLayout"]

    assert layout == "TITLE_ONLY"


def test_titulo_e_topicos_viram_texto(api):
    falsa = api(RESPOSTA_SLIDES)

    doc.criar_apresentacao(
        "Aula", [{"titulo": "Chaves", "topicos": ["Primária", "Estrangeira"]}]
    )

    textos = [
        p["insertText"]["text"]
        for p in falsa.batches[0]["requests"]
        if "insertText" in p
    ]

    assert "Chaves" in textos
    assert "Primária\nEstrangeira" in textos


def test_apresentacao_aceita_lista_de_titulos_simples(api):
    api(RESPOSTA_SLIDES)

    resultado = doc.criar_apresentacao("Aula", ["Introdução", "Conclusão"])

    assert "2 slides" in resultado


def test_slide_sem_titulo_e_recusado(api):
    falsa = api(RESPOSTA_SLIDES)

    resultado = doc.criar_apresentacao("Aula", [{"topicos": ["algo"]}])

    assert "sem título" in resultado
    assert falsa.criados == []


def test_slides_demais_sao_recusados(api):
    api(RESPOSTA_SLIDES)

    resultado = doc.criar_apresentacao(
        "Aula", [{"titulo": f"S{i}"} for i in range(doc.MAXIMO_SLIDES + 1)]
    )

    assert "acima do limite" in resultado


def test_apresentacao_avisa_que_e_base_para_ajustar(api):
    api(RESPOSTA_SLIDES)

    resultado = doc.criar_apresentacao("Aula", [{"titulo": "Capa"}])

    assert "base para você ajustar" in resultado


def test_falha_no_batch_avisa_que_o_arquivo_ficou_vazio(api):
    api(RESPOSTA_SLIDES, falhar_no_batch=True)

    resultado = doc.criar_apresentacao("Aula", [{"titulo": "Capa"}])

    assert "falhei ao montar os slides" in resultado


# ============================================================
# Documento
# ============================================================

RESPOSTA_DOCS = {"documentId": "d1"}


def test_documento_insere_todo_o_texto_de_uma_vez(api):
    """
    Cada inserção desloca os índices das seguintes. Inserir tudo junto
    e só depois aplicar estilos evita esse remendo.
    """
    falsa = api(RESPOSTA_DOCS)

    doc.criar_documento(
        "Lista",
        [
            {"tipo": "titulo", "texto": "Exercícios"},
            {"tipo": "texto", "texto": "Resolva as questões."},
        ],
    )

    pedidos = falsa.batches[0]["requests"]
    insercoes = [p for p in pedidos if "insertText" in p]

    assert len(insercoes) == 1
    assert insercoes[0]["insertText"]["text"] == (
        "Exercícios\nResolva as questões.\n"
    )


def test_faixas_de_estilo_batem_com_o_texto(api):
    falsa = api(RESPOSTA_DOCS)

    doc.criar_documento(
        "Lista",
        [
            {"tipo": "titulo", "texto": "Um"},
            {"tipo": "texto", "texto": "Dois"},
        ],
    )

    estilos = [
        p["updateParagraphStyle"]
        for p in falsa.batches[0]["requests"]
        if "updateParagraphStyle" in p
    ]

    # "Um\n" ocupa os índices 1 a 4; "Dois\n" começa em 4.
    assert estilos[0]["range"] == {"startIndex": 1, "endIndex": 4}
    assert estilos[0]["paragraphStyle"]["namedStyleType"] == "HEADING_1"
    assert estilos[1]["range"]["startIndex"] == 4


def test_lista_ganha_marcador(api):
    falsa = api(RESPOSTA_DOCS)

    doc.criar_documento("Lista", [{"tipo": "lista", "texto": "Primeiro item"}])

    texto = falsa.batches[0]["requests"][0]["insertText"]["text"]

    assert texto.startswith("• Primeiro item")


def test_tipo_desconhecido_vira_texto_normal(api):
    falsa = api(RESPOSTA_DOCS)

    doc.criar_documento("Doc", [{"tipo": "inventado", "texto": "Algo"}])

    estilo = [
        p for p in falsa.batches[0]["requests"] if "updateParagraphStyle" in p
    ][0]

    assert estilo["updateParagraphStyle"]["paragraphStyle"][
        "namedStyleType"
    ] == "NORMAL_TEXT"


def test_documento_aceita_texto_simples(api):
    api(RESPOSTA_DOCS)

    assert "1 parágrafos" in doc.criar_documento("Doc", "Um texto qualquer.")


def test_documento_sem_conteudo_e_recusado(api):
    falsa = api(RESPOSTA_DOCS)

    resultado = doc.criar_documento("Doc", [])

    assert "sem conteúdo" in resultado
    assert falsa.criados == []


# ============================================================
# Planilha
# ============================================================

RESPOSTA_SHEETS = {
    "spreadsheetId": "s1",
    "sheets": [{"properties": {"sheetId": 0, "title": "Notas"}}],
}


def test_planilha_preenche_os_dados(api):
    falsa = api(RESPOSTA_SHEETS)

    doc.criar_planilha(
        "Notas", [["Aluno", "Nota"], ["Ana", "8"]], nome_aba="Notas"
    )

    assert falsa.valores[0]["body"]["values"] == [
        ["Aluno", "Nota"],
        ["Ana", "8"],
    ]


def test_cabecalho_fica_em_negrito_e_congelado(api):
    falsa = api(RESPOSTA_SHEETS)

    doc.criar_planilha("Notas", [["Aluno"], ["Ana"]])

    pedidos = falsa.batches[0]["requests"]
    tipos = [list(p.keys())[0] for p in pedidos]

    assert "repeatCell" in tipos
    assert "updateSheetProperties" in tipos

    congelar = [p for p in pedidos if "updateSheetProperties" in p][0]
    assert congelar["updateSheetProperties"]["properties"][
        "gridProperties"
    ]["frozenRowCount"] == 1


def test_celulas_viram_texto(api):
    falsa = api(RESPOSTA_SHEETS)

    doc.criar_planilha("Notas", [["Aluno", "Nota"], ["Ana", 8]])

    assert falsa.valores[0]["body"]["values"][1] == ["Ana", "8"]


def test_planilha_sem_dados_e_recusada(api):
    falsa = api(RESPOSTA_SHEETS)

    assert "sem dados" in doc.criar_planilha("Notas", [])
    assert falsa.criados == []


def test_linhas_demais_sao_recusadas(api):
    api(RESPOSTA_SHEETS)

    resultado = doc.criar_planilha(
        "Notas", [["x"]] * (doc.MAXIMO_LINHAS + 1)
    )

    assert "acima do limite" in resultado


# ============================================================
# Planilha de notas com os alunos da turma
# ============================================================

def test_planilha_de_notas_traz_os_alunos(api, monkeypatch):
    """
    Digitar trinta nomes à mão é o trabalho que faz o professor não
    usar planilha nenhuma.
    """
    falsa = api(RESPOSTA_SHEETS)

    monkeypatch.setattr(
        "actions.classroom_actions._encontrar_turma",
        lambda nome: (
            ("prof@escola.com", None, None, {"id": "t1", "name": "3A"}, ""),
            None,
        ),
    )
    monkeypatch.setattr(
        "actions.classroom_actions._mapa_de_alunos",
        lambda servico, id_turma: (
            {"u1": "Bruno Lima", "u2": "Ana Souza"},
            None,
        ),
    )

    resultado = doc.criar_planilha_de_notas("3A", "Prova 1, Trabalho")

    linhas = falsa.valores[0]["body"]["values"]

    assert linhas[0] == ["Aluno", "Prova 1", "Trabalho"]
    # Em ordem alfabética, para conferir contra a chamada.
    assert linhas[1][0] == "Ana Souza"
    assert linhas[2][0] == "Bruno Lima"
    assert "3 linhas" in resultado


def test_planilha_de_notas_sem_colunas_usa_padrao(api, monkeypatch):
    falsa = api(RESPOSTA_SHEETS)

    monkeypatch.setattr(
        "actions.classroom_actions._encontrar_turma",
        lambda nome: (
            ("prof@escola.com", None, None, {"id": "t1", "name": "3A"}, ""),
            None,
        ),
    )
    monkeypatch.setattr(
        "actions.classroom_actions._mapa_de_alunos",
        lambda servico, id_turma: ({"u1": "Ana"}, None),
    )

    doc.criar_planilha_de_notas("3A")

    assert falsa.valores[0]["body"]["values"][0] == [
        "Aluno",
        "Nota 1",
        "Nota 2",
        "Nota 3",
        "Média",
    ]


# ============================================================
# Escopos e registro
# ============================================================

def test_nenhum_escopo_novo_foi_preciso():
    """
    As três APIs aceitam drive.file, que o Forms já trouxe. Se um dia
    alguém acrescentar 'presentations', 'documents' ou 'spreadsheets'
    aqui, será escopo mais amplo que o necessário.
    """
    from actions.classroom_contas import ESCOPOS

    assert "https://www.googleapis.com/auth/drive.file" in ESCOPOS

    for amplo in (
        "https://www.googleapis.com/auth/presentations",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ):
        assert amplo not in ESCOPOS


@pytest.mark.parametrize(
    "ferramenta",
    [
        "criar_apresentacao",
        "criar_documento",
        "criar_planilha",
        "criar_planilha_de_notas",
    ],
)
def test_ferramenta_registrada(ferramenta):
    assert f'name="{ferramenta}"' in CODIGO_CLIENTE


def test_instrucao_avisa_que_material_e_base_nao_final():
    assert "base para o professor ajustar" in CODIGO_CLIENTE
    assert "Nunca leia o conteúdo inteiro em voz alta" in CODIGO_CLIENTE
