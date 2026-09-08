"""Testes unitários para actions/text_actions.py (atalhos de teclado).

keybd_event é mockado para não enviar teclas reais durante os testes.
"""

from unittest.mock import patch

import pytest

from actions import text_actions


@pytest.mark.parametrize(
    "teclas,esperado",
    [
        ("ctrl+n", "ctrl+n"),
        ("Ctrl+S", "ctrl+s"),
        ("ctrl+shift+n", "ctrl+shift+n"),
        ("f5", "f5"),
    ],
)
def test_pressionar_atalho_teclado_com_sucesso(teclas, esperado):
    with patch.object(text_actions._USER32, "keybd_event") as mock_evento:
        resultado = text_actions.pressionar_atalho_teclado(teclas)

    assert esperado in resultado
    assert "executado com sucesso" in resultado
    assert mock_evento.called


def test_pressionar_atalho_teclado_vazio():
    resultado = text_actions.pressionar_atalho_teclado("")
    assert "Informe qual atalho" in resultado


def test_pressionar_atalho_teclado_modificador_desconhecido():
    resultado = text_actions.pressionar_atalho_teclado("ctrlx+n")
    assert "desconhecida" in resultado


def test_pressionar_atalho_teclado_tecla_desconhecida():
    resultado = text_actions.pressionar_atalho_teclado("ctrl+???")
    assert "Tecla desconhecida" in resultado


@pytest.mark.parametrize("atalho_bloqueado", ["alt+f4", "win+l", "ctrl+alt+delete"])
def test_pressionar_atalho_teclado_bloqueado_por_seguranca(atalho_bloqueado):
    with patch.object(text_actions._USER32, "keybd_event") as mock_evento:
        resultado = text_actions.pressionar_atalho_teclado(atalho_bloqueado)

    assert "bloqueado por segurança" in resultado
    assert not mock_evento.called


def test_pressionar_atalho_teclado_ordem_dos_eventos():
    # Modificadores devem descer antes da tecla principal e subir depois,
    # na ordem inversa (última modificadora pressionada é a primeira solta).
    chamadas = []
    with patch.object(text_actions._USER32, "keybd_event", side_effect=lambda *a: chamadas.append(a[0])):
        text_actions.pressionar_atalho_teclado("ctrl+shift+n")

    vk_ctrl = text_actions._VK_CONTROL
    vk_shift = text_actions._VK_SHIFT
    vk_n = ord("N")

    assert chamadas == [vk_ctrl, vk_shift, vk_n, vk_n, vk_shift, vk_ctrl]


def test_pressionar_atalho_teclado_simbolo_usa_layout_atual():
    # Regressão: "@" (raiz quadrada na Calculadora) usava ord("@") = 0x40,
    # que não corresponde a nenhuma tecla real do Windows. Agora usa
    # VkKeyScanW, que resolve o caractere para o layout de teclado ativo.
    esperado = text_actions._USER32.VkKeyScanW("@")
    assert esperado != -1, "Este teste requer um layout com o caractere '@'."
    vk_esperado = esperado & 0xFF

    chamadas = []
    with patch.object(text_actions._USER32, "keybd_event", side_effect=lambda *a: chamadas.append(a[0])):
        resultado = text_actions.pressionar_atalho_teclado("@")

    assert "executado com sucesso" in resultado
    assert vk_esperado in chamadas


def test_pressionar_atalho_teclado_apelido_plus_e_minus():
    with patch.object(text_actions._USER32, "keybd_event"):
        resultado_plus = text_actions.pressionar_atalho_teclado("plus")
        resultado_minus = text_actions.pressionar_atalho_teclado("minus")

    assert "executado com sucesso" in resultado_plus
    assert "executado com sucesso" in resultado_minus


def test_pressionar_atalho_teclado_simbolo_isolado_invalido():
    # "+" sozinho não pode ser usado como tecla principal porque também
    # é o separador da combinação; deve usar o apelido "plus" em vez disso.
    resultado = text_actions.pressionar_atalho_teclado("+")
    assert "inválido" in resultado

