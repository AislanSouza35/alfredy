"""
O log precisa dizer qual ferramenta rodou, não só quais falharam.

Em 18/09/2026 o ALF passou a dizer que não conseguia escrever num campo
do Chrome. O log daquela sessão não tinha nenhuma falha de ferramenta --
e, como só falhas eram registradas, não dava para saber se ele tinha
tentado e falhado ou se nem tinha chamado a função. Sem essa distinção,
qualquer conserto seria chute.

O sucesso entra só com o nome: o resultado de uma ferramenta costuma
trazer nome e trabalho de aluno.
"""

from pathlib import Path

import pytest

from gemini.live_client import GeminiLiveWorker


CODIGO = Path("gemini/live_client.py").read_text(encoding="utf-8")


@pytest.fixture
def log(tmp_path, monkeypatch):
    caminho = tmp_path / "alf_runtime_debug.log"
    monkeypatch.setattr(
        GeminiLiveWorker, "caminho_log_diagnostico", staticmethod(lambda: caminho)
    )
    return caminho


def test_ferramenta_que_deu_certo_aparece_no_log(log):
    GeminiLiveWorker.registrar_resultado_de_ferramenta(
        "escrever_no_campo_ativo", "Texto inserido no campo ativo com sucesso."
    )

    assert "Ferramenta 'escrever_no_campo_ativo' concluiu." in log.read_text(
        encoding="utf-8"
    )


def test_sucesso_nao_guarda_o_conteudo(log):
    """O resultado pode trazer nome e trabalho de aluno."""
    GeminiLiveWorker.registrar_resultado_de_ferramenta(
        "ler_entrega", "Ana Beatriz entregou: minha resposta da questão 1..."
    )

    conteudo = log.read_text(encoding="utf-8")

    assert "Ferramenta 'ler_entrega' concluiu." in conteudo
    assert "Ana Beatriz" not in conteudo


def test_falha_continua_com_o_motivo(log):
    GeminiLiveWorker.registrar_resultado_de_ferramenta(
        "clicar_elemento_visual",
        "Não consegui localizar o elemento com confiança suficiente.",
    )

    conteudo = log.read_text(encoding="utf-8")

    assert "nao concluiu" in conteudo
    assert "localizar o elemento" in conteudo


def test_falha_longa_e_cortada(log):
    GeminiLiveWorker.registrar_resultado_de_ferramenta(
        "ler_entrega", "Não consegui ler: " + "x" * 500
    )

    linha = log.read_text(encoding="utf-8").strip()

    assert len(linha) < 260


def test_instrucao_ensina_os_dois_passos_para_escrever_num_campo():
    assert "são DOIS passos" in CODIGO
    assert "escreve onde o cursor já" in CODIGO
    # Dizer só "não consigo escrever" foi exatamente a queixa.
    assert "em que passo parou" in CODIGO
