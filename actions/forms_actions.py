"""
Google Forms: criar questionário com correção automática.

É a peça que muda a rotina de correção: em vez de corrigir 30 provas
de múltipla escolha à mão, o formulário já vem com gabarito e o próprio
Google corrige. O professor dita as questões por voz, confere e anexa
à atividade do Classroom.

O formulário é criado no Drive da conta autorizada. O escopo usado é o
drive.file, que dá acesso apenas aos arquivos criados por este app --
não ao restante do Drive do professor.
"""

import unicodedata

from actions.classroom_contas import servicos


# Limites de sanidade, para um erro de transcrição não gerar um
# formulário gigante por engano.
MAXIMO_QUESTOES = 30
MAXIMO_OPCOES = 8


def _normalizar(texto):
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.split())


def _servico_forms(email=None):
    """Devolve (servico, email_usado, erro)."""

    contas = servicos()
    if not contas:
        return None, None, (
            "Nenhuma conta do Google está autorizada ainda."
        )

    escolhida = None
    if email:
        procurado = _normalizar(email)
        for atual, _, credenciais in contas:
            if procurado in _normalizar(atual):
                escolhida = (atual, credenciais)
                break
        if escolhida is None:
            return None, None, (
                f"Não tenho a conta {email} autorizada. "
                "As contas disponíveis são: "
                + ", ".join(c[0] for c in contas)
                + "."
            )
    else:
        escolhida = (contas[0][0], contas[0][2])

    try:
        from googleapiclient.discovery import build

        servico = build(
            "forms", "v1", credentials=escolhida[1], cache_discovery=False
        )
        return servico, escolhida[0], None
    except Exception as erro:
        return None, None, f"Não consegui acessar o Google Forms: {erro}"


def _validar_questoes(questoes):
    """Devolve (lista_limpa, erro)."""

    if not isinstance(questoes, (list, tuple)) or not questoes:
        return None, (
            "Nenhuma questão foi informada. Diga as perguntas, as "
            "alternativas e qual é a correta."
        )

    if len(questoes) > MAXIMO_QUESTOES:
        return None, (
            f"São {len(questoes)} questões, acima do limite de "
            f"{MAXIMO_QUESTOES}. Divida em mais de um questionário."
        )

    limpas = []

    for numero, bruta in enumerate(questoes, start=1):
        if not isinstance(bruta, dict):
            return None, f"A questão {numero} veio em formato inválido."

        pergunta = " ".join(str(bruta.get("pergunta", "")).split()).strip()
        if not pergunta:
            return None, f"A questão {numero} está sem enunciado."

        opcoes = bruta.get("opcoes") or []
        opcoes = [
            " ".join(str(o).split()).strip()
            for o in opcoes
            if str(o).strip()
        ]

        if len(opcoes) < 2:
            return None, (
                f"A questão {numero} precisa de pelo menos duas "
                "alternativas."
            )

        if len(opcoes) > MAXIMO_OPCOES:
            return None, (
                f"A questão {numero} tem alternativas demais "
                f"(máximo {MAXIMO_OPCOES})."
            )

        correta = " ".join(str(bruta.get("resposta_correta", "")).split()).strip()
        if not correta:
            return None, f"A questão {numero} está sem a resposta correta."

        # A resposta correta precisa ser uma das alternativas, senão o
        # Google recusa o gabarito e o formulário sai sem correção.
        casada = None
        for opcao in opcoes:
            if _normalizar(opcao) == _normalizar(correta):
                casada = opcao
                break

        if casada is None:
            return None, (
                f"Na questão {numero}, a resposta '{correta}' não é "
                f"nenhuma das alternativas ({', '.join(opcoes)}). "
                "Confirme com o usuário qual é a correta."
            )

        try:
            pontos = float(str(bruta.get("pontos", 1)).replace(",", "."))
        except (TypeError, ValueError):
            pontos = 1.0

        limpas.append(
            {
                "pergunta": pergunta,
                "opcoes": opcoes,
                "correta": casada,
                "pontos": max(0.0, pontos),
            }
        )

    return limpas, None


def _pedidos_de_criacao(questoes, descricao):
    """Monta as requisições do batchUpdate, na ordem que a API exige."""

    pedidos = []

    # Virar quiz precisa vir ANTES das questões: sem isso a API recusa
    # o gabarito, e o formulário sairia sem correção automática.
    pedidos.append(
        {
            "updateSettings": {
                "settings": {"quizSettings": {"isQuiz": True}},
                "updateMask": "quizSettings.isQuiz",
            }
        }
    )

    if descricao:
        pedidos.append(
            {
                "updateFormInfo": {
                    "info": {"description": descricao},
                    "updateMask": "description",
                }
            }
        )

    for indice, questao in enumerate(questoes):
        pedidos.append(
            {
                "createItem": {
                    "item": {
                        "title": questao["pergunta"],
                        "questionItem": {
                            "question": {
                                "required": True,
                                "grading": {
                                    "pointValue": int(questao["pontos"]),
                                    "correctAnswers": {
                                        "answers": [
                                            {"value": questao["correta"]}
                                        ]
                                    },
                                },
                                "choiceQuestion": {
                                    "type": "RADIO",
                                    "options": [
                                        {"value": o} for o in questao["opcoes"]
                                    ],
                                    "shuffle": False,
                                },
                            }
                        },
                    },
                    "location": {"index": indice},
                }
            }
        )

    return pedidos


def criar_questionario(titulo, questoes, descricao="", conta=""):
    """
    Cria um questionário com gabarito e devolve o link.

    O formulário nasce sem respostas e não vai para ninguém: o professor
    revisa e decide se anexa a uma atividade.
    """

    titulo = " ".join(str(titulo or "").split()).strip()
    if not titulo:
        return "Qual deve ser o título do questionário?"

    limpas, erro = _validar_questoes(questoes)
    if erro:
        return erro

    servico, email, erro = _servico_forms(conta)
    if erro:
        return erro

    try:
        formulario = servico.forms().create(
            body={"info": {"title": titulo, "documentTitle": titulo}}
        ).execute()
    except Exception as erro:
        texto = str(erro)
        if "403" in texto:
            return (
                "O Google recusou a criação. Confira se a API do Google "
                "Forms está ativada no projeto do console."
            )
        return f"Não consegui criar o questionário: {erro}"

    id_formulario = formulario.get("formId", "")

    try:
        servico.forms().batchUpdate(
            formId=id_formulario,
            body={
                "requests": _pedidos_de_criacao(
                    limpas, str(descricao or "").strip()
                )
            },
        ).execute()
    except Exception as erro:
        return (
            f"Criei o formulário, mas falhei ao montar as questões: {erro}. "
            f"Ele está no Drive da conta {email}, vazio; o usuário pode "
            "apagar."
        )

    link = formulario.get("responderUri") or (
        f"https://docs.google.com/forms/d/{id_formulario}/viewform"
    )

    total = sum(q["pontos"] for q in limpas)

    return (
        f"Criei o questionário '{titulo}' com {len(limpas)} questões, "
        f"valendo {total:g} pontos no total, na conta {email}. "
        "Ele já está configurado como quiz com gabarito, então o Google "
        "corrige sozinho. Ninguém recebeu ainda. "
        f"Link: {link} "
        "Diga ao usuário quantas questões foram criadas e pergunte se ele "
        "quer anexar isso a uma atividade do Classroom."
    )


def listar_respostas(id_ou_link, conta=""):
    """Mostra quantas pessoas responderam um questionário."""

    texto = str(id_ou_link or "").strip()
    if not texto:
        return "Diga qual questionário devo consultar."

    # Aceita o link inteiro ou só o identificador.
    id_formulario = texto
    if "/forms/d/" in texto:
        id_formulario = texto.split("/forms/d/")[1].split("/")[0]

    servico, email, erro = _servico_forms(conta)
    if erro:
        return erro

    try:
        formulario = servico.forms().get(formId=id_formulario).execute()
        respostas = servico.forms().responses().list(
            formId=id_formulario
        ).execute()
    except Exception as erro:
        if "404" in str(erro):
            return (
                "Não encontrei esse questionário. Ele pode ter sido criado "
                "por outra conta, ou por fora do ALF -- só enxergo os "
                "formulários que eu mesmo criei."
            )
        return f"Não consegui consultar o questionário: {erro}"

    titulo = formulario.get("info", {}).get("title", "sem título")
    lista = respostas.get("responses", [])

    if not lista:
        return f"O questionário '{titulo}' ainda não tem nenhuma resposta."

    notas = []
    for resposta in lista:
        total = resposta.get("totalScore")
        if total is not None:
            notas.append(total)

    partes = [f"O questionário '{titulo}' tem {len(lista)} respostas."]

    if notas:
        media = sum(notas) / len(notas)
        partes.append(
            f"A média das notas é {media:.1f}, "
            f"da menor {min(notas):g} até a maior {max(notas):g}."
        )

    partes.append("Resuma isso em voz alta, sem listar respostas uma a uma.")

    return " ".join(partes)
