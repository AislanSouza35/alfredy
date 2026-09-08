"""
Ler, criar e executar código.

Até aqui o ALF só conseguia ditar código para dentro de um editor já
aberto: não criava arquivo com conteúdo, não lia o que já existia e não
rodava nada. Ou seja, escrevia código novo bem, mas ficava cego diante
de código existente.

As três funções deste módulo fecham isso. Como elas mexem em arquivos
fora da Área de Trabalho e executam programas, cada uma tem limites
explícitos, descritos junto de cada trava.
"""

import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path


SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ============================================================
# ONDE É PERMITIDO MEXER
# ============================================================
#
# Tudo fica restrito à pasta do usuário. Fora dela ficam o Windows, os
# programas instalados e as configurações do sistema -- lugares onde um
# engano não tem volta e que nada tem a ver com programar.
RAIZ_PERMITIDA = Path.home().resolve()

# Dentro da pasta do usuário ainda existem áreas que não são projeto:
# credenciais, chaves e dados de aplicativos.
PASTAS_PROIBIDAS = {
    "appdata",
    ".ssh",
    ".aws",
    ".gnupg",
    ".config/gcloud",
    ".azure",
    ".kube",
    ".docker",
}

# Arquivos que costumam guardar segredo. Isto importa mais aqui do que
# em outros projetos: o ALF LÊ EM VOZ ALTA o que recebe. Ler o .env
# faria ele falar a GEMINI_API_KEY e a senha de app do e-mail.
PADROES_SECRETOS = (
    r"^\.env",
    r"\.env$",
    r"^id_rsa",
    r"^id_ed25519",
    r"\.pem$",
    r"\.pfx$",
    r"\.p12$",
    r"\.key$",
    r"credentials",
    r"credenciais",
    r"client_secret",
    r"senha",
    r"password",
    r"secrets?\.(json|ya?ml|txt)$",
    # Token OAuth do Classroom: dá acesso contínuo à conta Google do
    # usuário, então vale o mesmo cuidado do .env.
    r"token",
)

_SECRETOS = tuple(re.compile(p, re.IGNORECASE) for p in PADROES_SECRETOS)

# Limites de tamanho.
MAXIMO_LEITURA = 120_000
MAXIMO_ESCRITA = 200_000
MAXIMO_SAIDA_TERMINAL = 6_000


def _normalizar(texto):
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def parece_secreto(caminho):
    nome = Path(str(caminho)).name
    return any(padrao.search(nome) for padrao in _SECRETOS)


def _dentro_da_raiz(caminho):
    try:
        caminho.resolve().relative_to(RAIZ_PERMITIDA)
        return True
    except ValueError:
        return False


def _em_pasta_proibida(caminho):
    try:
        relativo = caminho.resolve().relative_to(RAIZ_PERMITIDA)
    except ValueError:
        return True

    partes = [_normalizar(p) for p in relativo.parts]
    caminho_normalizado = "/".join(partes)

    for proibida in PASTAS_PROIBIDAS:
        if proibida in partes or caminho_normalizado.startswith(proibida + "/"):
            return True

    return False


def validar_caminho(caminho, para_escrita=False):
    """
    Devolve (Path, erro). Um dos dois é sempre None.
    """

    texto = str(caminho or "").strip().strip('"').strip("'")

    if not texto:
        return None, "Diga qual arquivo."

    alvo = Path(texto).expanduser()

    if not alvo.is_absolute():
        # Reaproveita a busca do módulo do VS Code para achar a pasta
        # do projeto pelo nome, e resolve o arquivo dentro dela.
        from actions.vscode_actions import localizar_pasta

        partes = Path(texto).parts
        pasta = localizar_pasta(partes[0]) if partes else None

        if pasta is not None and len(partes) > 1:
            alvo = pasta.joinpath(*partes[1:])
        elif pasta is not None:
            alvo = pasta
        else:
            # Ancora na raiz permitida, não em Path.home() direto, para
            # que a checagem de pasta proibida logo abaixo seja aplicada
            # de forma coerente com o resto da função.
            alvo = RAIZ_PERMITIDA / texto

    if not _dentro_da_raiz(alvo):
        return None, (
            "Esse caminho fica fora da sua pasta de usuário. "
            "Por segurança só mexo em arquivos dentro dela."
        )

    if _em_pasta_proibida(alvo):
        return None, (
            "Essa pasta guarda configurações e credenciais do sistema. "
            "Não mexo nela."
        )

    if parece_secreto(alvo):
        return None, (
            f"O arquivo {alvo.name} parece guardar senha ou chave. "
            "Não leio nem altero arquivos assim, porque eu falo em voz "
            "alta o que leio. Abra você mesmo se precisar."
        )

    return alvo, None


# ============================================================
# LER
# ============================================================

def ler_arquivo(caminho):
    """
    Lê um arquivo de texto para o ALF poder trabalhar sobre ele.

    Sem isto ele só enxergava o código pela captura de tela, que pega
    apenas o trecho visível e erra em identação e caracteres.
    """

    alvo, erro = validar_caminho(caminho)
    if erro:
        return erro

    if not alvo.exists():
        return (
            f"Não encontrei o arquivo {alvo.name}. "
            "Confira o nome e a pasta."
        )

    if alvo.is_dir():
        itens = sorted(
            item.name + ("/" if item.is_dir() else "")
            for item in alvo.iterdir()
            if not item.name.startswith(".")
        )
        if not itens:
            return f"A pasta {alvo.name} está vazia."
        return f"{alvo.name} é uma pasta. Contém:\n" + "\n".join(itens[:80])

    try:
        tamanho = alvo.stat().st_size
    except OSError as falha:
        return f"Não consegui acessar o arquivo: {falha}"

    if tamanho > MAXIMO_LEITURA:
        return (
            f"O arquivo {alvo.name} tem {tamanho // 1024} KB, grande demais "
            "para eu ler inteiro. Diga qual parte ou qual função te interessa."
        )

    try:
        conteudo = alvo.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return (
            f"{alvo.name} não é um arquivo de texto legível "
            "(parece binário)."
        )
    except OSError as falha:
        return f"Não consegui ler o arquivo: {falha}"

    linhas = conteudo.count("\n") + 1

    return (
        f"Conteúdo de {alvo.name} ({linhas} linhas), caminho {alvo}:\n\n"
        f"{conteudo}\n\n"
        "Use esse conteúdo como base. Não leia o código em voz alta: "
        "resuma o que ele faz, ou diga apenas o que mudou."
    )


# ============================================================
# CRIAR E ALTERAR
# ============================================================

def criar_arquivo_codigo(caminho, conteudo, sobrescrever=False):
    """
    Grava um arquivo com o conteúdo já pronto.

    Quando o arquivo já existe, a versão anterior é copiada para um
    .bak com data e hora antes de gravar. O projeto inteiro segue a
    regra de nunca destruir nada sem deixar volta, e escrever código
    não é exceção.
    """

    alvo, erro = validar_caminho(caminho, para_escrita=True)
    if erro:
        return erro

    if conteudo is None:
        return "Diga o que devo escrever no arquivo."

    conteudo = str(conteudo)

    if len(conteudo) > MAXIMO_ESCRITA:
        return (
            f"O conteúdo passou de {MAXIMO_ESCRITA // 1000} mil caracteres. "
            "Divida em arquivos menores."
        )

    if alvo.is_dir():
        return f"{alvo.name} é uma pasta, não um arquivo."

    existia = alvo.exists()

    if existia and not sobrescrever:
        return (
            f"O arquivo {alvo.name} já existe. "
            "Se quiser mesmo substituir o conteúdo, confirme com o usuário "
            "e chame de novo com sobrescrever igual a verdadeiro. "
            "A versão atual será guardada como cópia de segurança."
        )

    copia = None
    try:
        alvo.parent.mkdir(parents=True, exist_ok=True)

        if existia:
            carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
            copia = alvo.with_name(f"{alvo.name}.{carimbo}.bak")
            shutil.copy2(alvo, copia)

        # Garante quebra de linha final, como todo editor faz.
        if conteudo and not conteudo.endswith("\n"):
            conteudo += "\n"

        alvo.write_text(conteudo, encoding="utf-8")

    except OSError as falha:
        return f"Não consegui gravar o arquivo: {falha}"

    linhas = conteudo.count("\n")

    if existia:
        return (
            f"Substituí {alvo.name} ({linhas} linhas). "
            f"A versão anterior ficou guardada como {copia.name}."
        )

    return f"Criei {alvo.name} com {linhas} linhas em {alvo.parent}."


# ============================================================
# EXECUTAR
# ============================================================
#
# Rodar comando é a única coisa aqui que pode causar dano fora do
# arquivo alvo, então funciona por lista fechada: o que não está
# liberado, não roda. Nada de shell, então "&&", "|" e redirecionamento
# não existem -- não há como encadear um comando proibido.
PROGRAMAS_PERMITIDOS = {
    "python",
    "python3",
    "py",
    "pip",
    "pytest",
    "node",
    "npm",
    "git",
    "java",
    "javac",
    "mvn",
    "dotnet",
}

# Subcomandos do git que só leem ou registram localmente. Ficam de fora
# os que publicam (push) e os que apagam trabalho (reset, clean).
GIT_PERMITIDO = {
    "status",
    "log",
    "diff",
    "show",
    "branch",
    "add",
    "commit",
    "fetch",
    "remote",
    "stash",
    "config",
}

# Trechos que denunciam intenção destrutiva mesmo dentro de um programa
# permitido.
ARGUMENTOS_PROIBIDOS = (
    "--force",
    "-rf",
    "-fr",
    "uninstall",
    "--hard",
    "--delete",
    "rimraf",
    "publish",
)


def _programa_de(comando):
    return Path(comando[0]).stem.lower()


def executar_no_terminal(comando, pasta=None, timeout=120):
    """
    Executa um comando de desenvolvimento e devolve a saída.

    Serve para rodar o código escrito, instalar dependência e conferir
    o estado do git -- sem isso o ALF escrevia código sem nunca saber
    se funcionava.
    """

    if isinstance(comando, str):
        texto = comando.strip()

        # Sem shell, então metacaractere não seria interpretado; recusar
        # deixa claro para o modelo que encadear não é o caminho.
        for simbolo in ("&&", "||", "|", ";", ">", "<", "`", "$("):
            if simbolo in texto:
                return (
                    "Não executo vários comandos encadeados. "
                    "Peça um comando de cada vez."
                )

        partes = texto.split()
    else:
        partes = [str(p) for p in (comando or [])]

    if not partes:
        return "Diga qual comando devo executar."

    programa = _programa_de(partes)

    if programa not in PROGRAMAS_PERMITIDOS:
        permitidos = ", ".join(sorted(PROGRAMAS_PERMITIDOS))
        return (
            f"Não posso executar '{partes[0]}'. "
            f"Só rodo estes programas: {permitidos}."
        )

    resto = [p.lower() for p in partes[1:]]

    if programa == "git":
        if not resto or resto[0] not in GIT_PERMITIDO:
            return (
                "Desse comando do git eu não cuido. "
                "Posso rodar status, log, diff, add, commit e semelhantes, "
                "mas não push, reset nem clean -- publicar ou apagar "
                "histórico tem que ser você."
            )

    for proibido in ARGUMENTOS_PROIBIDOS:
        if any(proibido in argumento for argumento in resto):
            return (
                f"O comando tem '{proibido}', que pode apagar ou publicar "
                "coisas. Faça essa parte manualmente."
            )

    diretorio = None
    if pasta:
        diretorio, erro = validar_caminho(pasta)
        if erro:
            return erro
        if not diretorio.is_dir():
            return f"A pasta {pasta} não existe."

    executavel = shutil.which(partes[0])
    if executavel is None:
        return (
            f"O programa '{partes[0]}' não está instalado ou não está no PATH."
        )

    try:
        resultado = subprocess.run(
            [executavel] + partes[1:],
            cwd=str(diretorio) if diretorio else str(RAIZ_PERMITIDA),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=SEM_JANELA if sys.platform.startswith("win") else 0,
        )
    except subprocess.TimeoutExpired:
        return (
            f"O comando passou de {timeout} segundos e foi interrompido. "
            "Ele pode estar esperando alguma resposta no terminal."
        )
    except OSError as falha:
        return f"Não consegui executar o comando: {falha}"

    saida = (resultado.stdout or "") + (resultado.stderr or "")
    saida = saida.strip()

    if len(saida) > MAXIMO_SAIDA_TERMINAL:
        saida = saida[:MAXIMO_SAIDA_TERMINAL] + "\n[...saída cortada...]"

    if not saida:
        saida = "(sem saída)"

    situacao = "concluído" if resultado.returncode == 0 else f"terminou com erro (código {resultado.returncode})"

    return (
        f"Comando {situacao}.\n\n{saida}\n\n"
        "Resuma o resultado em voz alta. Se houve erro, diga qual foi e "
        "o que pretende fazer, sem ler a saída inteira."
    )
