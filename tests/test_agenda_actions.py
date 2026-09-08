"""Testes unitários/integração para actions/agenda_actions.py.

Redireciona o arquivo de dados para um arquivo temporário via monkeypatch,
nunca tocando memory/agenda.json real.
"""

import pytest

from actions import agenda_actions


@pytest.fixture
def agenda_temporaria(tmp_path, monkeypatch):
    arquivo = tmp_path / "agenda.json"
    monkeypatch.setattr(agenda_actions, "PASTA_MEMORIA", tmp_path)
    monkeypatch.setattr(agenda_actions, "ARQUIVO_AGENDA", arquivo)
    return arquivo


def test_criar_evento_agenda_com_sucesso(agenda_temporaria):
    resultado = agenda_actions.criar_evento_agenda("Reunião", "2026-12-01 10:00")
    assert "agendado" in resultado
    assert "Reunião" in resultado


def test_criar_evento_agenda_data_invalida(agenda_temporaria):
    resultado = agenda_actions.criar_evento_agenda("Reunião", "data qualquer")
    assert "inválidas" in resultado


def test_criar_evento_agenda_titulo_vazio(agenda_temporaria):
    resultado = agenda_actions.criar_evento_agenda("   ", "2026-12-01 10:00")
    assert "Informe o nome do evento" in resultado


def test_listar_agenda_vazia(agenda_temporaria):
    assert agenda_actions.listar_agenda() == "Não há eventos agendados."


def test_listar_agenda_com_eventos(agenda_temporaria):
    agenda_actions.criar_evento_agenda("Consulta médica", "2026-12-01 10:00")
    agenda_actions.criar_evento_agenda("Reunião de pais", "2026-12-02 14:00")
    resultado = agenda_actions.listar_agenda()
    assert "Consulta médica" in resultado
    assert "Reunião de pais" in resultado


def test_cancelar_evento_por_id_exato(agenda_temporaria):
    agenda_actions.criar_evento_agenda("Consulta médica", "2026-12-01 10:00")
    resultado = agenda_actions.cancelar_evento_agenda("1")
    assert "removido da agenda" in resultado
    assert agenda_actions.listar_agenda() == "Não há eventos agendados."


def test_cancelar_evento_por_trecho_do_titulo(agenda_temporaria):
    # Regressão: antes, cancelar_evento_agenda só aceitava o ID exato,
    # apesar da ferramenta documentar suporte a trecho do título.
    agenda_actions.criar_evento_agenda("Consulta com o dentista", "2026-12-01 10:00")
    resultado = agenda_actions.cancelar_evento_agenda("dentista")
    assert "removido da agenda" in resultado
    assert agenda_actions.listar_agenda() == "Não há eventos agendados."


def test_cancelar_evento_titulo_ambiguo(agenda_temporaria):
    agenda_actions.criar_evento_agenda("Consulta com o dentista", "2026-12-01 10:00")
    agenda_actions.criar_evento_agenda("Consulta com o oftalmologista", "2026-12-02 10:00")
    resultado = agenda_actions.cancelar_evento_agenda("consulta")
    assert "mais de um compromisso parecido" in resultado
    # Nenhum evento deve ter sido removido em caso de ambiguidade.
    assert "Consulta com o dentista" in agenda_actions.listar_agenda()
    assert "Consulta com o oftalmologista" in agenda_actions.listar_agenda()


def test_cancelar_evento_inexistente(agenda_temporaria):
    resultado = agenda_actions.cancelar_evento_agenda("999")
    assert "Não encontrei nenhum compromisso" in resultado


def test_ids_incrementam_corretamente(agenda_temporaria):
    agenda_actions.criar_evento_agenda("Evento 1", "2026-01-01 08:00")
    agenda_actions.criar_evento_agenda("Evento 2", "2026-01-02 08:00")
    agenda_actions.cancelar_evento_agenda("1")
    agenda_actions.criar_evento_agenda("Evento 3", "2026-01-03 08:00")
    resultado = agenda_actions.listar_agenda()
    # O novo evento deve ganhar o próximo ID disponível (3), não reaproveitar o 1.
    assert "3 - Evento 3" in resultado
