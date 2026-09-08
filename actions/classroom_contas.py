"""
Contas do Google autorizadas para o Classroom.

O professor tem turmas em mais de uma conta: o Gmail pessoal e a conta
institucional. Adicionar o Gmail como professor colaborador nas turmas
da instituição resolveria, mas o administrador do domínio bloqueia
convidar professor de fora -- foi o que aconteceu aqui.

Então o ALF guarda um token por conta e consulta todas. Cada turma sabe
de qual conta veio, e a nota é lançada pela credencial daquela conta.
"""

import json
import re
import unicodedata
from pathlib import Path
from threading import Lock

from core.arquivo_seguro import substituir_com_retentativa


PASTA = Path(__file__).resolve().parent.parent / "memory"
ARQUIVO_CREDENCIAIS = PASTA / "classroom_credenciais.json"

# Um arquivo de token por conta: classroom_token_<conta>.json
PREFIXO_TOKEN = "classroom_token_"

# Nome usado antes de existir suporte a várias contas. Se ainda estiver
# lá, é migrado na primeira execução em vez de o usuário ter que
# autorizar de novo à toa.
TOKEN_ANTIGO = PASTA / "classroom_token.json"

ESCOPOS = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
    # Leitura dos arquivos que os alunos entregam.
    "https://www.googleapis.com/auth/drive.readonly",
    # Descobrir de qual conta é cada token, para nomear o arquivo e
    # dizer ao professor de qual conta veio cada turma.
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
    # Criar questionário com gabarito. O drive.file dá acesso apenas
    # aos arquivos criados por este app, nunca ao restante do Drive.
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive.file",
    # Agenda. calendar.events mexe só nos eventos; o escopo "calendar"
    # completo daria acesso também às configurações das agendas.
    "https://www.googleapis.com/auth/calendar.events",
]

# Sem estes o token não serve para nada e a conta é descartada.
#
# A separação existe porque a verificação era tudo-ou-nada: bastou
# acrescentar o escopo da agenda para as duas contas serem dadas como
# não autorizadas, e o lançamento de notas -- que nada tem a ver com
# agenda -- parou de funcionar no meio do trabalho do professor.
#
# Um recurso novo agora desabilita apenas ele mesmo.
ESCOPOS_ESSENCIAIS = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

# O que cada recurso opcional exige, para a recusa dizer exatamente o
# que falta em vez de um "não autorizado" genérico.
ESCOPOS_POR_RECURSO = {
    "entregas": ["https://www.googleapis.com/auth/drive.readonly"],
    "forms": [
        "https://www.googleapis.com/auth/forms.body",
        "https://www.googleapis.com/auth/drive.file",
    ],
    "documentos": ["https://www.googleapis.com/auth/drive.file"],
    "agenda": ["https://www.googleapis.com/auth/calendar.events"],
}

NOMES_DE_RECURSO = {
    "entregas": "ler os arquivos entregues pelos alunos",
    "forms": "criar questionários",
    "documentos": "criar apresentação, documento e planilha",
    "agenda": "usar o Google Calendar",
}

_LOCK = Lock()

# Serviços já montados, por e-mail.
_cache = {}


def _apelido(email):
    """Transforma o e-mail num nome de arquivo seguro."""

    texto = unicodedata.normalize("NFD", str(email).lower().strip())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_") or "conta"


def caminho_token(email):
    return PASTA / f"{PREFIXO_TOKEN}{_apelido(email)}.json"


def _arquivos_de_token():
    if not PASTA.is_dir():
        return []
    return sorted(PASTA.glob(f"{PREFIXO_TOKEN}*.json"))


# ============================================================
# CREDENCIAIS
# ============================================================

def _carregar_credenciais(caminho):
    """Devolve credenciais válidas, ou None se não servirem mais."""

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        return None

    # A checagem de escopo lê o ARQUIVO, não o objeto de credenciais.
    #
    # from_authorized_user_file(caminho, ESCOPOS) preenche
    # credenciais.scopes com os escopos PEDIDOS, não com os concedidos
    # pelo Google. Comparar contra esse campo fazia a verificação
    # sempre passar, e um token antigo era dado como bom -- o erro de
    # permissão só apareceria na hora de criar o formulário.
    try:
        guardado = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    concedidos = set(guardado.get("scopes") or [])

    # Só o essencial derruba a conta. Faltar o escopo de um recurso
    # opcional desabilita aquele recurso, não a conta inteira.
    if not set(ESCOPOS_ESSENCIAIS).issubset(concedidos):
        return None

    try:
        credenciais = Credentials.from_authorized_user_file(
            str(caminho), sorted(concedidos)
        )
    except (ValueError, json.JSONDecodeError, OSError):
        return None

    if credenciais.expired and credenciais.refresh_token:
        try:
            credenciais.refresh(Request())
            _gravar_token(caminho, credenciais, concedidos)
        except Exception:
            return None

    return credenciais if credenciais.valid else None


def escopos_da_conta(email):
    """Devolve o conjunto de escopos que o Google concedeu a esta conta."""

    caminho = caminho_token(email)

    if not caminho.is_file():
        return set()

    try:
        return set(
            json.loads(caminho.read_text(encoding="utf-8")).get("scopes") or []
        )
    except (json.JSONDecodeError, OSError):
        return set()


def falta_para_recurso(email, recurso):
    """
    Diz o que impede esta conta de usar um recurso.

    Devolve None quando está tudo certo, ou a frase a ser dita.
    """

    exigidos = ESCOPOS_POR_RECURSO.get(recurso, [])
    concedidos = escopos_da_conta(email)

    faltando = [e for e in exigidos if e not in concedidos]
    if not faltando:
        return None

    return (
        f"A conta {email} ainda não tem permissão para "
        f"{NOMES_DE_RECURSO.get(recurso, recurso)}. "
        "Diga ao usuário que ele precisa autorizar essa conta de novo, "
        "e NÃO faça isso no meio de outra tarefa: termine o que está "
        "fazendo primeiro."
    )


def _gravar_token(caminho, credenciais, escopos_concedidos=None):
    """
    Grava o token preservando os escopos que o Google realmente deu.

    credenciais.to_json() escreve os escopos PEDIDOS, não os
    concedidos, porque from_authorized_user_file(caminho, ESCOPOS)
    preenche o objeto com a lista pedida. Ao renovar um token, isso
    reescrevia o arquivo afirmando permissões que nunca foram dadas --
    e a verificação criada justamente para não mentir passava a mentir.
    """

    PASTA.mkdir(parents=True, exist_ok=True)

    dados = json.loads(credenciais.to_json())

    if escopos_concedidos is not None:
        dados["scopes"] = sorted(escopos_concedidos)

    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    substituir_com_retentativa(temporario, caminho)


def _descobrir_email(credenciais):
    """Pergunta ao Google de qual conta é esta credencial."""

    try:
        from googleapiclient.discovery import build

        servico = build(
            "oauth2", "v2", credentials=credenciais, cache_discovery=False
        )
        return servico.userinfo().get().execute().get("email", "")
    except Exception:
        return ""


def _migrar_token_antigo():
    """Renomeia o token de conta única para o formato novo."""

    if not TOKEN_ANTIGO.is_file():
        return

    credenciais = _carregar_credenciais(TOKEN_ANTIGO)

    if credenciais is None:
        # Escopos insuficientes: não dá para aproveitar. Remove para
        # não ficar um arquivo órfão confundindo o diagnóstico.
        TOKEN_ANTIGO.unlink(missing_ok=True)
        return

    email = _descobrir_email(credenciais)
    if email:
        _gravar_token(caminho_token(email), credenciais)

    TOKEN_ANTIGO.unlink(missing_ok=True)


# ============================================================
# AUTORIZAÇÃO
# ============================================================

def autorizar_conta():
    """
    Abre o navegador para autorizar mais uma conta do Google.

    Cada chamada acrescenta uma conta; nenhuma substitui a anterior.
    """

    if not ARQUIVO_CREDENCIAIS.is_file():
        return (
            "Falta o arquivo de credenciais em "
            "memory/classroom_credenciais.json."
        )

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        return "As bibliotecas do Google não estão instaladas."

    try:
        fluxo = InstalledAppFlow.from_client_secrets_file(
            str(ARQUIVO_CREDENCIAIS), ESCOPOS
        )
        credenciais = fluxo.run_local_server(
            port=0,
            prompt="consent",
            authorization_prompt_message=(
                "Abrindo o navegador para autorizar a conta..."
            ),
        )
    except Exception as erro:
        return f"Não consegui autorizar: {erro}"

    email = _descobrir_email(credenciais)
    if not email:
        return (
            "Autorizei, mas não consegui descobrir de qual conta é. "
            "Tente de novo."
        )

    # O Google pode conceder menos do que foi pedido, se o usuário
    # desmarcar alguma permissão na tela de consentimento.
    concedidos = set(credenciais.scopes or ESCOPOS)
    _gravar_token(caminho_token(email), credenciais, concedidos)

    with _LOCK:
        _cache.pop(email, None)

    faltando = [e for e in ESCOPOS if e not in concedidos]
    if faltando:
        nomes = ", ".join(e.split("/auth/")[-1] for e in faltando)
        return (
            f"Conta {email} autorizada, mas sem estas permissões: {nomes}. "
            "Os recursos que dependem delas não vão funcionar."
        )

    return f"Conta {email} autorizada com sucesso."


def contas_autorizadas():
    """Devolve a lista de e-mails com token válido."""

    _migrar_token_antigo()

    emails = []
    for caminho in _arquivos_de_token():
        credenciais = _carregar_credenciais(caminho)
        if credenciais is None:
            continue

        email = caminho.stem[len(PREFIXO_TOKEN):]
        emails.append((email, caminho))

    return emails


def servicos():
    """
    Devolve [(email, servico_classroom, credenciais)] de todas as contas.

    A lista vem vazia quando nenhuma conta está autorizada.
    """

    _migrar_token_antigo()

    try:
        from googleapiclient.discovery import build
    except ImportError:
        return []

    resultado = []

    for caminho in _arquivos_de_token():
        apelido = caminho.stem[len(PREFIXO_TOKEN):]

        with _LOCK:
            if apelido in _cache:
                resultado.append(_cache[apelido])
                continue

        credenciais = _carregar_credenciais(caminho)
        if credenciais is None:
            continue

        try:
            servico = build(
                "classroom", "v1",
                credentials=credenciais,
                cache_discovery=False,
            )
        except Exception:
            continue

        # O e-mail real vale mais que o apelido do arquivo na hora de
        # falar com o professor.
        email = _descobrir_email(credenciais) or apelido
        entrada = (email, servico, credenciais)

        with _LOCK:
            _cache[apelido] = entrada

        resultado.append(entrada)

    return resultado


def limpar_cache():
    with _LOCK:
        _cache.clear()


def remover_conta(email):
    caminho = caminho_token(email)

    if not caminho.is_file():
        return f"Não tenho nenhuma conta autorizada parecida com {email}."

    caminho.unlink()
    limpar_cache()

    return f"Removi a autorização da conta {email}."
