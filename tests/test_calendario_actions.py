"""
Testes da agenda no Google Calendar.

A agenda local do projeto vivia presa a este computador: não aparecia
no celular e não avisava nada. As três operações continuam as mesmas;
o que mudou foi onde elas guardam.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from actions import calendario_actions as cal


CODIGO_CLIENTE = Path("gemini/live_client.py").read_text(encoding="utf-8")


class _Exec:
    def __init__(self, resposta, erro=None):
        self._resposta = resposta
        self._erro = erro

    def execute(self):
        if self._erro:
            raise self._erro
        return self._resposta


class _CalendarioFalso:
    def __init__(self, eventos=None, erro=None):
        self._eventos = eventos or []
        self._erro = erro
        self.inseridos = []
        self.apagados = []

    def events(self):
        return self

    def insert(self, calendarId=None, body=None):
        if self._erro:
            return _Exec(None, erro=self._erro)
        self.inseridos.append(body)
        return _Exec({"id": "ev1"})

    def list(self, **kwargs):
        if self._erro:
            return _Exec(None, erro=self._erro)
        return _Exec({"items": self._eventos})

    def delete(self, calendarId=None, eventId=None):
        self.apagados.append(eventId)
        return _Exec({})


@pytest.fixture
def api(monkeypatch):
    def instalar(eventos=None, erro=None):
        falso = _CalendarioFalso(eventos, erro)
        monkeypatch.setattr(
            cal,
            "_servico_calendario",
            lambda conta="": (falso, "professor@escola.com", None),
        )
        return falso

    return instalar


def _evento(titulo, quando, local=""):
    dados = {
        "id": f"id_{titulo}",
        "summary": titulo,
        "start": {"dateTime": quando},
    }
    if local:
        dados["location"] = local
    return dados


# ============================================================
# Entender a data falada
# ============================================================

def test_amanha_com_hora():
    momento, erro = cal.interpretar_quando("amanhã às 14h")

    assert erro is None
    assert momento.date() == (datetime.now() + timedelta(days=1)).date()
    assert (momento.hour, momento.minute) == (14, 0)


def test_hoje_com_minutos():
    momento, _ = cal.interpretar_quando("hoje 19:30")

    assert momento.date() == datetime.now().date()
    assert (momento.hour, momento.minute) == (19, 30)


def test_depois_de_amanha():
    momento, _ = cal.interpretar_quando("depois de amanhã às 8")

    assert momento.date() == (datetime.now() + timedelta(days=2)).date()
    assert momento.hour == 8


def test_data_completa():
    momento, _ = cal.interpretar_quando("25/12/2026 14:00")

    assert (momento.day, momento.month, momento.hour) == (25, 12, 14)


def test_data_sem_hora_assume_nove_da_manha():
    momento, _ = cal.interpretar_quando("25/12/2026")

    assert (momento.hour, momento.minute) == (9, 0)


@pytest.mark.parametrize("ruim", ["semana que vem", "qualquer dia", ""])
def test_data_que_nao_da_para_entender(ruim):
    momento, erro = cal.interpretar_quando(ruim)

    assert momento is None
    assert erro


# ============================================================
# Criar
# ============================================================

def test_evento_leva_lembretes(api):
    """
    Sem lembrete o evento existe mas não avisa ninguém -- que era
    exatamente o problema da agenda local.
    """
    falso = api()

    cal.criar_evento("Reunião pedagógica", "amanhã às 14h")

    lembretes = falso.inseridos[0]["reminders"]

    assert lembretes["useDefault"] is False
    minutos = [o["minutes"] for o in lembretes["overrides"]]
    assert minutos == list(cal.MINUTOS_DE_LEMBRETE)


def test_duracao_padrao_de_uma_hora(api):
    falso = api()

    cal.criar_evento("Aula", "amanhã às 14h")

    corpo = falso.inseridos[0]
    inicio = datetime.fromisoformat(corpo["start"]["dateTime"])
    fim = datetime.fromisoformat(corpo["end"]["dateTime"])

    assert (fim - inicio).total_seconds() == 3600


def test_duracao_informada_e_respeitada(api):
    falso = api()

    cal.criar_evento("Prova", "amanhã às 14h", duracao_minutos="90")

    corpo = falso.inseridos[0]
    inicio = datetime.fromisoformat(corpo["start"]["dateTime"])
    fim = datetime.fromisoformat(corpo["end"]["dateTime"])

    assert (fim - inicio).total_seconds() == 5400


def test_fuso_e_o_do_brasil(api):
    falso = api()

    cal.criar_evento("Aula", "amanhã às 14h")

    assert falso.inseridos[0]["start"]["timeZone"] == "America/Sao_Paulo"


def test_local_entra_quando_informado(api):
    falso = api()

    cal.criar_evento("Reunião", "amanhã às 14h", local="Sala 3")

    assert falso.inseridos[0]["location"] == "Sala 3"


def test_evento_sem_titulo_e_recusado(api):
    falso = api()

    assert "Qual é o compromisso" in cal.criar_evento("", "amanhã às 14h")
    assert falso.inseridos == []


def test_data_invalida_nao_cria_nada(api):
    falso = api()

    resultado = cal.criar_evento("Reunião", "algum dia desses")

    assert "Não entendi a data" in resultado
    assert falso.inseridos == []


def test_api_desativada_e_explicada(api):
    api(erro=Exception("403 SERVICE_DISABLED"))

    resultado = cal.criar_evento("Reunião", "amanhã às 14h")

    assert "não está ativada" in resultado


# ============================================================
# Reserva local
# ============================================================

def test_sem_conta_do_google_cai_no_arquivo_local(monkeypatch):
    """A agenda local continua servindo, mas o usuário precisa saber."""
    monkeypatch.setattr(
        cal, "_servico_calendario", lambda conta="": (None, None, "sem contas")
    )

    chamadas = []
    monkeypatch.setattr(
        cal.agenda_actions,
        "criar_evento_agenda",
        lambda titulo, quando: chamadas.append((titulo, quando)) or "Salvei.",
    )

    resultado = cal.criar_evento("Reunião", "amanhã às 14h")

    assert chamadas
    assert "só neste computador" in resultado
    assert "não vai aparecer no celular" in resultado


# ============================================================
# Listar
# ============================================================

def test_listagem_traz_os_compromissos(api):
    api(
        [
            _evento("Reunião", "2026-09-10T14:00:00-03:00", "Sala 3"),
            _evento("Aula", "2026-09-11T08:00:00-03:00"),
        ]
    )

    resultado = cal.listar_eventos()

    assert "2 compromissos" in resultado
    assert "10/09 às 14:00" in resultado
    assert "Sala 3" in resultado


def test_agenda_vazia_e_dita_com_clareza(api):
    api([])

    assert "não tem nenhum compromisso" in cal.listar_eventos()


# ============================================================
# Cancelar
# ============================================================

def test_cancela_o_evento_certo(api):
    falso = api([_evento("Reunião pedagógica", "2026-09-10T14:00:00-03:00")])

    resultado = cal.cancelar_evento("reunião pedagógica")

    assert falso.apagados == ["id_Reunião pedagógica"]
    assert "Cancelei" in resultado


def test_nomes_parecidos_param_antes_de_apagar(api):
    """Cancelar apaga de verdade e avisa quem estiver convidado."""
    falso = api(
        [
            _evento("Reunião de pais", "2026-09-10T14:00:00-03:00"),
            _evento("Reunião pedagógica", "2026-09-11T14:00:00-03:00"),
        ]
    )

    resultado = cal.cancelar_evento("reunião")

    assert falso.apagados == []
    assert "mais de um compromisso" in resultado


def test_evento_inexistente_avisa(api):
    falso = api([])

    resultado = cal.cancelar_evento("almoço")

    assert "Não encontrei" in resultado
    assert falso.apagados == []


# ============================================================
# Escopo e instrução
# ============================================================

def test_escopo_da_agenda_e_o_estreito():
    """
    calendar.events mexe só nos eventos; o escopo "calendar" completo
    daria acesso também às configurações das agendas do professor.
    """
    from actions.classroom_contas import ESCOPOS

    assert "https://www.googleapis.com/auth/calendar.events" in ESCOPOS
    assert "https://www.googleapis.com/auth/calendar" not in ESCOPOS


def test_instrucao_nao_fala_mais_em_agenda_local():
    assert "agenda local" not in CODIGO_CLIENTE
    assert "Google Calendar" in CODIGO_CLIENTE


def test_continuam_sendo_tres_ferramentas_de_agenda():
    """
    Seis ferramentas de agenda -- local e Google lado a lado -- fariam
    o modelo adivinhar qual usar toda vez.
    """
    for ferramenta in (
        "criar_evento_agenda",
        "listar_agenda",
        "cancelar_evento_agenda",
    ):
        assert f'name="{ferramenta}"' in CODIGO_CLIENTE

    assert 'name="criar_evento_google"' not in CODIGO_CLIENTE
