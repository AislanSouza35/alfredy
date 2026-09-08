import math
import time

from PySide6.QtCore import (
    QPointF,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget


class AlfredVisualizer(QWidget):
    """
    Visualizador futurista do ALF.

    Elementos pesados (fundo e esfera) são desenhados em cache
    apenas quando o widget abre ou muda de tamanho. A cada quadro
    só são redesenhados os anéis, o brilho reativo, o indicador
    de áudio e os textos — o que mantém o uso de CPU baixo.
    """

    FPS_OFFLINE = 6
    FPS_ATIVO = 15
    FPS_FALANDO = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(360)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        self.ativo = False
        self.status = "OFFLINE"

        self.nivel_audio = 0.0
        self.nivel_suavizado = 0.0

        self.tempo_inicial = time.monotonic()

        self.cache_fundo = QPixmap()
        self.cache_esfera = QPixmap()
        self.ultimo_tamanho = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._atualizar_animacao)
        self._definir_fps(self.FPS_OFFLINE)
        self.timer.start()

    # ========================================================
    # CONTROLE EXTERNO
    # ========================================================

    def definir_status(self, texto):
        self.status = str(texto).upper()
        self.update()

    def definir_ativo(self, ativo):
        self.ativo = bool(ativo)
        if self.ativo:
            self._definir_fps(self.FPS_ATIVO)
        else:
            self.nivel_audio = 0.0
            self.nivel_suavizado = 0.0
            self._definir_fps(self.FPS_OFFLINE)
        self.update()

    def definir_nivel_audio(self, nivel):
        try:
            nivel = float(nivel)
        except (TypeError, ValueError):
            nivel = 0.0

        self.nivel_audio = max(0.0, min(1.0, nivel))

        if self.nivel_audio > 0.04:
            self._definir_fps(self.FPS_FALANDO)
        elif self.ativo:
            self._definir_fps(self.FPS_ATIVO)

    # ========================================================
    # FPS
    # ========================================================

    def _definir_fps(self, fps):
        intervalo = max(1, int(1000 / fps))
        if self.timer.interval() != intervalo:
            self.timer.setInterval(intervalo)

    # ========================================================
    # ANIMAÇÃO
    # ========================================================

    def _atualizar_animacao(self):
        alvo = self.nivel_audio

        # Mantém uma leve respiração mesmo em silêncio, quando ativo.
        if self.ativo and alvo < 0.02:
            alvo = 0.015

        velocidade = 0.36 if alvo > self.nivel_suavizado else 0.10
        self.nivel_suavizado += (alvo - self.nivel_suavizado) * velocidade

        if self.nivel_audio <= 0.02 and self.ativo:
            self._definir_fps(self.FPS_ATIVO)

        self.update()

    # ========================================================
    # REDIMENSIONAMENTO
    # ========================================================

    def resizeEvent(self, event):
        self._recriar_cache()
        super().resizeEvent(event)

    def _recriar_cache(self):
        tamanho = self.size()
        if tamanho.width() <= 0 or tamanho.height() <= 0:
            return

        tamanho_atual = (tamanho.width(), tamanho.height())
        if tamanho_atual == self.ultimo_tamanho:
            return

        self.ultimo_tamanho = tamanho_atual
        self.cache_fundo = self._criar_fundo_cache()
        self.cache_esfera = self._criar_esfera_cache()

    # ========================================================
    # FUNDO
    # ========================================================

    def _criar_fundo_cache(self):
        largura = self.width()
        altura = self.height()

        pixmap = QPixmap(largura, altura)
        pixmap.fill(QColor(3, 3, 5))

        painter = QPainter(pixmap)

        centro = QPointF(largura * 0.50, altura * 0.48)
        gradiente = QRadialGradient(centro, max(largura, altura) * 0.76)
        gradiente.setColorAt(0.0, QColor(48, 0, 9))
        gradiente.setColorAt(0.32, QColor(22, 0, 5))
        gradiente.setColorAt(0.68, QColor(7, 3, 5))
        gradiente.setColorAt(1.0, QColor(1, 1, 2))
        painter.fillRect(pixmap.rect(), gradiente)

        # Vinheta horizontal para escurecer as laterais.
        vinheta = QLinearGradient(0, 0, largura, 0)
        vinheta.setColorAt(0.0, QColor(0, 0, 0, 170))
        vinheta.setColorAt(0.20, QColor(0, 0, 0, 25))
        vinheta.setColorAt(0.80, QColor(0, 0, 0, 25))
        vinheta.setColorAt(1.0, QColor(0, 0, 0, 170))
        painter.fillRect(pixmap.rect(), vinheta)

        painter.end()
        return pixmap

    # ========================================================
    # ESFERA
    # ========================================================

    def _criar_esfera_cache(self):
        largura = self.width()
        altura = self.height()

        pixmap = QPixmap(largura, altura)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)

        centro = QPointF(largura * 0.50, altura * 0.49)
        raio = min(largura, altura) * 0.245

        # Sombra inferior.
        centro_sombra = QPointF(centro.x(), centro.y() + raio * 1.48)
        sombra = QRadialGradient(centro_sombra, raio * 1.05)
        sombra.setColorAt(0.0, QColor(255, 0, 30, 65))
        sombra.setColorAt(0.50, QColor(140, 0, 20, 20))
        sombra.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(sombra)
        painter.drawEllipse(centro_sombra, raio * 1.00, raio * 0.20)

        # Halo externo fixo.
        brilho_externo = QRadialGradient(centro, raio * 1.48)
        brilho_externo.setColorAt(0.0, QColor(255, 0, 38, 48))
        brilho_externo.setColorAt(0.62, QColor(160, 0, 24, 15))
        brilho_externo.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(brilho_externo)
        painter.drawEllipse(centro, raio * 1.48, raio * 1.48)

        # Corpo da esfera.
        esfera = QRadialGradient(
            QPointF(centro.x() - raio * 0.22, centro.y() - raio * 0.25),
            raio * 1.25,
        )
        esfera.setColorAt(0.0, QColor(112, 5, 22))
        esfera.setColorAt(0.32, QColor(55, 2, 12))
        esfera.setColorAt(0.72, QColor(15, 2, 5))
        esfera.setColorAt(1.0, QColor(2, 1, 2))
        painter.setPen(QPen(QColor(255, 50, 68, 190), 1.4))
        painter.setBrush(esfera)
        painter.drawEllipse(centro, raio, raio)
        painter.setBrush(Qt.NoBrush)

        # Linhas horizontais (efeito de globo).
        painter.setPen(QPen(QColor(255, 36, 54, 90), 0.9))
        for indice in range(-5, 6):
            proporcao = indice / 6.0
            y = centro.y() + proporcao * raio
            largura_linha = raio * math.sqrt(max(0.0, 1.0 - proporcao * proporcao))
            altura_curva = max(4.0, raio * 0.105)
            painter.drawEllipse(
                QRectF(
                    centro.x() - largura_linha,
                    y - altura_curva / 2,
                    largura_linha * 2,
                    altura_curva,
                )
            )

        # Linhas verticais (efeito de globo).
        for indice in range(-5, 6):
            proporcao = indice / 6.0
            largura_curva = raio * 2 * (0.10 + 0.72 * (1.0 - abs(proporcao)))
            deslocamento = proporcao * raio * 0.58
            painter.drawEllipse(
                QRectF(
                    centro.x() - largura_curva / 2 + deslocamento,
                    centro.y() - raio * 0.985,
                    largura_curva,
                    raio * 1.97,
                )
            )

        # Núcleo central brilhante.
        nucleo = QRadialGradient(centro, raio * 0.27)
        nucleo.setColorAt(0.0, QColor(255, 225, 230, 220))
        nucleo.setColorAt(0.18, QColor(255, 55, 74, 195))
        nucleo.setColorAt(1.0, QColor(180, 0, 25, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(nucleo)
        painter.drawEllipse(centro, raio * 0.27, raio * 0.27)

        painter.end()
        return pixmap

    # ========================================================
    # DESENHO PRINCIPAL
    # ========================================================

    def paintEvent(self, event):
        if self.cache_fundo.isNull() or self.cache_esfera.isNull():
            self._recriar_cache()

        largura = self.width()
        altura = self.height()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.drawPixmap(0, 0, self.cache_fundo)
        painter.drawPixmap(0, 0, self.cache_esfera)

        tempo = time.monotonic() - self.tempo_inicial
        centro = QPointF(largura * 0.50, altura * 0.49)
        raio = min(largura, altura) * 0.245

        self._desenhar_brilho_reativo(painter, centro, raio)
        self._desenhar_aneis(painter, centro, raio, tempo)
        self._desenhar_indicador_audio(painter, largura, altura, tempo)
        self._desenhar_textos(painter, largura, altura)

        painter.end()

    # ========================================================
    # BRILHO REATIVO
    # ========================================================

    def _desenhar_brilho_reativo(self, painter, centro, raio):
        if self.nivel_suavizado < 0.015:
            return

        intensidade = self.nivel_suavizado
        raio_brilho = raio * (1.06 + intensidade * 0.20)

        brilho = QRadialGradient(centro, raio_brilho)
        brilho.setColorAt(0.56, QColor(255, 0, 35, int(18 + intensidade * 58)))
        brilho.setColorAt(1.0, QColor(255, 0, 35, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(brilho)
        painter.drawEllipse(centro, raio_brilho, raio_brilho)

    # ========================================================
    # DOIS ANÉIS ANIMADOS
    # ========================================================

    def _desenhar_aneis(self, painter, centro, raio, tempo):
        painter.setBrush(Qt.NoBrush)

        energia = 1.0 + self.nivel_suavizado * 0.65

        # Cada tupla define: escala, achatamento, velocidade e transparência.
        dados_aneis = [
            (1.12, 0.48, 16.0, 125),
            (1.32, 0.66, -10.0, 85),
        ]

        for escala, achatamento, velocidade, alpha in dados_aneis:
            largura_anel = raio * 2 * escala
            altura_anel = largura_anel * achatamento

            retangulo = QRectF(
                centro.x() - largura_anel / 2,
                centro.y() - altura_anel / 2,
                largura_anel,
                altura_anel,
            )

            alpha_final = min(220, alpha + int(self.nivel_suavizado * 75))

            caneta = QPen(
                QColor(255, 38, 58, alpha_final),
                1.1 + self.nivel_suavizado * 1.4,
            )
            caneta.setDashPattern([9.0, 7.0])
            caneta.setDashOffset(tempo * velocidade * energia)

            painter.setPen(caneta)
            painter.drawEllipse(retangulo)

    # ========================================================
    # INDICADOR DE ÁUDIO
    # ========================================================

    def _desenhar_indicador_audio(self, painter, largura, altura, tempo):
        quantidade = 24
        largura_total = min(largura * 0.42, 420)
        inicio_x = (largura - largura_total) / 2
        base_y = altura * 0.89
        espaco = largura_total / quantidade
        altura_maxima = altura * 0.08

        painter.setPen(Qt.NoPen)

        for indice in range(quantidade):
            distancia_centro = abs(indice - (quantidade - 1) / 2)
            fator_centro = max(0.15, 1.0 - distancia_centro / (quantidade / 2))

            movimento = (math.sin(tempo * 5.0 + indice * 0.58) + 1.0) * 0.5

            valor = 0.05 + self.nivel_suavizado * fator_centro * (0.45 + movimento * 0.55)
            altura_barra = max(2.0, altura_maxima * valor)
            largura_barra = max(2.0, espaco * 0.28)

            alpha = int(55 + self.nivel_suavizado * 180)
            painter.setBrush(QColor(255, 38, 58, alpha))

            x = inicio_x + indice * espaco
            painter.drawRoundedRect(
                QRectF(x, base_y - altura_barra, largura_barra, altura_barra),
                largura_barra / 2,
                largura_barra / 2,
            )

    # ========================================================
    # TEXTOS
    # ========================================================

    def _desenhar_textos(self, painter, largura, altura):
        fonte_titulo = QFont("Segoe UI", 19)
        fonte_titulo.setWeight(QFont.DemiBold)
        fonte_titulo.setLetterSpacing(QFont.AbsoluteSpacing, 5)
        painter.setFont(fonte_titulo)
        painter.setPen(QColor(245, 238, 240, 235))

        # A altura do título vem da fonte, não de uma fração da janela.
        # Com posições proporcionais o status subia por cima do nome ALF
        # sempre que o painel ficava baixo.
        altura_titulo = painter.fontMetrics().height()
        topo_titulo = altura * 0.07

        painter.drawText(
            QRectF(0, topo_titulo, largura, altura_titulo),
            Qt.AlignCenter,
            "A L F",
        )

        fonte_status = QFont("Consolas", 9)
        fonte_status.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        painter.setFont(fonte_status)

        # Respiro fixo entre o nome e o estado, em qualquer tamanho.
        topo_status = topo_titulo + altura_titulo + 6
        altura_status = painter.fontMetrics().height()

        if self.ativo:
            cor = QColor(255, 48, 68, 220)
            simbolo = "●"
        else:
            cor = QColor(135, 135, 142, 175)
            simbolo = "○"

        painter.setPen(cor)
        painter.drawText(
            QRectF(0, topo_status, largura, altura_status),
            Qt.AlignCenter,
            f"{simbolo}  {self._estado_curto()}",
        )

    def _estado_curto(self):
        """
        Resume o status em uma única palavra.

        A caixa STATUS logo abaixo já mostra a mensagem completa. Repetir
        o mesmo texto aqui deixava a interface poluída e fazia a frase
        longa competir com o nome ALF. Aqui basta o estado da conexão.
        """

        if not self.ativo:
            return "OFFLINE"

        status = self.status

        for termo, estado in (
            ("ERRO", "ERRO"),
            ("ENCERRANDO", "ENCERRANDO"),
            ("RECONECTANDO", "RECONECTANDO"),
            ("RENOVANDO", "RECONECTANDO"),
            ("CONECTANDO", "CONECTANDO"),
            ("PREPARANDO", "CONECTANDO"),
        ):
            if termo in status:
                return estado

        return "ONLINE"

