"""
Testes do questionário com gabarito no Google Forms.

O ponto delicado aqui é o gabarito: se a resposta correta não for
exatamente uma das alternativas, o Google recusa a correção e o
formulário sai sem corrigir nada -- o professor só descobriria depois
que a turma inteira respondesse.
"""

import pytest

from actions import forms_actions as forms


CODIGO_CLIENTE = __import__("pathlib").Path(
    "gemini/live_client.py"
).read_text(encoding="utf-8")


QUESTAO = {
    "pergunta": "O que é uma chave primária?",
    "opcoes": [
        "Um campo que identifica cada linha",
        "Um índice qualquer",
        "Uma senha do banco",
    ],
    "resposta_correta": "Um campo que identifica cada linha",
    "pontos": "2",
}


# ============================================================
# Validação das questões
# ============================================================

def test_questao_valida_passa():
    limpas, erro = forms._validar_questoes([QUESTAO])

    assert erro is None
    assert limpas[0]["correta"] == "Um campo que identifica cada linha"
    assert limpas[0]["pontos"] == 2.0


def test_resposta_fora_das_alternativas_e_recusada():
    """Sem isto o formulário sairia sem gabarito, corrigindo nada."""
    ruim = dict(QUESTAO, resposta_correta="Nenhuma das anteriores")

    limpas, erro = forms._validar_questoes([ruim])

    assert limpas is None
    assert "não é nenhuma das alternativas" in erro


def test_resposta_correta_casa_ignorando_acento_e_caixa():
    questao = {
        "pergunta": "Qual normalização remove dependência parcial?",
        "opcoes": ["Segunda Forma Normal", "Terceira Forma Normal"],
        "resposta_correta": "SEGUNDA FORMA NORMAL",
    }

    limpas, erro = forms._validar_questoes([questao])

    assert erro is None
    # Guarda o texto exato da alternativa, não o que foi ditado.
    assert limpas[0]["correta"] == "Segunda Forma Normal"


def test_questao_sem_enunciado_e_recusada():
    limpas, erro = forms._validar_questoes([dict(QUESTAO, pergunta="  ")])

    assert limpas is None
    assert "sem enunciado" in erro


def test_questao_com_uma_alternativa_so_e_recusada():
    ruim = dict(QUESTAO, opcoes=["Só esta"], resposta_correta="Só esta")

    limpas, erro = forms._validar_questoes([ruim])

    assert limpas is None
    assert "pelo menos duas" in erro


def test_lista_vazia_e_recusada():
    limpas, erro = forms._validar_questoes([])

    assert limpas is None
    assert "Nenhuma questão" in erro


def test_questoes_demais_sao_recusadas():
    limpas, erro = forms._validar_questoes(
        [QUESTAO] * (forms.MAXIMO_QUESTOES + 1)
    )

    assert limpas is None
    assert "acima do limite" in erro


def test_pontos_invalidos_viram_um():
    limpas, _ = forms._validar_questoes([dict(QUESTAO, pontos="muito")])

    assert limpas[0]["pontos"] == 1.0


# ============================================================
# Montagem do formulário
# ============================================================

def test_quiz_e_ligado_antes_das_questoes():
    """
    A ordem importa: sem quizSettings ligado primeiro, a API recusa o
    gabarito e o formulário sai sem correção automática.
    """
    limpas, _ = forms._validar_questoes([QUESTAO])
    pedidos = forms._pedidos_de_criacao(limpas, "")

    assert "updateSettings" in pedidos[0]
    assert pedidos[0]["updateSettings"]["settings"]["quizSettings"]["isQuiz"]

    indices_de_questao = [
        i for i, p in enumerate(pedidos) if "createItem" in p
    ]
    assert min(indices_de_questao) > 0


def test_gabarito_vai_junto_da_questao():
    limpas, _ = forms._validar_questoes([QUESTAO])
    pedidos = forms._pedidos_de_criacao(limpas, "")

    item = [p for p in pedidos if "createItem" in p][0]
    questao = item["createItem"]["item"]["questionItem"]["question"]

    assert questao["grading"]["pointValue"] == 2
    assert questao["grading"]["correctAnswers"]["answers"] == [
        {"value": "Um campo que identifica cada linha"}
    ]
    assert len(questao["choiceQuestion"]["options"]) == 3


def test_descricao_entra_quando_informada():
    limpas, _ = forms._validar_questoes([QUESTAO])

    com = forms._pedidos_de_criacao(limpas, "Leia com atenção.")
    sem = forms._pedidos_de_criacao(limpas, "")

    assert any("updateFormInfo" in p for p in com)
    assert not any("updateFormInfo" in p for p in sem)


# ============================================================
# Criação ponta a ponta, com a API simulada
# ============================================================

class _FormsFalso:
    def __init__(self, falhar_no_batch=False):
        self.criados = []
        self.batches = []
        self._falhar = falhar_no_batch

    def forms(self):
        return self

    def create(self, body=None):
        self.criados.append(body)
        return _Exec(
            {
                "formId": "f1",
                "responderUri": "https://forms.gle/abc",
            }
        )

    def batchUpdate(self, formId=None, body=None):
        if self._falhar:
            return _Exec(None, erro=Exception("500 erro do servidor"))
        self.batches.append((formId, body))
        return _Exec({})


class _Exec:
    def __init__(self, resposta, erro=None):
        self._resposta = resposta
        self._erro = erro

    def execute(self):
        if self._erro:
            raise self._erro
        return self._resposta


@pytest.fixture
def api(monkeypatch):
    def instalar(falhar_no_batch=False):
        falso = _FormsFalso(falhar_no_batch)
        monkeypatch.setattr(
            forms,
            "_servico_forms",
            lambda conta=None: (falso, "professor@escola.com", None),
        )
        return falso

    return instalar


def test_criacao_completa(api):
    falso = api()

    resultado = forms.criar_questionario(
        "Prova de Banco de Dados", [QUESTAO], "Boa prova."
    )

    assert falso.criados[0]["info"]["title"] == "Prova de Banco de Dados"
    assert "2 pontos" in resultado
    assert "1 questões" in resultado
    assert "forms.gle" in resultado
    assert "Ninguém recebeu ainda" in resultado


def test_questao_invalida_nao_cria_nada(api):
    falso = api()

    resultado = forms.criar_questionario(
        "Prova", [dict(QUESTAO, resposta_correta="Outra coisa")]
    )

    assert falso.criados == []
    assert "não é nenhuma das alternativas" in resultado


def test_titulo_vazio_e_recusado(api):
    falso = api()

    assert "título" in forms.criar_questionario("", [QUESTAO])
    assert falso.criados == []


def test_falha_ao_montar_questoes_avisa_do_formulario_vazio(api):
    """O formulário já foi criado: o professor precisa saber."""
    api(falhar_no_batch=True)

    resultado = forms.criar_questionario("Prova", [QUESTAO])

    assert "falhei ao montar as questões" in resultado
    assert "pode apagar" in resultado


def test_sem_conta_autorizada_avisa(monkeypatch):
    monkeypatch.setattr(forms, "servicos", lambda: [])

    resultado = forms.criar_questionario("Prova", [QUESTAO])

    assert "Nenhuma conta" in resultado


# ============================================================
# Escopos e registro
# ============================================================

def test_escopos_do_forms_sao_os_estreitos():
    from actions.classroom_contas import ESCOPOS

    assert "https://www.googleapis.com/auth/forms.body" in ESCOPOS
    # drive.file dá acesso só ao que o app cria; drive puro daria ao
    # Drive inteiro do professor.
    assert "https://www.googleapis.com/auth/drive.file" in ESCOPOS
    assert "https://www.googleapis.com/auth/drive" not in ESCOPOS


@pytest.mark.parametrize(
    "ferramenta",
    [
        "criar_atividade",
        "devolver_atividade",
        "criar_questionario",
        "listar_respostas",
    ],
)
def test_ferramenta_registrada(ferramenta):
    assert f'name="{ferramenta}"' in CODIGO_CLIENTE


def test_instrucao_deixa_claro_que_atividade_nasce_rascunho():
    assert "nasce como RASCUNHO" in CODIGO_CLIENTE
    assert "Nunca invente prazo nem pontuação" in CODIGO_CLIENTE
