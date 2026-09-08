"""
Ajustes do processo que precisam acontecer antes da interface subir.

Dois problemas de verdade dependem deste arquivo:

1. Consciência de DPI. Sem ela o Windows entrega ao processo uma cópia
   redimensionada da tela em monitores com escala de 125% ou 150%.
   A captura sai borrada e, pior, as coordenadas devolvidas pelo
   localizador visual ficam deslocadas em relação ao clique real.

2. Registro de falhas fatais. O ALF é empacotado sem console
   (console=False no ALF.spec), então uma exceção não tratada fecha a
   janela sem deixar nenhuma pista. O gancho abaixo grava o traceback
   completo no log de diagnóstico antes de o processo morrer.
"""

import ctypes
import sys
import threading
import traceback


# Valor de DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2.
# É o modo mais moderno e o único que devolve pixels reais em telas
# com escala diferente de 100%.
_CONTEXTO_POR_MONITOR_V2 = ctypes.c_void_p(-4)

# Valor de PROCESS_PER_MONITOR_DPI_AWARE, usado como alternativa
# em versões mais antigas do Windows.
_POR_MONITOR_DPI_AWARE = 2


def ativar_consciencia_dpi():
    """
    Coloca o processo em modo "per monitor DPI aware".

    Devolve True quando algum dos caminhos funcionou. Nunca levanta erro:
    em um Windows antigo o ALF continua abrindo, apenas com a captura
    sujeita ao redimensionamento do sistema.
    """

    if not sys.platform.startswith("win"):
        return False

    try:
        user32 = ctypes.windll.user32
        if user32.SetProcessDpiAwarenessContext(_CONTEXTO_POR_MONITOR_V2):
            return True
    except Exception:
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(
            _POR_MONITOR_DPI_AWARE
        )
        return True
    except Exception:
        pass

    try:
        return bool(ctypes.windll.user32.SetProcessDPIAware())
    except Exception:
        return False


def definir_id_aplicacao(app_id="Alfredy.ALF.Vision"):
    """
    Dá ao processo uma identidade própria na barra de tarefas.

    Agora que o ALF é iniciado pelo pythonw.exe, o Windows agrupa a
    janela sob o Python e mostra o ícone do interpretador na barra de
    tarefas. Declarar um AppUserModelID próprio faz o Windows tratar o
    ALF como um aplicativo separado e usar o ícone da janela.
    """

    if not sys.platform.startswith("win"):
        return False

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            app_id
        )
        return True
    except Exception:
        return False


def instalar_registro_de_falhas(registrar):
    """
    Faz toda exceção não tratada ser gravada no log de diagnóstico.

    O parâmetro registrar é a função de log do projeto
    (GeminiLiveWorker.registrar_diagnostico).
    """

    excepthook_anterior = sys.excepthook

    def tratar_excecao(tipo, valor, tb):
        try:
            registrar(
                "Excecao nao tratada na thread principal:\n"
                + "".join(
                    traceback.format_exception(tipo, valor, tb)
                )
            )
        except Exception:
            pass

        excepthook_anterior(tipo, valor, tb)

    sys.excepthook = tratar_excecao

    # threading.excepthook cobre as exceções que escapam de QThread
    # e das threads auxiliares de áudio.
    def tratar_excecao_thread(args):
        try:
            registrar(
                f"Excecao nao tratada na thread {args.thread!r}:\n"
                + "".join(
                    traceback.format_exception(
                        args.exc_type,
                        args.exc_value,
                        args.exc_traceback,
                    )
                )
            )
        except Exception:
            pass

    threading.excepthook = tratar_excecao_thread
