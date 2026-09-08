# Ativar o ambiente virtual:
# .\venv\Scripts\Activate.ps1

# [CURSO] sys fornece acesso aos argumentos da linha de comando
# [CURSO] e também é utilizado para encerrar corretamente a aplicação.
import sys

# [CURSO] qInstallMessageHandler permite interceptar mensagens internas do Qt.
# [CURSO] Aqui é usado para ocultar apenas o aviso conhecido de DPI no Windows.
from PySide6.QtCore import qInstallMessageHandler

# [CURSO] QApplication é o núcleo de qualquer aplicação Qt.
# [CURSO] Ela cria o loop principal responsável pela interface gráfica.
from PySide6.QtWidgets import QApplication, QMessageBox

# Ajustes do processo que precisam acontecer antes de qualquer janela.
from PySide6.QtGui import QIcon

from core.runtime_windows import (
    ativar_consciencia_dpi,
    definir_id_aplicacao,
    instalar_registro_de_falhas,
)

# Localiza o ícone do ALF tanto no código-fonte quanto no executável.
from core.recursos import caminho_icone

# Impede dois ALF abertos ao mesmo tempo disputando microfone e webcam.
from core.instancia_unica import obter_bloqueio_instancia


# [CURSO] Oculta somente o aviso conhecido de DPI do Qt no Windows.
# [CURSO] Outros avisos e erros continuam aparecendo normalmente.
def filtro_mensagens_qt(tipo, contexto, mensagem):
    mensagem = str(mensagem)

    if "SetProcessDpiAwarenessContext() failed" in mensagem:
        return

    # Em modo janela (sem console) sys.stderr é None.
    if sys.stderr is not None:
        sys.stderr.write(mensagem + "\n")


# [CURSO] Função principal da aplicação.
# [CURSO] Ela inicializa o Qt, cria a janela e inicia o loop de eventos.
def main():

    # A consciência de DPI precisa ser definida antes do QApplication.
    # Depois disso o Windows não permite mais alterar o modo do processo.
    # Sem isso a captura de tela vem redimensionada e as coordenadas do
    # clique visual ficam deslocadas em monitores com escala.
    ativar_consciencia_dpi()

    # Precisa vir antes da primeira janela, senão a barra de tarefas
    # mostra o ícone do Python no lugar do ícone do ALF.
    definir_id_aplicacao()

    # [CURSO] Instala o filtro antes da criação do QApplication.
    qInstallMessageHandler(filtro_mensagens_qt)

    # [CURSO] Cria a aplicação Qt.
    # [CURSO] sys.argv permite que o Qt receba argumentos
    # [CURSO] passados pela linha de comando, quando existirem.
    app = QApplication(sys.argv)

    # Ícone usado pela barra de tarefas e pelo alternador de janelas.
    icone = caminho_icone()
    if icone is not None:
        app.setWindowIcon(
            QIcon(str(icone))
        )

    # A importação acontece depois do QApplication para manter o
    # tempo de abertura da janela o menor possível.
    from gemini.live_client import GeminiLiveWorker
    from ui.main_window import MainWindow

    # Sem console, uma exceção não tratada fecharia a janela em silêncio.
    # A partir daqui todo erro fatal fica gravado em logs/alf_runtime_debug.log.
    instalar_registro_de_falhas(
        GeminiLiveWorker.registrar_diagnostico
    )

    # Dois processos do ALF brigam pelo mesmo microfone e pela mesma
    # webcam. O segundo falha ao abrir o áudio e a sessão entra em um
    # ciclo de reconexão sem fim.
    if not obter_bloqueio_instancia():
        GeminiLiveWorker.registrar_diagnostico(
            "Abertura recusada: ja existe outro ALF em execucao."
        )

        QMessageBox.warning(
            None,
            "ALF já está aberto",
            "O ALF já está em execução neste computador.\n\n"
            "Feche a janela que está aberta (ou encerre ALF.exe pelo "
            "Gerenciador de Tarefas) antes de iniciar de novo.",
        )

        return 0

    # [CURSO] Cria uma instância da janela principal.
    window = MainWindow()

    # [CURSO] Torna a janela visível para o usuário.
    window.show()

    # [CURSO] Inicia o loop de eventos do Qt.
    return app.exec()


# [CURSO] Este bloco garante que a função main()
# [CURSO] seja executada somente quando este arquivo
# [CURSO] for iniciado diretamente.
if __name__ == "__main__":
    sys.exit(main())
