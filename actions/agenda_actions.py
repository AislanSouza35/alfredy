import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from threading import Lock

from core.arquivo_seguro import substituir_com_retentativa

PASTA_RAIZ = Path(__file__).resolve().parent.parent
PASTA_MEMORIA = PASTA_RAIZ / "memory"
ARQUIVO_AGENDA = PASTA_MEMORIA / "agenda.json"
MAXIMO_EVENTOS = 20
_LOCK = Lock()


def _normalizar(texto):
    texto = str(texto or "").strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto)


def _dados_vazios():
    return {"versao": 1, "eventos": []}


def _interpretar_data_hora(valor):
    valor = re.sub(r"\s+", " ", str(valor or "")).strip()
    formatos = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M")
    for formato in formatos:
        try:
            return datetime.strptime(valor, formato)
        except ValueError:
            continue
    return None


def _salvar_dados(dados):
    PASTA_MEMORIA.mkdir(parents=True, exist_ok=True)
    temporario = ARQUIVO_AGENDA.with_suffix(".tmp")
    try:
        with temporario.open("w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)
            arquivo.flush()
            try:
                import os
                os.fsync(arquivo.fileno())
            except OSError:
                pass
        substituir_com_retentativa(temporario, ARQUIVO_AGENDA)
    except OSError as erro:
        if temporario.exists():
            try:
                temporario.unlink()
            except OSError:
                pass
        raise OSError(f"Não foi possível salvar a agenda em: {ARQUIVO_AGENDA}") from erro


def _criar_arquivo_se_necessario():
    PASTA_MEMORIA.mkdir(parents=True, exist_ok=True)
    if not ARQUIVO_AGENDA.exists():
        _salvar_dados(_dados_vazios())
        return
    try:
        conteudo = ARQUIVO_AGENDA.read_text(encoding="utf-8").strip()
    except OSError as erro:
        raise OSError(f"Não foi possível ler a agenda em: {ARQUIVO_AGENDA}") from erro
    if not conteudo:
        _salvar_dados(_dados_vazios())
        return
    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError:
        _salvar_dados(_dados_vazios())
        return
    if not isinstance(dados, dict):
        _salvar_dados(_dados_vazios())
        return
    if not isinstance(dados.get("eventos"), list):
        dados = _dados_vazios()
        _salvar_dados(dados)


def _carregar_dados():
    _criar_arquivo_se_necessario()
    try:
        with ARQUIVO_AGENDA.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except (json.JSONDecodeError, OSError):
        dados = _dados_vazios()
        _salvar_dados(dados)
    if not isinstance(dados, dict):
        dados = _dados_vazios()
    eventos = dados.get("eventos", [])
    if not isinstance(eventos, list):
        eventos = []
    eventos_validos = []
    for evento in eventos:
        if not isinstance(evento, dict):
            continue
        titulo = re.sub(r"\s+", " ", str(evento.get("titulo", ""))).strip()
        data_hora = str(evento.get("data_hora", "")).strip()
        momento = _interpretar_data_hora(data_hora)
        if not titulo or momento is None:
            continue
        eventos_validos.append({
            "id": str(evento.get("id", "")).strip(),
            "titulo": titulo,
            "data_hora": momento.strftime("%Y-%m-%d %H:%M"),
            "criado_em": str(evento.get("criado_em", "")).strip(),
        })
    dados_tratados = {"versao": 1, "eventos": eventos_validos}
    return dados_tratados


def _proximo_id():
    dados = _carregar_dados()
    ids = []
    for evento in dados.get("eventos", []):
        valor = str(evento.get("id", "")).strip()
        if valor.isdigit():
            ids.append(int(valor))
    return str(max(ids) + 1) if ids else "1"


def criar_evento_agenda(titulo, data_hora):
    titulo = re.sub(r"\s+", " ", str(titulo or "")).strip()
    if not titulo:
        return "Informe o nome do evento."
    momento = _interpretar_data_hora(data_hora)
    if momento is None:
        return "Data e hora inválidas. Use o formato YYYY-MM-DD HH:MM ou DD/MM/YYYY HH:MM."
    with _LOCK:
        dados = _carregar_dados()
        eventos = dados.get("eventos", [])
        evento = {
            "id": _proximo_id(),
            "titulo": titulo,
            "data_hora": momento.strftime("%Y-%m-%d %H:%M"),
            "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        eventos.append(evento)
        dados["eventos"] = eventos
        _salvar_dados(dados)
    return f"Evento '{titulo}' agendado para {momento.strftime('%d/%m/%Y %H:%M')}."


def listar_agenda():
    dados = _carregar_dados()
    eventos = dados.get("eventos", [])
    if not eventos:
        return "Não há eventos agendados."
    linhas = []
    for evento in eventos:
        linhas.append(f"{evento.get('id', '')} - {evento.get('titulo', '')} - {evento.get('data_hora', '')}")
    return "Eventos agendados:\n" + "\n".join(linhas)


def cancelar_evento_agenda(referencia):
    referencia = str(referencia or "").strip()
    if not referencia:
        return "Informe o número ou o título do compromisso a cancelar."
    with _LOCK:
        dados = _carregar_dados()
        eventos = dados.get("eventos", [])

        # Primeiro tenta encontrar pelo ID exato.
        correspondentes = [
            evento for evento in eventos
            if str(evento.get("id", "")).strip() == referencia
        ]

        # Se não achou por ID, tenta por trecho do título.
        if not correspondentes:
            referencia_normalizada = _normalizar(referencia)
            correspondentes = [
                evento for evento in eventos
                if referencia_normalizada in _normalizar(evento.get("titulo", ""))
            ]

        if not correspondentes:
            return f"Não encontrei nenhum compromisso correspondente a '{referencia}'."

        if len(correspondentes) > 1:
            opcoes = "; ".join(
                f"{evento.get('id')} - {evento.get('titulo')}"
                for evento in correspondentes[:8]
            )
            return f"Encontrei mais de um compromisso parecido: {opcoes}. Informe o número exato."

        alvo = correspondentes[0]
        dados["eventos"] = [evento for evento in eventos if evento is not alvo]
        _salvar_dados(dados)

    return f"Evento '{alvo.get('titulo')}' (id {alvo.get('id')}) removido da agenda."
