import json
import os
import re
import shutil
import subprocess
import unicodedata
import webbrowser
from pathlib import Path


_AREA_TRANSFERENCIA = {
    "origem": None,
    "operacao": None,
}


def normalizar_texto(texto):
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(caractere for caractere in texto if unicodedata.category(caractere) != "Mn")


def executar_comando(comando):
    subprocess.Popen(comando, shell=False)


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


def area_de_trabalho():
    usuario = Path.home()
    opcoes = [
        usuario / "OneDrive" / "Desktop",
        usuario / "OneDrive" / "Área de Trabalho",
        usuario / "Desktop",
        usuario / "Área de Trabalho",
    ]
    for pasta in opcoes:
        if pasta.exists() and pasta.is_dir():
            return pasta.resolve()
    raise FileNotFoundError("Não foi possível localizar a Área de Trabalho.")


def limpar_nome(nome):
    if not isinstance(nome, str):
        return ""
    proibidos = ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]
    for caractere in proibidos:
        nome = nome.replace(caractere, "")
    return nome.strip().rstrip(".")


def _normalizar(texto):
    texto = str(texto or "").strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(caractere for caractere in texto if unicodedata.category(caractere) != "Mn")
    # Trata "_" e "-" como espaço para que buscas por voz (ex.: "relatório
    # final") encontrem arquivos como "relatorio_final_2024.docx".
    texto = re.sub(r"[_\-]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _esta_dentro_da_area(caminho):
    desktop = area_de_trabalho()
    caminho = Path(caminho).resolve()
    try:
        caminho.relative_to(desktop)
        return True
    except ValueError:
        return False


def _resolver_caminho_relativo(caminho_relativo=""):
    desktop = area_de_trabalho()
    caminho_relativo = str(caminho_relativo or "").strip()
    if not caminho_relativo:
        return desktop
    caminho_relativo = caminho_relativo.replace("\\", "/")
    partes = [limpar_nome(parte) for parte in caminho_relativo.split("/") if limpar_nome(parte)]
    caminho = desktop.joinpath(*partes).resolve()
    if not _esta_dentro_da_area(caminho):
        raise ValueError("O caminho informado está fora da Área de Trabalho.")
    return caminho


def _localizar_item(nome, pasta_relativa=""):
    nome = str(nome or "").strip()
    if not nome:
        return None, "Informe o nome do arquivo ou pasta."
    pasta = _resolver_caminho_relativo(pasta_relativa)
    if not pasta.exists() or not pasta.is_dir():
        return None, f"A pasta de origem '{pasta_relativa}' não foi encontrada."
    procurado = _normalizar(nome)
    itens = list(pasta.iterdir())
    exatos = [item for item in itens if _normalizar(item.name) == procurado]
    if len(exatos) == 1:
        return exatos[0], None
    parciais = [item for item in itens if procurado in _normalizar(item.name)]
    if len(parciais) == 1:
        return parciais[0], None
    if len(parciais) > 1:
        opcoes = ", ".join(item.name for item in parciais[:8])
        return None, f"Encontrei mais de um item parecido: {opcoes}. Informe o nome completo."
    return None, f"Não encontrei '{nome}'" + (f" dentro de '{pasta_relativa}'." if pasta_relativa else " na Área de Trabalho.")


def criar_pasta_area_trabalho(nome):
    nome = limpar_nome(nome)
    if not nome:
        return "Nome de pasta inválido."
    desktop = area_de_trabalho()
    caminho = desktop / nome
    if caminho.exists():
        return f"A pasta '{nome}' já existe. Não alterei nada."
    caminho.mkdir(parents=True, exist_ok=False)
    return f"Pasta '{nome}' criada com sucesso na área de trabalho."


def listar_area_de_trabalho():
    desktop = area_de_trabalho()
    itens = [item.name for item in desktop.iterdir()]
    if not itens:
        return "A área de trabalho está vazia."
    return "Itens na área de trabalho: " + ", ".join(itens[:50])


def organizar_area_de_trabalho_basico():
    desktop = area_de_trabalho()
    pastas = {
        "Imagens": [".png", ".jpg", ".jpeg", ".webp"],
        "PDFs": [".pdf"],
        "Documentos": [".doc", ".docx", ".txt", ".xlsx", ".pptx"],
        "Compactados": [".zip", ".rar", ".7z"],
    }
    movidos = []
    for item in desktop.iterdir():
        if item.is_dir():
            continue
        for pasta, extensoes in pastas.items():
            if item.suffix.lower() in extensoes:
                destino_pasta = desktop / pasta
                destino_pasta.mkdir(exist_ok=True)
                destino = destino_pasta / item.name
                if destino.exists():
                    break
                shutil.move(str(item), str(destino))
                movidos.append(item.name)
                break
    if not movidos:
        return "Não encontrei arquivos para organizar ou todos já estavam organizados."
    return "Organizei estes arquivos: " + ", ".join(movidos)


def copiar_item_area_trabalho(nome, pasta_origem=""):
    item, erro = _localizar_item(nome, pasta_origem)
    if erro:
        return erro
    _AREA_TRANSFERENCIA["origem"] = str(item.resolve())
    _AREA_TRANSFERENCIA["operacao"] = "copiar"
    return f"'{item.name}' foi preparado para copiar. Agora informe onde deseja colar."


def recortar_item_area_trabalho(nome, pasta_origem=""):
    item, erro = _localizar_item(nome, pasta_origem)
    if erro:
        return erro
    _AREA_TRANSFERENCIA["origem"] = str(item.resolve())
    _AREA_TRANSFERENCIA["operacao"] = "recortar"
    return f"'{item.name}' foi preparado para mover. Agora informe onde deseja colar."


def colar_item_area_trabalho(pasta_destino=""):
    origem_texto = _AREA_TRANSFERENCIA.get("origem")
    operacao = _AREA_TRANSFERENCIA.get("operacao")
    if not origem_texto or operacao not in ("copiar", "recortar"):
        return "Não há nenhum arquivo ou pasta preparado para copiar ou recortar."
    origem = Path(origem_texto)
    if not origem.exists():
        _AREA_TRANSFERENCIA["origem"] = None
        _AREA_TRANSFERENCIA["operacao"] = None
        return "O item preparado não existe mais. A operação foi cancelada."
    if not _esta_dentro_da_area(origem):
        _AREA_TRANSFERENCIA["origem"] = None
        _AREA_TRANSFERENCIA["operacao"] = None
        return "A operação foi bloqueada porque o item está fora da Área de Trabalho."
    try:
        destino_pasta = _resolver_caminho_relativo(pasta_destino)
    except ValueError as erro:
        return str(erro)
    if not destino_pasta.exists():
        return f"A pasta de destino '{pasta_destino}' não foi encontrada."
    if not destino_pasta.is_dir():
        return f"'{pasta_destino}' não é uma pasta válida."
    if origem.is_dir():
        try:
            destino_pasta.resolve().relative_to(origem.resolve())
            return "Não é possível colar uma pasta dentro dela mesma."
        except ValueError:
            pass
    destino = destino_pasta / origem.name
    if destino.exists():
        return f"Já existe um item chamado '{origem.name}' no destino. Não sobrescrevi nada."
    try:
        if operacao == "copiar":
            if origem.is_dir():
                shutil.copytree(str(origem), str(destino))
            else:
                shutil.copy2(str(origem), str(destino))
            return f"'{origem.name}' foi copiado com sucesso" + (f" para '{pasta_destino}'." if pasta_destino else " para a Área de Trabalho.")
        shutil.move(str(origem), str(destino))
        _AREA_TRANSFERENCIA["origem"] = None
        _AREA_TRANSFERENCIA["operacao"] = None
        return f"'{origem.name}' foi movido com sucesso" + (f" para '{pasta_destino}'." if pasta_destino else " para a Área de Trabalho.")
    except OSError as erro:
        return f"Não consegui concluir a operação. Detalhes: {erro}"


def renomear_item_area_trabalho(nome_atual, novo_nome, pasta_origem=""):
    item, erro = _localizar_item(nome_atual, pasta_origem)
    if erro:
        return erro
    novo_nome = limpar_nome(novo_nome)
    if not novo_nome:
        return "O novo nome é inválido. Nenhuma alteração foi feita."
    if item.is_file() and item.suffix and not Path(novo_nome).suffix:
        novo_nome += item.suffix
    destino = item.with_name(novo_nome)
    if destino == item:
        return f"O item já se chama '{item.name}'. Não alterei nada."
    if destino.exists():
        return f"Já existe um item chamado '{novo_nome}'. Não sobrescrevi nada."
    try:
        item.rename(destino)
        origem_transferencia = _AREA_TRANSFERENCIA.get("origem")
        if origem_transferencia and Path(origem_transferencia) == item.resolve():
            _AREA_TRANSFERENCIA["origem"] = str(destino.resolve())
        return f"'{item.name}' foi renomeado para '{destino.name}' com sucesso."
    except OSError as erro:
        return f"Não consegui renomear o item. Detalhes: {erro}"


def cancelar_transferencia_area_trabalho():
    _AREA_TRANSFERENCIA["origem"] = None
    _AREA_TRANSFERENCIA["operacao"] = None
    return "A operação de copiar ou recortar foi cancelada."
