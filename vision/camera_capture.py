

# [CURSO] OpenCV (cv2) é responsável por acessar a webcam
# [CURSO] e capturar os frames da câmera.
import cv2

# [CURSO] Pillow (PIL) será utilizada para transformar
# [CURSO] o frame do OpenCV em uma imagem JPEG.
from PIL import Image

# [CURSO] io.BytesIO cria um arquivo totalmente em memória.
# [CURSO] Assim não precisamos salvar nenhuma imagem no disco.
import io

import sys


# Quantidade de frames descartados antes da foto final.
# Os primeiros frames vêm do buffer antigo do driver e mostram uma
# imagem do momento anterior. Cinco já é suficiente e economiza
# quase meio segundo em relação aos dez usados antes.
FRAMES_DESCARTADOS = 5

# Qualidade do JPEG enviado ao Gemini.
QUALIDADE_JPEG = 85


def _abrir_camera():
    """
    Abre a webcam padrão pelo caminho mais rápido disponível.

    No Windows, o backend padrão (MSMF) pode levar vários segundos só
    para inicializar a câmera, e essa espera aparecia como demora do
    ALF em responder. O DirectShow abre praticamente na hora. Se ele
    falhar, a função volta para o backend padrão do OpenCV.
    """

    if sys.platform.startswith("win"):
        camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)

        if camera.isOpened():
            return camera

        camera.release()

    return cv2.VideoCapture(0)


# [CURSO] Esta função captura uma fotografia da webcam
# [CURSO] e devolve a imagem em formato JPEG (bytes).
def capturar_camera_bytes():
    """
    Captura uma imagem da webcam padrão.
    Descarta alguns frames iniciais para dar tempo
    da câmera ajustar foco, luz e exposição.
    """

    camera = _abrir_camera()

    # [CURSO] Confirma se a câmera foi aberta corretamente.
    if not camera.isOpened():
        raise RuntimeError("Não foi possível acessar a webcam.")

    try:
        # Mantém apenas o frame mais recente no buffer do driver.
        # Sem isso o OpenCV entrega imagens acumuladas, ou seja,
        # uma foto de alguns segundos atrás.
        try:
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        # [CURSO] Variável que armazenará o último frame válido.
        frame = None

        # Descarta os primeiros frames ruins/desatualizados.
        # A leitura já é bloqueante, então ela sozinha dá à câmera
        # o tempo de ajustar foco e exposição.
        for _ in range(FRAMES_DESCARTADOS):
            sucesso, frame = camera.read()

            if not sucesso:
                raise RuntimeError(
                    "Não foi possível capturar imagem da webcam."
                )

    finally:
        # [CURSO] Libera a webcam para que outros programas
        # [CURSO] possam utilizá-la normalmente.
        camera.release()

    # [CURSO] O OpenCV trabalha em BGR e a Pillow utiliza RGB.
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # [CURSO] Converte o array NumPy em uma imagem Pillow.
    imagem = Image.fromarray(frame_rgb)

    # [CURSO] Cria um arquivo temporário somente na memória RAM.
    buffer = io.BytesIO()

    # [CURSO] Salva a imagem no buffer em formato JPEG.
    imagem.save(
        buffer,
        format="JPEG",
        quality=QUALIDADE_JPEG,
    )

    # [CURSO] Retorna apenas os bytes do JPEG.
    return buffer.getvalue()
