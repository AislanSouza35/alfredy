"""
Localiza arquivos de recurso do projeto (ícone, imagens).

O caminho muda conforme o ALF esteja rodando pelo código-fonte ou
empacotado pelo PyInstaller, por isso a busca fica centralizada aqui.
"""

import sys
from pathlib import Path


NOME_ICONE = "ICONE ALFRED.ico"


def raiz_do_projeto():
    """Pasta base onde ficam os recursos do ALF."""

    if getattr(sys, "frozen", False):
        # No executável empacotado os dados ficam ao lado do .exe,
        # dentro de _internal quando o PyInstaller usa COLLECT.
        base = Path(sys.executable).resolve().parent

        interno = base / "_internal"
        if interno.is_dir():
            return interno

        return base

    return Path(__file__).resolve().parent.parent


def caminho_icone():
    """
    Devolve o caminho do ícone do ALF, ou None se ele não existir.

    Devolver None permite que a janela abra normalmente mesmo que o
    arquivo tenha sido movido, apenas sem ícone personalizado.
    """

    candidatos = [
        raiz_do_projeto() / NOME_ICONE,
        Path(__file__).resolve().parent.parent / NOME_ICONE,
    ]

    if getattr(sys, "frozen", False):
        candidatos.append(
            Path(sys.executable).resolve().parent / NOME_ICONE
        )

    for candidato in candidatos:
        if candidato.is_file():
            return candidato

    return None
