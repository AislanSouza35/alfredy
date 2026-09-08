"""
Ações executadas dentro do VS Code.

Abrir o VS Code já funcionava, mas ele abria vazio: não havia nenhum
caminho para pedir "abre a pasta X no VS Code". O modelo tentava
improvisar com atalhos de teclado (ctrl+k ctrl+o) e depois teria que
navegar numa caixa de diálogo de arquivos por reconhecimento visual --
lento e quase sempre errado.

O VS Code aceita o caminho direto na linha de comando, que é o jeito
certo e instantâneo. Para o resto (comandos internos que não têm
equivalente na linha de comando), a paleta de comandos é acionada de
uma vez só, sem depender de vários turnos de conversa.
"""

import os
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

from actions.text_actions import escrever_no_campo_ativo, pressionar_atalho_teclado


# Evita a janela de console ao iniciar o VS Code por um .cmd.
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Quantas pastas abaixo de cada raiz a busca desce. Dois níveis cobrem
# "Downloads/Projetos/MeuApp" sem varrer o disco inteiro.
PROFUNDIDADE_BUSCA = 2

# Pastas que nunca entram na busca: são grandes e não interessam.
PASTAS_IGNORADAS = {
    "node_modules",
    "venv",
    ".venv",
    ".git",
    "__pycache__",
    "appdata",
    "dist",
    "build",
    ".cache",
}


def _normalizar(texto):
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )
    return " ".join(texto.split())


def localizar_executavel_vscode():
    """
    Encontra o VS Code.

    Prefere o Code.exe ao code.cmd: o .cmd é um script de lote e o
    Windows não o executa diretamente por CreateProcess, além de piscar
    console.
    """

    candidatos = []

    local = os.getenv("LOCALAPPDATA")
    if local:
        candidatos.append(
            Path(local) / "Programs" / "Microsoft VS Code" / "Code.exe"
        )

    for variavel in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.getenv(variavel)
        if base:
            candidatos.append(
                Path(base) / "Microsoft VS Code" / "Code.exe"
            )

    for candidato in candidatos:
        if candidato.is_file():
            return candidato

    encontrado = shutil.which("Code.exe") or shutil.which("code")
    if encontrado:
        return Path(encontrado)

    return None


def _raizes_de_busca():
    """Pastas onde faz sentido procurar um projeto do usuário."""

    inicio = Path.home()
    raizes = [inicio]

    for nome in (
        "OneDrive/Área de Trabalho",
        "OneDrive/Desktop",
        "Desktop",
        "Documents",
        "OneDrive/Documentos",
        "Documentos",
        "Downloads",
        "Projetos",
        "Projects",
        "source/repos",
    ):
        caminho = inicio / nome
        if caminho.is_dir():
            raizes.append(caminho)

    return raizes


def localizar_pasta(nome):
    """
    Traduz o que o usuário falou num caminho real de pasta.

    Aceita caminho absoluto pronto ou apenas o nome, procurando nas
    pastas onde as pessoas guardam projetos.
    """

    nome = str(nome or "").strip().strip('"').strip("'")
    if not nome:
        return None

    direto = Path(nome).expanduser()
    if direto.is_dir():
        return direto.resolve()

    procurado = _normalizar(nome)

    exatas = []
    parciais = []

    for raiz in _raizes_de_busca():
        for atual, subpastas, _ in os.walk(raiz):
            caminho_atual = Path(atual)

            profundidade = len(caminho_atual.relative_to(raiz).parts)
            if profundidade >= PROFUNDIDADE_BUSCA:
                subpastas.clear()
                continue

            subpastas[:] = [
                sub
                for sub in subpastas
                if _normalizar(sub) not in PASTAS_IGNORADAS
                and not sub.startswith(".")
            ]

            for sub in subpastas:
                normalizado = _normalizar(sub)
                if normalizado == procurado:
                    exatas.append(caminho_atual / sub)
                elif procurado in normalizado:
                    parciais.append(caminho_atual / sub)

        if exatas:
            break

    candidatos = exatas or parciais
    if not candidatos:
        return None

    # O caminho mais curto costuma ser a pasta principal, não uma
    # subpasta com nome parecido.
    candidatos.sort(key=lambda item: len(str(item)))
    return candidatos[0].resolve()


def abrir_no_vscode(caminho, nova_janela=False):
    """
    Abre uma pasta ou arquivo dentro do VS Code.

    Passar o caminho na linha de comando é o jeito suportado pelo
    próprio VS Code, instantâneo e sem depender de caixa de diálogo.
    """

    caminho = str(caminho or "").strip()
    if not caminho:
        return "Diga qual pasta ou arquivo devo abrir no VS Code."

    executavel = localizar_executavel_vscode()
    if executavel is None:
        return (
            "Não encontrei o VS Code instalado neste computador. "
            "Confira se ele está instalado."
        )

    alvo = localizar_pasta(caminho)

    if alvo is None:
        # Pode ser um arquivo, não uma pasta.
        possivel_arquivo = Path(caminho).expanduser()
        if possivel_arquivo.is_file():
            alvo = possivel_arquivo.resolve()

    if alvo is None:
        return (
            f"Não encontrei nenhuma pasta chamada {caminho} na Área de "
            "Trabalho, Documentos, Downloads ou na sua pasta de usuário. "
            "Diga o caminho completo, ou o nome exato da pasta."
        )

    argumentos = [str(executavel)]
    if nova_janela:
        argumentos.append("--new-window")
    else:
        argumentos.append("--reuse-window")
    argumentos.append(str(alvo))

    try:
        subprocess.Popen(
            argumentos,
            creationflags=SEM_JANELA if sys.platform.startswith("win") else 0,
        )
    except OSError as erro:
        return f"Não consegui iniciar o VS Code: {erro}"

    tipo = "pasta" if alvo.is_dir() else "arquivo"
    return f"Abri a {tipo} {alvo.name} no VS Code."


# ============================================================
# PALETA DE COMANDOS
# ============================================================
#
# Para o que não existe na linha de comando. A paleta é textual, então
# é bem mais confiável que procurar item de menu por imagem.
#
# Comandos que fecham, apagam ou desinstalam ficam de fora: eles
# poderiam perder trabalho sem o usuário ver o que aconteceu.
COMANDOS_BLOQUEADOS = (
    "uninstall",
    "desinstalar",
    "delete",
    "excluir",
    "apagar",
    "remove folder",
    "remover pasta",
    "reset",
    "redefinir",
    "clear editor history",
    "developer: reload",
)

# Tempo para a paleta aparecer e para a lista filtrar antes do Enter.
ESPERA_PALETA = 0.45
ESPERA_FILTRO = 0.65


def executar_comando_vscode(comando, pausa=time.sleep):
    """
    Executa um comando interno pela paleta do VS Code.

    Faz a sequência inteira de uma vez -- abrir a paleta, digitar e
    confirmar -- porque dividir isso em três pedidos separados do
    modelo deixava o VS Code perder o foco no meio do caminho.
    """

    comando = str(comando or "").strip()
    if not comando:
        return "Diga qual comando do VS Code devo executar."

    normalizado = _normalizar(comando)
    for bloqueado in COMANDOS_BLOQUEADOS:
        if bloqueado in normalizado:
            return (
                "Esse comando do VS Code foi bloqueado por segurança, "
                "porque poderia remover ou redefinir algo sem revisão. "
                "Faça essa ação manualmente."
            )

    resultado = pressionar_atalho_teclado("ctrl+shift+p")
    if "bloqueado" in resultado.lower() or "desconhecid" in resultado.lower():
        return f"Não consegui abrir a paleta de comandos: {resultado}"

    pausa(ESPERA_PALETA)

    escrita = escrever_no_campo_ativo(comando)
    if "não" in escrita.lower() and "possível" in escrita.lower():
        return f"Não consegui digitar o comando: {escrita}"

    pausa(ESPERA_FILTRO)
    pressionar_atalho_teclado("enter")

    return (
        f"Executei o comando '{comando}' na paleta do VS Code. "
        "Confira na tela se era o comando esperado."
    )
