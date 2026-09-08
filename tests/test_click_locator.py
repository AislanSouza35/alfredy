"""Testes unitários/integração para vision/click_locator.py.

Não faz chamadas de rede reais: mss e o cliente Gemini são mockados.
A captura de tela é substituída por uma imagem sintética gerada com PIL.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from vision import click_locator


def _imagem_falsa(largura=400, altura=300):
    return Image.new("RGB", (largura, altura), color=(10, 20, 30))


@pytest.fixture
def mock_mss(monkeypatch):
    """Substitui mss.mss() por uma captura de tela sintética 400x300."""
    largura, altura = 400, 300
    imagem = _imagem_falsa(largura, altura)

    captura_falsa = SimpleNamespace(
        size=(largura, altura),
        rgb=imagem.tobytes(),
        width=largura,
        height=altura,
    )

    sct_falso = MagicMock()
    sct_falso.monitors = [None, {"left": 0, "top": 0, "width": largura, "height": altura}]
    sct_falso.grab.return_value = captura_falsa

    gerenciador_falso = MagicMock()
    gerenciador_falso.__enter__.return_value = sct_falso
    gerenciador_falso.__exit__.return_value = False

    # _AbrirCaptura é o ponto de entrada do módulo para abrir o mss.
    # Substituir só ele evita mexer no módulo mss global.
    monkeypatch.setattr(
        click_locator,
        "_AbrirCaptura",
        lambda: gerenciador_falso,
    )
    return largura, altura


@pytest.fixture
def api_key_falsa(monkeypatch):
    monkeypatch.setattr(click_locator, "GEMINI_API_KEY", "chave-de-teste")


# ============================================================
# Bloqueio por termos sensíveis
# ============================================================

@pytest.mark.parametrize(
    "alvo",
    [
        "botão de excluir conta",
        "confirmar pagamento do pedido",
        "botão instalar programa",
    ],
)
def test_alvo_bloqueado_por_termos_sensiveis(alvo, api_key_falsa):
    resultado = click_locator.localizar_elemento_na_tela(alvo)
    assert resultado["sucesso"] is False
    assert "bloqueado por segurança" in resultado["mensagem"]


def test_alvo_vazio():
    resultado = click_locator.localizar_elemento_na_tela("   ")
    assert resultado["sucesso"] is False
    assert "não foi informado" in resultado["mensagem"]


def test_sem_api_key(monkeypatch):
    monkeypatch.setattr(click_locator, "GEMINI_API_KEY", None)
    resultado = click_locator.localizar_elemento_na_tela("botão continuar")
    assert resultado["sucesso"] is False
    assert "GEMINI_API_KEY" in resultado["mensagem"]


# ============================================================
# Conversão de coordenadas normalizadas (0-1000) para pixels
# ============================================================

def test_localizar_elemento_pula_refinamento_quando_confianca_alta(mock_mss, api_key_falsa):
    largura, altura = mock_mss

    resposta_alta_confianca = {
        "encontrado": True,
        "x": 500,   # meio da largura
        "y": 500,   # meio da altura
        "confianca": 0.99,
        "descricao": "botão continuar",
    }

    with patch.object(click_locator, "genai") as mock_genai:
        mock_cliente = mock_genai.Client.return_value
        mock_cliente.models.generate_content.return_value = SimpleNamespace(
            text=(
                '{"encontrado": true, "x": 500, "y": 500, '
                '"confianca": 0.99, "descricao": "botão continuar"}'
            )
        )

        resultado = click_locator.localizar_elemento_na_tela("botão continuar")

        # Só deve ter feito UMA chamada (sem a segunda passagem de refinamento).
        assert mock_cliente.models.generate_content.call_count == 1
        assert "http_options" in mock_genai.Client.call_args.kwargs

    assert resultado["sucesso"] is True
    assert resultado["x"] == round(0.5 * largura)
    assert resultado["y"] == round(0.5 * altura)


def test_localizar_elemento_faz_segunda_passagem_quando_confianca_media(mock_mss, api_key_falsa):
    largura, altura = mock_mss

    respostas = [
        # Primeira passagem: confiança abaixo do limiar de pular refinamento.
        SimpleNamespace(
            text=(
                '{"encontrado": true, "x": 500, "y": 500, '
                '"confianca": 0.85, "descricao": "campo de nota"}'
            )
        ),
        # Segunda passagem (no recorte ampliado): coordenada central do recorte.
        SimpleNamespace(
            text=(
                '{"encontrado": true, "x": 500, "y": 500, '
                '"confianca": 0.9, "descricao": "campo de nota"}'
            )
        ),
    ]

    with patch.object(click_locator, "genai") as mock_genai:
        mock_cliente = mock_genai.Client.return_value
        mock_cliente.models.generate_content.side_effect = respostas

        resultado = click_locator.localizar_elemento_na_tela("campo de nota")

        assert mock_cliente.models.generate_content.call_count == 2

    assert resultado["sucesso"] is True
    # A posição final deve continuar dentro dos limites da captura.
    assert 0 <= resultado["x"] <= largura
    assert 0 <= resultado["y"] <= altura


def test_localizar_elemento_nao_encontrado(mock_mss, api_key_falsa):
    with patch.object(click_locator, "genai") as mock_genai:
        mock_cliente = mock_genai.Client.return_value
        mock_cliente.models.generate_content.return_value = SimpleNamespace(
            text='{"encontrado": false, "x": 0, "y": 0, "confianca": 0.1, "descricao": ""}'
        )

        resultado = click_locator.localizar_elemento_na_tela("elemento que não existe")

    assert resultado["sucesso"] is False
    assert "confiança suficiente" in resultado["mensagem"]


def test_perguntar_coordenada_faz_retry_em_erro_temporario(mock_mss, api_key_falsa, monkeypatch):
    # Evita esperar de verdade entre as tentativas durante o teste.
    monkeypatch.setattr(click_locator.time, "sleep", lambda segundos: None)

    cliente_falso = MagicMock()
    cliente_falso.models.generate_content.side_effect = [
        RuntimeError("503 UNAVAILABLE"),
        SimpleNamespace(
            text='{"encontrado": true, "x": 500, "y": 500, "confianca": 0.99, "descricao": "ok"}'
        ),
    ]

    resultado = click_locator._perguntar_coordenada(
        cliente_falso,
        b"dados-fake-da-imagem",
        "algum alvo",
    )

    assert resultado["encontrado"] is True
    assert cliente_falso.models.generate_content.call_count == 2


def test_perguntar_coordenada_desiste_apos_tentativas_esgotadas(monkeypatch):
    monkeypatch.setattr(click_locator.time, "sleep", lambda segundos: None)

    cliente_falso = MagicMock()
    cliente_falso.models.generate_content.side_effect = RuntimeError("503 UNAVAILABLE")

    with pytest.raises(RuntimeError):
        click_locator._perguntar_coordenada(
            cliente_falso,
            b"dados-fake-da-imagem",
            "algum alvo",
        )

    assert cliente_falso.models.generate_content.call_count == click_locator.TENTATIVAS_GEMINI
