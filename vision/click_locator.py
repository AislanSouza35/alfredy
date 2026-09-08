import io
import json
import os
import time

import mss
from PIL import Image
from google import genai
from google.genai import types

from core.config import GEMINI_API_KEY
from core.gemini_ssl import criar_http_options_gemini
# mss.mss() está a caminho da remoção e emite um aviso de descontinuação
# a cada captura. mss.MSS é o nome novo da mesma classe; o fallback
# mantém o ALF funcionando em versões antigas da biblioteca.
_AbrirCaptura = getattr(mss, "MSS", mss.mss)

MODELO_LOCALIZADOR = os.getenv("GEMINI_VISION_MODEL", "gemini-3.1-flash-lite")
CONFIANCA_MINIMA = 0.78
# Acima deste valor, a primeira passagem já é confiável o suficiente
# e pulamos a segunda chamada de refinamento para responder mais rápido.
CONFIANCA_ALTA_SEM_REFINAMENTO = 0.94
# Tamanho do recorte usado na segunda passagem de refinamento,
# em proporção da largura/altura da captura original.
PROPORCAO_RECORTE = 0.22
# Tentativas ao encontrar erros temporários da API (ex.: 503 alta demanda).
TENTATIVAS_GEMINI = 3
ESPERA_ENTRE_TENTATIVAS = 1.5
TERMOS_BLOQUEADOS = (
    "excluir",
    "apagar",
    "deletar",
    "remover permanentemente",
    "esvaziar lixeira",
    "formatar",
    "comprar",
    "finalizar compra",
    "pagar",
    "confirmar pagamento",
    "transferir",
    "enviar dinheiro",
    "instalar",
    "desinstalar",
    "executar como administrador",
)


def _normalizar(texto):
    return " ".join(str(texto).lower().split()).strip()


def _alvo_bloqueado(alvo):
    alvo_normalizado = _normalizar(alvo)
    return any(termo in alvo_normalizado for termo in TERMOS_BLOQUEADOS)


def _capturar_tela_principal():
    with _AbrirCaptura() as sct:
        monitor = sct.monitors[1]
        captura = sct.grab(monitor)
        imagem = Image.frombytes("RGB", captura.size, captura.rgb)
        return {
            "imagem": imagem,
            "largura": captura.width,
            "altura": captura.height,
            "esquerda": monitor["left"],
            "topo": monitor["top"],
        }


def _codificar_jpeg(imagem_pil, qualidade=88):
    buffer = io.BytesIO()
    imagem_pil.save(buffer, format="JPEG", quality=qualidade)
    return buffer.getvalue()


def _extrair_json(texto):
    texto = str(texto or "").strip()
    if texto.startswith("```"):
        linhas = texto.splitlines()
        linhas = [linha for linha in linhas if not linha.strip().startswith("```")]
        texto = "\n".join(linhas).strip()
    return json.loads(texto)


def _perguntar_coordenada(cliente, imagem_bytes, alvo):
    """
    Envia uma imagem ao Gemini e pede a posição normalizada (0 a 1000)
    do elemento solicitado dentro dessa imagem especificamente.
    """
    esquema = {
        "type": "object",
        "properties": {
            "encontrado": {"type": "boolean"},
            "x": {"type": "integer", "minimum": 0, "maximum": 1000},
            "y": {"type": "integer", "minimum": 0, "maximum": 1000},
            "confianca": {"type": "number", "minimum": 0, "maximum": 1},
            "descricao": {"type": "string"},
        },
        "required": ["encontrado", "x", "y", "confianca", "descricao"],
    }
    prompt = (
        "Você é um localizador visual de interface de computador. "
        "Encontre nesta imagem o elemento solicitado pelo usuário. "
        "Retorne o centro clicável do elemento. "
        "Use coordenadas normalizadas: x=0 é a borda esquerda, x=1000 a direita; "
        "y=0 é o topo e y=1000 a borda inferior. "
        "Seja o mais preciso possível quanto ao centro exato do elemento. "
        "Se houver mais de um elemento parecido, escolha somente quando a descrição do usuário permitir distinguir claramente. "
        "Caso contrário, marque encontrado=false. "
        "Não invente coordenadas e não escolha elementos parcialmente escondidos. "
        f"Elemento solicitado: {alvo}"
    )

    # Erros como "503 UNAVAILABLE" (alta demanda) costumam ser temporários.
    # Tenta novamente algumas vezes com uma pequena espera antes de desistir.
    ultimo_erro = None
    for tentativa in range(TENTATIVAS_GEMINI):
        try:
            resposta = cliente.models.generate_content(
                model=MODELO_LOCALIZADOR,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=imagem_bytes, mime_type="image/jpeg"),
                ],
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_schema=esquema,
                ),
            )
            dados = _extrair_json(resposta.text)
            return {
                "encontrado": bool(dados.get("encontrado", False)),
                "confianca": float(dados.get("confianca", 0)),
                "x": int(dados.get("x", 0)),
                "y": int(dados.get("y", 0)),
                "descricao": str(dados.get("descricao", "elemento")),
            }
        except Exception as erro:
            ultimo_erro = erro
            if tentativa < TENTATIVAS_GEMINI - 1:
                time.sleep(ESPERA_ENTRE_TENTATIVAS * (tentativa + 1))

    raise ultimo_erro


def localizar_elemento_na_tela(alvo):
    alvo = " ".join(str(alvo).split()).strip()
    if not alvo:
        return {"sucesso": False, "mensagem": "O alvo do clique não foi informado."}
    if _alvo_bloqueado(alvo):
        return {"sucesso": False, "mensagem": "Esse clique foi bloqueado por segurança. Nenhuma ação foi executada."}
    if not GEMINI_API_KEY:
        return {"sucesso": False, "mensagem": "GEMINI_API_KEY não encontrada."}

    captura = _capturar_tela_principal()
    imagem_completa = captura["imagem"]
    largura = captura["largura"]
    altura = captura["altura"]

    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=criar_http_options_gemini(types),
    )

    # Primeira passagem: localização aproximada na tela inteira.
    primeira = _perguntar_coordenada(
        client,
        _codificar_jpeg(imagem_completa),
        alvo,
    )

    if not primeira["encontrado"] or primeira["confianca"] < CONFIANCA_MINIMA:
        return {"sucesso": False, "mensagem": "Não consegui localizar o elemento com confiança suficiente."}

    # Converte a coordenada aproximada (0 a 1000) para pixels
    # relativos à captura, usados para recortar a região do alvo.
    x_aprox = (primeira["x"] / 1000.0) * largura
    y_aprox = (primeira["y"] / 1000.0) * altura

    # Quando a primeira passagem já veio com confiança muito alta,
    # pula o refinamento para responder mais rápido.
    if primeira["confianca"] >= CONFIANCA_ALTA_SEM_REFINAMENTO:
        x = captura["esquerda"] + round(x_aprox)
        y = captura["topo"] + round(y_aprox)
        return {
            "sucesso": True,
            "x": x,
            "y": y,
            "confianca": primeira["confianca"],
            "descricao": primeira["descricao"],
            "mensagem": "Elemento localizado com sucesso.",
        }

    # Segunda passagem: recorta uma região ao redor do ponto aproximado
    # e pede a coordenada novamente dentro desse recorte ampliado.
    # Isso aumenta bastante a precisão do clique final.
    largura_recorte = largura * PROPORCAO_RECORTE
    altura_recorte = altura * PROPORCAO_RECORTE

    esquerda_recorte = max(0, min(largura - largura_recorte, x_aprox - largura_recorte / 2))
    topo_recorte = max(0, min(altura - altura_recorte, y_aprox - altura_recorte / 2))

    caixa = (
        int(esquerda_recorte),
        int(topo_recorte),
        int(min(largura, esquerda_recorte + largura_recorte)),
        int(min(altura, topo_recorte + altura_recorte)),
    )

    imagem_recorte = imagem_completa.crop(caixa)

    # Amplia o recorte para dar ao modelo mais detalhe do alvo.
    fator_ampliacao = 3
    imagem_recorte = imagem_recorte.resize(
        (
            imagem_recorte.width * fator_ampliacao,
            imagem_recorte.height * fator_ampliacao,
        ),
        Image.LANCZOS,
    )

    segunda = _perguntar_coordenada(
        client,
        _codificar_jpeg(imagem_recorte),
        alvo,
    )

    if segunda["encontrado"] and segunda["confianca"] >= CONFIANCA_MINIMA:
        # Coordenada final: desloca a posição relativa ao recorte
        # de volta para a captura completa.
        x_local = caixa[0] + (segunda["x"] / 1000.0) * (caixa[2] - caixa[0])
        y_local = caixa[1] + (segunda["y"] / 1000.0) * (caixa[3] - caixa[1])
        confianca_final = segunda["confianca"]
        descricao_final = segunda["descricao"]
    else:
        # Se o refinamento falhar, usa a estimativa da primeira passagem.
        x_local = x_aprox
        y_local = y_aprox
        confianca_final = primeira["confianca"]
        descricao_final = primeira["descricao"]

    x = captura["esquerda"] + round(x_local)
    y = captura["topo"] + round(y_local)

    return {
        "sucesso": True,
        "x": x,
        "y": y,
        "confianca": confianca_final,
        "descricao": descricao_final,
        "mensagem": "Elemento localizado com sucesso.",
    }
