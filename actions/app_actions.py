import ctypes
import os
import shutil
import subprocess
import sys
import time
import unicodedata
import webbrowser
from ctypes import wintypes
from pathlib import Path
from urllib.parse import quote_plus


# Rodando por pythonw.exe o ALF não tem console. Quando ele cria um
# processo filho de linha de comando, o Windows abre um console novo
# só para esse filho -- era a "tela preta do Python" que aparecia e
# sumia ao pedir para abrir alguma coisa. Esta flag impede a criação
# dessa janela.
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _flags_sem_console(ocultar):
    if ocultar and sys.platform.startswith("win"):
        return {"creationflags": SEM_JANELA}
    return {}


def normalizar_texto(texto):
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(caractere for caractere in texto if unicodedata.category(caractere) != "Mn")


def executar_comando(comando, ocultar_console=True):
    """
    Inicia um programa.

    ocultar_console fica ligado por padrão porque a maioria dos alvos é
    aplicativo gráfico. Passe False quando o console FOR o programa
    pedido, como no cmd e no PowerShell.
    """
    subprocess.Popen(
        comando,
        shell=False,
        **_flags_sem_console(ocultar_console),
    )


def abrir_url(url):
    webbrowser.open(url)


def localizar_pasta_usuario(nomes):
    usuario = Path.home()
    onedrive = Path(os.getenv("OneDrive", usuario / "OneDrive"))
    bases = [usuario, onedrive]
    for base in bases:
        for nome in nomes:
            caminho = base / nome
            if caminho.exists() and caminho.is_dir():
                return caminho
    return None


def abrir_pasta_usuario(tipo):
    pastas = {
        "documentos": ["Documents", "Documentos"],
        "downloads": ["Downloads"],
        "videos": ["Videos", "Vídeos"],
        "musicas": ["Music", "Músicas"],
    }
    nomes = pastas.get(tipo)
    if not nomes:
        return False
    caminho = localizar_pasta_usuario(nomes)
    if not caminho:
        return False
    os.startfile(str(caminho))
    return True


def pastas_menu_iniciar():
    caminhos = []
    appdata = os.getenv("APPDATA")
    programdata = os.getenv("PROGRAMDATA")
    if appdata:
        caminhos.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if programdata:
        caminhos.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return [caminho for caminho in caminhos if caminho.exists()]


def procurar_atalho_menu_iniciar(nome):
    procurado = normalizar_texto(nome)
    exatos = []
    parciais = []
    for pasta in pastas_menu_iniciar():
        for extensao in ("*.lnk", "*.url"):
            for atalho in pasta.rglob(extensao):
                nome_atalho = normalizar_texto(atalho.stem)
                if nome_atalho == procurado:
                    exatos.append(atalho)
                elif procurado in nome_atalho:
                    parciais.append(atalho)
    candidatos = exatos or parciais
    if not candidatos:
        return None
    candidatos.sort(key=lambda item: len(item.stem))
    return candidatos[0]


# A lista de aplicativos instalados não muda enquanto o ALF está
# aberto, e consultá-la custa alguns segundos. Guardar o resultado faz
# o segundo "abra o X" responder na hora.
_CACHE_APPS = {"valor": None, "momento": 0.0}
VALIDADE_CACHE_APPS = 300.0


def listar_aplicativos_windows(usar_cache=True):
    agora = time.monotonic()

    if (
        usar_cache
        and _CACHE_APPS["valor"] is not None
        and agora - _CACHE_APPS["momento"] < VALIDADE_CACHE_APPS
    ):
        return _CACHE_APPS["valor"]

    comando = "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
    try:
        resultado = subprocess.run([
            "powershell", "-NoProfile", "-Command", comando
        ], capture_output=True, text=True, encoding="utf-8", errors="ignore",
            timeout=10, check=False,
            **_flags_sem_console(True))
        if resultado.returncode != 0:
            return []
        texto = resultado.stdout.strip()
        if not texto:
            return []
        dados = __import__("json").loads(texto)
        if isinstance(dados, dict):
            dados = [dados]

        _CACHE_APPS["valor"] = dados
        _CACHE_APPS["momento"] = agora
        return dados
    except (subprocess.SubprocessError, __import__("json").JSONDecodeError, OSError):
        return []


def procurar_app_windows(nome):
    procurado = normalizar_texto(nome)
    exatos = []
    parciais = []
    for app in listar_aplicativos_windows():
        nome_app = app.get("Name", "")
        app_id = app.get("AppID", "")
        if not nome_app or not app_id:
            continue
        nome_normalizado = normalizar_texto(nome_app)
        if nome_normalizado == procurado:
            exatos.append((nome_app, app_id))
        elif procurado in nome_normalizado:
            parciais.append((nome_app, app_id))
    candidatos = exatos or parciais
    if not candidatos:
        return None
    candidatos.sort(key=lambda item: len(item[0]))
    return candidatos[0]


def abrir_app_windows(nome):
    encontrado = procurar_app_windows(nome)
    if not encontrado:
        return None
    nome_app, app_id = encontrado
    executar_comando(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
    return nome_app


# Como as pessoas FALAM o nome dos programas versus como o Windows os
# REGISTRA. O caso que motivou esta tabela: pedir "abra o VS Code"
# falhava em todos os caminhos, porque o menu iniciar registra
# "Visual Studio Code" e a comparação por substring nunca casa
# ("vs code" não está dentro de "visual studio code").
SINONIMOS_APLICATIVOS = {
    "vs code": ["visual studio code", "code"],
    "vscode": ["visual studio code", "code"],
    "vs": ["visual studio code", "code"],
    "visual code": ["visual studio code", "code"],
    "codigo": ["visual studio code", "code"],
    "visual studio": ["visual studio", "visual studio code"],
    "bloco de notas": ["notepad", "bloco de notas"],
    "navegador chrome": ["google chrome", "chrome"],
    "planilha": ["excel", "microsoft excel"],
    "planilhas": ["excel", "microsoft excel"],
    "editor de texto": ["word", "microsoft word"],
    "apresentacao": ["powerpoint", "microsoft powerpoint"],
    "powerpoint": ["powerpoint", "microsoft powerpoint"],
    "terminal": ["terminal", "windows terminal"],
    "gerenciador de tarefas": ["gerenciador de tarefas", "task manager"],
    "loja": ["microsoft store"],
    "explorer": ["explorador de arquivos"],
}


def nomes_candidatos(nome):
    """
    Devolve o nome pedido mais os sinônimos conhecidos.

    A ordem importa: o nome falado vem primeiro, para não sequestrar um
    programa que realmente se chame assim.
    """

    procurado = normalizar_texto(nome)
    candidatos = [nome]

    for apelido, alternativos in SINONIMOS_APLICATIVOS.items():
        if apelido == procurado or apelido in procurado.split(" e "):
            for alternativo in alternativos:
                if alternativo not in candidatos:
                    candidatos.append(alternativo)

    return candidatos


def abrir_executavel_conhecido(nome):
    executaveis = {
        "chrome": ["chrome.exe", "chrome"],
        "google chrome": ["chrome.exe", "chrome"],
        "edge": ["msedge.exe", "msedge"],
        "microsoft edge": ["msedge.exe", "msedge"],
        "word": ["winword.exe", "winword"],
        "microsoft word": ["winword.exe", "winword"],
        "excel": ["excel.exe", "excel"],
        "microsoft excel": ["excel.exe", "excel"],
        "steam": ["steam.exe", "steam"],
        # O VS Code não estava aqui, e era o programa do exemplo que
        # falhou. O code.cmd é o que fica no PATH numa instalação
        # normal por usuário.
        "code": ["code.cmd", "code.exe", "code"],
        "visual studio code": ["code.cmd", "code.exe", "code"],
        "powerpoint": ["powerpnt.exe", "powerpnt"],
        "microsoft powerpoint": ["powerpnt.exe", "powerpnt"],
        "firefox": ["firefox.exe", "firefox"],
        "notepad++": ["notepad++.exe"],
    }
    procurado = normalizar_texto(nome)
    candidatos = executaveis.get(procurado, [])
    for executavel in candidatos:
        caminho = shutil.which(executavel)
        if caminho:
            executar_comando([caminho])
            return True
    return False


def abrir_especial(nome):
    nome = normalizar_texto(nome)
    aliases = {
        "meu computador": "meu_computador",
        "este computador": "meu_computador",
        "computador": "meu_computador",
        "explorador de arquivos": "explorador",
        "explorador": "explorador",
        "navegador": "navegador",
        "google": "navegador",
        "antivirus": "defender",
        "anti virus": "defender",
        "windows defender": "defender",
        "seguranca do windows": "defender",
        "configuracoes": "configuracoes",
        "calculadora": "calculadora",
        "relogio": "relogio",
        "alarme": "relogio",
        "relogio e alarmes": "relogio",
        "cmd": "cmd",
        "prompt de comando": "cmd",
        "powershell": "powershell",
        "power shell": "powershell",
        "bloco de notas": "notepad",
        "notepad": "notepad",
        "paint": "paint",
        "painel de controle": "painel",
        "meus documentos": "documentos",
        "documentos": "documentos",
        "meus downloads": "downloads",
        "downloads": "downloads",
        "meus videos": "videos",
        "videos": "videos",
        "minhas musicas": "musicas",
        "musicas": "musicas",
    }
    for apelido in sorted(aliases, key=len, reverse=True):
        if apelido in nome:
            acao = aliases[apelido]
            if acao == "meu_computador":
                executar_comando(["explorer.exe", "shell:MyComputerFolder"])
                return "Abrindo Meu Computador."
            if acao == "explorador":
                executar_comando(["explorer.exe"])
                return "Abrindo o Explorador de Arquivos."
            if acao == "navegador":
                abrir_url("https://www.google.com")
                return "Abrindo o navegador."
            if acao == "defender":
                os.startfile("windowsdefender:")
                return "Abrindo a Segurança do Windows."
            if acao == "configuracoes":
                os.startfile("ms-settings:")
                return "Abrindo as Configurações."
            if acao == "calculadora":
                executar_comando(["calc.exe"])
                return "Abrindo a Calculadora."
            if acao == "relogio":
                os.startfile("ms-clock:")
                return "Abrindo o Relógio."
            if acao == "cmd":
                executar_comando(["cmd.exe"], ocultar_console=False)
                return "Abrindo o Prompt de Comando."
            if acao == "powershell":
                executar_comando(["powershell.exe"], ocultar_console=False)
                return "Abrindo o PowerShell."
            if acao == "notepad":
                executar_comando(["notepad.exe"])
                return "Abrindo o Bloco de Notas."
            if acao == "paint":
                executar_comando(["mspaint.exe"])
                return "Abrindo o Paint."
            if acao == "painel":
                executar_comando(["control.exe"])
                return "Abrindo o Painel de Controle."
            if acao in ("documentos", "downloads", "videos", "musicas"):
                abriu = abrir_pasta_usuario(acao)
                return "Abrindo a pasta pessoal." if abriu else f"Não consegui abrir a pasta de {acao}."
    return "Não encontrei um recurso do Windows com esse nome."


# Sites que as pessoas pedem como se fossem programas. Sem esta
# tabela, "abra o youtube" percorria todos os caminhos (app instalado,
# atalho do menu iniciar, executável conhecido, recurso do Windows) e
# terminava em "não encontrei", que era o comportamento relatado.
SITES_CONHECIDOS = {
    "youtube": "https://www.youtube.com",
    "you tube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "email": "https://mail.google.com",
    "e mail": "https://mail.google.com",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "google agenda": "https://calendar.google.com",
    "google calendar": "https://calendar.google.com",
    "google tradutor": "https://translate.google.com",
    "tradutor": "https://translate.google.com",
    "google maps": "https://www.google.com/maps",
    "maps": "https://www.google.com/maps",
    "mapas": "https://www.google.com/maps",
    "whatsapp web": "https://web.whatsapp.com",
    "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "linkedin": "https://www.linkedin.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "chatgpt": "https://chat.openai.com",
    "chat gpt": "https://chat.openai.com",
    "github": "https://github.com",
    "sigeduc": "https://sigeduc.rn.gov.br",
    "classroom": "https://classroom.google.com",
    "google classroom": "https://classroom.google.com",
    "google meet": "https://meet.google.com",
    "meet": "https://meet.google.com",
    "teams": "https://teams.microsoft.com",
    "canva": "https://www.canva.com",
    "wikipedia": "https://pt.wikipedia.org",
    "correios": "https://www.correios.com.br",
}


def abrir_site_conhecido(nome):
    """
    Abre um site quando o nome pedido corresponde a um site conhecido.

    Devolve a mensagem de confirmação, ou None quando o nome não é de
    um site — assim quem chama segue tentando os outros caminhos.
    """

    procurado = normalizar_texto(nome)

    # Correspondência exata primeiro, para "meet" não cair em
    # "google meet" nem "drive" em "google drive".
    if procurado in SITES_CONHECIDOS:
        abrir_url(SITES_CONHECIDOS[procurado])
        return f"Abrindo {nome}."

    # Depois aceita o nome dentro de uma frase, como
    # "abra o site do youtube pra mim".
    for apelido in sorted(SITES_CONHECIDOS, key=len, reverse=True):
        if apelido in procurado:
            abrir_url(SITES_CONHECIDOS[apelido])
            return f"Abrindo {apelido}."

    return None


def abrir_site_generico(nome):
    """
    Último recurso para nomes que parecem endereço de internet.

    Cobre pedidos como "abra o site tabnews.com.br", que não estão na
    tabela acima e não são programas instalados.
    """

    texto = str(nome or "").strip()

    if " " in texto:
        return None

    if texto.lower().startswith(("http://", "https://")):
        abrir_url(texto)
        return f"Abrindo {texto}."

    # Precisa parecer um domínio: tem ponto e termina em letras.
    if "." in texto and texto.rsplit(".", 1)[-1].isalpha():
        abrir_url("https://" + texto)
        return f"Abrindo {texto}."

    return None


# Programas que o ALF nunca deve fechar: fechá-los derruba a área de
# trabalho, o áudio do sistema ou o próprio ALF.
PROTEGIDOS_DE_FECHAMENTO = {
    "explorer",
    "dwm",
    "csrss",
    "winlogon",
    "services",
    "lsass",
    "svchost",
    "audiodg",
    "python",
    "pythonw",
    "alf",
}


def _janelas_visiveis():
    """
    Lista as janelas de nível superior visíveis, com título e processo.

    Devolve tuplas (hwnd, titulo, nome_do_processo).
    """

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    janelas = []

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True

        tamanho = user32.GetWindowTextLengthW(hwnd)
        if tamanho == 0:
            return True

        buffer = ctypes.create_unicode_buffer(tamanho + 1)
        user32.GetWindowTextW(hwnd, buffer, tamanho + 1)

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        nome_processo = ""
        # PROCESS_QUERY_LIMITED_INFORMATION
        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        if handle:
            try:
                caminho = ctypes.create_unicode_buffer(1024)
                tamanho_caminho = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(
                    handle, 0, caminho, ctypes.byref(tamanho_caminho)
                ):
                    nome_processo = Path(caminho.value).stem
            finally:
                kernel32.CloseHandle(handle)

        janelas.append((hwnd, buffer.value, nome_processo))
        return True

    prototipo = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )
    user32.EnumWindows(prototipo(callback), 0)
    return janelas


# Mensagem que o Windows envia quando o usuário clica no X da janela.
WM_CLOSE = 0x0010


def _pedir_fechamento(hwnd):
    """
    Pede educadamente para a janela fechar.

    WM_CLOSE é o mesmo caminho do clique no X: o programa ainda exibe
    "deseja salvar?" se houver trabalho pendente. Em nenhum momento o
    ALF mata o processo à força, justamente para não haver perda.
    """

    ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def fechar_aplicativo(nome):
    """
    Fecha um programa aberto, pelo nome da janela ou do processo.

    Não existia nenhuma função assim, então o modelo improvisava com
    alt+f4 -- que fecha a janela que estiver em foco, e não a que foi
    pedida. No histórico do usuário isso resultou em alt+f4 fechando
    coisa errada no meio de outra tarefa.

    Envia WM_CLOSE, que é o mesmo que clicar no X: o programa ainda
    pergunta se quer salvar. Nunca mata o processo à força, para não
    haver perda de trabalho não salvo.
    """

    nome = str(nome or "").strip()
    if not nome:
        return "Diga qual programa devo fechar."

    procurado = normalizar_texto(nome)

    if procurado in PROTEGIDOS_DE_FECHAMENTO:
        return (
            f"Não posso fechar {nome}: é um componente do Windows ou o "
            "próprio ALF."
        )

    # Aceita também os sinônimos, para "feche o VS Code" funcionar.
    procurados = [normalizar_texto(c) for c in nomes_candidatos(nome)]

    alvos = []
    for hwnd, titulo, processo in _janelas_visiveis():
        titulo_normalizado = normalizar_texto(titulo)
        processo_normalizado = normalizar_texto(processo)

        if processo_normalizado in PROTEGIDOS_DE_FECHAMENTO:
            continue

        for candidato in procurados:
            if not candidato:
                continue
            if candidato in titulo_normalizado or candidato in processo_normalizado:
                alvos.append((hwnd, titulo))
                break

    if not alvos:
        return (
            f"Não encontrei nenhuma janela aberta de {nome}. "
            "Confira se o programa está mesmo aberto."
        )

    fechadas = []
    for hwnd, titulo in alvos:
        _pedir_fechamento(hwnd)
        fechadas.append(titulo or nome)

    if len(fechadas) == 1:
        return (
            f"Pedi para fechar: {fechadas[0]}. "
            "Se houver algo não salvo, o programa vai perguntar."
        )

    return (
        f"Pedi para fechar {len(fechadas)} janelas de {nome}. "
        "Se houver algo não salvo, os programas vão perguntar."
    )


def abrir_aplicativo(nome):
    nome = str(nome or "").strip()
    if not nome:
        return "Informe o nome do aplicativo."
    normal = normalizar_texto(nome)
    if "".join(normal.split()) == "":
        return "Informe o nome do aplicativo."
    # Tenta o nome falado e depois os sinônimos conhecidos.
    # É o que faz "abra o VS Code" chegar em "Visual Studio Code".
    for candidato in nomes_candidatos(nome):
        app = abrir_app_windows(candidato)
        if app:
            return f"Abrindo {app}."

        achou = procurar_atalho_menu_iniciar(candidato)
        if achou:
            executar_comando([str(achou)])
            return f"Abrindo {achou.stem}."

        if abrir_executavel_conhecido(candidato):
            return f"Abrindo {candidato}."

    # Sites vêm antes dos recursos do Windows: quem pede "youtube"
    # quer o site, não um programa com esse nome.
    site = abrir_site_conhecido(nome)
    if site:
        return site

    resultado = abrir_especial(nome)
    if resultado != "Não encontrei um recurso do Windows com esse nome.":
        return resultado

    # Antes de desistir, tenta interpretar como endereço de internet.
    generico = abrir_site_generico(nome)
    if generico:
        return generico

    return (
        f"Não encontrei nada chamado {nome} neste computador nem um "
        "site com esse nome. Diga o nome exato do programa, ou peça "
        "uma pesquisa no navegador."
    )
