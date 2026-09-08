"""
Testes das contas autorizadas do Classroom.

O caso que motivou o teste principal: ao adicionar os escopos do Forms,
a conta do Gmail teve a autorização negada, mas o ALF continuou
listando-a como válida. O erro de permissão só apareceria na hora de
criar o questionário -- no meio do trabalho do professor.
"""

import json

import pytest

from actions import classroom_contas as contas


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    monkeypatch.setattr(contas, "PASTA", tmp_path)
    monkeypatch.setattr(
        contas, "ARQUIVO_CREDENCIAIS", tmp_path / "credenciais.json"
    )
    monkeypatch.setattr(contas, "TOKEN_ANTIGO", tmp_path / "token_antigo.json")
    contas.limpar_cache()
    return tmp_path


def _gravar_token(pasta, apelido, escopos):
    caminho = pasta / f"{contas.PREFIXO_TOKEN}{apelido}.json"
    caminho.write_text(
        json.dumps(
            {
                "token": "x",
                "refresh_token": "y",
                "client_id": "c",
                "client_secret": "s",
                "scopes": escopos,
            }
        ),
        encoding="utf-8",
    )
    return caminho


# ============================================================
# Escopos concedidos versus escopos pedidos
# ============================================================

def test_token_sem_todos_os_escopos_e_recusado(pasta):
    """
    A checagem tem que olhar os escopos CONCEDIDOS, guardados no
    arquivo. from_authorized_user_file(caminho, ESCOPOS) preenche
    credenciais.scopes com os escopos PEDIDOS, então comparar contra
    esse campo fazia a verificação passar sempre.
    """
    caminho = _gravar_token(pasta, "antigo", contas.ESCOPOS[:3])

    assert contas._carregar_credenciais(caminho) is None


def test_token_completo_passa_da_checagem_de_escopo(pasta, monkeypatch):
    caminho = _gravar_token(pasta, "completo", list(contas.ESCOPOS))

    # Isola a validação de credencial do Google: o que este teste
    # verifica é a comparação de escopos, não o refresh de token.
    class CredencialFalsa:
        expired = False
        valid = True
        scopes = list(contas.ESCOPOS)

    monkeypatch.setattr(
        "google.oauth2.credentials.Credentials.from_authorized_user_file",
        classmethod(lambda cls, caminho, escopos: CredencialFalsa()),
    )

    assert contas._carregar_credenciais(caminho) is not None


def test_token_com_escopos_extras_continua_valido(pasta, monkeypatch):
    """O Google devolve 'openid' e afins a mais; isso não invalida."""
    caminho = _gravar_token(
        pasta, "extras", list(contas.ESCOPOS) + ["https://exemplo/extra"]
    )

    class CredencialFalsa:
        expired = False
        valid = True
        scopes = list(contas.ESCOPOS)

    monkeypatch.setattr(
        "google.oauth2.credentials.Credentials.from_authorized_user_file",
        classmethod(lambda cls, caminho, escopos: CredencialFalsa()),
    )

    assert contas._carregar_credenciais(caminho) is not None


def test_arquivo_corrompido_e_recusado(pasta):
    caminho = pasta / f"{contas.PREFIXO_TOKEN}quebrado.json"
    caminho.write_text("isto nao e json", encoding="utf-8")

    assert contas._carregar_credenciais(caminho) is None


# ============================================================
# Um arquivo por conta
# ============================================================

def test_apelido_gera_nome_de_arquivo_seguro():
    caminho = contas.caminho_token("aislan.souza@ba.docente.senai.br")

    assert caminho.name.startswith(contas.PREFIXO_TOKEN)
    assert "@" not in caminho.name
    assert "." not in caminho.stem


def test_contas_diferentes_nao_se_sobrescrevem():
    um = contas.caminho_token("professor@gmail.com")
    outro = contas.caminho_token("professor@escola.edu.br")

    assert um != outro


def test_sem_token_nenhum_a_lista_vem_vazia(pasta):
    assert contas.contas_autorizadas() == []
    assert contas.servicos() == []


def test_remover_conta_apaga_o_token(pasta):
    _gravar_token(pasta, "professor_gmail_com", list(contas.ESCOPOS))

    resultado = contas.remover_conta("professor@gmail.com")

    assert "Removi" in resultado
    assert not (
        pasta / f"{contas.PREFIXO_TOKEN}professor_gmail_com.json"
    ).exists()


def test_remover_conta_que_nao_existe_avisa(pasta):
    assert "Não tenho" in contas.remover_conta("ninguem@lugar.com")


# ============================================================
# Configuração ausente
# ============================================================

def test_autorizar_sem_credenciais_explica(pasta):
    assert "classroom_credenciais.json" in contas.autorizar_conta()


# ============================================================
# Escopo por recurso, nao tudo-ou-nada
# ============================================================
#
# Caso real: bastou acrescentar o escopo da agenda para as duas contas
# serem dadas como nao autorizadas, e o lancamento de notas -- que nada
# tem a ver com agenda -- parou no meio do trabalho do professor.

def test_falta_de_escopo_opcional_nao_derruba_a_conta(pasta, monkeypatch):
    _gravar_token(pasta, "professor_escola_com", list(contas.ESCOPOS_ESSENCIAIS))

    class CredencialFalsa:
        expired = False
        valid = True
        scopes = list(contas.ESCOPOS_ESSENCIAIS)

    monkeypatch.setattr(
        "google.oauth2.credentials.Credentials.from_authorized_user_file",
        classmethod(lambda cls, caminho, escopos: CredencialFalsa()),
    )

    caminho = pasta / f"{contas.PREFIXO_TOKEN}professor_escola_com.json"
    assert contas._carregar_credenciais(caminho) is not None


def test_falta_de_escopo_essencial_derruba_a_conta(pasta):
    _gravar_token(pasta, "incompleto", contas.ESCOPOS_ESSENCIAIS[:2])

    caminho = pasta / f"{contas.PREFIXO_TOKEN}incompleto.json"
    assert contas._carregar_credenciais(caminho) is None


def test_recurso_sem_permissao_diz_o_que_falta(pasta):
    _gravar_token(pasta, "professor_escola_com", list(contas.ESCOPOS_ESSENCIAIS))

    aviso = contas.falta_para_recurso("professor@escola.com", "agenda")

    assert aviso is not None
    assert "Google Calendar" in aviso
    assert "NÃO faça isso no meio de outra tarefa" in aviso


def test_recurso_com_permissao_nao_reclama(pasta):
    escopos = list(contas.ESCOPOS_ESSENCIAIS) + list(
        contas.ESCOPOS_POR_RECURSO["agenda"]
    )
    _gravar_token(pasta, "professor_escola_com", escopos)

    assert contas.falta_para_recurso("professor@escola.com", "agenda") is None


def test_agenda_nao_derruba_o_classroom(pasta):
    """As duas coisas sao independentes e precisam continuar sendo."""
    _gravar_token(pasta, "professor_escola_com", list(contas.ESCOPOS_ESSENCIAIS))

    assert contas.falta_para_recurso("professor@escola.com", "agenda")
    # O essencial do Classroom continua satisfeito.
    caminho = pasta / f"{contas.PREFIXO_TOKEN}professor_escola_com.json"
    guardado = json.loads(caminho.read_text(encoding="utf-8"))
    assert set(contas.ESCOPOS_ESSENCIAIS).issubset(set(guardado["scopes"]))


# ============================================================
# A renovacao nao pode inventar permissoes
# ============================================================

def test_renovacao_preserva_os_escopos_concedidos(pasta):
    """
    credenciais.to_json() escreve os escopos PEDIDOS. Ao renovar, isso
    reescrevia o arquivo afirmando permissoes que o Google nunca deu --
    e a verificacao criada para nao mentir passava a mentir.
    """
    concedidos = list(contas.ESCOPOS_ESSENCIAIS)
    caminho = pasta / f"{contas.PREFIXO_TOKEN}renovado.json"

    class CredencialFalsa:
        # Como o objeto fica depois de from_authorized_user_file: com a
        # lista PEDIDA, que inclui escopos nunca concedidos.
        def to_json(self):
            return json.dumps(
                {"token": "novo", "scopes": list(contas.ESCOPOS)}
            )

    contas._gravar_token(caminho, CredencialFalsa(), concedidos)

    guardado = json.loads(caminho.read_text(encoding="utf-8"))

    assert set(guardado["scopes"]) == set(concedidos)
    assert "https://www.googleapis.com/auth/calendar.events" not in guardado["scopes"]


def test_autorizacao_parcial_e_avisada(pasta, monkeypatch):
    """O usuario pode desmarcar permissoes na tela de consentimento."""
    monkeypatch.setattr(
        contas, "ARQUIVO_CREDENCIAIS", pasta / "credenciais.json"
    )
    (pasta / "credenciais.json").write_text("{}", encoding="utf-8")

    class FluxoFalso:
        @staticmethod
        def from_client_secrets_file(caminho, escopos):
            return FluxoFalso()

        def run_local_server(self, **kwargs):
            class Cred:
                scopes = list(contas.ESCOPOS_ESSENCIAIS)

                def to_json(self):
                    return json.dumps({"token": "x", "scopes": self.scopes})

            return Cred()

    import sys
    import types as _t

    modulo = _t.ModuleType("google_auth_oauthlib.flow")
    modulo.InstalledAppFlow = FluxoFalso
    monkeypatch.setitem(sys.modules, "google_auth_oauthlib.flow", modulo)
    monkeypatch.setattr(contas, "_descobrir_email", lambda c: "prof@escola.com")

    resultado = contas.autorizar_conta()

    assert "sem estas permissões" in resultado
    assert "calendar.events" in resultado
