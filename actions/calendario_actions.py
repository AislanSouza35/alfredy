"""
Agenda: Google Calendar quando disponível, arquivo local como reserva.

O projeto já tinha uma agenda local em memory/agenda.json, mas ela vive
presa a este computador: não aparece no celular, não manda lembrete e
não conversa com nada. Para um professor isso é quase inútil.

Este módulo mantém EXATAMENTE as mesmas três operações e apenas troca
onde elas guardam. Se houver conta do Google autorizada, o evento vai
para o Google Calendar; se não houver, cai no arquivo local como antes.

Manter três operações em vez de seis é deliberado: com "criar evento
local" e "criar evento no Google" lado a lado, o modelo teria que
adivinhar qual usar toda vez.
"""

import re
import unicodedata
from datetime import datetime, timedelta

from actions import agenda_actions
from actions.classroom_contas import falta_para_recurso, servicos


# Lembretes que acompanham todo evento criado. Sem isto o evento existe
# mas não avisa ninguém, que é o problema da agenda local.
MINUTOS_DE_LEMBRETE = (60, 10)

# Duração assumida quando o professor não diz quanto tempo dura.
DURACAO_PADRAO_MINUTOS = 60

# Janela padrão ao listar, em dias.
DIAS_PARA_FRENTE = 14

MAXIMO_EVENTOS = 50


def _normalizar(texto):
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.split())


def _servico_calendario(conta=""):
    """Devolve (servico, email, erro). Erro não vazio significa usar o local."""

    contas = servicos()
    if not contas:
        return None, None, "sem contas"

    escolhida = None

    if conta:
        procurado = _normalizar(conta)
        for email, _, credenciais in contas:
            if procurado in _normalizar(email):
                escolhida = (email, credenciais)
                break
        if escolhida is None:
            return None, None, (
                f"Não tenho a conta {conta} autorizada. Disponíveis: "
                + ", ".join(c[0] for c in contas)
                + "."
            )
    else:
        escolhida = (contas[0][0], contas[0][2])

    # A conta pode estar boa para o Classroom e ainda não ter a
    # permissão da agenda: cada recurso é verificado por si.
    pendente = falta_para_recurso(escolhida[0], "agenda")
    if pendente:
        return None, None, pendente

    try:
        from googleapiclient.discovery import build

        return (
            build(
                "calendar", "v3",
                credentials=escolhida[1],
                cache_discovery=False,
            ),
            escolhida[0],
            None,
        )
    except Exception as erro:
        return None, None, f"Não consegui acessar o Google Calendar: {erro}"


def _traduzir_falha(erro):
    texto = str(erro)

    if "SERVICE_DISABLED" in texto or "has not been used in project" in texto:
        return (
            "A API do Google Calendar não está ativada no projeto do "
            "console. Avise o usuário: é um clique em "
            "console.cloud.google.com."
        )
    if "403" in texto:
        return "O Google recusou o acesso à agenda."
    if "404" in texto:
        return "Não encontrei esse evento."

    return f"O Google Calendar devolveu um erro: {erro}"


# ============================================================
# DATA E HORA
# ============================================================

def interpretar_quando(quando):
    """
    Converte o que foi falado numa data e hora.

    Aceita os formatos da agenda local mais "hoje" e "amanhã", que são
    o jeito natural de falar.

    Devolve (datetime, erro).
    """

    texto = re.sub(r"\s+", " ", str(quando or "")).strip()
    if not texto:
        return None, "Diga a data e a hora do compromisso."

    minusculo = _normalizar(texto)
    hoje = datetime.now()

    # "hoje 14:00" e "amanha 09:30" viram a data correspondente.
    for palavra, dias in (("depois de amanha", 2), ("amanha", 1), ("hoje", 0)):
        if minusculo.startswith(palavra):
            resto = minusculo[len(palavra):].strip().replace("as ", "").strip()
            alvo = hoje + timedelta(days=dias)

            hora, minuto = 9, 0
            if resto:
                pedacos = resto.replace("h", ":").strip(":").split(":")
                try:
                    hora = int(pedacos[0])
                    minuto = int(pedacos[1]) if len(pedacos) > 1 and pedacos[1] else 0
                except (ValueError, IndexError):
                    return None, f"Não entendi o horário '{resto}'."

            try:
                return alvo.replace(
                    hour=hora, minute=minuto, second=0, microsecond=0
                ), None
            except ValueError:
                return None, f"O horário '{resto}' não existe."

    quando_datado = agenda_actions._interpretar_data_hora(texto)
    if quando_datado is not None:
        return quando_datado, None

    # Data sem hora: assume nove da manhã.
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            base = datetime.strptime(texto, formato)
            return base.replace(hour=9, minute=0), None
        except ValueError:
            continue

    return None, (
        f"Não entendi a data '{quando}'. Diga algo como 'amanhã às 14h' "
        "ou '25/12/2026 14:00'."
    )


# ============================================================
# OPERAÇÕES
# ============================================================

def criar_evento(titulo, quando, duracao_minutos="", local="", conta=""):
    """Cria um compromisso, no Google Calendar ou na agenda local."""

    titulo = " ".join(str(titulo or "").split()).strip()
    if not titulo:
        return "Qual é o compromisso?"

    inicio, erro = interpretar_quando(quando)
    if erro:
        return erro

    try:
        minutos = int(str(duracao_minutos or DURACAO_PADRAO_MINUTOS))
    except (TypeError, ValueError):
        minutos = DURACAO_PADRAO_MINUTOS

    minutos = max(5, min(minutos, 60 * 12))
    fim = inicio + timedelta(minutes=minutos)

    servico, email, erro_servico = _servico_calendario(conta)

    if servico is None:
        if erro_servico != "sem contas":
            return erro_servico

        # Sem Google autorizado, a agenda local continua servindo.
        resultado = agenda_actions.criar_evento_agenda(
            titulo, inicio.strftime("%d/%m/%Y %H:%M")
        )
        return (
            f"{resultado} Guardei só neste computador, porque nenhuma conta "
            "do Google está autorizada: não vai aparecer no celular nem "
            "avisar você."
        )

    corpo = {
        "summary": titulo,
        "start": {
            "dateTime": inicio.isoformat(),
            "timeZone": "America/Sao_Paulo",
        },
        "end": {
            "dateTime": fim.isoformat(),
            "timeZone": "America/Sao_Paulo",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": m}
                for m in MINUTOS_DE_LEMBRETE
            ],
        },
    }

    local = " ".join(str(local or "").split()).strip()
    if local:
        corpo["location"] = local

    try:
        evento = servico.events().insert(
            calendarId="primary", body=corpo
        ).execute()
    except Exception as erro:
        return _traduzir_falha(erro)

    quando_falado = inicio.strftime("%d/%m às %H:%M")
    onde = f", em {local}" if local else ""

    return (
        f"Agendei '{titulo}' para {quando_falado}{onde}, de {minutos} "
        f"minutos, na agenda de {email}. "
        "Você recebe lembrete uma hora antes e dez minutos antes, "
        "inclusive no celular. "
        f"Identificador: {evento.get('id', '')}"
    )


def listar_eventos(dias="", conta=""):
    """Lista os próximos compromissos."""

    try:
        janela = int(str(dias or DIAS_PARA_FRENTE))
    except (TypeError, ValueError):
        janela = DIAS_PARA_FRENTE

    janela = max(1, min(janela, 365))

    servico, email, erro_servico = _servico_calendario(conta)

    if servico is None:
        if erro_servico != "sem contas":
            return erro_servico
        return agenda_actions.listar_agenda()

    agora = datetime.now().astimezone()
    limite = agora + timedelta(days=janela)

    try:
        resposta = servico.events().list(
            calendarId="primary",
            timeMin=agora.isoformat(),
            timeMax=limite.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=MAXIMO_EVENTOS,
        ).execute()
    except Exception as erro:
        return _traduzir_falha(erro)

    eventos = resposta.get("items", [])

    if not eventos:
        return (
            f"Você não tem nenhum compromisso nos próximos {janela} dias "
            f"na agenda de {email}."
        )

    linhas = []
    for evento in eventos:
        inicio = evento.get("start", {})
        quando = inicio.get("dateTime") or inicio.get("date", "")

        try:
            momento = datetime.fromisoformat(quando)
            if inicio.get("dateTime"):
                quando_falado = momento.strftime("%d/%m às %H:%M")
            else:
                quando_falado = momento.strftime("%d/%m, o dia todo")
        except ValueError:
            quando_falado = quando

        titulo = evento.get("summary", "sem título")
        onde = evento.get("location", "")
        linhas.append(
            f"- {quando_falado}: {titulo}" + (f" ({onde})" if onde else "")
        )

    return (
        f"Você tem {len(eventos)} compromissos nos próximos {janela} dias "
        f"na agenda de {email}:\n"
        + "\n".join(linhas)
        + "\nResuma em voz alta os mais próximos; só liste todos se o "
        "usuário pedir."
    )


def cancelar_evento(referencia, conta=""):
    """
    Cancela um compromisso pelo título ou pelo identificador.

    Cancelar apaga de verdade e o convidado é avisado, então um título
    que casa com vários eventos faz a função parar e perguntar em vez
    de escolher sozinha.
    """

    referencia = " ".join(str(referencia or "").split()).strip()
    if not referencia:
        return "Qual compromisso devo cancelar?"

    servico, email, erro_servico = _servico_calendario(conta)

    if servico is None:
        if erro_servico != "sem contas":
            return erro_servico
        return agenda_actions.cancelar_evento_agenda(referencia)

    agora = datetime.now().astimezone()
    limite = agora + timedelta(days=365)

    try:
        resposta = servico.events().list(
            calendarId="primary",
            timeMin=agora.isoformat(),
            timeMax=limite.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
        ).execute()
    except Exception as erro:
        return _traduzir_falha(erro)

    eventos = resposta.get("items", [])
    procurado = _normalizar(referencia)

    exatos = [
        e for e in eventos
        if _normalizar(e.get("summary", "")) == procurado
        or e.get("id", "") == referencia
    ]
    parciais = [
        e for e in eventos if procurado in _normalizar(e.get("summary", ""))
    ]

    candidatos = exatos or parciais

    if not candidatos:
        return (
            f"Não encontrei nenhum compromisso chamado {referencia} na "
            f"agenda de {email}."
        )

    if len(candidatos) > 1:
        nomes = ", ".join(
            f"{e.get('summary', '')} em "
            + (e.get("start", {}).get("dateTime", "")[:16].replace("T", " às "))
            for e in candidatos[:5]
        )
        return (
            f"Tenho mais de um compromisso parecido com {referencia}: "
            f"{nomes}. Pergunte qual deles antes de cancelar."
        )

    alvo = candidatos[0]

    try:
        servico.events().delete(
            calendarId="primary", eventId=alvo["id"]
        ).execute()
    except Exception as erro:
        return _traduzir_falha(erro)

    inicio = alvo.get("start", {}).get("dateTime", "")
    quando_falado = inicio[:16].replace("T", " às ") if inicio else ""

    return (
        f"Cancelei '{alvo.get('summary', '')}'"
        + (f" de {quando_falado}" if quando_falado else "")
        + f" na agenda de {email}."
    )
