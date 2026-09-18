"""
Aviso de memória curta.

Em 18/09/2026 o ALF travava, picotava o áudio e atrasava a tela. O log
não tinha uma única queda de conexão: a máquina estava com 94% da
memória em uso, quase 14 GB deles em janelas de navegador. O ALF usava
206 MB e levou a culpa.

Ele engasgava calado. Agora avisa.
"""

import core.memoria as memoria
import gemini.live_client as live_client
from gemini.live_client import GeminiLiveWorker


def test_le_a_memoria_da_maquina():
    livre, total = memoria.estado_da_memoria()

    assert isinstance(livre, int) and isinstance(total, int)
    assert 0 < livre <= total


def test_memoria_curta_vira_aviso(monkeypatch):
    monkeypatch.setattr(memoria, "estado_da_memoria", lambda: (900, 20314))

    apertada, mensagem = memoria.memoria_apertada()

    assert apertada
    assert "900 MB livres de 20314 MB" in mensagem
    # Precisa dizer o que fazer e que não é a conexão.
    assert "Feche" in mensagem
    assert "não é a conexão" in mensagem


def test_memoria_folgada_nao_avisa(monkeypatch):
    monkeypatch.setattr(memoria, "estado_da_memoria", lambda: (8000, 20314))

    assert memoria.memoria_apertada() == (False, "")


def test_sem_saber_a_memoria_nao_inventa_alarme(monkeypatch):
    """Um palpite errado viraria alarme falso a cada conexão."""
    monkeypatch.setattr(memoria, "estado_da_memoria", lambda: (None, None))

    assert memoria.memoria_apertada() == (False, "")


def test_aviso_sai_uma_vez_so(monkeypatch):
    """Avisar a cada renovação, de nove em nove minutos, seria barulho."""
    monkeypatch.setattr(live_client, "memoria_apertada", lambda: (True, "pouca memoria"))

    worker = GeminiLiveWorker()
    ditos = []
    worker.status_recebido.connect(ditos.append)

    worker.avisar_se_memoria_apertada()
    worker.avisar_se_memoria_apertada()

    assert ditos == ["pouca memoria"]


def test_avisa_de_novo_depois_de_melhorar(monkeypatch):
    estado = {"apertada": True}
    monkeypatch.setattr(
        live_client,
        "memoria_apertada",
        lambda: (estado["apertada"], "pouca memoria"),
    )

    worker = GeminiLiveWorker()
    ditos = []
    worker.status_recebido.connect(ditos.append)

    worker.avisar_se_memoria_apertada()
    estado["apertada"] = False
    worker.avisar_se_memoria_apertada()
    estado["apertada"] = True
    worker.avisar_se_memoria_apertada()

    assert ditos == ["pouca memoria", "pouca memoria"]
