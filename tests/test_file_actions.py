"""Testes unitários e de integração para actions/file_actions.py.

Usa tmp_path como Área de Trabalho falsa (monkeypatch em area_de_trabalho)
para nunca tocar arquivos reais do usuário.
"""

import pytest

from actions import file_actions


@pytest.fixture
def area_falsa(tmp_path, monkeypatch):
    monkeypatch.setattr(file_actions, "area_de_trabalho", lambda: tmp_path)
    file_actions._AREA_TRANSFERENCIA["origem"] = None
    file_actions._AREA_TRANSFERENCIA["operacao"] = None
    return tmp_path


# ============================================================
# limpar_nome / normalização
# ============================================================

@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("Relatório Final", "Relatório Final"),
        ("nome/com:proibidos*?\"<>|", "nomecomproibidos"),
        ("nome.com.pontos...", "nome.com.pontos"),
        ("   espacos   ", "espacos"),
    ],
)
def test_limpar_nome(entrada, esperado):
    assert file_actions.limpar_nome(entrada) == esperado


def test_limpar_nome_valor_nao_string():
    assert file_actions.limpar_nome(123) == ""


# ============================================================
# criar_pasta_area_trabalho
# ============================================================

def test_criar_pasta_area_trabalho_cria_com_sucesso(area_falsa):
    resultado = file_actions.criar_pasta_area_trabalho("Projetos")
    assert "criada com sucesso" in resultado
    assert (area_falsa / "Projetos").is_dir()


def test_criar_pasta_area_trabalho_nao_sobrescreve_existente(area_falsa):
    (area_falsa / "Projetos").mkdir()
    resultado = file_actions.criar_pasta_area_trabalho("Projetos")
    assert "já existe" in resultado


def test_criar_pasta_area_trabalho_nome_invalido(area_falsa):
    resultado = file_actions.criar_pasta_area_trabalho("///")
    assert "inválido" in resultado


# ============================================================
# listar_area_de_trabalho
# ============================================================

def test_listar_area_de_trabalho_vazia(area_falsa):
    assert file_actions.listar_area_de_trabalho() == "A área de trabalho está vazia."


def test_listar_area_de_trabalho_com_itens(area_falsa):
    (area_falsa / "a.txt").write_text("x")
    (area_falsa / "pasta").mkdir()
    resultado = file_actions.listar_area_de_trabalho()
    assert "a.txt" in resultado
    assert "pasta" in resultado


# ============================================================
# organizar_area_de_trabalho_basico
# ============================================================

def test_organizar_area_de_trabalho_move_por_extensao(area_falsa):
    (area_falsa / "foto.png").write_text("x")
    (area_falsa / "documento.pdf").write_text("x")

    resultado = file_actions.organizar_area_de_trabalho_basico()

    assert (area_falsa / "Imagens" / "foto.png").exists()
    assert (area_falsa / "PDFs" / "documento.pdf").exists()
    assert "foto.png" in resultado
    assert "documento.pdf" in resultado


def test_organizar_area_de_trabalho_sem_arquivos(area_falsa):
    resultado = file_actions.organizar_area_de_trabalho_basico()
    assert "Não encontrei arquivos" in resultado


# ============================================================
# copiar / recortar / colar
# ============================================================

def test_copiar_e_colar_arquivo(area_falsa):
    (area_falsa / "origem.txt").write_text("conteudo")
    (area_falsa / "destino").mkdir()

    resultado_copia = file_actions.copiar_item_area_trabalho("origem.txt")
    assert "preparado para copiar" in resultado_copia

    resultado_colar = file_actions.colar_item_area_trabalho("destino")
    assert "copiado com sucesso" in resultado_colar
    assert (area_falsa / "destino" / "origem.txt").exists()
    # O original deve continuar existindo após copiar (não é recortar).
    assert (area_falsa / "origem.txt").exists()


def test_recortar_e_colar_arquivo(area_falsa):
    (area_falsa / "origem.txt").write_text("conteudo")
    (area_falsa / "destino").mkdir()

    file_actions.recortar_item_area_trabalho("origem.txt")
    resultado = file_actions.colar_item_area_trabalho("destino")

    assert "movido com sucesso" in resultado
    assert (area_falsa / "destino" / "origem.txt").exists()
    assert not (area_falsa / "origem.txt").exists()


def test_colar_sem_preparar_nada_antes(area_falsa):
    resultado = file_actions.colar_item_area_trabalho("")
    assert "Não há nenhum arquivo ou pasta preparado" in resultado


def test_colar_nao_sobrescreve_item_existente(area_falsa):
    (area_falsa / "origem.txt").write_text("conteudo")
    (area_falsa / "destino").mkdir()
    (area_falsa / "destino" / "origem.txt").write_text("ja existe")

    file_actions.copiar_item_area_trabalho("origem.txt")
    resultado = file_actions.colar_item_area_trabalho("destino")

    assert "Não sobrescrevi nada" in resultado
    assert (area_falsa / "destino" / "origem.txt").read_text() == "ja existe"


def test_colar_pasta_dentro_dela_mesma_e_bloqueado(area_falsa):
    pasta = area_falsa / "Pasta"
    pasta.mkdir()

    file_actions.recortar_item_area_trabalho("Pasta")
    resultado = file_actions.colar_item_area_trabalho("Pasta")

    assert "dentro dela mesma" in resultado


# ============================================================
# renomear
# ============================================================

def test_renomear_item_com_sucesso(area_falsa):
    (area_falsa / "antigo.txt").write_text("x")
    resultado = file_actions.renomear_item_area_trabalho("antigo.txt", "novo.txt")
    assert "renomeado" in resultado
    assert (area_falsa / "novo.txt").exists()
    assert not (area_falsa / "antigo.txt").exists()


def test_renomear_nao_sobrescreve_existente(area_falsa):
    (area_falsa / "a.txt").write_text("a")
    (area_falsa / "b.txt").write_text("b")
    resultado = file_actions.renomear_item_area_trabalho("a.txt", "b.txt")
    assert "Não sobrescrevi nada" in resultado


def test_renomear_item_inexistente(area_falsa):
    resultado = file_actions.renomear_item_area_trabalho("naoexiste.txt", "novo.txt")
    assert "Não encontrei" in resultado


# ============================================================
# segurança: caminhos fora da Área de Trabalho
# ============================================================

def test_resolver_caminho_relativo_neutraliza_tentativa_de_saida(area_falsa):
    # limpar_nome() remove segmentos só de pontos (".." vira ""), então a
    # tentativa de escapar da Área de Trabalho é neutralizada silenciosamente
    # em vez de subir diretórios: "../../fora" cai dentro de "fora".
    resultado = file_actions._resolver_caminho_relativo("../../fora")
    assert file_actions._esta_dentro_da_area(resultado)
    assert resultado == area_falsa / "fora"


def test_localizar_item_com_nome_parcial_unico(area_falsa):
    (area_falsa / "relatorio_final_2024.docx").write_text("x")
    item, erro = file_actions._localizar_item("relatorio final")
    assert erro is None
    assert item.name == "relatorio_final_2024.docx"


def test_localizar_item_ambiguo_retorna_erro(area_falsa):
    (area_falsa / "relatorio_a.txt").write_text("x")
    (area_falsa / "relatorio_b.txt").write_text("x")
    item, erro = file_actions._localizar_item("relatorio")
    assert item is None
    assert "mais de um item parecido" in erro
