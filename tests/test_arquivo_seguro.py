"""
Testes da substituição atômica tolerante a bloqueio.

O projeto vive dentro de uma pasta do OneDrive. Enquanto o OneDrive
sincroniza memory.json ou agenda.json, o destino fica aberto e a troca
falha com PermissionError, fazendo o ALF perder memórias e compromissos
de forma aparentemente aleatória.
"""

import pytest

from core.arquivo_seguro import substituir_com_retentativa


class _CaminhoFalso:
    """Falha nas primeiras N trocas e depois funciona."""

    def __init__(self, falhas):
        self.falhas = falhas
        self.tentativas = 0
        self.destino_final = None

    def replace(self, destino):
        self.tentativas += 1
        if self.tentativas <= self.falhas:
            raise PermissionError("arquivo em uso pelo OneDrive")
        self.destino_final = destino


def test_troca_no_primeiro_sucesso_nao_espera():
    origem = _CaminhoFalso(falhas=0)
    esperas = []

    substituir_com_retentativa(
        origem,
        "destino",
        pausa=esperas.append,
    )

    assert origem.tentativas == 1
    assert origem.destino_final == "destino"
    assert esperas == []


def test_bloqueio_momentaneo_e_superado_pela_retentativa():
    origem = _CaminhoFalso(falhas=2)
    esperas = []

    substituir_com_retentativa(
        origem,
        "destino",
        espera_inicial=0.01,
        pausa=esperas.append,
    )

    assert origem.tentativas == 3
    assert origem.destino_final == "destino"
    # A espera cresce a cada tentativa.
    assert esperas == [0.01, 0.02]


def test_bloqueio_permanente_ainda_levanta_o_erro():
    origem = _CaminhoFalso(falhas=99)

    with pytest.raises(PermissionError):
        substituir_com_retentativa(
            origem,
            "destino",
            tentativas=3,
            espera_inicial=0.01,
            pausa=lambda _: None,
        )

    assert origem.tentativas == 3
