"""
Testes do envio de e-mail.

A regra central é: NADA sai sem confirmação explícita, num turno
separado. A transcrição de voz erra nomes e negações -- "manda pro joão"
vira "joana", "não vou poder ir" perde o "não" -- e e-mail enviado não
volta. Os testes abaixo travam esse comportamento.
"""

from pathlib import Path

import pytest

from actions import email_actions as mail


CODIGO_CLIENTE = Path("gemini/live_client.py").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def ambiente_isolado(tmp_path, monkeypatch):
    """Contatos em arquivo próprio e SMTP configurado de mentira."""
    monkeypatch.setattr(mail, "ARQUIVO_CONTATOS", tmp_path / "contatos.json")
    monkeypatch.setattr(mail, "EMAIL_REMETENTE", "eu@gmail.com")
    monkeypatch.setattr(mail, "EMAIL_SENHA_APP", "senha-de-app-falsa")
    monkeypatch.setattr(mail, "EMAIL_NOME_REMETENTE", "Eu")
    monkeypatch.setattr(mail, "EMAIL_SMTP_SERVIDOR", None)
    monkeypatch.setattr(mail, "EMAIL_SMTP_PORTA", None)
    mail._rascunho["dados"] = None
    mail._rascunho["momento"] = 0.0

    # Nenhum teste consulta DNS de verdade. Testes que exercitam a
    # checagem de domínio substituem isto por conta própria.
    monkeypatch.setattr(
        mail.socket, "getaddrinfo", lambda dominio, porta: [("ok",)]
    )


@pytest.fixture
def enviados():
    registro = []

    def enviar_falso(mensagem, servidor, porta):
        # Com anexo a mensagem vira multipart, e get_content() não
        # sabe lidar com isso. get_body() pega só o texto.
        corpo = mensagem.get_body(preferencelist=("plain",))

        registro.append(
            {
                "para": mensagem["To"],
                "assunto": mensagem["Subject"],
                "corpo": corpo.get_content().strip() if corpo else "",
                "anexos": [
                    parte.get_filename()
                    for parte in mensagem.iter_attachments()
                ],
                "servidor": servidor,
                "porta": porta,
            }
        )

    enviar_falso.registro = registro
    return enviar_falso


# ============================================================
# A trava principal
# ============================================================

def test_preparar_nao_envia_nada(enviados):
    mail.preparar_email("joao@correio-fake.net", "Reunião", "Confirmado para as 10h.")

    assert enviados.registro == []
    assert mail.rascunho_pendente() is not None


def test_envio_so_acontece_apos_confirmacao(enviados):
    mail.preparar_email("joao@correio-fake.net", "Reunião", "Confirmado para as 10h.")
    assert enviados.registro == []

    resultado = mail.confirmar_envio_email(enviar=enviados)

    assert len(enviados.registro) == 1
    assert enviados.registro[0]["para"] == "joao@correio-fake.net"
    assert enviados.registro[0]["assunto"] == "Reunião"
    assert "Confirmado para as 10h." in enviados.registro[0]["corpo"]
    assert "enviado" in resultado


def test_confirmar_sem_rascunho_nao_envia(enviados):
    resultado = mail.confirmar_envio_email(enviar=enviados)

    assert enviados.registro == []
    assert "Não há nenhum e-mail pronto" in resultado


def test_rascunho_expira_e_nao_e_enviado_depois(enviados, monkeypatch):
    """
    Um "pode enviar" dito muito depois, já em outro assunto, não pode
    disparar o e-mail antigo.
    """
    mail.preparar_email("joao@correio-fake.net", "Assunto", "Corpo.")

    relogio = mail.time.monotonic() + mail.VALIDADE_RASCUNHO + 1
    monkeypatch.setattr(mail.time, "monotonic", lambda: relogio)

    resultado = mail.confirmar_envio_email(enviar=enviados)

    assert enviados.registro == []
    assert "expirou" in resultado


def test_cancelar_descarta_o_rascunho(enviados):
    mail.preparar_email("joao@correio-fake.net", "Assunto", "Corpo.")

    assert "Descartei" in mail.cancelar_email()
    assert mail.rascunho_pendente() is None

    mail.confirmar_envio_email(enviar=enviados)
    assert enviados.registro == []


def test_nao_reenvia_o_mesmo_rascunho_duas_vezes(enviados):
    mail.preparar_email("joao@correio-fake.net", "Assunto", "Corpo.")
    mail.confirmar_envio_email(enviar=enviados)
    mail.confirmar_envio_email(enviar=enviados)

    assert len(enviados.registro) == 1


def test_rascunho_sobrevive_a_falha_de_envio(monkeypatch):
    """Falhou o envio, o texto não pode ser perdido."""
    mail.preparar_email("joao@correio-fake.net", "Assunto", "Corpo.")

    def falhar(mensagem, servidor, porta):
        raise mail.smtplib.SMTPException("servidor fora do ar")

    resultado = mail.confirmar_envio_email(enviar=falhar)

    assert "NÃO foi enviado" in resultado
    assert mail.rascunho_pendente() is not None


def test_erro_de_autenticacao_orienta_a_senha_de_app():
    mail.preparar_email("joao@correio-fake.net", "Assunto", "Corpo.")

    def recusar(mensagem, servidor, porta):
        raise mail.smtplib.SMTPAuthenticationError(535, b"bad")

    resultado = mail.confirmar_envio_email(enviar=recusar)

    assert "senha de app" in resultado
    assert "NÃO foi enviado" in resultado


# ============================================================
# Validação do rascunho
# ============================================================

def test_leitura_em_voz_alta_traz_os_tres_campos():
    retorno = mail.preparar_email(
        "joao@correio-fake.net", "Reunião", "Confirmado para as 10h."
    )

    assert "joao@correio-fake.net" in retorno
    assert "Reunião" in retorno
    assert "Confirmado para as 10h." in retorno
    assert "NÃO enviado" in retorno


@pytest.mark.parametrize(
    "destinatario,assunto,mensagem,esperado",
    [
        ("", "a", "b", "Diga para quem"),
        ("joao@correio-fake.net", "", "b", "assunto"),
        ("joao@correio-fake.net", "a", "", "corpo"),
    ],
)
def test_campos_faltando_sao_perguntados(destinatario, assunto, mensagem, esperado):
    retorno = mail.preparar_email(destinatario, assunto, mensagem)

    assert esperado in retorno
    assert mail.rascunho_pendente() is None


def test_sem_configuracao_avisa_o_que_falta(monkeypatch):
    monkeypatch.setattr(mail, "EMAIL_SENHA_APP", None)

    retorno = mail.preparar_email("joao@correio-fake.net", "a", "b")

    assert "não está configurado" in retorno
    assert "EMAIL_SENHA_APP" in retorno


def test_mensagem_gigante_e_recusada():
    retorno = mail.preparar_email(
        "joao@correio-fake.net", "a", "x" * (mail.MAXIMO_MENSAGEM + 1)
    )

    assert "Resuma" in retorno
    assert mail.rascunho_pendente() is None


# ============================================================
# Contatos
# ============================================================

def test_guarda_e_usa_contato_pelo_nome(enviados):
    mail.salvar_contato("João Silva", "joao.silva@correio-fake.net")

    mail.preparar_email("joão silva", "Oi", "Tudo bem?")
    mail.confirmar_envio_email(enviar=enviados)

    assert enviados.registro[0]["para"] == "joao.silva@correio-fake.net"


def test_contato_ambiguo_pede_esclarecimento():
    mail.salvar_contato("João Silva", "joao.silva@correio-fake.net")
    mail.salvar_contato("João Pedro", "joao.pedro@correio-fake.net")

    retorno = mail.preparar_email("joão", "Oi", "Tudo bem?")

    assert "mais de um contato" in retorno
    assert mail.rascunho_pendente() is None


def test_destinatario_desconhecido_nao_vira_rascunho():
    retorno = mail.preparar_email("fulano", "Oi", "Tudo bem?")

    assert "Não tenho o e-mail" in retorno
    assert mail.rascunho_pendente() is None


def test_endereco_invalido_e_recusado():
    assert "não parece um e-mail válido" in mail.salvar_contato("Ana", "ana arroba x")


def test_atualizar_contato_existente():
    mail.salvar_contato("Ana", "ana@antigo.com")
    retorno = mail.salvar_contato("Ana", "ana@novo.com")

    assert "Atualizei" in retorno
    assert "ana@novo.com" in mail.listar_contatos()
    assert "ana@antigo.com" not in mail.listar_contatos()


def test_remover_contato():
    mail.salvar_contato("Ana", "ana@correio-fake.net")

    assert "Removi" in mail.remover_contato("Ana")
    assert "Não tenho nenhum contato" in mail.listar_contatos()


# ============================================================
# Servidor SMTP
# ============================================================

@pytest.mark.parametrize(
    "remetente,servidor",
    [
        ("eu@gmail.com", "smtp.gmail.com"),
        ("eu@outlook.com", "smtp-mail.outlook.com"),
        ("eu@hotmail.com", "smtp-mail.outlook.com"),
        ("eu@yahoo.com.br", "smtp.mail.yahoo.com"),
    ],
)
def test_servidor_deduzido_pelo_dominio(remetente, servidor, monkeypatch):
    monkeypatch.setattr(mail, "EMAIL_REMETENTE", remetente)

    assert mail.configuracao_smtp()[0] == servidor


def test_provedor_desconhecido_pede_configuracao(monkeypatch):
    monkeypatch.setattr(mail, "EMAIL_REMETENTE", "eu@empresa-propria.com.br")

    assert "EMAIL_SMTP_SERVIDOR" in mail.configuracao_smtp()[2]


# ============================================================
# Instrução do modelo
# ============================================================

@pytest.mark.parametrize(
    "ferramenta",
    [
        "preparar_email",
        "confirmar_envio_email",
        "cancelar_email",
        "salvar_contato",
        "listar_contatos",
        "remover_contato",
    ],
)
def test_ferramenta_registrada(ferramenta):
    assert f'name="{ferramenta}"' in CODIGO_CLIENTE


def test_instrucao_exige_dois_turnos_para_enviar():
    assert "Nunca chame confirmar_envio_email no mesmo turno" in CODIGO_CLIENTE
    assert "leia em voz alta" in CODIGO_CLIENTE.lower()


# ============================================================
# Destinatário inventado
# ============================================================
#
# Caso real: pedido um "e-mail de teste" sem destinatário, o modelo
# inventou arlas@example.com e o envio saiu. Voltou como falha de
# entrega, mas se o domínio inventado existisse, a mensagem teria
# chegado a um estranho.

@pytest.mark.parametrize(
    "endereco",
    [
        "arlas@example.com",
        "alguem@example.org",
        "teste@teste.com",
        "fulano@exemplo.com.br",
        "x@dominio.com",
        "y@algo.invalid",
        "z@coisa.test",
        "w@maquina.localhost",
    ],
)
def test_dominio_de_exemplo_nao_vira_rascunho(endereco, enviados):
    resultado = mail.preparar_email(endereco, "Teste", "Corpo.")

    assert "domínio de exemplo" in resultado
    assert mail.rascunho_pendente() is None
    assert enviados.registro == []


def test_dominio_inexistente_e_recusado(monkeypatch, enviados):
    """Pega erro de digitação antes de tentar entregar."""

    def resolver_falso(dominio, porta):
        if dominio == "gmail.com":
            return [("ok",)]
        raise mail.socket.gaierror("nao encontrado")

    monkeypatch.setattr(mail.socket, "getaddrinfo", resolver_falso)

    resultado = mail.preparar_email("joao@naoexiste-9988.com", "a", "b")

    assert "não existe" in resultado
    assert mail.rascunho_pendente() is None
    assert enviados.registro == []


def test_sem_internet_nao_bloqueia_endereco_valido(monkeypatch):
    """
    Se o DNS inteiro está fora, a culpa não é do endereço. Bloquear aí
    seria recusar e-mail legítimo por problema de rede.
    """

    def tudo_falha(dominio, porta):
        raise mail.socket.gaierror("sem rede")

    monkeypatch.setattr(mail.socket, "getaddrinfo", tudo_falha)

    existe, falha_de_rede = mail.dominio_existe("joao@empresa-real.com.br")

    assert existe is True
    assert falha_de_rede is True


def test_contato_com_dominio_de_exemplo_e_recusado():
    """A agenda também não pode receber endereço inventado."""
    resultado = mail.salvar_contato("Fulano", "fulano@example.com")

    assert "domínio de exemplo" in resultado
    assert "Não tenho nenhum contato" in mail.listar_contatos()


def test_endereco_real_continua_passando():
    resultado = mail.preparar_email("aislan.ss29@gmail.com", "Oi", "Teste.")

    assert resultado.startswith("Rascunho pronto")


def test_instrucao_proibe_inventar_destinatario():
    assert "NUNCA invente o endereço do destinatário" in CODIGO_CLIENTE
    assert "pertencer a um estranho" in CODIGO_CLIENTE


# ============================================================
# Anexos
# ============================================================

@pytest.fixture
def pasta_de_arquivos(tmp_path, monkeypatch):
    """Faz a busca de anexo olhar só uma pasta controlada."""
    from actions import vscode_actions

    monkeypatch.setattr(vscode_actions, "_raizes_de_busca", lambda: [tmp_path])
    monkeypatch.setattr(
        "actions.codigo_actions.RAIZ_PERMITIDA", tmp_path.resolve()
    )
    return tmp_path


def test_anexo_chega_intacto_na_mensagem(pasta_de_arquivos, enviados):
    conteudo = b"conteudo binario \x00\x01 do arquivo"
    (pasta_de_arquivos / "relatorio.pdf").write_bytes(conteudo)

    mail.preparar_email(
        "joao@correio-fake.net", "Relatório", "Segue.", anexo="relatorio.pdf"
    )
    mail.confirmar_envio_email(enviar=enviados)

    assert len(enviados.registro) == 1
    assert enviados.registro[0]["anexos"] == ["relatorio.pdf"]
    assert enviados.registro[0]["corpo"] == "Segue."


def test_mensagem_montada_carrega_o_arquivo(pasta_de_arquivos):
    conteudo = b"x" * 500
    (pasta_de_arquivos / "notas.xlsx").write_bytes(conteudo)

    mail.preparar_email(
        "joao@correio-fake.net", "Notas", "Segue.", anexo="notas.xlsx"
    )
    mensagem = mail._montar_mensagem(mail.rascunho_pendente())

    anexos = list(mensagem.iter_attachments())
    assert len(anexos) == 1
    assert anexos[0].get_filename() == "notas.xlsx"
    assert anexos[0].get_payload(decode=True) == conteudo


def test_leitura_em_voz_alta_menciona_nome_e_tamanho(pasta_de_arquivos):
    (pasta_de_arquivos / "planilha.xlsx").write_bytes(b"y" * 4096)

    retorno = mail.preparar_email(
        "joao@correio-fake.net", "Notas", "Segue.", anexo="planilha"
    )

    assert "planilha.xlsx" in retorno
    assert "KB" in retorno


def test_acha_arquivo_pelo_nome_sem_extensao(pasta_de_arquivos):
    (pasta_de_arquivos / "meu-relatorio.pdf").write_bytes(b"z")

    encontrados = mail.localizar_arquivo("meu-relatorio")

    assert len(encontrados) == 1
    assert encontrados[0].name == "meu-relatorio.pdf"


def test_arquivo_inexistente_nao_vira_rascunho(pasta_de_arquivos):
    retorno = mail.preparar_email(
        "joao@correio-fake.net", "a", "b", anexo="nao-existe-999.pdf"
    )

    assert "Não encontrei" in retorno
    assert mail.rascunho_pendente() is None


def test_arquivos_ambiguos_pedem_escolha(pasta_de_arquivos):
    (pasta_de_arquivos / "notas-3A.xlsx").write_bytes(b"a")
    (pasta_de_arquivos / "notas-3B.xlsx").write_bytes(b"b")

    retorno = mail.preparar_email(
        "joao@correio-fake.net", "a", "b", anexo="notas"
    )

    assert "mais de um arquivo" in retorno
    assert mail.rascunho_pendente() is None


@pytest.mark.parametrize(
    "nome", [".env", "id_rsa", "credentials.json", "senha.txt"]
)
def test_arquivo_de_segredo_nunca_e_anexado(nome, pasta_de_arquivos):
    """
    Anexar é pior que ler: manda o conteúdo para fora da máquina.
    O .env carrega a chave do Gemini e a senha de app do e-mail.
    """
    (pasta_de_arquivos / nome).write_bytes(b"CHAVE=secreta")

    retorno = mail.preparar_email(
        "joao@correio-fake.net", "a", "b", anexo=nome
    )

    assert "senha ou chave" in retorno
    assert mail.rascunho_pendente() is None


@pytest.mark.parametrize("nome", ["virus.exe", "script.bat", "macro.vbs", "app.msi"])
def test_executavel_e_recusado(nome, pasta_de_arquivos):
    (pasta_de_arquivos / nome).write_bytes(b"MZ")

    retorno = mail.preparar_email(
        "joao@correio-fake.net", "a", "b", anexo=nome
    )

    assert "executável" in retorno
    assert mail.rascunho_pendente() is None


def test_arquivo_grande_demais_e_recusado(pasta_de_arquivos, monkeypatch):
    monkeypatch.setattr(mail, "MAXIMO_ANEXO", 1024)
    (pasta_de_arquivos / "grande.zip").write_bytes(b"x" * 5000)

    retorno = mail.preparar_email(
        "joao@correio-fake.net", "a", "b", anexo="grande.zip"
    )

    assert "acima do" in retorno
    assert mail.rascunho_pendente() is None


def test_arquivo_vazio_e_recusado(pasta_de_arquivos):
    (pasta_de_arquivos / "vazio.txt").write_bytes(b"")

    retorno = mail.preparar_email(
        "joao@correio-fake.net", "a", "b", anexo="vazio.txt"
    )

    assert "está vazio" in retorno


def test_email_sem_anexo_continua_funcionando(enviados):
    mail.preparar_email("joao@correio-fake.net", "Oi", "Sem anexo.")
    mensagem = mail._montar_mensagem(mail.rascunho_pendente())

    assert list(mensagem.iter_attachments()) == []

    mail.confirmar_envio_email(enviar=enviados)
    assert len(enviados.registro) == 1


def test_confirmacao_menciona_o_anexo(pasta_de_arquivos, enviados):
    (pasta_de_arquivos / "doc.pdf").write_bytes(b"pdf")

    mail.preparar_email(
        "joao@correio-fake.net", "Doc", "Segue.", anexo="doc.pdf"
    )
    resultado = mail.confirmar_envio_email(enviar=enviados)

    assert "doc.pdf" in resultado


def test_instrucao_proibe_inventar_anexo():
    assert "Nunca invente nome de arquivo" in CODIGO_CLIENTE
    assert "nunca diga que anexou" in CODIGO_CLIENTE
