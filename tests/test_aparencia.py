"""
Testes da aparência da janela.

Dois problemas visuais reportados em uso real:
- o visualizador repetia, letra por letra, o mesmo texto já exibido na
  caixa STATUS logo abaixo;
- a barra de título ficava com o ícone branco padrão do Qt, porque
  nenhum setWindowIcon era chamado.
"""

from pathlib import Path

from core.recursos import NOME_ICONE, caminho_icone
from ui.alfred_visualizer import AlfredVisualizer


# ============================================================
# Estado curto do visualizador
# ============================================================

def _visualizador(status, ativo):
    visualizador = AlfredVisualizer.__new__(AlfredVisualizer)
    visualizador.status = status
    visualizador.ativo = ativo
    return visualizador


def test_estado_curto_offline_quando_inativo():
    visualizador = _visualizador("IMAGEM DA TELA ENVIADA PARA ANÁLISE.", False)
    assert visualizador._estado_curto() == "OFFLINE"


def test_estado_curto_resume_mensagem_longa():
    """
    Este é o caso do problema: a mensagem completa aparecia dentro do
    visualizador e de novo na caixa STATUS.
    """
    visualizador = _visualizador("IMAGEM DA TELA ENVIADA PARA ANÁLISE.", True)
    assert visualizador._estado_curto() == "ONLINE"


def test_estado_curto_reconhece_situacoes_relevantes():
    casos = {
        "CONECTANDO AO GEMINI LIVE...": "CONECTANDO",
        "PREPARANDO CONEXÃO...": "CONECTANDO",
        "RENOVANDO A CONEXÃO. A CONVERSA CONTINUA.": "RECONECTANDO",
        "RECONECTANDO AO GEMINI LIVE... (TENTATIVA 2/5)": "RECONECTANDO",
        "ENCERRANDO": "ENCERRANDO",
        "ERRO": "ERRO",
        "ALF CONECTADO. PODE FALAR.": "ONLINE",
    }

    for status, esperado in casos.items():
        assert _visualizador(status, True)._estado_curto() == esperado, status


def test_estado_curto_nunca_repete_a_mensagem_completa():
    longa = "IMAGEM DA CÂMERA ENVIADA PARA ANÁLISE."
    curto = _visualizador(longa, True)._estado_curto()

    assert curto != longa
    assert " " not in curto


# ============================================================
# Ícone da janela
# ============================================================

def test_icone_do_projeto_existe():
    caminho = caminho_icone()

    assert caminho is not None, f"{NOME_ICONE} não encontrado no projeto"
    assert caminho.is_file()
    assert caminho.suffix.lower() == ".ico"


def test_janela_e_aplicacao_definem_o_icone():
    """Garante que o setWindowIcon não seja removido por engano."""

    janela = Path("ui/main_window.py").read_text(encoding="utf-8")
    principal = Path("main_basic.py").read_text(encoding="utf-8")

    assert "setWindowIcon" in janela
    assert "setWindowIcon" in principal
    assert "definir_id_aplicacao" in principal


def test_spec_empacota_o_icone_como_dado():
    """
    O ícone é lido em tempo de execução, então precisa existir como
    arquivo dentro do pacote, não só embutido no cabeçalho do .exe.
    """

    spec = Path("ALF.spec").read_text(encoding="utf-8")

    assert f"('{NOME_ICONE}', '.')" in spec
