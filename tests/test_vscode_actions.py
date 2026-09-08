"""
Testes das ações executadas dentro do VS Code.

Caso de uso real: o ALF passou a abrir o VS Code, mas ele abria vazio.
Não havia como pedir "abra a pasta X no VS Code" -- o modelo tentava
ctrl+k ctrl+o e depois teria que navegar a caixa de diálogo de arquivos
por reconhecimento visual, que é lento e quase sempre erra.
"""

from pathlib import Path

import pytest

from actions import vscode_actions


CODIGO_CLIENTE = Path("gemini/live_client.py").read_text(encoding="utf-8")


@pytest.fixture
def vscode_falso(monkeypatch, tmp_path):
    """Substitui o executável e captura os argumentos passados."""
    executavel = tmp_path / "Code.exe"
    executavel.write_text("", encoding="utf-8")

    chamadas = []
    monkeypatch.setattr(
        vscode_actions, "localizar_executavel_vscode", lambda: executavel
    )
    monkeypatch.setattr(
        vscode_actions.subprocess,
        "Popen",
        lambda argumentos, **kwargs: chamadas.append((argumentos, kwargs)),
    )
    return chamadas


# ============================================================
# Abrir pasta
# ============================================================

def test_abre_a_pasta_passando_o_caminho_na_linha_de_comando(vscode_falso, tmp_path):
    projeto = tmp_path / "MeuProjeto"
    projeto.mkdir()

    resultado = vscode_actions.abrir_no_vscode(str(projeto))

    argumentos = vscode_falso[0][0]
    assert str(projeto) in argumentos[-1]
    assert "MeuProjeto" in resultado


def test_reaproveita_a_janela_por_padrao(vscode_falso, tmp_path):
    projeto = tmp_path / "Projeto"
    projeto.mkdir()

    vscode_actions.abrir_no_vscode(str(projeto))

    assert "--reuse-window" in vscode_falso[0][0]


def test_nova_janela_quando_pedido(vscode_falso, tmp_path):
    projeto = tmp_path / "Projeto"
    projeto.mkdir()

    vscode_actions.abrir_no_vscode(str(projeto), nova_janela=True)

    assert "--new-window" in vscode_falso[0][0]


def test_abre_arquivo_alem_de_pasta(vscode_falso, tmp_path):
    arquivo = tmp_path / "main.py"
    arquivo.write_text("print()", encoding="utf-8")

    resultado = vscode_actions.abrir_no_vscode(str(arquivo))

    assert str(arquivo) in vscode_falso[0][0][-1]
    assert "arquivo" in resultado


def test_pasta_inexistente_explica_onde_procurou(vscode_falso):
    resultado = vscode_actions.abrir_no_vscode("pasta que nao existe xyz 987")

    assert vscode_falso == []
    assert "Não encontrei" in resultado
    assert "Área de Trabalho" in resultado


def test_sem_vscode_instalado_avisa(monkeypatch):
    monkeypatch.setattr(
        vscode_actions, "localizar_executavel_vscode", lambda: None
    )

    resultado = vscode_actions.abrir_no_vscode("qualquer")

    assert "Não encontrei o VS Code instalado" in resultado


def test_caminho_vazio_pede_esclarecimento():
    assert "Diga qual pasta" in vscode_actions.abrir_no_vscode("")


def test_nao_abre_console_ao_iniciar(vscode_falso, tmp_path):
    """O Code.exe é iniciado sem janela de console."""
    projeto = tmp_path / "Projeto"
    projeto.mkdir()

    vscode_actions.abrir_no_vscode(str(projeto))

    assert vscode_falso[0][1]["creationflags"] == vscode_actions.SEM_JANELA


# ============================================================
# Localizar pasta pelo nome
# ============================================================

def test_localiza_pasta_pelo_nome(monkeypatch, tmp_path):
    raiz = tmp_path / "Desktop"
    (raiz / "MeuApp").mkdir(parents=True)
    monkeypatch.setattr(vscode_actions, "_raizes_de_busca", lambda: [raiz])

    assert vscode_actions.localizar_pasta("meuapp") == (raiz / "MeuApp").resolve()


def test_busca_ignora_acento_e_caixa(monkeypatch, tmp_path):
    raiz = tmp_path / "Desktop"
    (raiz / "Relatórios").mkdir(parents=True)
    monkeypatch.setattr(vscode_actions, "_raizes_de_busca", lambda: [raiz])

    assert vscode_actions.localizar_pasta("RELATORIOS") is not None


def test_busca_pula_pastas_pesadas(monkeypatch, tmp_path):
    """node_modules e venv não podem ser vasculhados nem devolvidos."""
    raiz = tmp_path / "Desktop"
    (raiz / "node_modules" / "alvo").mkdir(parents=True)
    monkeypatch.setattr(vscode_actions, "_raizes_de_busca", lambda: [raiz])

    assert vscode_actions.localizar_pasta("alvo") is None


def test_caminho_absoluto_e_usado_direto(tmp_path):
    projeto = tmp_path / "Projeto"
    projeto.mkdir()

    assert vscode_actions.localizar_pasta(str(projeto)) == projeto.resolve()


# ============================================================
# Paleta de comandos
# ============================================================

@pytest.fixture
def teclado_falso(monkeypatch):
    eventos = []
    monkeypatch.setattr(
        vscode_actions,
        "pressionar_atalho_teclado",
        lambda teclas: eventos.append(("atalho", teclas)) or "ok",
    )
    monkeypatch.setattr(
        vscode_actions,
        "escrever_no_campo_ativo",
        lambda texto: eventos.append(("texto", texto)) or "ok",
    )
    return eventos


def test_paleta_faz_a_sequencia_completa(teclado_falso):
    resultado = vscode_actions.executar_comando_vscode(
        "Toggle Terminal", pausa=lambda _: None
    )

    assert teclado_falso == [
        ("atalho", "ctrl+shift+p"),
        ("texto", "Toggle Terminal"),
        ("atalho", "enter"),
    ]
    assert "Toggle Terminal" in resultado


@pytest.mark.parametrize(
    "comando",
    [
        "Extensions: Uninstall Extension",
        "Delete Folder",
        "Developer: Reload Window",
        "apagar arquivo",
    ],
)
def test_comandos_destrutivos_sao_bloqueados(comando, teclado_falso):
    resultado = vscode_actions.executar_comando_vscode(
        comando, pausa=lambda _: None
    )

    assert "bloqueado por segurança" in resultado
    assert teclado_falso == []


def test_comando_vazio_pede_esclarecimento():
    assert "Diga qual comando" in vscode_actions.executar_comando_vscode("")


# ============================================================
# Registro no modelo
# ============================================================

@pytest.mark.parametrize(
    "ferramenta", ["abrir_no_vscode", "executar_comando_vscode"]
)
def test_ferramenta_registrada(ferramenta):
    assert f'name="{ferramenta}"' in CODIGO_CLIENTE


def test_instrucao_proibe_o_caminho_frageis():
    """ctrl+k ctrl+o mais diálogo visual era o que falhava antes."""
    assert "Nunca use ctrl+k ctrl+o" in CODIGO_CLIENTE
