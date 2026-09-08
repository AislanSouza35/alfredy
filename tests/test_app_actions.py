"""
Testes de actions/app_actions.py.

Dois problemas relatados em uso real:

1. "abra o youtube" terminava em "Não encontrei um recurso do Windows
   com esse nome" -- nenhum caminho da função tratava sites.

2. Ao pedir para abrir qualquer coisa, piscava uma janela preta de
   console por alguns segundos. Rodando por pythonw.exe o ALF não tem
   console, então o Windows criava um só para a consulta do PowerShell.
"""

import subprocess
import sys

import pytest

from actions import app_actions


@pytest.fixture
def urls_abertas(monkeypatch):
    abertas = []
    monkeypatch.setattr(app_actions, "abrir_url", abertas.append)
    return abertas


@pytest.fixture
def sem_apps_instalados(monkeypatch):
    """Simula um computador sem app, atalho ou executável com o nome."""
    monkeypatch.setattr(app_actions, "abrir_app_windows", lambda nome: None)
    monkeypatch.setattr(app_actions, "procurar_atalho_menu_iniciar", lambda nome: None)
    monkeypatch.setattr(app_actions, "abrir_executavel_conhecido", lambda nome: False)


# ============================================================
# Sites
# ============================================================

def test_abrir_youtube_abre_o_site(sem_apps_instalados, urls_abertas):
    resultado = app_actions.abrir_aplicativo("youtube")

    assert urls_abertas == ["https://www.youtube.com"]
    assert "Abrindo" in resultado


def test_abrir_youtube_dentro_de_uma_frase(sem_apps_instalados, urls_abertas):
    app_actions.abrir_aplicativo("o site do YouTube")

    assert urls_abertas == ["https://www.youtube.com"]


def test_nome_exato_tem_prioridade_sobre_nome_parcial(sem_apps_instalados, urls_abertas):
    """'meet' não pode ser confundido com 'google meet' e vice-versa."""
    app_actions.abrir_aplicativo("meet")

    assert urls_abertas == ["https://meet.google.com"]


def test_endereco_de_internet_e_aberto(sem_apps_instalados, urls_abertas):
    app_actions.abrir_aplicativo("tabnews.com.br")

    assert urls_abertas == ["https://tabnews.com.br"]


def test_nome_desconhecido_explica_o_que_fazer(sem_apps_instalados, urls_abertas):
    resultado = app_actions.abrir_aplicativo("programa que nao existe")

    assert urls_abertas == []
    assert "Não encontrei" in resultado
    assert "pesquisa no navegador" in resultado


def test_recursos_do_windows_continuam_funcionando(sem_apps_instalados, monkeypatch):
    comandos = []
    monkeypatch.setattr(
        app_actions,
        "executar_comando",
        lambda comando, **kwargs: comandos.append((comando, kwargs)),
    )

    resultado = app_actions.abrir_aplicativo("calculadora")

    assert comandos[0][0] == ["calc.exe"]
    assert "Calculadora" in resultado


# ============================================================
# Console oculto
# ============================================================

@pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="CREATE_NO_WINDOW só existe no Windows.",
)
def test_programa_grafico_nao_abre_console(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        app_actions.subprocess,
        "Popen",
        lambda comando, **kwargs: chamadas.append(kwargs),
    )

    app_actions.executar_comando(["notepad.exe"])

    assert chamadas[0]["creationflags"] == subprocess.CREATE_NO_WINDOW


@pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="CREATE_NO_WINDOW só existe no Windows.",
)
def test_prompt_de_comando_ainda_mostra_a_janela(monkeypatch):
    """No cmd e no PowerShell a janela é o próprio programa pedido."""
    chamadas = []
    monkeypatch.setattr(
        app_actions.subprocess,
        "Popen",
        lambda comando, **kwargs: chamadas.append(kwargs),
    )

    app_actions.executar_comando(["cmd.exe"], ocultar_console=False)

    assert "creationflags" not in chamadas[0]


@pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="CREATE_NO_WINDOW só existe no Windows.",
)
def test_consulta_de_apps_nao_abre_console(monkeypatch):
    capturado = {}

    class RespostaFalsa:
        returncode = 0
        stdout = "[]"

    def run_falso(comando, **kwargs):
        capturado.update(kwargs)
        return RespostaFalsa()

    monkeypatch.setattr(app_actions.subprocess, "run", run_falso)
    app_actions.listar_aplicativos_windows(usar_cache=False)

    assert capturado["creationflags"] == subprocess.CREATE_NO_WINDOW


# ============================================================
# Cache
# ============================================================

def test_lista_de_apps_fica_em_cache(monkeypatch):
    """A consulta custa segundos; repeti-la a cada pedido é desperdício."""
    chamadas = []

    class RespostaFalsa:
        returncode = 0
        stdout = '{"Name": "Bloco de Notas", "AppID": "notepad"}'

    def run_falso(comando, **kwargs):
        chamadas.append(comando)
        return RespostaFalsa()

    monkeypatch.setattr(app_actions.subprocess, "run", run_falso)
    monkeypatch.setattr(
        app_actions,
        "_CACHE_APPS",
        {"valor": None, "momento": 0.0},
    )

    primeira = app_actions.listar_aplicativos_windows()
    segunda = app_actions.listar_aplicativos_windows()

    assert primeira == segunda
    assert len(chamadas) == 1
