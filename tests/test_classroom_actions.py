"""
Testes da integração com o Google Classroom.

O que mais importa aqui: nota lançada errada afeta a vida de um aluno e
não se desfaz sozinha. Por isso o lançamento é em dois passos, igual ao
e-mail, e os testes abaixo travam esse comportamento.

Nenhum teste toca a API real -- o serviço é substituído por um duplo.
"""

from pathlib import Path

import pytest

from actions import classroom_actions as sala


CODIGO_CLIENTE = Path("gemini/live_client.py").read_text(encoding="utf-8")


# ============================================================
# Duplo da API do Classroom
# ============================================================

class _Requisicao:
    def __init__(self, resposta, erro=None):
        self._resposta = resposta
        self._erro = erro

    def execute(self):
        if self._erro:
            raise self._erro
        return self._resposta


class _ServicoFalso:
    """Reproduz só o encadeamento que o módulo usa."""

    def __init__(self, turmas=None, atividades=None, entregas=None, alunos=None):
        self._turmas = turmas or []
        self._atividades = atividades or []
        self._entregas = entregas or []
        self._alunos = alunos or []
        self.patches = []

    def courses(self):
        # Reinicia o contexto: o encadeamento sempre começa aqui, e sem
        # isto uma consulta anterior deixava o duplo no estado errado.
        self._contexto = "turmas"
        return self

    def list(self, **kwargs):
        if "courseWorkId" in kwargs:
            return _Requisicao({"studentSubmissions": self._entregas})
        if "courseId" in kwargs and self._contexto == "atividades":
            return _Requisicao({"courseWork": self._atividades})
        if "courseId" in kwargs and self._contexto == "alunos":
            return _Requisicao({"students": self._alunos})
        return _Requisicao({"courses": self._turmas})

    # O encadeamento real é courses().courseWork().studentSubmissions().
    _contexto = "turmas"

    def courseWork(self):
        self._contexto = "atividades"
        return self

    def students(self):
        self._contexto = "alunos"
        return self

    def studentSubmissions(self):
        self._contexto = "entregas"
        return self

    def patch(self, **kwargs):
        self.patches.append(kwargs)
        return _Requisicao({"id": kwargs.get("id")})


def _aluno(uid, nome):
    return {"userId": uid, "profile": {"name": {"fullName": nome}}}


@pytest.fixture
def servico(monkeypatch):
    falso = _ServicoFalso(
        turmas=[{"id": "t1", "name": "3A Matemática"}],
        atividades=[{"id": "a1", "title": "Prova 1", "maxPoints": 10}],
        alunos=[_aluno("u1", "Ana Souza"), _aluno("u2", "Bruno Lima")],
        entregas=[
            {"id": "e1", "userId": "u1", "state": "TURNED_IN",
             "associatedWithDeveloper": True},
            {"id": "e2", "userId": "u2", "state": "CREATED",
             "associatedWithDeveloper": True},
        ],
    )
    # Agora o módulo trabalha com várias contas: servicos() devolve
    # uma lista de (email, servico, credenciais).
    monkeypatch.setattr(
        sala,
        "servicos",
        lambda: [("professor@escola.com", falso, "credenciais-falsas")],
    )
    sala._nota_pendente["dados"] = None
    sala._nota_pendente["momento"] = 0.0
    return falso


# ============================================================
# A trava principal: nota não sai sem confirmação
# ============================================================

def test_preparar_nao_lanca_nada(servico):
    sala.preparar_nota("3A", "Prova 1", "Ana", "8")

    assert servico.patches == []
    assert sala.nota_pendente() is not None


def test_lancamento_so_acontece_apos_confirmacao(servico):
    sala.preparar_nota("3A", "Prova 1", "Ana", "8")
    assert servico.patches == []

    lancados = []
    resultado = sala.confirmar_nota(lancar=lambda dados: lancados.append(dados))

    assert len(lancados) == 1
    assert lancados[0]["nome_aluno"] == "Ana Souza"
    assert lancados[0]["nota"] == 8.0
    assert "lançada" in resultado


def test_confirmar_sem_preparo_nao_lanca(servico):
    lancados = []
    resultado = sala.confirmar_nota(lancar=lambda dados: lancados.append(dados))

    assert lancados == []
    assert "Não há nenhuma nota pronta" in resultado


def test_preparo_expira(servico, monkeypatch):
    sala.preparar_nota("3A", "Prova 1", "Ana", "8")

    relogio = sala.time.monotonic() + sala.VALIDADE_NOTA_PENDENTE + 1
    monkeypatch.setattr(sala.time, "monotonic", lambda: relogio)

    lancados = []
    resultado = sala.confirmar_nota(lancar=lambda dados: lancados.append(dados))

    assert lancados == []
    assert "expirou" in resultado


def test_cancelar_descarta(servico):
    sala.preparar_nota("3A", "Prova 1", "Ana", "8")

    assert "Descartei" in sala.cancelar_nota()
    assert sala.nota_pendente() is None


def test_nao_lanca_a_mesma_nota_duas_vezes(servico):
    sala.preparar_nota("3A", "Prova 1", "Ana", "8")

    lancados = []
    sala.confirmar_nota(lancar=lambda dados: lancados.append(dados))
    sala.confirmar_nota(lancar=lambda dados: lancados.append(dados))

    assert len(lancados) == 1


def test_falha_ao_lancar_preserva_o_preparo(servico):
    sala.preparar_nota("3A", "Prova 1", "Ana", "8")

    resultado = sala.confirmar_nota(lancar=lambda dados: "servidor fora do ar")

    assert "NÃO foi lançada" in resultado
    assert sala.nota_pendente() is not None


# ============================================================
# Validação da nota
# ============================================================

def test_leitura_em_voz_alta_traz_aluno_atividade_e_valor(servico):
    retorno = sala.preparar_nota("3A", "Prova 1", "Ana", "8")

    assert "Ana Souza" in retorno
    assert "Prova 1" in retorno
    assert "8" in retorno
    assert "NÃO lançada" in retorno


def test_nota_acima_do_maximo_e_recusada(servico):
    retorno = sala.preparar_nota("3A", "Prova 1", "Ana", "50")

    assert "passa do valor máximo" in retorno
    assert sala.nota_pendente() is None


def test_nota_negativa_e_recusada(servico):
    assert "não pode ser negativa" in sala.preparar_nota("3A", "Prova 1", "Ana", "-1")


def test_nota_nao_numerica_e_recusada(servico):
    assert "não é uma nota válida" in sala.preparar_nota("3A", "Prova 1", "Ana", "oito")


def test_aceita_virgula_como_separador(servico):
    sala.preparar_nota("3A", "Prova 1", "Ana", "7,5")

    assert sala.nota_pendente()["nota"] == 7.5


def test_avisa_quando_vai_substituir_nota_existente(servico):
    servico._entregas = [
        {"id": "e1", "userId": "u1", "state": "RETURNED", "assignedGrade": 6,
         "associatedWithDeveloper": True}
    ]

    retorno = sala.preparar_nota("3A", "Prova 1", "Ana", "8")

    assert "ATENÇÃO" in retorno
    assert "já tem a nota 6" in retorno


# ============================================================
# Identificação de turma, atividade e aluno
# ============================================================

def test_turma_inexistente_lista_as_disponiveis(servico):
    retorno = sala.preparar_nota("9Z", "Prova 1", "Ana", "8")

    assert "Não encontrei a turma" in retorno
    assert "3A Matemática" in retorno


def test_aluno_inexistente_e_avisado(servico):
    retorno = sala.preparar_nota("3A", "Prova 1", "Carlos", "8")

    assert "Não encontrei nenhum aluno" in retorno
    assert sala.nota_pendente() is None


def test_alunos_com_nome_parecido_pedem_escolha(servico):
    servico._alunos = [_aluno("u1", "Ana Souza"), _aluno("u3", "Ana Paula")]

    retorno = sala.preparar_nota("3A", "Prova 1", "Ana", "8")

    assert "mais de um aluno" in retorno
    assert sala.nota_pendente() is None


def test_busca_ignora_acento_e_caixa(servico):
    retorno = sala.preparar_nota("3a matematica", "prova 1", "ANA SOUZA", "8")

    assert retorno.startswith("Nota preparada")


# ============================================================
# Consultas
# ============================================================

def test_listar_entregas_separa_situacoes(servico):
    retorno = sala.listar_entregas("3A", "Prova 1")

    assert "Ana Souza" in retorno
    assert "Bruno Lima" in retorno
    assert "Não entregaram" in retorno


def test_listar_turmas(servico):
    assert "3A Matemática" in sala.listar_turmas()


def test_listar_atividades_mostra_pontuacao(servico):
    retorno = sala.listar_atividades("3A")

    assert "Prova 1" in retorno
    assert "10 pontos" in retorno


def test_ler_entrega_de_quem_nao_entregou(servico):
    servico._entregas = [{"id": "e2", "userId": "u2", "state": "CREATED",
             "associatedWithDeveloper": True}]

    retorno = sala.ler_entrega("3A", "Prova 1", "Bruno")

    assert "ainda não entregou" in retorno


def test_ler_entrega_mostra_resposta_do_aluno(servico):
    servico._entregas = [
        {
            "id": "e1",
            "userId": "u1",
            "state": "TURNED_IN",
            "associatedWithDeveloper": True,
            "associatedWithDeveloper": True,
            "shortAnswerSubmission": {"answer": "A resposta é 42."},
        }
    ]

    retorno = sala.ler_entrega("3A", "Prova 1", "Ana")

    assert "A resposta é 42." in retorno


def test_ler_entrega_abre_o_arquivo_do_drive(servico, monkeypatch):
    """
    O ALF passou a abrir o anexo em vez de mandar o professor abrir.
    Antes ele só sabia o nome do arquivo, o que deixava a correção
    pela metade.
    """
    servico._entregas = [
        {
            "id": "e1",
            "userId": "u1",
            "state": "TURNED_IN",
            "associatedWithDeveloper": True,
            "associatedWithDeveloper": True,
            "assignmentSubmission": {
                "attachments": [
                    {"driveFile": {"id": "d1", "title": "trabalho.pdf"}}
                ]
            },
        }
    ]

    lidos = []

    def ler_falso(id_arquivo, nome="", credenciais=None):
        # As credenciais são as da conta dona da turma: com mais de uma
        # conta autorizada, a outra não enxerga o arquivo deste aluno.
        lidos.append((id_arquivo, nome, credenciais))
        return "Conteúdo de trabalho.pdf:\n\nA resposta do aluno."

    monkeypatch.setattr(
        "actions.drive_actions.ler_arquivo_do_drive", ler_falso
    )

    retorno = sala.ler_entrega("3A", "Prova 1", "Ana")

    assert lidos == [("d1", "trabalho.pdf", "credenciais-falsas")]
    assert "A resposta do aluno." in retorno
    assert "Resuma o que o aluno entregou" in retorno


def test_ler_entrega_avisa_sobre_anexo_que_nao_da_para_abrir(servico):
    """Vídeo e formulário não têm como ser lidos; o aviso precisa ser claro."""
    servico._entregas = [
        {
            "id": "e1",
            "userId": "u1",
            "state": "TURNED_IN",
            "associatedWithDeveloper": True,
            "associatedWithDeveloper": True,
            "assignmentSubmission": {
                "attachments": [
                    {"youTubeVideo": {"title": "Minha apresentação"}}
                ]
            },
        }
    ]

    retorno = sala.ler_entrega("3A", "Prova 1", "Ana")

    assert "Minha apresentação" in retorno
    assert "precisa abrir" in retorno


# ============================================================
# Configuração ausente
# ============================================================

def test_sem_conta_autorizada_explica_o_que_falta(monkeypatch):
    monkeypatch.setattr(sala, "servicos", lambda: [])

    for consulta in (
        sala.listar_turmas(),
        sala.listar_atividades("3A"),
        sala.listar_entregas("3A", "Prova 1"),
        sala.ler_entrega("3A", "Prova 1", "Ana"),
        sala.preparar_nota("3A", "Prova 1", "Ana", "8"),
    ):
        assert "Nenhuma conta do Google está autorizada" in consulta


def test_sem_credenciais_o_pedido_de_autorizacao_explica(monkeypatch, tmp_path):
    from actions import classroom_contas

    monkeypatch.setattr(
        classroom_contas, "ARQUIVO_CREDENCIAIS", tmp_path / "nao-existe.json"
    )

    assert "classroom_credenciais.json" in classroom_contas.autorizar_conta()


# ============================================================
# Token OAuth é segredo
# ============================================================

def test_token_do_classroom_nao_pode_ser_lido_nem_anexado():
    """
    O token dá acesso contínuo à conta Google do usuário. Vale o mesmo
    cuidado do .env, que o ALF já recusa.
    """
    from actions.codigo_actions import parece_secreto

    assert parece_secreto("classroom_token.json")
    assert parece_secreto("classroom_credenciais.json")


# ============================================================
# Registro no modelo
# ============================================================

@pytest.mark.parametrize(
    "ferramenta",
    [
        "listar_turmas",
        "listar_atividades",
        "listar_entregas",
        "ler_entrega",
        "preparar_nota",
        "confirmar_nota",
        "cancelar_nota",
    ],
)
def test_ferramenta_registrada(ferramenta):
    assert f'name="{ferramenta}"' in CODIGO_CLIENTE


def test_instrucao_exige_dois_turnos_e_proibe_inventar_nota():
    assert "Nunca chame confirmar_nota no mesmo turno" in CODIGO_CLIENTE
    assert "Nunca invente nota" in CODIGO_CLIENTE
    assert "deixe" in CODIGO_CLIENTE and "decisão com o professor" in CODIGO_CLIENTE


# ============================================================
# Prazo da atividade
# ============================================================
#
# A API do Classroom trata data e hora como UTC. A primeira versão
# convertia só a hora: 23:59 do dia 25 virava 02:59 do MESMO dia 25,
# ou seja, o prazo caía 24 horas antes e o aluno entregaria atrasado
# sem ter culpa. A conversão precisa mexer na data junto.

def test_prazo_noturno_avanca_o_dia_em_utc():
    corpo, erro = sala._montar_prazo("25/12/2026 23:59")

    assert erro is None
    # A data local vai junto, para a confirmação falada dizer 25/12 e
    # não 26/12, que é a data em UTC.
    assert corpo["_local"].day == 25
    assert corpo["_local"].hour == 23
    # 23:59 em Brasília é 02:59 do dia seguinte em UTC.
    assert corpo["dueDate"]["day"] == 26
    assert corpo["dueTime"]["hours"] == 2
    assert corpo["dueTime"]["minutes"] == 59


def test_prazo_matinal_fica_no_mesmo_dia():
    corpo, _ = sala._montar_prazo("25/12/2026 08:00")

    assert corpo["dueDate"]["day"] == 25
    assert corpo["dueTime"]["hours"] == 11


def test_prazo_na_virada_do_ano():
    corpo, _ = sala._montar_prazo("31/12/2026 22:00")

    assert corpo["dueDate"] == {"year": 2027, "month": 1, "day": 1}


def test_prazo_sem_hora_assume_fim_do_dia():
    corpo, _ = sala._montar_prazo("25/12/2026")

    assert corpo["dueDate"]["day"] == 26
    assert corpo["dueTime"]["hours"] == 2


def test_prazo_vazio_nao_define_nada():
    corpo, erro = sala._montar_prazo("")

    assert corpo == {}
    assert erro is None


@pytest.mark.parametrize("ruim", ["amanha", "32/13/2026", "25-12", "abc"])
def test_data_invalida_e_recusada(ruim):
    corpo, erro = sala._montar_prazo(ruim)

    assert corpo is None
    assert erro


# ============================================================
# Criar atividade
# ============================================================

def test_atividade_nasce_sempre_como_rascunho(servico, monkeypatch):
    """
    Publicar avisa a turma na hora. Um erro de transcrição no enunciado
    ou na data já teria chegado a todos os alunos.
    """
    criados = []

    def create_falso(courseId=None, body=None):
        criados.append(body)

        class R:
            def execute(self):
                return {"id": "novo"}

        return R()

    monkeypatch.setattr(servico, "create", create_falso, raising=False)

    resultado = sala.criar_atividade("3A", "Trabalho", "Enunciado.", "10")

    assert criados[0]["state"] == "DRAFT"
    assert criados[0]["maxPoints"] == 10.0
    assert "RASCUNHO" in resultado
    assert "ainda não veem" in resultado


def test_atividade_sem_titulo_e_recusada(servico):
    assert "título" in sala.criar_atividade("3A", "  ")


def test_pontuacao_invalida_e_recusada(servico):
    assert "não é uma pontuação válida" in sala.criar_atividade(
        "3A", "Trabalho", "", "muitos"
    )


def test_link_do_questionario_vira_anexo(servico, monkeypatch):
    criados = []

    def create_falso(courseId=None, body=None):
        criados.append(body)

        class R:
            def execute(self):
                return {"id": "novo"}

        return R()

    monkeypatch.setattr(servico, "create", create_falso, raising=False)

    sala.criar_atividade(
        "3A", "Quiz", link="https://forms.gle/abc"
    )

    assert criados[0]["materials"] == [
        {"link": {"url": "https://forms.gle/abc"}}
    ]


# ============================================================
# Devolver corrigido
# ============================================================

def test_nao_devolve_sem_nota_lancada(servico):
    """Devolver sem nota não faz sentido e confunde o aluno."""
    servico._entregas = [{"id": "e1", "userId": "u1", "state": "TURNED_IN",
             "associatedWithDeveloper": True}]

    resultado = sala.devolver_atividade("3A", "Prova 1", "Ana")

    assert "ainda não tem nota" in resultado


# ============================================================
# Atividade que nao pertence a este projeto
# ============================================================
#
# Caso real: o lancamento de nota falhava com
# "403 @ProjectPermissionDenied". O Google Classroom so deixa um
# projeto externo lancar nota em atividades criadas por ele mesmo; as
# que o professor criou pela interface sao somente leitura. Das 21
# entregas reais examinadas, zero pertenciam a este projeto.

def test_nao_prepara_nota_de_atividade_criada_fora(servico):
    servico._entregas = [
        {
            "id": "e1",
            "userId": "u1",
            "state": "TURNED_IN",
            "associatedWithDeveloper": False,
        }
    ]

    resultado = sala.preparar_nota("3A", "Prova 1", "Ana", "8")

    assert "só permite que eu lance nota em atividades criadas por mim" in resultado
    assert sala.nota_pendente() is None


def test_recusa_explica_que_nao_e_permissao(servico):
    """
    Sem isto o modelo tenta reautorizar a conta, abrindo o navegador no
    meio da correcao -- foi o que aconteceu de verdade.
    """
    servico._entregas = [
        {
            "id": "e1",
            "userId": "u1",
            "state": "TURNED_IN",
            "associatedWithDeveloper": False,
        }
    ]

    resultado = sala.preparar_nota("3A", "Prova 1", "Ana", "8")

    assert "Não é permissão faltando" in resultado
    assert "lança essa nota à mão" in resultado


def test_nao_devolve_atividade_criada_fora(servico):
    servico._entregas = [
        {
            "id": "e1",
            "userId": "u1",
            "state": "TURNED_IN",
            "assignedGrade": 8,
            "associatedWithDeveloper": False,
        }
    ]

    resultado = sala.devolver_atividade("3A", "Prova 1", "Ana")

    assert "criadas por mim" in resultado


def test_erro_da_api_tambem_e_traduzido():
    """Se escapar da checagem previa, a mensagem ainda tem que ser clara."""
    from actions.classroom_actions import _executar

    class RequisicaoFalsa:
        def execute(self):
            raise Exception(
                '403 "@ProjectPermissionDenied The Developer Console '
                'project is not permitted to make this request."'
            )

    _, erro = _executar(RequisicaoFalsa())

    assert "criadas por mim" in erro
    assert "regra da plataforma" in erro or "Não é permissão faltando" in erro


def test_instrucao_proibe_reautorizar_por_causa_disso():
    # O texto da instrução é quebrado em várias linhas no código, então
    # a busca é por trechos que cabem numa linha só.
    assert "reautorizar conta por causa disso" in CODIGO_CLIENTE
    assert "somente leitura para você" in CODIGO_CLIENTE


def test_campo_auxiliar_nao_vai_para_a_api(servico, monkeypatch):
    """A API recusaria um campo desconhecido no corpo."""
    criados = []

    def create_falso(courseId=None, body=None):
        criados.append(body)

        class R:
            def execute(self):
                return {"id": "novo"}

        return R()

    monkeypatch.setattr(servico, "create", create_falso, raising=False)

    sala.criar_atividade("3A", "Trabalho", prazo="25/12/2026 23:59")

    assert "_local" not in criados[0]
    assert criados[0]["dueDate"]["day"] == 26


def test_confirmacao_diz_a_data_que_o_professor_pediu(servico, monkeypatch):
    """
    O professor pedia 25/12 as 23:59 e ouvia "prazo 26/12", que e a
    data em UTC -- como se ele tivesse errado.
    """

    def create_falso(courseId=None, body=None):
        class R:
            def execute(self):
                return {"id": "novo"}

        return R()

    monkeypatch.setattr(servico, "create", create_falso, raising=False)

    resultado = sala.criar_atividade(
        "3A", "Trabalho", prazo="25/12/2026 23:59"
    )

    assert "25/12 às 23:59" in resultado
    assert "26/12" not in resultado
