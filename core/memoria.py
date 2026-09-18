"""
Quanto de memória livre a máquina tem.

Com a memória no limite, o Windows empurra pedaços dos programas para o
disco. Quando a placa de som pede o próximo bloco de áudio e ele não
está mais na memória, a fala sai picotada; a captura de tela atrasa; e
encerrar a chamada passa do prazo.

Aconteceu em 18/09/2026: 94% da memória em uso (19.116 MB de 20.314),
quase 14 GB só de navegador, e o ALF -- com 206 MB, 1% do total --
levando a culpa por travar. O log daquele dia não tinha uma única queda
de conexão.

Sem psutil de propósito: a API do Windows responde isso direto, e uma
dependência a menos é uma dependência a menos para empacotar.
"""

import ctypes
from ctypes import wintypes


# Abaixo disto o Windows já está paginando para o disco, e é aí que o
# áudio começa a falhar.
LIMITE_APERTADO_MB = 1500


class _EstadoMemoria(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def estado_da_memoria():
    """
    Devolve (livre_mb, total_mb).

    (None, None) quando não dá para saber -- fora do Windows, ou se a
    chamada falhar. Quem chama trata isso como "sem aviso", nunca como
    "memória cheia": um palpite errado aqui viraria um alarme falso a
    cada conexão.
    """

    try:
        info = _EstadoMemoria()
        info.dwLength = ctypes.sizeof(_EstadoMemoria)

        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
            return None, None

        um_mb = 1024 * 1024
        return int(info.ullAvailPhys // um_mb), int(info.ullTotalPhys // um_mb)

    except Exception:
        return None, None


def memoria_apertada():
    """Devolve (apertada, mensagem). Mensagem vazia quando está tudo bem."""

    livre, total = estado_da_memoria()

    if livre is None or livre >= LIMITE_APERTADO_MB:
        return False, ""

    return True, (
        f"A memória do computador está quase no fim: {livre} MB livres de "
        f"{total} MB. Feche algumas janelas do navegador. Enquanto estiver "
        "assim, o áudio pica, a tela atrasa e a chamada pode travar -- e "
        "não é a conexão."
    )
