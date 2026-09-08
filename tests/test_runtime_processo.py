"""
Testes dos ajustes de processo: instância única e consciência de DPI.

Ambos existem por causa de falhas observadas em uso real:
- dois ALF abertos disputando microfone e webcam derrubavam a sessão;
- sem consciência de DPI a captura vinha redimensionada e o clique
  visual caía fora do lugar em monitores com escala.
"""

import sys

import pytest

from core.instancia_unica import obter_bloqueio_instancia
from core.runtime_windows import (
    ativar_consciencia_dpi,
    instalar_registro_de_falhas,
)


pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="Ajustes específicos do Windows.",
)


def test_segunda_instancia_e_recusada():
    nome = r"Local\ALF_TESTE_INSTANCIA_UNICA"

    assert obter_bloqueio_instancia(nome) is True
    assert obter_bloqueio_instancia(nome) is False


def test_ativar_consciencia_dpi_nao_levanta_erro():
    # O processo do pytest pode já estar com o modo definido; o que
    # importa é a função nunca derrubar a abertura do ALF.
    assert ativar_consciencia_dpi() in (True, False)


def test_registro_de_falhas_grava_excecao_nao_tratada():
    registradas = []

    excepthook_original = sys.excepthook
    try:
        instalar_registro_de_falhas(registradas.append)

        try:
            raise ValueError("falha de teste")
        except ValueError:
            sys.excepthook(*sys.exc_info())

    finally:
        sys.excepthook = excepthook_original

    assert registradas
    assert "falha de teste" in registradas[0]
