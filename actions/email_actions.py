"""
Envio de e-mail por SMTP, com confirmação obrigatória.

O envio é dividido em dois passos de propósito:

    preparar_email(...)      -> monta o rascunho e devolve para o ALF
                                ler em voz alta
    confirmar_envio_email()  -> só então o e-mail sai

O motivo é a transcrição de voz. "manda pro joão" pode virar "joana",
e "não vou poder ir" pode perder o "não". E-mail enviado não volta;
uma leitura em voz alta antes custa três segundos e evita o problema.

Nada aqui envia nada sem que confirmar_envio_email() seja chamada.
"""

import json
import mimetypes
import re
import smtplib
import socket
import time
import unicodedata
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path
from threading import Lock

from core.arquivo_seguro import substituir_com_retentativa
from core.gemini_ssl import criar_contexto_ssl_compativel
from core.config import (
    EMAIL_NOME_REMETENTE,
    EMAIL_REMETENTE,
    EMAIL_SENHA_APP,
    EMAIL_SMTP_PORTA,
    EMAIL_SMTP_SERVIDOR,
)


# Servidores SMTP dos provedores mais comuns, deduzidos pelo domínio do
# remetente. Evita pedir configuração extra para quem usa Gmail.
SERVIDORES_CONHECIDOS = {
    "gmail.com": ("smtp.gmail.com", 587),
    "googlemail.com": ("smtp.gmail.com", 587),
    "outlook.com": ("smtp-mail.outlook.com", 587),
    "hotmail.com": ("smtp-mail.outlook.com", 587),
    "live.com": ("smtp-mail.outlook.com", 587),
    "msn.com": ("smtp-mail.outlook.com", 587),
    "yahoo.com": ("smtp.mail.yahoo.com", 587),
    "yahoo.com.br": ("smtp.mail.yahoo.com", 587),
    "uol.com.br": ("smtps.uol.com.br", 587),
    "bol.com.br": ("smtps.bol.com.br", 587),
    "terra.com.br": ("smtp.terra.com.br", 587),
    "ig.com.br": ("smtp.ig.com.br", 587),
}

# Um rascunho parado perde a validade. Sem isso, um "pode enviar" dito
# vinte minutos depois, já em outro assunto, dispararia o e-mail antigo.
VALIDADE_RASCUNHO = 300.0

# Limites de sanidade.
MAXIMO_ASSUNTO = 200
MAXIMO_MENSAGEM = 5000

# ============================================================
# ANEXOS
# ============================================================
#
# Vinte megabytes. O Gmail corta em 25 MB, e a codificação em base64
# infla o arquivo em cerca de um terço no caminho.
MAXIMO_ANEXO = 20 * 1024 * 1024

# Provedor de e-mail bloqueia executável de qualquer forma. Recusar
# aqui evita o usuário descobrir isso só quando a mensagem voltar.
EXTENSOES_BLOQUEADAS = {
    ".exe", ".bat", ".cmd", ".com", ".scr", ".pif",
    ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".msi", ".msp", ".jar", ".reg", ".dll", ".cpl",
}

# Agenda de contatos, para não precisar ditar endereço letra por letra.
ARQUIVO_CONTATOS = Path(__file__).resolve().parent.parent / "memory" / "contatos.json"
MAXIMO_CONTATOS = 100

_LOCK = Lock()

# Rascunho aguardando confirmação. Nunca é enviado sozinho.
_rascunho = {"dados": None, "momento": 0.0}

_PADRAO_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")

# ============================================================
# DOMÍNIOS QUE NÃO PODEM RECEBER E-MAIL
# ============================================================
#
# Caso real: pedido um "e-mail de teste" sem destinatário, o modelo
# inventou arlas@example.com e o envio saiu. Voltou como falha de
# entrega -- example.com é reservado e recusa e-mail por definição --
# mas se ele tivesse inventado um domínio de verdade, a mensagem teria
# chegado a um estranho.
#
# Endereço tem que vir do usuário. Estes aqui denunciam invenção.
DOMINIOS_RESERVADOS = {
    "example.com",
    "example.org",
    "example.net",
    "example.edu",
    "exemplo.com",
    "exemplo.com.br",
    "teste.com",
    "teste.com.br",
    "test.com",
    "dominio.com",
    "dominio.com.br",
    "seudominio.com",
    "meudominio.com",
    "empresa.com",
    "empresa.com.br",
    "escola.com",
    "provedor.com",
}

# Reservados por norma (RFC 2606 e RFC 6761): nunca existem de verdade.
SUFIXOS_RESERVADOS = (
    ".example",
    ".invalid",
    ".test",
    ".localhost",
    ".local",
)


def dominio_de(endereco):
    return str(endereco or "").split("@")[-1].strip().lower()


def dominio_reservado(endereco):
    """Diz se o domínio é de exemplo/teste e portanto foi inventado."""

    dominio = dominio_de(endereco)

    if dominio in DOMINIOS_RESERVADOS:
        return True

    return dominio.endswith(SUFIXOS_RESERVADOS)


def dominio_existe(endereco, resolver=None):
    """
    Confere se o domínio existe de fato.

    Pega erro de digitação e domínio inventado antes de tentar enviar.
    Devolve (existe, houve_falha_de_rede).
    """

    dominio = dominio_de(endereco)
    if not dominio:
        return False, False

    consultar = resolver or socket.getaddrinfo

    try:
        consultar(dominio, None)
        return True, False
    except socket.gaierror:
        pass
    except OSError:
        # Problema de rede, não do domínio.
        return True, True

    # Confere se a internet está de pé antes de culpar o domínio.
    try:
        consultar("gmail.com", None)
    except Exception:
        return True, True

    return False, False


def _normalizar(texto):
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        c for c in texto if unicodedata.category(c) != "Mn"
    )
    return " ".join(texto.split())


def endereco_valido(endereco):
    return bool(_PADRAO_EMAIL.match(str(endereco or "").strip()))


# ============================================================
# CONTATOS
# ============================================================

def _carregar_contatos():
    if not ARQUIVO_CONTATOS.exists():
        return []

    try:
        with ARQUIVO_CONTATOS.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(dados, dict):
        return []

    contatos = dados.get("contatos", [])
    if not isinstance(contatos, list):
        return []

    validos = []
    for item in contatos:
        if not isinstance(item, dict):
            continue
        nome = str(item.get("nome", "")).strip()
        email = str(item.get("email", "")).strip()
        if nome and endereco_valido(email):
            validos.append({"nome": nome, "email": email})

    return validos[:MAXIMO_CONTATOS]


def _salvar_contatos(contatos):
    ARQUIVO_CONTATOS.parent.mkdir(parents=True, exist_ok=True)

    temporario = ARQUIVO_CONTATOS.with_suffix(".tmp")
    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(
            {"versao": 1, "contatos": contatos},
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    substituir_com_retentativa(temporario, ARQUIVO_CONTATOS)


def salvar_contato(nome, email):
    """Guarda um endereço para poder dizer só o nome depois."""

    nome = " ".join(str(nome or "").split()).strip()
    email = str(email or "").strip()

    if not nome:
        return "Diga o nome do contato."

    if not endereco_valido(email):
        return (
            f"O endereço '{email}' não parece um e-mail válido. "
            "Confira e diga de novo, soletrando se precisar."
        )

    if dominio_reservado(email):
        return (
            f"O endereço '{email}' usa um domínio de exemplo e não existe "
            "de verdade. Peça o endereço real ao usuário."
        )

    with _LOCK:
        contatos = _carregar_contatos()

        for contato in contatos:
            if _normalizar(contato["nome"]) == _normalizar(nome):
                anterior = contato["email"]
                contato["email"] = email
                _salvar_contatos(contatos)
                return (
                    f"Atualizei o contato {nome}: de {anterior} para {email}."
                )

        if len(contatos) >= MAXIMO_CONTATOS:
            return (
                f"A agenda de contatos atingiu o limite de {MAXIMO_CONTATOS}. "
                "Peça para remover algum antes."
            )

        contatos.append({"nome": nome, "email": email})
        _salvar_contatos(contatos)

    return f"Guardei o contato {nome} com o e-mail {email}."


def listar_contatos():
    with _LOCK:
        contatos = _carregar_contatos()

    if not contatos:
        return "Não tenho nenhum contato de e-mail guardado ainda."

    linhas = [f"- {c['nome']}: {c['email']}" for c in contatos]
    return "Contatos guardados:\n" + "\n".join(linhas)


def remover_contato(nome):
    nome = str(nome or "").strip()
    if not nome:
        return "Diga qual contato devo remover."

    procurado = _normalizar(nome)

    with _LOCK:
        contatos = _carregar_contatos()

        for contato in list(contatos):
            if procurado in _normalizar(contato["nome"]):
                contatos.remove(contato)
                _salvar_contatos(contatos)
                return f"Removi o contato {contato['nome']}."

    return f"Não encontrei nenhum contato chamado {nome}."


def resolver_destinatario(destinatario):
    """
    Traduz o que foi falado num endereço de e-mail.

    Aceita o endereço pronto ou o nome de um contato guardado. Devolve
    (endereco, mensagem_de_erro); um dos dois é sempre None.
    """

    destinatario = str(destinatario or "").strip()

    if not destinatario:
        return None, "Diga para quem devo enviar o e-mail."

    if endereco_valido(destinatario):
        if dominio_reservado(destinatario):
            return None, (
                f"O endereço {destinatario} usa um domínio de exemplo, que "
                "não recebe e-mail de verdade. Eu não invento endereço: "
                "pergunte ao usuário para quem ele quer enviar."
            )

        existe, falha_de_rede = dominio_existe(destinatario)
        if not existe:
            return None, (
                f"O domínio de {destinatario} não existe. "
                "Confira o endereço com o usuário, letra por letra se "
                "precisar. Nada foi enviado."
            )

        return destinatario, None

    procurado = _normalizar(destinatario)
    contatos = _carregar_contatos()

    exatos = [c for c in contatos if _normalizar(c["nome"]) == procurado]
    parciais = [c for c in contatos if procurado in _normalizar(c["nome"])]

    candidatos = exatos or parciais

    if len(candidatos) == 1:
        return candidatos[0]["email"], None

    if len(candidatos) > 1:
        nomes = ", ".join(c["nome"] for c in candidatos)
        return None, (
            f"Tenho mais de um contato parecido com {destinatario}: {nomes}. "
            "Diga qual deles."
        )

    return None, (
        f"Não tenho o e-mail de {destinatario} guardado, e o que você disse "
        "não parece um endereço. Diga o endereço completo, ou peça para eu "
        "guardar o contato primeiro."
    )


# ============================================================
# LOCALIZAR O ANEXO
# ============================================================

def localizar_arquivo(nome):
    """
    Acha um arquivo pelo nome nas pastas onde as pessoas guardam coisas.

    Devolve (lista_de_caminhos_encontrados). Mais de um resultado
    significa que o ALF precisa perguntar qual, em vez de escolher.
    """

    from actions.vscode_actions import _raizes_de_busca

    texto = str(nome or "").strip().strip('"').strip("'")
    if not texto:
        return []

    direto = Path(texto).expanduser()
    if direto.is_file():
        return [direto.resolve()]

    procurado = _normalizar(texto)
    com_extensao = "." in Path(texto).name

    exatos = []
    parciais = []

    for raiz in _raizes_de_busca():
        if not raiz.is_dir():
            continue

        try:
            candidatos = list(raiz.iterdir()) + [
                item
                for sub in raiz.iterdir()
                if sub.is_dir() and not sub.name.startswith(".")
                for item in sub.iterdir()
            ]
        except (OSError, PermissionError):
            continue

        for item in candidatos:
            if not item.is_file():
                continue

            # Arquivos ocultos entram na busca de propósito: o .env
            # precisa ser encontrado para ser recusado com a mensagem
            # certa ("parece guardar senha ou chave") em vez de um
            # "não encontrei" que esconde o motivo.

            nome_normalizado = _normalizar(item.name)
            sem_extensao = _normalizar(item.stem)

            if nome_normalizado == procurado or (
                not com_extensao and sem_extensao == procurado
            ):
                if item.resolve() not in exatos:
                    exatos.append(item.resolve())
            elif procurado in sem_extensao:
                if item.resolve() not in parciais:
                    parciais.append(item.resolve())

    encontrados = exatos or parciais

    # Do mais recente para o mais antigo: "o relatório" costuma ser o
    # último que a pessoa mexeu.
    encontrados.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return encontrados


def validar_anexo(caminho):
    """
    Devolve (Path, erro). Um dos dois é sempre None.
    """

    from actions.codigo_actions import RAIZ_PERMITIDA, parece_secreto

    encontrados = localizar_arquivo(caminho)

    if not encontrados:
        return None, (
            f"Não encontrei nenhum arquivo chamado {caminho} na Área de "
            "Trabalho, Documentos ou Downloads. Confira o nome, ou diga o "
            "caminho completo. Nada foi preparado."
        )

    if len(encontrados) > 1:
        nomes = ", ".join(item.name for item in encontrados[:5])
        return None, (
            f"Encontrei mais de um arquivo parecido com {caminho}: {nomes}. "
            "Pergunte ao usuário qual deles é."
        )

    arquivo = encontrados[0]

    # A checagem de segredo vem primeiro de propósito. Um arquivo de
    # credenciais é um segredo esteja ele onde estiver, e essa é a
    # informação que o usuário precisa ouvir -- dizer apenas "fica fora
    # da sua pasta" esconderia o motivo real da recusa.
    #
    # Anexar é pior que ler: manda o conteúdo para fora da máquina.
    # O .env carrega a chave do Gemini e a senha de app do e-mail.
    if parece_secreto(arquivo):
        return None, (
            f"O arquivo {arquivo.name} parece guardar senha ou chave. "
            "Não anexo arquivos assim: enviar um deles vazaria suas "
            "credenciais para fora do computador."
        )

    try:
        arquivo.resolve().relative_to(RAIZ_PERMITIDA)
    except ValueError:
        return None, (
            "Esse arquivo fica fora da sua pasta de usuário. "
            "Por segurança não anexo arquivos de fora dela."
        )

    if arquivo.suffix.lower() in EXTENSOES_BLOQUEADAS:
        return None, (
            f"{arquivo.name} é um programa executável. Provedores de "
            "e-mail bloqueiam esse tipo de anexo. Compacte em .zip se "
            "precisar mesmo enviar."
        )

    try:
        tamanho = arquivo.stat().st_size
    except OSError as falha:
        return None, f"Não consegui acessar o arquivo: {falha}"

    if tamanho > MAXIMO_ANEXO:
        return None, (
            f"{arquivo.name} tem {tamanho // (1024 * 1024)} MB, acima do "
            f"limite de {MAXIMO_ANEXO // (1024 * 1024)} MB. "
            "Compacte o arquivo ou use um link compartilhado."
        )

    if tamanho == 0:
        return None, f"{arquivo.name} está vazio. Confira se é esse mesmo."

    return arquivo, None


def _descrever_tamanho(bytes_):
    if bytes_ >= 1024 * 1024:
        return f"{bytes_ / (1024 * 1024):.1f} MB"
    return f"{max(1, bytes_ // 1024)} KB"


# ============================================================
# CONFIGURAÇÃO SMTP
# ============================================================

def configuracao_smtp():
    """Devolve (servidor, porta, erro)."""

    if not EMAIL_REMETENTE or not EMAIL_SENHA_APP:
        return None, None, (
            "O envio de e-mail ainda não está configurado. "
            "Falta preencher EMAIL_REMETENTE e EMAIL_SENHA_APP no arquivo "
            ".env, usando uma senha de app da sua conta."
        )

    if EMAIL_SMTP_SERVIDOR:
        porta = EMAIL_SMTP_PORTA or 587
        return EMAIL_SMTP_SERVIDOR, int(porta), None

    dominio = EMAIL_REMETENTE.split("@")[-1].lower()
    conhecido = SERVIDORES_CONHECIDOS.get(dominio)

    if conhecido:
        servidor, porta = conhecido
        return servidor, int(EMAIL_SMTP_PORTA or porta), None

    return None, None, (
        f"Não sei qual servidor de e-mail usar para {dominio}. "
        "Preencha EMAIL_SMTP_SERVIDOR no arquivo .env."
    )


# ============================================================
# PREPARAR E CONFIRMAR
# ============================================================

def preparar_email(destinatario, assunto, mensagem, anexo=None):
    """
    Monta o rascunho e devolve a leitura para conferência.

    NÃO envia nada. O envio só acontece em confirmar_envio_email().
    """

    _, _, erro_config = configuracao_smtp()
    if erro_config:
        return erro_config

    endereco, erro = resolver_destinatario(destinatario)
    if erro:
        return erro

    assunto = " ".join(str(assunto or "").split()).strip()
    mensagem = str(mensagem or "").strip()

    if not assunto:
        return "Qual deve ser o assunto do e-mail?"

    if not mensagem:
        return "O que devo escrever no corpo do e-mail?"

    if len(assunto) > MAXIMO_ASSUNTO:
        return f"O assunto passou de {MAXIMO_ASSUNTO} caracteres. Resuma."

    if len(mensagem) > MAXIMO_MENSAGEM:
        return f"A mensagem passou de {MAXIMO_MENSAGEM} caracteres. Resuma."

    caminho_anexo = None
    descricao_anexo = ""

    if anexo:
        caminho_anexo, erro_anexo = validar_anexo(anexo)
        if erro_anexo:
            return erro_anexo

        tamanho = _descrever_tamanho(caminho_anexo.stat().st_size)
        descricao_anexo = (
            f"Anexo: {caminho_anexo.name}, {tamanho}, "
            f"da pasta {caminho_anexo.parent.name}. "
        )

    with _LOCK:
        _rascunho["dados"] = {
            "destinatario": endereco,
            "assunto": assunto,
            "mensagem": mensagem,
            "anexo": str(caminho_anexo) if caminho_anexo else None,
        }
        _rascunho["momento"] = time.monotonic()

    return (
        "Rascunho pronto, ainda NÃO enviado. "
        f"Para: {endereco}. "
        f"Assunto: {assunto}. "
        f"Mensagem: {mensagem} "
        f"{descricao_anexo}"
        "Leia isso em voz alta para o usuário, exatamente como está, "
        "incluindo o nome do arquivo anexado se houver, e pergunte se "
        "pode enviar. Só chame confirmar_envio_email depois que ele "
        "responder que sim."
    )


def rascunho_pendente():
    """Devolve o rascunho válido, ou None se não houver ou tiver expirado."""

    dados = _rascunho["dados"]
    if dados is None:
        return None

    if time.monotonic() - _rascunho["momento"] > VALIDADE_RASCUNHO:
        _rascunho["dados"] = None
        return None

    return dados


def cancelar_email():
    with _LOCK:
        tinha = _rascunho["dados"] is not None
        _rascunho["dados"] = None

    if tinha:
        return "Descartei o rascunho. Nada foi enviado."

    return "Não havia nenhum e-mail esperando envio."


def _montar_mensagem(dados):
    email_msg = EmailMessage()
    email_msg["From"] = formataddr(
        (EMAIL_NOME_REMETENTE or parseaddr(EMAIL_REMETENTE)[0] or "", EMAIL_REMETENTE)
    )
    email_msg["To"] = dados["destinatario"]
    email_msg["Subject"] = dados["assunto"]
    email_msg.set_content(dados["mensagem"])

    caminho = dados.get("anexo")
    if caminho:
        arquivo = Path(caminho)
        tipo, _ = mimetypes.guess_type(arquivo.name)
        principal, _, secundario = (tipo or "application/octet-stream").partition("/")

        email_msg.add_attachment(
            arquivo.read_bytes(),
            maintype=principal,
            subtype=secundario or "octet-stream",
            filename=arquivo.name,
        )

    return email_msg


def confirmar_envio_email(enviar=None):
    """
    Envia o rascunho pendente.

    O parâmetro enviar existe para os testes trocarem o envio real.
    """

    with _LOCK:
        dados = rascunho_pendente()

        if dados is None:
            return (
                "Não há nenhum e-mail pronto para enviar. "
                "Monte o e-mail primeiro; se já fazia tempo, o rascunho "
                "expirou por segurança e precisa ser refeito."
            )

        servidor, porta, erro_config = configuracao_smtp()
        if erro_config:
            return erro_config

        email_msg = _montar_mensagem(dados)

        try:
            if enviar is not None:
                enviar(email_msg, servidor, porta)
            else:
                # O contexto tolerante é necessário porque antivírus que
                # inspecionam e-mail (Avast Mail Shield) trocam o
                # certificado do servidor por um gerado na hora, que o
                # OpenSSL 3.x recusa sob verificação estrita.
                contexto = criar_contexto_ssl_compativel()
                with smtplib.SMTP(servidor, porta, timeout=30) as conexao:
                    conexao.starttls(context=contexto)
                    conexao.login(EMAIL_REMETENTE, EMAIL_SENHA_APP)
                    conexao.send_message(email_msg)

        except smtplib.SMTPAuthenticationError:
            return (
                "O servidor recusou o login. Confira se EMAIL_SENHA_APP no "
                ".env é uma senha de app, e não a senha normal da conta. "
                "O e-mail NÃO foi enviado."
            )
        except (smtplib.SMTPException, OSError) as erro:
            return (
                f"Não consegui enviar o e-mail: {erro}. "
                "Ele NÃO foi enviado; o rascunho continua guardado."
            )

        # Só descarta o rascunho depois do envio dar certo.
        _rascunho["dados"] = None

    if dados.get("anexo"):
        return (
            f"E-mail enviado para {dados['destinatario']} "
            f"com o assunto {dados['assunto']} e o anexo "
            f"{Path(dados['anexo']).name}."
        )

    return (
        f"E-mail enviado para {dados['destinatario']} "
        f"com o assunto {dados['assunto']}."
    )
