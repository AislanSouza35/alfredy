"""
Garante que o ALF não volte a dizer que "não consegue" usar o mouse.

O acesso ao mouse e ao teclado sempre funcionou -- verificado na
prática movendo o ponteiro, clicando, digitando e usando ctrl+a numa
janela de teste. O que falhava era a instrução do sistema, que trazia
uma frase de uma versão anterior:

    "Use clicar_mouse ... somente na posição atual do ponteiro.
     Ainda não localize elementos pela imagem."

Essa última frase contradizia o parágrafo seguinte, que manda usar
clicar_elemento_visual justamente para localizar elementos na imagem.
Diante da contradição, o modelo respondia que não conseguia.
"""

import sys
from pathlib import Path

import pytest

from vision.click_locator import _alvo_bloqueado


CODIGO = Path("gemini/live_client.py").read_text(encoding="utf-8")


# ============================================================
# A instrução não pode se contradizer
# ============================================================

def test_frase_contraditoria_foi_removida():
    assert "Ainda não localize elementos pela imagem" not in CODIGO


def test_instrucao_afirma_o_acesso_ao_mouse_e_teclado():
    assert "TEM acesso ao mouse e ao teclado" in CODIGO
    assert "Nunca diga que não consegue mexer no mouse" in CODIGO


def test_instrucao_ensina_a_fechar_pelo_mouse():
    assert "botão X de fechar da janela" in CODIGO


def test_instrucao_prefere_fechar_aplicativo_quando_o_mouse_nao_foi_exigido():
    assert "prefira" in CODIGO
    assert "fechar_aplicativo, que é mais confiável" in CODIGO


# ============================================================
# Fechar pelo mouse não pode cair no bloqueio de segurança
# ============================================================

@pytest.mark.parametrize(
    "alvo",
    [
        "botão X de fechar da janela",
        "botão fechar no canto superior direito",
        "X da janela do navegador",
        "fechar aba atual",
    ],
)
def test_alvos_de_fechamento_nao_sao_bloqueados(alvo):
    assert not _alvo_bloqueado(alvo)


@pytest.mark.parametrize(
    "alvo",
    [
        "botão excluir conta",
        "confirmar pagamento",
        "esvaziar lixeira",
        "desinstalar programa",
    ],
)
def test_alvos_realmente_perigosos_continuam_bloqueados(alvo):
    assert _alvo_bloqueado(alvo)


# ============================================================
# As funções de mouse e teclado existem e são chamáveis
# ============================================================

@pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="As ações de mouse e teclado usam APIs do Windows.",
)
def test_funcoes_de_mouse_e_teclado_estao_disponiveis():
    from actions import mouse_actions, text_actions

    for funcao in (
        "clicar_mouse",
        "duplo_clique_mouse",
        "clique_direito_mouse",
        "rolar_pagina",
        "mover_mouse_para",
        "mover_e_clicar",
        "obter_posicao_mouse",
    ):
        assert callable(getattr(mouse_actions, funcao)), funcao

    for funcao in ("escrever_no_campo_ativo", "pressionar_atalho_teclado"):
        assert callable(getattr(text_actions, funcao)), funcao


@pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="As ações de mouse usam APIs do Windows.",
)
def test_leitura_da_posicao_do_mouse_funciona():
    """Se isto falhar, o acesso ao mouse está mesmo indisponível."""
    from actions.mouse_actions import obter_posicao_mouse

    posicao = obter_posicao_mouse()

    assert posicao is not None
    assert len(posicao) == 2


@pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="As ações de mouse usam APIs do Windows.",
)
def test_movimento_para_fora_da_tela_e_recusado():
    """A recusa precisa ser explícita, não um clique em lugar errado."""
    from actions.mouse_actions import mover_mouse_para

    resultado = mover_mouse_para(999999, 999999)

    assert "fora da tela" in resultado


# ============================================================
# As ferramentas continuam registradas
# ============================================================

@pytest.mark.parametrize(
    "ferramenta",
    [
        "clicar_mouse",
        "duplo_clique_mouse",
        "clique_direito_mouse",
        "rolar_pagina",
        "clicar_elemento_visual",
        "escrever_no_campo_ativo",
        "pressionar_atalho_teclado",
        "fechar_aplicativo",
    ],
)
def test_ferramenta_registrada_no_modelo(ferramenta):
    assert f'name="{ferramenta}"' in CODIGO
