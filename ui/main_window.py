

# Qt fornece constantes do framework.
# Neste arquivo, é utilizado principalmente para alinhar textos ao centro.
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon, QTextCursor

# Importa os componentes visuais utilizados pela janela:
# QGridLayout organiza itens em linhas e colunas.
# QHBoxLayout organiza itens horizontalmente.
# QLabel exibe textos.
# QMainWindow cria a janela principal.
# QPushButton cria botões.
# QTextEdit cria a área de registro.
# QVBoxLayout organiza itens verticalmente.
# QWidget funciona como container central.
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Importa a thread responsável pela conexão com o Gemini Live.
# Essa classe cuida do áudio, da visão e da comunicação em tempo real.
from core.recursos import caminho_icone
from gemini.live_client import GeminiLiveWorker

# Importa o visualizador animado, que substitui o antigo título estático
# e reage ao status e ao nível de áudio da chamada em tempo real.
from ui.alfred_visualizer import AlfredVisualizer


# QSS é a linguagem de estilos do Qt.
# Ela possui sintaxe parecida com CSS e define cores,
# fontes, bordas, tamanhos e estados dos componentes.
# A paleta segue o mesmo tom escuro e vermelho já usado no AlfredVisualizer.
ESTILO_GLOBAL = """
/* Define o estilo da janela principal. */
QMainWindow {
    background: qlineargradient(
        x1:0, y1:0,
        x2:0, y2:1,
        stop:0 #09090b,
        stop:0.55 #050507,
        stop:1 #0b0b0e
    );
}

/* Define o estilo padrão de todos os widgets. */
QWidget {
    color: #e8e8ec;
    font-family: "Segoe UI";
    background-color: transparent;
}

/* Estilo usado nos títulos de pequenas seções. */
QLabel#statusTitulo {
    color: #8a8a92;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
}

/* Estilo do valor atual do status. */
QLabel#statusValor {
    color: #ff3b52;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 1.3px;
    text-transform: uppercase;
    background-color: rgba(255, 59, 82, 0.08);
    border: 1px solid rgba(255, 59, 82, 0.22);
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 28px;
}

/* Painel escuro que envolve o visualizador. */
QFrame#painelVisualizador {
    background: qlineargradient(
        x1:0, y1:0,
        x2:1, y2:1,
        stop:0 #070709,
        stop:0.5 #0d0c10,
        stop:1 #040406
    );
    border: 1px solid #2a1a21;
    border-radius: 12px;
}

/* Estilo padrão aplicado a todos os botões. */
QPushButton {
    min-height: 42px;
    padding: 0 16px;
    color: #e8e8ec;
    background-color: #17141b;
    border: 1px solid #2d2430;
    border-radius: 8px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    text-transform: uppercase;
    outline: none;
}

/* Estilo aplicado quando o mouse passa sobre o botão. */
QPushButton:hover {
    background-color: #201b22;
    border: 1px solid #3d2b38;
}

/* Estilo aplicado enquanto o botão está pressionado. */
QPushButton:pressed {
    background-color: #110f13;
    border: 1px solid #2a1d28;
}

/* Estilo específico do botão principal de chamada. */
QPushButton#botaoChamada {
    color: #ffffff;
    background: qlineargradient(
        x1:0, y1:0,
        x2:1, y2:0,
        stop:0 #ff2d4d,
        stop:1 #cf0d2b
    );
    border: 1px solid #ff5b6f;
    font-size: 13px;
    font-weight: 800;
    box-shadow: 0 0 0 1px rgba(255, 90, 110, 0.2);
}

QPushButton#botaoChamada:hover {
    background: qlineargradient(
        x1:0, y1:0,
        x2:1, y2:0,
        stop:0 #ff4965,
        stop:1 #e20d2d
    );
    border: 1px solid #ff7a88;
}

/* Estilo aplicado quando a propriedade personalizada
   "encerrando" estiver definida como true. */
QPushButton#botaoChamada[encerrando="true"] {
    color: #dfe0e7;
    background-color: #201d22;
    border: 1px solid #3c3640;
}

QPushButton#botaoLimpar {
    color: #f0e6ea;
    background-color: #120d11;
    border: 1px solid #3a2833;
}

QPushButton#botaoLimpar:hover {
    background-color: #1b1419;
    border: 1px solid #533241;
}

QPushButton#botaoCopiarLog {
    color: #f0e6ea;
    background-color: #141017;
    border: 1px solid #2e2434;
}

QPushButton#botaoCopiarLog:hover {
    background-color: #1d151c;
    border: 1px solid #4a3240;
}

QPushButton#botaoExportarLog {
    color: #f0e6ea;
    background-color: #120f14;
    border: 1px solid #2c2430;
}

QPushButton#botaoExportarLog:hover {
    background-color: #19151b;
    border: 1px solid #453041;
}

QPushButton#botaoAbrirLogs {
    color: #f0e6ea;
    background-color: #110f12;
    border: 1px solid #2f2732;
}

QPushButton#botaoAbrirLogs:hover {
    background-color: #1a1419;
    border: 1px solid #4d3343;
}

/* Estilo da caixa que exibe o registro de atividades. */
QTextEdit#registro {
    color: #c9c9d1;
    background-color: #09090b;
    border: 1px solid #2b1b23;
    border-radius: 9px;
    padding: 10px;
    font-family: "Consolas";
    font-size: 10px;
    selection-background-color: #a70d2d;
}

QTextEdit#registro:focus {
    border: 1px solid #3d2b38;
}
"""


# Classe principal da interface básica do ALFRED.
# Ela herda de QMainWindow, que fornece estrutura de janela,
# barra de título e área central.
class MainWindow(QMainWindow):

    # Construtor da janela.
    # Configura tamanho, título, estilo e componentes.
    def __init__(self):
        # Inicializa a classe QMainWindow.
        super().__init__()

        # Define o texto exibido na barra superior da janela.
        self.setWindowTitle(
            "ALF"
        )

        # Sem isto a barra de título fica com o ícone branco padrão
        # do Qt, que destoa do resto da interface.
        icone = caminho_icone()
        if icone is not None:
            self.setWindowIcon(
                QIcon(str(icone))
            )

        # Define o menor tamanho permitido para a janela.
        self.setMinimumSize(
            560,
            460,
        )

        # Define o tamanho inicial da janela.
        self.resize(
            640,
            520,
        )

        # Remove a referência da thread encerrada.
        self.live_worker = None

        # Aplica o estilo QSS em toda a janela.
        self.setStyleSheet(
            ESTILO_GLOBAL
        )

        # Cria e organiza todos os componentes visuais.
        self._criar_interface()

    # Monta a interface completa da janela.
    def _criar_interface(self):
        # Cria o widget central que receberá o layout principal.
        container = QWidget()

        # Cria um layout vertical dentro do container.
        layout = QVBoxLayout(
            container
        )

        # Define as margens internas:
        # esquerda, superior, direita e inferior.
        layout.setContentsMargins(
            24,
            20,
            24,
            20,
        )

        # Define a distância padrão entre os componentes.
        layout.setSpacing(
            14
        )

        # Painel escuro que envolve o visualizador animado.
        painel_visualizador = QFrame()
        painel_visualizador.setObjectName(
            "painelVisualizador"
        )

        layout_painel = QVBoxLayout(
            painel_visualizador
        )
        layout_painel.setContentsMargins(0, 0, 0, 0)

        # Substitui o antigo título estático pelo visualizador animado,
        # que já desenha o nome ALF e reage ao status/áudio da chamada.
        self.visualizer = AlfredVisualizer()
        layout_painel.addWidget(
            self.visualizer
        )

        # Cria o texto fixo "Status".
        status_titulo = QLabel(
            "Status"
        )

        status_titulo.setObjectName(
            "statusTitulo"
        )

        status_titulo.setAlignment(
            Qt.AlignCenter
        )

        # Cria o rótulo que mostrará o estado atual.
        # É salvo em self porque será atualizado depois.
        self.status_valor = QLabel(
            "OFFLINE"
        )

        self.status_valor.setObjectName(
            "statusValor"
        )

        self.status_valor.setAlignment(
            Qt.AlignCenter
        )

        # Cria o botão principal para iniciar ou encerrar a chamada.
        self.btn_chamada = QPushButton(
            "INICIAR CHAMADA"
        )

        # Define o nome usado pelo estilo específico do botão.
        self.btn_chamada.setObjectName(
            "botaoChamada"
        )

        # Layout em grade para manter todos os botões legíveis
        # mesmo quando a janela estiver na largura mínima.
        layout_visao = QGridLayout()

        # Define o espaço entre os botões de tela e câmera.
        layout_visao.setSpacing(
            10
        )

        # Botão que solicita a análise da tela.
        self.btn_tela = QPushButton(
            "ANALISAR TELA"
        )

        # Botão que solicita a análise da webcam.
        self.btn_camera = QPushButton(
            "ANALISAR CÂMERA"
        )

        # Botão para limpar o registro de atividades.
        self.btn_limpar = QPushButton(
            "LIMPAR LOG"
        )
        self.btn_limpar.setObjectName(
            "botaoLimpar"
        )

        # Botão para copiar o conteúdo do registro para a área de transferência.
        self.btn_copiar_log = QPushButton(
            "COPIAR LOG"
        )
        self.btn_copiar_log.setObjectName(
            "botaoCopiarLog"
        )

        # Botão para exportar o registro atual para um arquivo em disco.
        self.btn_exportar_log = QPushButton(
            "EXPORTAR LOG"
        )
        self.btn_exportar_log.setObjectName(
            "botaoExportarLog"
        )

        # Botão para abrir a pasta com os logs exportados.
        self.btn_abrir_logs = QPushButton(
            "ABRIR LOGS"
        )
        self.btn_abrir_logs.setObjectName(
            "botaoAbrirLogs"
        )

        botoes_secundarios = [
            self.btn_tela,
            self.btn_camera,
            self.btn_limpar,
            self.btn_copiar_log,
            self.btn_exportar_log,
            self.btn_abrir_logs,
        ]

        for botao in botoes_secundarios:
            botao.setMinimumWidth(
                130
            )

        # Adiciona um botão ao layout em grade.
        layout_visao.addWidget(
            self.btn_tela,
            0,
            0,
        )

        # Adiciona um botão ao layout em grade.
        layout_visao.addWidget(
            self.btn_camera,
            0,
            1,
        )

        # Adiciona o botão de limpeza ao layout em grade.
        layout_visao.addWidget(
            self.btn_limpar,
            0,
            2,
        )

        # Adiciona o botão de cópia ao layout em grade.
        layout_visao.addWidget(
            self.btn_copiar_log,
            1,
            0,
        )

        # Adiciona o botão de exportação ao layout em grade.
        layout_visao.addWidget(
            self.btn_exportar_log,
            1,
            1,
        )

        # Adiciona o botão para abrir a pasta de logs.
        layout_visao.addWidget(
            self.btn_abrir_logs,
            1,
            2,
        )

        # Cria o título da área de registro.
        registro_titulo = QLabel(
            "Registro de atividade"
        )

        registro_titulo.setObjectName(
            "statusTitulo"
        )

        # Cria a caixa de texto que exibirá os eventos.
        self.log_box = QTextEdit()

        # Define o nome usado pelo estilo QSS.
        self.log_box.setObjectName(
            "registro"
        )

        # Impede que o usuário edite manualmente o registro.
        self.log_box.setReadOnly(
            True
        )

        # Exibe uma mensagem enquanto o registro estiver vazio.
        self.log_box.setPlaceholderText(
            "Aguardando eventos..."
        )

        # Adiciona o painel com o visualizador animado ao layout vertical.
        layout.addWidget(
            painel_visualizador,
            1,
        )

        # Adiciona um espaço fixo entre grupos de componentes.
        layout.addSpacing(
            4
        )

        # Adiciona um componente ao layout vertical.
        layout.addWidget(
            status_titulo
        )

        # Adiciona um componente ao layout vertical.
        layout.addWidget(
            self.status_valor
        )

        # Adiciona um espaço fixo entre grupos de componentes.
        layout.addSpacing(
            6
        )

        # Adiciona um componente ao layout vertical.
        layout.addWidget(
            self.btn_chamada
        )

        # Adiciona o layout horizontal dentro do layout principal.
        layout.addLayout(
            layout_visao
        )

        # Adiciona um espaço fixo entre grupos de componentes.
        layout.addSpacing(
            8
        )

        # Adiciona um componente ao layout vertical.
        layout.addWidget(
            registro_titulo
        )

        # Adiciona um componente ao layout vertical.
        layout.addWidget(
            self.log_box,
            1,
        )

        # Define o container como área central da QMainWindow.
        self.setCentralWidget(
            container
        )

        # Conecta o clique do botão principal
        # ao método que alterna entre iniciar e encerrar.
        self.btn_chamada.clicked.connect(
            self.alternar_chamada
        )

        # Conecta o botão de tela ao método analisar_tela.
        self.btn_tela.clicked.connect(
            self.analisar_tela
        )

        # Conecta o botão da câmera ao método analisar_camera.
        self.btn_camera.clicked.connect(
            self.analisar_camera
        )

        # Conecta o botão de limpar log ao método limpar_log.
        self.btn_limpar.clicked.connect(
            self.limpar_log
        )

        # Conecta o botão de copiar log ao método copiar_log.
        self.btn_copiar_log.clicked.connect(
            self.copiar_log
        )

        # Conecta o botão de exportar log ao método exportar_log.
        self.btn_exportar_log.clicked.connect(
            self.exportar_log
        )

        # Conecta o botão para abrir os logs ao método abrir_logs.
        self.btn_abrir_logs.clicked.connect(
            self.abrir_logs
        )

    # Adiciona uma nova mensagem ao registro de atividade.
    def escrever_log(self, texto):
        # append adiciona o texto em uma nova linha e mantém
        # a visualização sempre no fim do registro.
        self.log_box.append(
            f"> {texto}"
        )

        cursor = self.log_box.textCursor()
        cursor.movePosition(
            QTextCursor.MoveOperation.End,
        )
        self.log_box.setTextCursor(
            cursor
        )

    # Limpa o registro de atividade sem gravar texto artificial no histórico.
    def limpar_log(self):
        self.log_box.clear()
        self.log_box.setPlaceholderText(
            "Registro limpo. Aguardando eventos..."
        )

    # Copia o conteúdo atual do registro para a área de transferência.
    def copiar_log(self):
        texto = self.log_box.toPlainText().strip()
        if not texto:
            self.escrever_log(
                "Registro vazio. Nada foi copiado."
            )
            return

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(texto)
            self.escrever_log(
                "Conteúdo do registro copiado para a área de transferência."
            )
            return

        self.escrever_log(
            "Não foi possível acessar a área de transferência."
        )

    # Exporta o conteúdo atual do registro para um arquivo de texto com marcação temporal.
    def exportar_log(self):
        texto = self.log_box.toPlainText().strip()
        if not texto:
            self.escrever_log(
                "Registro vazio. Nada foi exportado."
            )
            return

        pasta = Path(__file__).resolve().parent.parent
        pasta_logs = pasta / "logs"
        pasta_logs.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        caminho = pasta_logs / f"alfred_log_{timestamp}.txt"

        try:
            caminho.write_text(
                texto + "\n",
                encoding="utf-8",
            )
            self.escrever_log(
                f"Log exportado para: {caminho}"
            )
        except Exception as erro:
            self.escrever_log(
                f"Não foi possível exportar o log: {erro}"
            )

    # Abre a pasta que contém os logs exportados.
    def abrir_logs(self):
        pasta = Path(__file__).resolve().parent.parent / "logs"
        pasta.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            if os.name == "nt":
                os.startfile(str(pasta))
            else:
                os.system(f"xdg-open '{pasta}'")
            self.escrever_log(
                f"Pasta de logs aberta: {pasta}"
            )
        except Exception as erro:
            self.escrever_log(
                f"Não foi possível abrir a pasta de logs: {erro}"
            )

    # Atualiza o texto do status exibido na interface.
    def definir_status(self, texto):
        # Converte para texto e mostra em letras maiúsculas.
        self.status_valor.setText(
            str(texto).upper()
        )

        # Mantém o visualizador animado sincronizado com o mesmo status.
        self.visualizer.definir_status(
            texto
        )

    # Decide entre iniciar ou encerrar a chamada.
    def alternar_chamada(self):
        # Se não existe worker, inicia uma nova chamada.
        if self.live_worker is None:
            self.iniciar_chamada()

        # Se já existe worker, solicita o encerramento.
        else:
            self.encerrar_chamada()

    # Prepara a interface e inicia a thread do Gemini Live.
    def iniciar_chamada(self):
        # Troca o texto do botão para indicar encerramento.
        self.btn_chamada.setText(
            "ENCERRAR CHAMADA"
        )

        # Volta a propriedade "encerrando" para False.
        self.btn_chamada.setProperty(
            "encerrando",
            True,
        )

        # Remove temporariamente o estilo atual do botão.
        self.btn_chamada.style().unpolish(
            self.btn_chamada
        )

        # Reaplica o estilo para considerar a nova propriedade.
        self.btn_chamada.style().polish(
            self.btn_chamada
        )

        # Atualiza o status visual.
        self.definir_status(
            "CONECTANDO"
        )

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            "Iniciando conexão..."
        )
        GeminiLiveWorker.registrar_diagnostico(
            "UI iniciar_chamada: antes de criar GeminiLiveWorker."
        )

        # Cria a thread responsável pela sessão Gemini.
        self.live_worker = GeminiLiveWorker()
        GeminiLiveWorker.registrar_diagnostico(
            "UI iniciar_chamada: GeminiLiveWorker criado."
        )

        # Recebe mensagens de status vindas da thread.
        self.live_worker.status_recebido.connect(
            self.atualizar_status
        )

        # Recebe erros emitidos pela thread.
        self.live_worker.erro_recebido.connect(
            self.mostrar_erro
        )

        # Executa a limpeza da interface quando a thread termina.
        self.live_worker.chamada_encerrada.connect(
            self.chamada_finalizada
        )

        # Permite que um comando de voz encerre a chamada.
        self.live_worker.solicitou_encerramento.connect(
            self.encerrar_chamada
        )

        # Registra no log quando o worker reconecta automaticamente
        # (renovação do servidor ou queda inesperada da conexão).
        self.live_worker.solicitou_reconexao.connect(
            lambda: self.escrever_log(
                "Reconectando automaticamente..."
            )
        )

        # Anima o visualizador de acordo com o nível de áudio da resposta.
        self.live_worker.nivel_audio.connect(
            self.visualizer.definir_nivel_audio
        )
        GeminiLiveWorker.registrar_diagnostico(
            "UI iniciar_chamada: sinais conectados."
        )

        # Marca o visualizador como ativo enquanto a chamada estiver aberta.
        self.visualizer.definir_ativo(
            True
        )

        # Inicia efetivamente a QThread.
        self.live_worker.start()
        GeminiLiveWorker.registrar_diagnostico(
            "UI iniciar_chamada: live_worker.start() chamado."
        )

        # Confirma no log que a thread foi disparada e verifica se ela avança.
        self.escrever_log(
            "Thread de conexão iniciada."
        )
        QTimer.singleShot(
            5000,
            self.verificar_conexao,
        )

    # Detecta uma thread que não iniciou ou não enviou nenhum status.
    def verificar_conexao(self):
        if self.live_worker is None:
            return

        if not self.live_worker.isRunning():
            self.definir_status(
                "ERRO"
            )
            self.escrever_log(
                "A thread de conexão terminou sem informar o motivo. "
                "Verifique o arquivo .env e a conexão com a internet."
            )

    # Solicita o encerramento da chamada ativa.
    def encerrar_chamada(self):
        # Só executa se existir uma thread ativa.
        if self.live_worker:
            self.definir_status(
                "ENCERRANDO"
            )

            self.escrever_log(
                "Encerrando chamada..."
            )

            # Altera o estado interno do worker para encerrar os loops.
            self.live_worker.parar()

            # Rede de segurança: se a thread não terminar sozinha (um
            # driver de áudio travado, por exemplo), a interface voltava
            # ao normal e o botão ficava preso em "ENCERRAR CHAMADA".
            QTimer.singleShot(
                8000,
                self.forcar_encerramento_travado,
            )

    # Destrava a interface quando a thread não termina sozinha.
    def forcar_encerramento_travado(self):
        if self.live_worker is None:
            return

        if not self.live_worker.isRunning():
            return

        GeminiLiveWorker.registrar_diagnostico(
            "Encerramento forcado: a thread nao terminou no prazo."
        )

        self.escrever_log(
            "A conexão não encerrou sozinha e foi finalizada à força."
        )

        self.live_worker.terminate()
        self.live_worker.wait(2000)
        self.chamada_finalizada()

    # Recebe uma mensagem do worker e atualiza
    # tanto o status quanto o registro.
    def atualizar_status(self, texto):
        # Atualiza o status visual.
        self.definir_status(
            texto
        )

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            texto
        )

    # Exibe um erro recebido da thread.
    def mostrar_erro(self, erro):
        # Atualiza o status visual.
        self.definir_status(
            "ERRO"
        )

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            f"Erro: {erro}"
        )

    # Restaura a interface quando a chamada termina.
    def chamada_finalizada(self):
        # Remove a referência da thread encerrada.
        self.live_worker = None

        # Desativa a animação do visualizador.
        self.visualizer.definir_ativo(
            False
        )

        # Troca o texto do botão para indicar encerramento.
        self.btn_chamada.setText(
            "INICIAR CHAMADA"
        )

        # Volta a propriedade "encerrando" para False.
        self.btn_chamada.setProperty(
            "encerrando",
            False,
        )

        # Remove temporariamente o estilo atual do botão.
        self.btn_chamada.style().unpolish(
            self.btn_chamada
        )

        # Reaplica o estilo para considerar a nova propriedade.
        self.btn_chamada.style().polish(
            self.btn_chamada
        )

        # Atualiza o status visual.
        self.definir_status(
            "OFFLINE"
        )

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            "Chamada encerrada."
        )

    # Solicita ao worker uma captura e análise da tela.
    def analisar_tela(self):
        # Impede a análise quando não existe sessão ativa.
        if not self.live_worker:
            self.escrever_log(
                "Inicie a chamada antes de analisar a tela."
            )

            return

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            "Solicitando análise da tela..."
        )

        # Chama o método público da thread responsável pela tela.
        self.live_worker.solicitar_analise_tela()

    # Solicita ao worker uma captura e análise da câmera.
    def analisar_camera(self):
        # Impede a análise quando não existe sessão ativa.
        if not self.live_worker:
            self.escrever_log(
                "Inicie a chamada antes de analisar a câmera."
            )

            return

        # Registra o acontecimento na caixa de atividades.
        self.escrever_log(
            "Solicitando análise da câmera..."
        )

        # Chama o método público da thread responsável pela webcam.
        self.live_worker.solicitar_analise_camera()

    # Evento executado automaticamente ao fechar a janela.
    # Garante que a thread não continue rodando em segundo plano.
    def closeEvent(self, event):
        # Só executa se existir uma thread ativa.
        if self.live_worker:
            # Altera o estado interno do worker para encerrar os loops.
            self.live_worker.parar()

            # Aguarda a thread finalizar. O fechamento do WebSocket e a
            # devolução dos dispositivos de áudio podem passar de três
            # segundos; se a janela sumir antes, o processo continua
            # vivo em segundo plano segurando o microfone e o próximo
            # ALF aberto não consegue gravar.
            if not self.live_worker.wait(8000):
                GeminiLiveWorker.registrar_diagnostico(
                    "Fechamento da janela: thread nao terminou, "
                    "encerrando a forca."
                )
                self.live_worker.terminate()
                self.live_worker.wait(2000)

        # Autoriza o fechamento da janela.
        event.accept()
