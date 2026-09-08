"""
Testes de abertura por apelido e de fechamento de programas.

Casos vindos do uso real:

- "abra o VS Code" falhava em todos os caminhos, porque o menu iniciar
  registra "Visual Studio Code" e a comparação por substring nunca casa
  ("vs code" não está dentro de "visual studio code").

- Não existia função para fechar programa, então o modelo improvisava
  com alt+f4 -- que fecha a janela em foco, não a pedida.
"""

import sys

import pytest

from actions import app_actions


pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="Depende das APIs de janela do Windows.",
)


# ============================================================
# Apelidos na abertura
# ============================================================

def test_vs_code_expande_para_o_nome_registrado():
    candidatos = [
        app_actions.normalizar_texto(c)
        for c in app_actions.nomes_candidatos("VS Code")
    ]

    assert "visual studio code" in candidatos


@pytest.mark.parametrize("falado", ["VS Code", "vscode", "vs code", "visual code"])
def test_apelidos_do_vs_code(falado):
    candidatos = [
        app_actions.normalizar_texto(c)
        for c in app_actions.nomes_candidatos(falado)
    ]

    assert "visual studio code" in candidatos


def test_nome_falado_vem_antes_dos_sinonimos():
    """Um programa que realmente se chame assim não pode ser sequestrado."""
    candidatos = app_actions.nomes_candidatos("VS Code")

    assert candidatos[0] == "VS Code"


def test_nome_sem_sinonimo_fica_intacto():
    assert app_actions.nomes_candidatos("Blender") == ["Blender"]


def test_abertura_tenta_todos_os_candidatos(monkeypatch):
    tentados = []

    def app_windows_falso(nome):
        tentados.append(nome)
        return "Visual Studio Code" if "visual studio" in nome.lower() else None

    monkeypatch.setattr(app_actions, "abrir_app_windows", app_windows_falso)
    monkeypatch.setattr(app_actions, "procurar_atalho_menu_iniciar", lambda nome: None)
    monkeypatch.setattr(app_actions, "abrir_executavel_conhecido", lambda nome: False)

    resultado = app_actions.abrir_aplicativo("VS Code")

    assert "Visual Studio Code" in resultado
    assert tentados[0] == "VS Code"


# ============================================================
# Fechamento
# ============================================================

def _janelas(*itens):
    return lambda: list(itens)


def test_fecha_a_janela_certa_pelo_titulo(monkeypatch):
    monkeypatch.setattr(
        app_actions,
        "_janelas_visiveis",
        _janelas(
            (111, "Documento.txt - Bloco de Notas", "notepad"),
            (222, "Planilha - Excel", "excel"),
        ),
    )

    enviados = []
    monkeypatch.setattr(app_actions, "_pedir_fechamento", enviados.append)

    resultado = app_actions.fechar_aplicativo("bloco de notas")

    assert enviados == [111]
    assert "Bloco de Notas" in resultado


def test_fechar_usa_wm_close_e_nunca_mata_o_processo(monkeypatch):
    """
    WM_CLOSE é o equivalente a clicar no X: o programa ainda pergunta se
    há algo não salvo. Matar o processo perderia trabalho.
    """
    monkeypatch.setattr(
        app_actions,
        "_janelas_visiveis",
        _janelas((333, "Sem título - Bloco de Notas", "notepad")),
    )

    fechadas = []
    monkeypatch.setattr(app_actions, "_pedir_fechamento", fechadas.append)

    matou = []
    monkeypatch.setattr(
        app_actions.subprocess,
        "run",
        lambda *a, **k: matou.append(a),
    )

    app_actions.fechar_aplicativo("notepad")

    # Fecha pela janela, e nunca por taskkill ou equivalente.
    assert fechadas == [333]
    assert matou == []
    assert app_actions.WM_CLOSE == 0x0010


@pytest.mark.parametrize("protegido", ["explorer", "dwm", "python", "pythonw", "alf"])
def test_componentes_do_windows_e_o_proprio_alf_sao_protegidos(protegido, monkeypatch):
    monkeypatch.setattr(
        app_actions,
        "_janelas_visiveis",
        _janelas((444, "qualquer", protegido)),
    )

    resultado = app_actions.fechar_aplicativo(protegido)

    assert "Não posso fechar" in resultado


def test_processo_protegido_nao_e_fechado_nem_por_titulo(monkeypatch):
    """Uma janela do explorer não pode ser fechada por casar no título."""
    monkeypatch.setattr(
        app_actions,
        "_janelas_visiveis",
        _janelas((555, "Downloads – Explorador de Arquivos", "explorer")),
    )

    enviados = []
    monkeypatch.setattr(app_actions, "_pedir_fechamento", enviados.append)

    resultado = app_actions.fechar_aplicativo("downloads")

    assert enviados == []
    assert "Não encontrei" in resultado


def test_programa_fechado_avisa_em_vez_de_falhar(monkeypatch):
    monkeypatch.setattr(app_actions, "_janelas_visiveis", _janelas())

    resultado = app_actions.fechar_aplicativo("chrome")

    assert "Não encontrei" in resultado
    assert "está mesmo aberto" in resultado


def test_nome_vazio_pede_esclarecimento():
    assert "Diga qual programa" in app_actions.fechar_aplicativo("")


def test_fechar_entende_apelido(monkeypatch):
    monkeypatch.setattr(
        app_actions,
        "_janelas_visiveis",
        _janelas((666, "main.py - Visual Studio Code", "Code")),
    )

    enviados = []
    monkeypatch.setattr(app_actions, "_pedir_fechamento", enviados.append)

    resultado = app_actions.fechar_aplicativo("VS Code")

    assert enviados == [666]
    assert "Visual Studio Code" in resultado
