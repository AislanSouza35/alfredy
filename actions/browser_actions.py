import re
import webbrowser
from html import unescape
from urllib.error import URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

CABECALHOS_NAVEGADOR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def _limpar_texto(texto):
    if not isinstance(texto, str):
        return ""
    return " ".join(texto.split()).strip()


def pesquisar_no_navegador(consulta):
    consulta = _limpar_texto(consulta)
    if not consulta:
        return "Informe o que deseja pesquisar no navegador."
    url = "https://www.google.com/search?q=" + quote_plus(consulta)
    abriu = webbrowser.open(url, new=2)
    if not abriu:
        return "Não consegui abrir o navegador padrão para realizar a pesquisa."
    return f"Abri no navegador uma pesquisa por: {consulta}."


def _obter_html_youtube(busca):
    url = "https://www.youtube.com/results?search_query=" + quote_plus(busca)
    requisicao = Request(url, headers=CABECALHOS_NAVEGADOR)
    with urlopen(requisicao, timeout=12) as resposta:
        return resposta.read().decode("utf-8", errors="ignore")


def _extrair_video_id(html):
    ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
    if not ids:
        return None
    vistos = set()
    for video_id in ids:
        if video_id in vistos:
            continue
        vistos.add(video_id)
        return video_id
    return None


def tocar_no_youtube(busca):
    busca = _limpar_texto(busca)
    if not busca:
        return "Informe qual música ou vídeo deseja reproduzir."
    termo_busca = busca + " official audio official video"
    try:
        html = _obter_html_youtube(termo_busca)
        video_id = _extrair_video_id(html)
        if not video_id:
            url_resultados = "https://www.youtube.com/results?search_query=" + quote_plus(termo_busca)
            webbrowser.open(url_resultados, new=2)
            return f"Não consegui identificar automaticamente o primeiro vídeo. Abri os resultados do YouTube para: {busca}."
        url_video = "https://www.youtube.com/watch?v=" + video_id + "&autoplay=1"
        abriu = webbrowser.open(url_video, new=2)
        if not abriu:
            return "Encontrei o vídeo, mas não consegui abrir o navegador padrão."
        return f"Abrindo no YouTube: {busca}."
    except (URLError, TimeoutError, OSError) as erro:
        url_resultados = "https://www.youtube.com/results?search_query=" + quote_plus(termo_busca)
        webbrowser.open(url_resultados, new=2)
        return f"Não consegui abrir o vídeo diretamente. Abri os resultados do YouTube para você. Detalhes: {erro}"
