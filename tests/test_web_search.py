"""Testes unitários para actions/web_search.py (filtro de decisão e formatação).

Não faz chamadas de rede reais: pesquisar_informacao_atual é testado com
o DDGS mockado.
"""

from unittest.mock import patch

import pytest

from actions import web_search


# ============================================================
# avaliar_necessidade_pesquisa
# ============================================================

@pytest.mark.parametrize(
    "consulta",
    [
        "qual é a cotação do dólar hoje?",
        "previsão do tempo em Salvador amanhã",
        "notícias recentes sobre o Bahia",
        "quem é o presidente do Brasil atualmente",
        "placar do jogo do Bahia agora",
    ],
)
def test_avaliar_necessidade_pesquisa_casos_que_devem_pesquisar(consulta):
    decisao = web_search.avaliar_necessidade_pesquisa(consulta)
    assert decisao.pesquisar is True


@pytest.mark.parametrize(
    "consulta",
    [
        "o que é Python?",
        "quem foi Albert Einstein?",
        "como funciona um motor a combustão?",
        "explique o que é uma API",
        "qual a diferença entre lista e tupla em Python",
    ],
)
def test_avaliar_necessidade_pesquisa_casos_estaveis(consulta):
    decisao = web_search.avaliar_necessidade_pesquisa(consulta)
    assert decisao.pesquisar is False


def test_avaliar_necessidade_pesquisa_consulta_vazia():
    decisao = web_search.avaliar_necessidade_pesquisa("   ")
    assert decisao.pesquisar is False
    assert decisao.motivo == "consulta vazia"


def test_avaliar_necessidade_pesquisa_ignora_acentos_e_caixa():
    # "cotação" sem acento e em maiúsculas ainda deve ser detectado.
    decisao = web_search.avaliar_necessidade_pesquisa("COTACAO DO EURO")
    assert decisao.pesquisar is True


def test_avaliar_necessidade_pesquisa_detecta_precos_de_commodities():
    assert web_search.avaliar_necessidade_pesquisa("qual é o preço do ouro?").pesquisar is True
    assert web_search.avaliar_necessidade_pesquisa("qual o valor do petróleo?").pesquisar is True


def test_precisa_pesquisar_e_atalho_booleano():
    assert web_search.precisa_pesquisar("o que é uma variável?") is False
    assert web_search.precisa_pesquisar("cotação do dólar hoje") is True


def test_resposta_sem_pesquisa_inclui_motivo():
    texto = web_search.resposta_sem_pesquisa("o que é Python?")
    assert "PESQUISA NA INTERNET NÃO NECESSÁRIA" in texto
    assert "Motivo:" in texto


# ============================================================
# pesquisar_informacao_atual (DDGS mockado)
# ============================================================

def test_pesquisar_informacao_atual_nao_pesquisa_quando_filtro_bloqueia():
    resultado = web_search.pesquisar_informacao_atual("o que é uma lista em Python?")
    assert "PESQUISA NA INTERNET NÃO NECESSÁRIA" in resultado


def test_pesquisar_informacao_atual_usa_ddgs_e_formata_resultado():
    web_search._CACHE.clear()

    resultados_falsos = [
        {
            "title": "Cotação do dólar hoje",
            "body": "O dólar está cotado a R$ 5,00.",
            "href": "https://exemplo.com/dolar",
        }
    ]

    with patch("ddgs.DDGS") as MockDDGS:
        instancia = MockDDGS.return_value
        instancia.text.return_value = resultados_falsos

        resultado = web_search.pesquisar_informacao_atual("cotação do dólar hoje")

    assert "Cotação do dólar hoje" in resultado
    assert "R$ 5,00" in resultado
    assert "exemplo.com/dolar" in resultado


def test_pesquisar_informacao_atual_usa_cache_na_segunda_chamada():
    web_search._CACHE.clear()

    resultados_falsos = [
        {"title": "Notícia A", "body": "Resumo A", "href": "https://a.com"}
    ]

    with patch("ddgs.DDGS") as MockDDGS:
        instancia = MockDDGS.return_value
        instancia.text.return_value = resultados_falsos

        primeiro = web_search.pesquisar_informacao_atual("notícias de hoje sobre futebol")
        segundo = web_search.pesquisar_informacao_atual("notícias de hoje sobre futebol")

        # DDGS().text só deveria ter sido chamado uma vez (cache reutilizado).
        assert instancia.text.call_count == 1

    assert "Notícia A" in primeiro
    assert "cache local recente" in segundo


def test_pesquisar_informacao_atual_trata_erro_do_ddgs():
    web_search._CACHE.clear()

    with patch("ddgs.DDGS") as MockDDGS:
        MockDDGS.return_value.text.side_effect = RuntimeError("falha de rede")

        resultado = web_search.pesquisar_informacao_atual("cotação do bitcoin agora")

    assert "Não foi possível consultar informações atuais" in resultado


def test_pesquisar_informacao_atual_sem_resultados():
    web_search._CACHE.clear()

    with patch("ddgs.DDGS") as MockDDGS:
        MockDDGS.return_value.text.return_value = []

        resultado = web_search.pesquisar_informacao_atual("previsão do tempo em Marte hoje")

    assert "Não encontrei resultados suficientes" in resultado
