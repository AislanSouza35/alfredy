"""Testes unitários/integração para memory/memory_manager.py.

Redireciona o arquivo de dados para um arquivo temporário via monkeypatch,
nunca tocando memory/memory.json real.
"""

import pytest

from memory import memory_manager


@pytest.fixture
def memoria_temporaria(tmp_path, monkeypatch):
    arquivo = tmp_path / "memory.json"
    monkeypatch.setattr(memory_manager, "PASTA_MEMORIA", tmp_path)
    monkeypatch.setattr(memory_manager, "ARQUIVO_MEMORIA", arquivo)
    return arquivo


def test_salvar_memoria_com_sucesso(memoria_temporaria):
    resultado = memory_manager.salvar_memoria("O usuário prefere café sem açúcar")
    assert "Memória salva" in resultado
    assert "1 de" in resultado


def test_salvar_memoria_vazia(memoria_temporaria):
    resultado = memory_manager.salvar_memoria("   ")
    assert "Não recebi nenhuma informação" in resultado


def test_salvar_memoria_tipo_invalido(memoria_temporaria):
    resultado = memory_manager.salvar_memoria(123)
    assert "inválida" in resultado


def test_salvar_memoria_muito_longa(memoria_temporaria):
    texto_longo = "a" * (memory_manager.MAXIMO_CARACTERES + 1)
    resultado = memory_manager.salvar_memoria(texto_longo)
    assert "longa demais" in resultado


def test_salvar_memoria_duplicada_ignorando_acentos_e_caixa(memoria_temporaria):
    memory_manager.salvar_memoria("Prefere café sem açúcar")
    resultado = memory_manager.salvar_memoria("PREFERE CAFE SEM ACUCAR")
    assert "já está salva" in resultado


def test_salvar_memoria_respeita_limite_maximo(memoria_temporaria, monkeypatch):
    monkeypatch.setattr(memory_manager, "MAXIMO_MEMORIAS", 2)
    memory_manager.salvar_memoria("Memória 1")
    memory_manager.salvar_memoria("Memória 2")
    resultado = memory_manager.salvar_memoria("Memória 3")
    assert "limite" in resultado


def test_listar_memorias_vazia(memoria_temporaria):
    assert memory_manager.listar_memorias() == "Nenhuma memória foi salva ainda."


def test_listar_memorias_com_conteudo(memoria_temporaria):
    memory_manager.salvar_memoria("Gosta de rock")
    memory_manager.salvar_memoria("Mora em Salvador")
    resultado = memory_manager.listar_memorias()
    assert "Gosta de rock" in resultado
    assert "Mora em Salvador" in resultado


def test_esquecer_memoria_por_id(memoria_temporaria):
    memory_manager.salvar_memoria("Gosta de rock")
    resultado = memory_manager.esquecer_memoria("1")
    assert resultado is not None
    assert memory_manager.listar_memorias() == "Nenhuma memória foi salva ainda."


def test_esquecer_memoria_bloqueia_apagar_tudo(memoria_temporaria):
    memory_manager.salvar_memoria("Gosta de rock")
    resultado = memory_manager.esquecer_memoria("tudo")
    assert "não apago todas" in resultado
    assert "Gosta de rock" in memory_manager.listar_memorias()


def test_contexto_memorias_nao_falha_sem_memorias(memoria_temporaria):
    # contexto_memorias() é usado para montar a instrução de sistema;
    # não deve lançar exceção mesmo sem nenhuma memória salva.
    resultado = memory_manager.contexto_memorias()
    assert isinstance(resultado, str)
