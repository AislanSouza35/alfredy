"""
Testes da leitura dos arquivos que os alunos entregam no Drive.

Antes o ALF só via o nome do arquivo e mandava o professor abrir, o que
deixava a correção pela metade. Aqui o arquivo vira texto conforme o
tipo. Nenhum teste toca o Drive real.
"""

import io

import pytest

from actions import drive_actions as drive


# ============================================================
# Conversão por tipo de arquivo
# ============================================================

def test_texto_puro_e_lido_direto():
    conteudo = "def soma(a, b):\n    return a + b\n"

    resultado = drive._converter(conteudo.encode("utf-8"), "text/plain", "codigo.py")

    assert "def soma" in resultado


def test_texto_com_acento_em_latin1_nao_quebra():
    dados = "Conclusão do relatório".encode("latin-1")

    resultado = drive._converter(dados, "text/plain", "nota.txt")

    assert "Conclus" in resultado


def test_pdf_tem_o_texto_extraido():
    pypdf = pytest.importorskip("pypdf")

    escritor = pypdf.PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    escritor.write(buffer)

    resultado = drive._texto_de_pdf(buffer.getvalue())

    # Página em branco não tem texto: o aviso precisa ser explícito,
    # para o ALF não inventar o que estava escrito.
    assert "não tem texto selecionável" in resultado


def test_pdf_corrompido_nao_derruba():
    resultado = drive._texto_de_pdf(b"isto nao e um pdf")

    assert "Não consegui ler o PDF" in resultado


def test_docx_traz_paragrafos_e_tabelas():
    docx = pytest.importorskip("docx")

    documento = docx.Document()
    documento.add_paragraph("Resposta da questão 1.")
    tabela = documento.add_table(rows=1, cols=2)
    tabela.rows[0].cells[0].text = "Item"
    tabela.rows[0].cells[1].text = "Valor"

    buffer = io.BytesIO()
    documento.save(buffer)

    resultado = drive._texto_de_docx(buffer.getvalue())

    assert "Resposta da questão 1." in resultado
    assert "Item | Valor" in resultado


def test_planilha_e_lida_por_aba():
    openpyxl = pytest.importorskip("openpyxl")

    planilha = openpyxl.Workbook()
    aba = planilha.active
    aba.title = "Notas"
    aba.append(["Aluno", "Nota"])
    aba.append(["Ana", 8])

    buffer = io.BytesIO()
    planilha.save(buffer)

    resultado = drive._texto_de_xlsx(buffer.getvalue())

    assert "[aba Notas]" in resultado
    assert "Ana | 8" in resultado


def test_arquivo_binario_desconhecido_avisa():
    resultado = drive._converter(b"\x00\x01\x02\xff", "application/octet-stream", "x.bin")

    assert "não consigo ler" in resultado
    assert "precisa abrir" in resultado


def test_imagem_vai_para_o_gemini(monkeypatch):
    """Foto do caderno é comum; sem transcrever, a entrega fica ilegível."""
    chamadas = []

    def descrever_falso(dados, nome):
        chamadas.append(nome)
        return "Transcrição: a resposta é 42."

    monkeypatch.setattr(drive, "_descrever_imagem", descrever_falso)

    resultado = drive._converter(b"\x89PNG", "image/png", "foto.png")

    assert chamadas == ["foto.png"]
    assert "42" in resultado


def test_imagem_sem_chave_avisa_em_vez_de_falhar(monkeypatch):
    monkeypatch.setattr(drive, "GEMINI_API_KEY", None)

    resultado = drive._descrever_imagem(b"\x89PNG", "foto.png")

    assert "falta a chave" in resultado


# ============================================================
# Limites
# ============================================================

def test_texto_muito_longo_e_cortado():
    resultado = drive._cortar("x" * (drive.MAXIMO_TEXTO + 500))

    assert len(resultado) < drive.MAXIMO_TEXTO + 100
    assert "texto cortado" in resultado


def test_texto_dentro_do_limite_fica_inteiro():
    assert drive._cortar("resposta curta") == "resposta curta"


# ============================================================
# Leitura pelo Drive
# ============================================================

class _RequisicaoFalsa:
    def __init__(self, resposta):
        self._resposta = resposta

    def execute(self):
        return self._resposta


class _DriveFalso:
    def __init__(self, info, conteudo=b"", erro=None):
        self._info = info
        self._conteudo = conteudo
        self._erro = erro
        self.exportou = False

    def files(self):
        return self

    def get(self, **kwargs):
        if self._erro:
            raise self._erro
        return _RequisicaoFalsa(self._info)

    def get_media(self, **kwargs):
        return ("media", self._conteudo)

    def export_media(self, **kwargs):
        self.exportou = True
        return ("export", self._conteudo)


@pytest.fixture
def drive_falso(monkeypatch):
    def instalar(info, conteudo=b"", erro=None):
        falso = _DriveFalso(info, conteudo, erro)
        # Aceita as credenciais da conta dona da turma, como o módulo
        # real passa desde o suporte a várias contas.
        monkeypatch.setattr(
            drive,
            "obter_servico_drive",
            lambda credenciais=None: (falso, None),
        )

        class DownloadFalso:
            def __init__(self, buffer, requisicao):
                self._buffer = buffer
                self._dados = requisicao[1]

            def next_chunk(self):
                self._buffer.write(self._dados)
                return None, True

        monkeypatch.setattr(
            "googleapiclient.http.MediaIoBaseDownload", DownloadFalso
        )
        return falso

    return instalar


def test_documento_do_google_e_exportado(drive_falso):
    falso = drive_falso(
        {
            "name": "Trabalho da Ana",
            "mimeType": "application/vnd.google-apps.document",
        },
        conteudo="A resposta é 42.".encode("utf-8"),
    )

    resultado = drive.ler_arquivo_do_drive("d1")

    assert falso.exportou is True
    assert "A resposta é 42." in resultado
    assert "Trabalho da Ana" in resultado


def test_arquivo_comum_e_baixado(drive_falso):
    falso = drive_falso(
        {"name": "resposta.txt", "mimeType": "text/plain"},
        conteudo=b"minha resposta",
    )

    resultado = drive.ler_arquivo_do_drive("d1")

    assert falso.exportou is False
    assert "minha resposta" in resultado


def test_arquivo_grande_demais_nao_e_baixado(drive_falso):
    drive_falso(
        {
            "name": "video.mp4",
            "mimeType": "video/mp4",
            "size": str(drive.MAXIMO_DOWNLOAD + 1),
        }
    )

    resultado = drive.ler_arquivo_do_drive("d1")

    assert "grande demais" in resultado


def test_arquivo_vazio_e_avisado(drive_falso):
    drive_falso({"name": "vazio.txt", "mimeType": "text/plain"}, conteudo=b"")

    assert "está vazio" in drive.ler_arquivo_do_drive("d1")


def test_sem_permissao_explica(drive_falso):
    drive_falso({}, erro=Exception("403 insufficient permissions"))

    resultado = drive.ler_arquivo_do_drive("d1")

    assert "recusou o acesso" in resultado


def test_arquivo_apagado_explica(drive_falso):
    drive_falso({}, erro=Exception("404 not found"))

    resultado = drive.ler_arquivo_do_drive("d1")

    assert "apagado" in resultado


# ============================================================
# Escopo e reautorização
# ============================================================

def test_escopo_do_drive_esta_pedido():
    from actions.classroom_actions import ESCOPOS

    assert "https://www.googleapis.com/auth/drive.readonly" in ESCOPOS


def test_nenhum_escopo_da_acesso_amplo_de_escrita_ao_drive():
    """
    O ALF nunca deve poder alterar arquivo de aluno.

    Dois escopos de Drive são aceitáveis e nenhum permite isso:
      drive.readonly -> lê tudo, não escreve nada
      drive.file     -> escreve, mas SÓ nos arquivos criados pelo app

    O proibido é o escopo "drive" puro, que daria acesso total de
    escrita ao Drive inteiro do professor e dos alunos.
    """
    from actions.classroom_actions import ESCOPOS

    permitidos = {
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
    }

    escopos_de_drive = [e for e in ESCOPOS if "/drive" in e]

    assert escopos_de_drive, "esperava algum escopo de Drive"

    for escopo in escopos_de_drive:
        assert escopo in permitidos, f"escopo amplo demais: {escopo}"

    assert "https://www.googleapis.com/auth/drive" not in ESCOPOS
