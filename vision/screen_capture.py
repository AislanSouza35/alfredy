

# [CURSO] io permite criar arquivos temporários diretamente na memória RAM.
# [CURSO] Isso evita salvar imagens no disco antes de enviá-las ao Gemini.
import io

# [CURSO] mss é uma biblioteca extremamente rápida para captura de tela.
# [CURSO] Ela acessa diretamente os pixels do monitor.
import mss

# [CURSO] Pillow (PIL) será utilizada para transformar os pixels
# [CURSO] capturados pelo mss em uma imagem JPEG.
from PIL import Image
# mss.mss() está a caminho da remoção e emite um aviso de descontinuação
# a cada captura. mss.MSS é o nome novo da mesma classe; o fallback
# mantém o ALF funcionando em versões antigas da biblioteca.
_AbrirCaptura = getattr(mss, "MSS", mss.mss)


# Largura máxima enviada ao Gemini.
# Uma tela 4K gera um JPEG de vários megabytes, e subir esse arquivo pelo
# WebSocket antes de o modelo começar a responder é uma das causas de
# demora perceptível. O modelo reduz a imagem de qualquer forma, então
# encolher aqui não perde informação útil e corta o tempo de envio.
LARGURA_MAXIMA_ENVIO = 1600

# Qualidade do JPEG final.
QUALIDADE_JPEG = 78


# [CURSO] Esta função captura a tela principal do computador
# [CURSO] e devolve uma imagem JPEG em formato de bytes.
# [CURSO] Esses bytes são enviados diretamente para o Gemini Vision.
def capturar_tela_bytes():
    """
    Captura a tela principal neste exato momento
    e retorna JPEG em bytes.

    Uma instância nova de mss é criada a cada chamada de propósito:
    reaproveitar o objeto entre threads diferentes faz o Windows
    devolver o conteúdo do device context anterior, ou seja, uma
    imagem antiga da tela.
    """

    # [CURSO] Abre o capturador de tela.
    # [CURSO] O bloco "with" garante que os recursos
    # [CURSO] sejam liberados automaticamente ao final.
    with _AbrirCaptura() as sct:

        # [CURSO] monitors[1] normalmente representa o monitor principal.
        # [CURSO] monitors[0] corresponde à área virtual de todos os monitores.
        monitor = sct.monitors[1]

        # [CURSO] Captura todos os pixels do monitor escolhido.
        screenshot = sct.grab(
            monitor
        )

        # [CURSO] Converte os pixels capturados em uma imagem Pillow.
        # [CURSO] O mss fornece os pixels em RGB, compatíveis com a Pillow.
        imagem = Image.frombytes(
            "RGB",
            screenshot.size,
            screenshot.rgb
        )

    # Reduz a imagem apenas quando ela é maior que o necessário.
    # LANCZOS mantém o texto da tela legível para o modelo.
    if imagem.width > LARGURA_MAXIMA_ENVIO:
        nova_altura = round(
            imagem.height * LARGURA_MAXIMA_ENVIO / imagem.width
        )

        imagem = imagem.resize(
            (
                LARGURA_MAXIMA_ENVIO,
                nova_altura,
            ),
            Image.LANCZOS,
        )

    # [CURSO] Cria um buffer em memória para armazenar o JPEG.
    buffer = io.BytesIO()

    # [CURSO] Salva a imagem no buffer.
    imagem.save(
        buffer,
        format="JPEG",
        quality=QUALIDADE_JPEG,
        optimize=True,
    )

    # [CURSO] Retorna apenas os bytes da imagem JPEG.
    # [CURSO] Nenhum arquivo é criado no disco.
    return buffer.getvalue()
