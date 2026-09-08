import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def test_escrever_log_adiciona_mensagem_sem_excecao():
    app = QApplication.instance() or QApplication([])
    janela = MainWindow()

    janela.escrever_log("Mensagem de teste")

    assert "> Mensagem de teste" in janela.log_box.toPlainText()


def test_botoes_secundarios_tem_largura_minima_para_leitura():
    app = QApplication.instance() or QApplication([])
    janela = MainWindow()

    botoes = [
        janela.btn_tela,
        janela.btn_camera,
        janela.btn_limpar,
        janela.btn_copiar_log,
        janela.btn_exportar_log,
        janela.btn_abrir_logs,
    ]

    for botao in botoes:
        assert botao.minimumWidth() >= 130
