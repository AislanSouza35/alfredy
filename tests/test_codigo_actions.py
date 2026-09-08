"""
Testes de ler, criar e executar código.

Estas são as funções mais poderosas do ALF: gravam arquivo fora da Área
de Trabalho e executam programas. Cada teste aqui corresponde a um
limite que precisa continuar valendo.
"""

from pathlib import Path

import pytest

from actions import codigo_actions as cod


CODIGO_CLIENTE = Path("gemini/live_client.py").read_text(encoding="utf-8")


@pytest.fixture
def projeto(tmp_path, monkeypatch):
    """Faz a pasta temporária valer como pasta do usuário."""
    monkeypatch.setattr(cod, "RAIZ_PERMITIDA", tmp_path.resolve())
    return tmp_path


# ============================================================
# Onde pode mexer
# ============================================================

def test_recusa_caminho_fora_da_pasta_do_usuario(projeto):
    resultado = cod.ler_arquivo("C:/Windows/system32/config/sam")

    assert "fora da sua pasta de usuário" in resultado


@pytest.mark.parametrize(
    "caminho",
    ["AppData/Local/x.txt", ".ssh/config", ".aws/credentials"],
)
def test_recusa_pastas_de_credencial(caminho, projeto):
    resultado = cod.ler_arquivo(caminho)

    assert "Não mexo" in resultado or "senha ou chave" in resultado


@pytest.mark.parametrize(
    "nome",
    [".env", "id_rsa", "certificado.pem", "credentials.json", "senha.txt"],
)
def test_arquivos_de_segredo_sao_recusados(nome, projeto):
    """
    Importa mais aqui que em outros projetos: o ALF fala em voz alta o
    que lê. Ler o .env faria ele ditar a chave da API e a senha do e-mail.
    """
    (projeto / nome).write_text("SEGREDO=123", encoding="utf-8")

    resultado = cod.ler_arquivo(str(projeto / nome))

    assert "senha ou chave" in resultado
    assert "SEGREDO" not in resultado


def test_nao_grava_por_cima_de_arquivo_de_segredo(projeto):
    env = projeto / ".env"
    env.write_text("CHAVE=original", encoding="utf-8")

    cod.criar_arquivo_codigo(str(env), "CHAVE=hackeada")

    assert env.read_text(encoding="utf-8") == "CHAVE=original"


# ============================================================
# Ler
# ============================================================

def test_le_o_conteudo_real(projeto):
    arquivo = projeto / "main.py"
    arquivo.write_text("print('oi')\n", encoding="utf-8")

    resultado = cod.ler_arquivo(str(arquivo))

    assert "print('oi')" in resultado
    assert "main.py" in resultado


def test_leitura_orienta_a_nao_ditar_o_codigo(projeto):
    arquivo = projeto / "main.py"
    arquivo.write_text("x = 1\n", encoding="utf-8")

    assert "Não leia o código em voz alta" in cod.ler_arquivo(str(arquivo))


def test_arquivo_inexistente_avisa(projeto):
    assert "Não encontrei" in cod.ler_arquivo(str(projeto / "sumiu.py"))


def test_arquivo_grande_demais_pede_recorte(projeto):
    grande = projeto / "grande.py"
    grande.write_text("x" * (cod.MAXIMO_LEITURA + 10), encoding="utf-8")

    assert "grande demais" in cod.ler_arquivo(str(grande))


def test_arquivo_binario_e_identificado(projeto):
    binario = projeto / "imagem.png"
    binario.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")

    assert "não é um arquivo de texto" in cod.ler_arquivo(str(binario))


def test_pasta_devolve_listagem(projeto):
    (projeto / "src").mkdir()
    (projeto / "src" / "a.py").write_text("", encoding="utf-8")

    resultado = cod.ler_arquivo(str(projeto / "src"))

    assert "é uma pasta" in resultado
    assert "a.py" in resultado


# ============================================================
# Criar e substituir
# ============================================================

def test_cria_arquivo_com_conteudo(projeto):
    alvo = projeto / "novo.py"

    resultado = cod.criar_arquivo_codigo(str(alvo), "def f():\n    return 1")

    assert alvo.exists()
    assert "def f():" in alvo.read_text(encoding="utf-8")
    assert "Criei novo.py" in resultado


def test_cria_pastas_intermediarias(projeto):
    alvo = projeto / "src" / "utils" / "helper.py"

    cod.criar_arquivo_codigo(str(alvo), "x = 1")

    assert alvo.exists()


def test_identacao_e_preservada(projeto):
    alvo = projeto / "codigo.py"
    conteudo = "def f(n):\n    if n:\n        return 1\n    return 0\n"

    cod.criar_arquivo_codigo(str(alvo), conteudo)

    assert alvo.read_text(encoding="utf-8") == conteudo


def test_nao_substitui_sem_confirmacao(projeto):
    alvo = projeto / "existente.py"
    alvo.write_text("original = True\n", encoding="utf-8")

    resultado = cod.criar_arquivo_codigo(str(alvo), "novo = True")

    assert "já existe" in resultado
    assert alvo.read_text(encoding="utf-8") == "original = True\n"


def test_substituicao_guarda_copia_de_seguranca(projeto):
    alvo = projeto / "existente.py"
    alvo.write_text("original = True\n", encoding="utf-8")

    resultado = cod.criar_arquivo_codigo(
        str(alvo), "novo = True", sobrescrever=True
    )

    backups = list(projeto.glob("existente.py.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "original = True\n"
    assert "novo = True" in alvo.read_text(encoding="utf-8")
    assert ".bak" in resultado


def test_conteudo_gigante_e_recusado(projeto):
    resultado = cod.criar_arquivo_codigo(
        str(projeto / "x.py"), "a" * (cod.MAXIMO_ESCRITA + 1)
    )

    assert "Divida em arquivos menores" in resultado


# ============================================================
# Executar
# ============================================================

@pytest.mark.parametrize(
    "comando",
    ["rm -rf /", "del *.*", "format c:", "shutdown -s", "curl algo"],
)
def test_programa_fora_da_lista_e_recusado(comando, projeto):
    resultado = cod.executar_no_terminal(comando)

    assert "Não posso executar" in resultado


@pytest.mark.parametrize(
    "comando",
    ["git push origin main", "git reset --hard", "git clean -fd"],
)
def test_git_destrutivo_ou_que_publica_e_recusado(comando, projeto):
    resultado = cod.executar_no_terminal(comando)

    assert "não cuido" in resultado or "apagar ou publicar" in resultado


@pytest.mark.parametrize(
    "comando",
    [
        "python a.py && del tudo",
        "python a.py | rm x",
        "python a.py; format c:",
        "python -c print > arquivo",
    ],
)
def test_comandos_encadeados_sao_recusados(comando, projeto):
    """Sem shell nada seria interpretado, mas recusar deixa a regra clara."""
    resultado = cod.executar_no_terminal(comando)

    assert "encadeados" in resultado


@pytest.mark.parametrize(
    "comando",
    ["pip uninstall requests", "npm publish", "git push --force"],
)
def test_argumentos_perigosos_sao_recusados(comando, projeto):
    resultado = cod.executar_no_terminal(comando)

    assert "apagar ou publicar" in resultado or "não cuido" in resultado


def test_comando_permitido_roda_e_devolve_a_saida(projeto):
    arquivo = projeto / "ola.py"
    arquivo.write_text("print('funcionou')\n", encoding="utf-8")

    resultado = cod.executar_no_terminal(
        "python ola.py", pasta=str(projeto)
    )

    assert "funcionou" in resultado
    assert "concluído" in resultado


def test_erro_de_execucao_e_reportado(projeto):
    arquivo = projeto / "quebrado.py"
    arquivo.write_text("raise ValueError('falhou de proposito')\n", encoding="utf-8")

    resultado = cod.executar_no_terminal(
        "python quebrado.py", pasta=str(projeto)
    )

    assert "erro" in resultado.lower()
    assert "falhou de proposito" in resultado


def test_comando_travado_e_interrompido(projeto):
    arquivo = projeto / "eterno.py"
    arquivo.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")

    resultado = cod.executar_no_terminal(
        "python eterno.py", pasta=str(projeto), timeout=3
    )

    assert "interrompido" in resultado


def test_programa_inexistente_avisa(projeto, monkeypatch):
    monkeypatch.setattr(cod.shutil, "which", lambda nome: None)

    assert "não está instalado" in cod.executar_no_terminal("python x.py")


# ============================================================
# Registro no modelo
# ============================================================

@pytest.mark.parametrize(
    "ferramenta",
    ["ler_arquivo", "criar_arquivo_codigo", "executar_no_terminal"],
)
def test_ferramenta_registrada(ferramenta):
    assert f'name="{ferramenta}"' in CODIGO_CLIENTE


def test_instrucao_exige_ler_antes_de_alterar():
    assert "ANTES de alterar qualquer arquivo que já existe, chame" in CODIGO_CLIENTE
    assert "Nunca leia código em voz alta" in CODIGO_CLIENTE
