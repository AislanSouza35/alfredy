"""
Garante que apenas um ALF esteja rodando por vez.

Dois processos do ALF ao mesmo tempo (por exemplo o executável de
dist/ALF e um "python main_basic.py" aberto no editor) disputam o
mesmo microfone e a mesma webcam. O segundo processo falha ao abrir
o RawInputStream, a tarefa interna morre e a sessão Live reinicia em
loop. Esse era um dos motivos de o serviço "reiniciar várias vezes".
"""

import ctypes
import sys

# Nome global do mutex. O prefixo Local\ mantém o bloqueio dentro da
# sessão do usuário atual, o que é o comportamento desejado aqui.
NOME_MUTEX = r"Local\ALF_VISION_INSTANCIA_UNICA"

# Código devolvido pelo Windows quando o mutex já existe.
ERRO_JA_EXISTE = 183

# Mantém a referência viva enquanto o processo existir. Se o handle for
# coletado pelo garbage collector o mutex é liberado antes da hora.
_handle_mutex = None


def obter_bloqueio_instancia(nome=NOME_MUTEX):
    """
    Tenta reservar o nome global do ALF.

    Devolve True quando este processo é o único rodando e False quando
    já existe outro ALF ativo. Em sistemas que não sejam Windows a função
    simplesmente libera a execução.
    """

    global _handle_mutex

    if not sys.platform.startswith("win"):
        return True

    try:
        kernel32 = ctypes.windll.kernel32

        handle = kernel32.CreateMutexW(
            None,
            False,
            nome,
        )

        if not handle:
            # Sem handle não há como garantir a exclusividade.
            # Nesse caso é melhor deixar o programa abrir normalmente.
            return True

        if kernel32.GetLastError() == ERRO_JA_EXISTE:
            kernel32.CloseHandle(handle)
            return False

        _handle_mutex = handle
        return True

    except Exception:
        # Qualquer falha inesperada não pode impedir o ALF de abrir.
        return True
