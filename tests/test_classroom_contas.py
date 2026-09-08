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
