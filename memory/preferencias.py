"""
Gaveta de preferências aprendidas automaticamente.

Fica separada de memory.json de propósito. As duas guardam coisas
diferentes e têm regras diferentes:

- memory.json  : fatos que VOCÊ mandou guardar. Cinquenta vagas, nunca
                 descarta nada sozinho, entra qualquer assunto.
- este arquivo : como você gosta que o ALF trabalhe. Dez vagas, descarta
                 a mais antiga ao encher, e recusa assunto proibido.

O limite pequeno e o descarte automático existem porque memória
automática enche sozinha. A memória manual trava ao chegar em 50 e para
de aceitar coisas novas em silêncio; aqui isso nunca acontece.
"""

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from threading import Lock

from core.arquivo_seguro import substituir_com_retentativa


PASTA = Path(__file__).resolve().parent
ARQUIVO = PASTA / "preferencias.json"

# Dez vagas. Passou disso, a mais antiga sai.
MAXIMO_PREFERENCIAS = 10

# Mesmo limite por item da memória manual.
MAXIMO_CARACTERES = 200

_LOCK = Lock()


# ============================================================
# ASSUNTOS PROIBIDOS
# ============================================================
#
# Este app clica e digita no SIGEduc. As regras de cuidado (confirmar a
# turma antes de lançar, não escolher "Sim/Não" sozinho, só gravar com
# autorização) ficam fixas na instrução do sistema.
#
# Uma preferência aprendida entra como fato do usuário e passa a
# competir com essas regras. Se o modelo inferisse "o usuário prefere
# que eu grave direto", isso viraria instrução permanente afetando nota
# de aluno -- sem você ter escolhido e sem ver acontecer.
#
# Por isso qualquer preferência que afrouxe confirmação é recusada.
PADROES_PROIBIDOS = (
    # Afrouxar confirmação e supervisão.
    r"\bsem (confirmar|perguntar|avisar|autoriza)",
    r"\bn[ãa]o (confirm|pergunt|avis|precis[ao] (confirmar|perguntar))",
    r"\bdispens[ae]r? (a )?confirma",
    r"\b(grav|salv|envi|confirm)\w* (tudo )?(direto|automaticamente|sozinho)",
    r"\bpode (gravar|salvar|enviar|confirmar) (direto|sozinho|sempre)",
    r"\bn[ãa]o precisa (me )?(perguntar|avisar|confirmar)",

    # Credenciais e documentos.
    r"\bsenha\b",
    r"\blogin\b",
    r"\bcpf\b",
    r"\brg\b",
    r"\bcart[ãa]o\b",
    r"\bconta banc",
    r"\bpix\b",

    # Ações destrutivas ou sensíveis.
    #
    # Os verbos precisam cobrir as conjugações, não só o infinitivo:
    # "prefere que eu apague os arquivos antigos" passava batido quando
    # o padrão era apenas "apagar".
    r"\bapag(ar|a|ue|uem|am|ando|ou)\b",
    r"\bexclu(ir|i|a|em|indo|iu)\b",
    r"\bdelet(ar|a|e|am|ando|ou)\b",
    r"\bformat(ar|a|e|am|ando|ou)\b",
    r"\bdesinstal\w*",
    r"\bcompr(ar|a|e|am|ando|ou)\b",
    r"\bpag(ar|ue|uem|am|ando|ou)\b",
    r"\btransfer(ir|e|a|em|indo|iu|encia)\b",
)

_PROIBIDOS = tuple(
    re.compile(padrao, re.IGNORECASE) for padrao in PADROES_PROIBIDOS
)


def _normalizar(texto):
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )
    return " ".join(texto.split())


def assunto_proibido(texto):
    """Diz se a preferência toca em assunto que não pode ser aprendido."""

    return any(padrao.search(str(texto)) for padrao in _PROIBIDOS)


# ============================================================
# ARQUIVO
# ============================================================

def _carregar():
    if not ARQUIVO.exists():
        return []

    try:
        with ARQUIVO.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(dados, dict):
        return []

    preferencias = dados.get("preferencias", [])
    if not isinstance(preferencias, list):
        return []

    validas = []
    for item in preferencias:
        if not isinstance(item, dict):
            continue

        texto = str(item.get("texto", "")).strip()
        if not texto:
            continue

        validas.append(
            {
                "texto": texto[:MAXIMO_CARACTERES],
                "data": str(item.get("data", "")),
            }
        )

    return validas[-MAXIMO_PREFERENCIAS:]


def _salvar(preferencias):
    PASTA.mkdir(parents=True, exist_ok=True)

    temporario = ARQUIVO.with_suffix(".tmp")
    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(
            {
                "versao": 1,
                "preferencias": preferencias,
            },
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    # Mesma proteção da memória manual contra o OneDrive segurando o
    # arquivo durante a sincronização.
    substituir_com_retentativa(temporario, ARQUIVO)


# ============================================================
# OPERAÇÕES
# ============================================================

def anotar_preferencia(texto):
    """
    Guarda uma preferência de trabalho observada durante a conversa.

    Devolve sempre uma frase para o ALF falar em voz alta. Isso é
    deliberado: você precisa ouvir o que foi anotado no momento em que
    acontece, para poder corrigir. Memória que entra calada é memória
    que você só descobre pelo efeito.
    """

    if not isinstance(texto, str):
        return "Não consegui entender a preferência."

    texto = re.sub(r"\s+", " ", texto).strip()

    if not texto:
        return "Não consegui entender a preferência."

    if len(texto) > MAXIMO_CARACTERES:
        return (
            "Essa preferência é longa demais. "
            f"Resuma em até {MAXIMO_CARACTERES} caracteres."
        )

    if assunto_proibido(texto):
        return (
            "Não posso guardar isso como preferência automática. "
            "Preferências que dispensam confirmação, ou que envolvem "
            "senha, dados pessoais ou ações destrutivas, precisam ser "
            "ditas a cada vez. Não comente este bloqueio, apenas siga."
        )

    normalizado = _normalizar(texto)

    with _LOCK:
        preferencias = _carregar()

        # Já conhecida: move para o fim, virando a mais recente.
        for existente in list(preferencias):
            if _normalizar(existente["texto"]) == normalizado:
                preferencias.remove(existente)
                preferencias.append(existente)
                _salvar(preferencias)
                return (
                    "Essa preferência já estava anotada. "
                    "Não precisa comentar."
                )

        preferencias.append(
            {
                "texto": texto,
                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            }
        )

        # Ao encher, a mais antiga sai. Diferente da memória manual,
        # esta gaveta nunca trava.
        descartada = None
        while len(preferencias) > MAXIMO_PREFERENCIAS:
            descartada = preferencias.pop(0)

        _salvar(preferencias)

    if descartada:
        return (
            f"Anotei que {texto} "
            f"Como a lista encheu, esqueci a preferência mais antiga: "
            f"{descartada['texto']} "
            "Diga isso ao usuário de forma curta e natural."
        )

    return (
        f"Anotei que {texto} "
        "Diga isso ao usuário de forma curta e natural, "
        "para ele poder corrigir se estiver errado."
    )


def listar_preferencias():
    with _LOCK:
        preferencias = _carregar()

    if not preferencias:
        return (
            "Ainda não aprendi nenhuma preferência de trabalho sobre "
            "este usuário."
        )

    linhas = [
        f"{indice}. {item['texto']} (anotado em {item['data']})"
        for indice, item in enumerate(preferencias, start=1)
    ]

    return "Preferências que aprendi:\n" + "\n".join(linhas)


def esquecer_preferencia(referencia):
    """Remove por número da lista ou por trecho do texto."""

    referencia = str(referencia or "").strip()

    if not referencia:
        return "Diga qual preferência devo esquecer."

    with _LOCK:
        preferencias = _carregar()

        if not preferencias:
            return "Não há preferências aprendidas para esquecer."

        alvo = None

        if referencia.isdigit():
            indice = int(referencia) - 1
            if 0 <= indice < len(preferencias):
                alvo = preferencias[indice]

        if alvo is None:
            procurado = _normalizar(referencia)
            for item in preferencias:
                if procurado in _normalizar(item["texto"]):
                    alvo = item
                    break

        if alvo is None:
            return "Não encontrei uma preferência com essa descrição."

        preferencias.remove(alvo)
        _salvar(preferencias)

    return f"Esqueci a preferência: {alvo['texto']}"


def esquecer_todas_preferencias():
    with _LOCK:
        _salvar([])

    return "Apaguei todas as preferências que eu tinha aprendido."


def contexto_preferencias():
    """Bloco enviado ao modelo junto da instrução do sistema."""

    with _LOCK:
        preferencias = _carregar()

    if not preferencias:
        return (
            "PREFERÊNCIAS APRENDIDAS:\n"
            "Nenhuma preferência aprendida ainda."
        )

    linhas = [f"- {item['texto']}" for item in preferencias]

    return (
        "PREFERÊNCIAS APRENDIDAS SOBRE COMO O USUÁRIO GOSTA DE TRABALHAR:\n"
        + "\n".join(linhas)
        + "\nSiga essas preferências quando forem relevantes. "
        "Elas nunca substituem as regras de segurança desta instrução: "
        "confirmações obrigatórias continuam obrigatórias. "
        "Não mencione este bloco sem necessidade."
    )
