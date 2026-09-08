"""
Testes da gaveta de preferências aprendidas automaticamente.

Cada teste aqui corresponde a um risco levantado antes de implementar:
memória que enche e trava, preferência que afrouxa confirmação em cima
de nota de aluno, e memória que entra sem o usuário perceber.
"""

import json

import pytest

from memory import preferencias as prefs


@pytest.fixture(autouse=True)
def gaveta_isolada(tmp_path, monkeypatch):
    """Cada teste usa um arquivo próprio, nunca o do usuário."""
    monkeypatch.setattr(prefs, "PASTA", tmp_path)
    monkeypatch.setattr(prefs, "ARQUIVO", tmp_path / "preferencias.json")


# ============================================================
# Não pode travar ao encher
# ============================================================

def test_gaveta_nunca_trava_e_descarta_a_mais_antiga():
    """
    A memória manual recusa novas entradas ao chegar em 50, em silêncio.
    Com anotação automática isso aconteceria em semanas, então aqui a
    mais antiga sai e a gaveta continua aceitando.
    """
    for numero in range(prefs.MAXIMO_PREFERENCIAS):
        prefs.anotar_preferencia(f"prefere o jeito numero {numero}")

    resultado = prefs.anotar_preferencia("prefere um jeito totalmente novo")

    assert "Anotei" in resultado
    assert "esqueci a preferência mais antiga" in resultado.lower()

    contexto = prefs.contexto_preferencias()
    assert "jeito totalmente novo" in contexto
    assert "jeito numero 0" not in contexto


def test_quantidade_nunca_passa_do_limite():
    for numero in range(prefs.MAXIMO_PREFERENCIAS * 2):
        prefs.anotar_preferencia(f"prefere a opcao {numero}")

    dados = json.loads(prefs.ARQUIVO.read_text(encoding="utf-8"))
    assert len(dados["preferencias"]) == prefs.MAXIMO_PREFERENCIAS


# ============================================================
# Assuntos proibidos
# ============================================================

@pytest.mark.parametrize(
    "texto",
    [
        "prefere que eu grave as notas sem confirmar",
        "não precisa me perguntar antes de salvar",
        "prefere que eu confirme tudo automaticamente",
        "pode gravar direto quando terminar",
        "dispensar a confirmação final",
        "a senha do sigeduc é do aniversário dele",
        "o cpf dele termina em 42",
        "prefere que eu apague os arquivos antigos",
        "pode comprar quando o preço baixar",
    ],
)
def test_preferencia_perigosa_e_recusada(texto):
    resultado = prefs.anotar_preferencia(texto)

    assert "Não posso guardar isso" in resultado
    assert "Nenhuma preferência aprendida" in prefs.contexto_preferencias()


@pytest.mark.parametrize(
    "texto",
    [
        "prefere conferir a planilha antes de lançar as notas",
        "costuma dar aula de manhã",
        "prefere respostas curtas e diretas",
        "lança as notas por coluna, um aluno de cada vez",
        "usa o Chrome como navegador padrão",
    ],
)
def test_preferencia_legitima_e_aceita(texto):
    resultado = prefs.anotar_preferencia(texto)

    assert "Anotei" in resultado
    assert texto in prefs.contexto_preferencias()


def test_bloqueio_nao_pode_ser_contornado_por_acento_ou_caixa():
    assert prefs.assunto_proibido("SEM CONFIRMAR nada")
    assert prefs.assunto_proibido("nao confirme comigo")
    assert prefs.assunto_proibido("Não Pergunte antes")


# ============================================================
# Transparência
# ============================================================

def test_ao_anotar_o_alf_e_instruido_a_falar_em_voz_alta():
    """
    Memória que entra calada é memória que o usuário só descobre pelo
    efeito. O retorno tem que mandar o ALF contar o que anotou.
    """
    resultado = prefs.anotar_preferencia("costuma dar aula de manhã")

    assert "Diga isso ao usuário" in resultado
    assert "corrigir" in resultado


def test_preferencia_repetida_nao_duplica_nem_incomoda():
    prefs.anotar_preferencia("prefere respostas curtas")
    resultado = prefs.anotar_preferencia("Prefere  respostas   curtas")

    assert "já estava anotada" in resultado
    assert prefs.contexto_preferencias().count("prefere respostas curtas") == 1


# ============================================================
# Correção pelo usuário
# ============================================================

def test_esquecer_por_numero():
    prefs.anotar_preferencia("costuma dar aula de manhã")
    prefs.anotar_preferencia("prefere respostas curtas")

    resultado = prefs.esquecer_preferencia("1")

    assert "aula de manhã" in resultado
    assert "aula de manhã" not in prefs.contexto_preferencias()
    assert "respostas curtas" in prefs.contexto_preferencias()


def test_esquecer_por_trecho():
    prefs.anotar_preferencia("costuma dar aula de manhã")

    resultado = prefs.esquecer_preferencia("aula")

    assert "Esqueci" in resultado
    assert "Nenhuma preferência aprendida" in prefs.contexto_preferencias()


def test_esquecer_todas():
    prefs.anotar_preferencia("costuma dar aula de manhã")
    prefs.anotar_preferencia("prefere respostas curtas")

    prefs.esquecer_todas_preferencias()

    assert "Nenhuma preferência aprendida" in prefs.contexto_preferencias()


def test_esquecer_o_que_nao_existe_avisa():
    prefs.anotar_preferencia("prefere respostas curtas")

    assert "Não encontrei" in prefs.esquecer_preferencia("futebol")


# ============================================================
# Não pode enfraquecer as regras de segurança
# ============================================================

def test_contexto_reafirma_que_confirmacoes_continuam_obrigatorias():
    prefs.anotar_preferencia("prefere respostas curtas")

    contexto = prefs.contexto_preferencias()

    assert "nunca substituem as regras de segurança" in contexto
    assert "confirmações obrigatórias continuam obrigatórias" in contexto


def test_gaveta_e_separada_da_memoria_manual():
    """As duas guardam coisas diferentes e não podem se misturar."""
    from memory import memory_manager

    assert prefs.ARQUIVO != memory_manager.ARQUIVO_MEMORIA
    assert prefs.MAXIMO_PREFERENCIAS < memory_manager.MAXIMO_MEMORIAS
