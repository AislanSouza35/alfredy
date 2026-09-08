"""
Google Classroom: consultar turmas, entregas e lançar notas.

Por que API e não clique visual: corrigir 30 alunos pela tela significa
30 buscas de imagem, cada uma podendo errar de linha. Pela API a nota
vai para o ID do aluno, sem depender de acertar a posição na tela.

O lançamento de nota segue o mesmo desenho do e-mail -- dois passos com
confirmação obrigatória -- pelo mesmo motivo: nota lançada errada afeta
a vida de outra pessoa e não se desfaz sozinha.

Várias contas: o professor tem turmas no Gmail pessoal e na conta da
instituição, e o domínio da instituição bloqueia convidar professor de
fora. Então todas as consultas varrem todas as contas autorizadas, e
cada turma carrega de qual conta veio -- a nota é lançada pela
credencial daquela conta, porque a outra não tem permissão nela.

A autorização e os tokens ficam em classroom_contas.py.
"""

import time
import unicodedata
from datetime import datetime, timezone
from threading import Lock

from actions.classroom_contas import (
    ARQUIVO_CREDENCIAIS,
    ESCOPOS,
    autorizar_conta,
    contas_autorizadas,
    limpar_cache,
    remover_conta,
    servicos,
)


VALIDADE_NOTA_PENDENTE = 300.0

_LOCK = Lock()

# Nota aguardando confirmação. Nunca é lançada sozinha.
_nota_pendente = {"dados": None, "momento": 0.0}


def _normalizar(texto):
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.split())


def _compacto(texto):
    """
    Mesma normalização, sem nenhum espaço.

    Códigos de turma são escritos de todo jeito: "5TIN", "5 TIN",
    "5 TIN1". A transcrição de voz sempre separa, e não casava com a
    turma chamada "5TIN". Comparar também sem espaços resolve nos dois
    sentidos.
    """

    return _normalizar(texto).replace(" ", "")


def _casa(procurado, candidato):
    return (
        _normalizar(procurado) == _normalizar(candidato)
        or _compacto(procurado) == _compacto(candidato)
    )


def _contem(procurado, candidato):
    return (
        _normalizar(procurado) in _normalizar(candidato)
        or _compacto(procurado) in _compacto(candidato)
    )


# O Google Classroom só permite que um projeto externo lance nota em
# atividades criadas por ele mesmo. Atividade feita pelo professor na
# interface do Classroom é somente leitura para a API -- a tentativa
# volta como "@ProjectPermissionDenied".
#
# Não é permissão faltando nem escopo errado: é regra da plataforma, e
# não existe configuração que a contorne.
MENSAGEM_ATIVIDADE_DE_FORA = (
    "Não posso lançar nota nesta atividade. O Google Classroom só "
    "permite que eu lance nota em atividades criadas por mim; as que "
    "você criou pela interface do Classroom são somente leitura para "
    "mim, por regra da plataforma. Não é permissão faltando e não há "
    "configuração que resolva. "
    "Explique isso ao usuário e ofereça duas saídas: ele lança essa "
    "nota à mão no Classroom, ou passa a criar as atividades por mim "
    "com criar_atividade, e aí eu consigo corrigir. "
    "Continuo lendo tudo normalmente: entregas, quem falta e o "
    "conteúdo enviado."
)


def _sem_contas():
    return (
        "Nenhuma conta do Google está autorizada ainda. "
        "Peça para autorizar o Classroom antes de usar."
    )


def _executar(requisicao):
    """Chama a API traduzindo a falha para uma frase compreensível."""

    try:
        return requisicao.execute(), None
    except Exception as erro:
        texto = str(erro)

        # Vem ANTES da checagem genérica de 403: este caso também chega
        # como 403, e cair na mensagem genérica mandaria o usuário
        # conferir permissões que estão corretas.
        if "ProjectPermissionDenied" in texto:
            return None, MENSAGEM_ATIVIDADE_DE_FORA

        if "403" in texto:
            return None, (
                "O Google recusou o acesso. Confira se a API do Classroom "
                "está ativada e se sua conta é professora dessa turma."
            )
        if "404" in texto:
            return None, "Não encontrei esse item no Classroom."
        return None, f"O Classroom devolveu um erro: {erro}"


# ============================================================
# CONTAS
# ============================================================

def listar_contas():
    """
    Lista as contas autorizadas pelo endereço real.

    O nome do arquivo de token troca pontos e arroba por sublinhado,
    então usar o apelido do arquivo aqui mostrava o endereço mastigado
    ("aislan souza ba docente senai br"). servicos() traz o e-mail como
    o Google informa.
    """

    contas = servicos()

    if not contas:
        return _sem_contas()

    return (
        "Contas autorizadas: "
        + ", ".join(email for email, _, _ in contas)
        + "."
    )


# ============================================================
# TURMAS
# ============================================================

def _todas_as_turmas():
    """Devolve [(email, servico, credenciais, turma)] de todas as contas."""

    encontradas = []

    for email, servico, credenciais in servicos():
        resposta, erro = _executar(
            servico.courses().list(courseStates=["ACTIVE"], pageSize=100)
        )
        if erro:
            continue

        for turma in resposta.get("courses", []):
            encontradas.append((email, servico, credenciais, turma))

    return encontradas


def listar_turmas():
    if not servicos():
        return _sem_contas()

    turmas = _todas_as_turmas()

    if not turmas:
        return "Não encontrei nenhuma turma ativa nas contas autorizadas."

    por_conta = {}
    for email, _, _, turma in turmas:
        por_conta.setdefault(email, []).append(turma.get("name", "sem nome"))

    partes = [f"Você tem {len(turmas)} turmas ativas."]

    for email, nomes in por_conta.items():
        partes.append(f"\nNa conta {email} ({len(nomes)}):")
        partes.extend(f"- {nome}" for nome in nomes)

    partes.append(
        "\nDiga os números por conta em voz alta; só liste os nomes se o "
        "usuário pedir."
    )

    return "\n".join(partes)


def _encontrar_turma(nome):
    """
    Procura a turma em todas as contas.

    Devolve (contexto, erro), onde contexto é
    (email, servico, credenciais, turma).
    """

    turmas = _todas_as_turmas()

    if not turmas:
        return None, (
            "Não encontrei nenhuma turma ativa nas contas autorizadas."
        )

    exatas = [t for t in turmas if _casa(nome, t[3].get("name", ""))]
    parciais = [t for t in turmas if _contem(nome, t[3].get("name", ""))]

    candidatas = exatas or parciais

    if not candidatas:
        disponiveis = ", ".join(t[3].get("name", "") for t in turmas[:8])
        return None, (
            f"Não encontrei a turma {nome}. Algumas das suas turmas: "
            f"{disponiveis}."
        )

    if len(candidatas) > 1:
        nomes = ", ".join(
            f"{t[3].get('name', '')} (conta {t[0]})" for t in candidatas
        )
        return None, (
            f"Tenho mais de uma turma parecida com {nome}: {nomes}. "
            "Pergunte qual delas."
        )

    email, servico, credenciais, turma = candidatas[0]

    # O nome exato ganha do parcial, o que costuma estar certo. Mas com
    # duas contas isso pode descartar em silêncio uma turma parecida da
    # outra conta -- "banco de dados" casa exatamente com uma turma do
    # SENAI e parcialmente com "1 TIV - banco de dados" do Gmail.
    #
    # Ao lançar nota o professor ouve a conta na confirmação e pega o
    # engano. Numa consulta não há confirmação nenhuma, e ele receberia
    # os dados da turma errada sem perceber. Por isso o descarte vira
    # aviso em vez de silêncio.
    aviso = ""

    descartadas = [
        t for t in parciais
        if t[3].get("id") != turma.get("id") and t[0] != email
    ]

    if exatas and descartadas:
        outras = ", ".join(
            f"{t[3].get('name', '')} (conta {t[0]})" for t in descartadas
        )
        aviso = (
            f"\nAtenção: usei a turma {turma.get('name', '')} da conta "
            f"{email}, por ser o nome exato. Existe também: {outras}. "
            "Diga isso ao usuário e confirme que é a turma certa."
        )

    return (email, servico, credenciais, turma, aviso), None


# ============================================================
# ATIVIDADES
# ============================================================

def listar_atividades(turma):
    if not servicos():
        return _sem_contas()

    contexto, erro = _encontrar_turma(turma)
    if erro:
        return erro

    _, servico, _, dados_turma, aviso = contexto

    resposta, erro = _executar(
        servico.courses().courseWork().list(
            courseId=dados_turma["id"], pageSize=50
        )
    )
    if erro:
        return erro

    atividades = resposta.get("courseWork", [])
    if not atividades:
        return f"A turma {dados_turma['name']} não tem atividades criadas."

    linhas = []
    for atividade in atividades:
        pontos = atividade.get("maxPoints")
        valor = f", vale {pontos:g} pontos" if pontos else ""
        linhas.append(f"- {atividade.get('title', 'sem título')}{valor}")

    return (
        f"Atividades da turma {dados_turma['name']}:\n"
        + "\n".join(linhas)
        + aviso
    )


def _encontrar_atividade(servico, id_turma, nome):
    resposta, erro = _executar(
        servico.courses().courseWork().list(courseId=id_turma, pageSize=50)
    )
    if erro:
        return None, erro

    atividades = resposta.get("courseWork", [])

    exatas = [a for a in atividades if _casa(nome, a.get("title", ""))]
    parciais = [a for a in atividades if _contem(nome, a.get("title", ""))]

    candidatas = exatas or parciais

    if not candidatas:
        disponiveis = ", ".join(a.get("title", "") for a in atividades[:8])
        return None, (
            f"Não encontrei a atividade {nome}. Nessa turma existem: "
            f"{disponiveis}."
        )

    if len(candidatas) > 1:
        nomes = ", ".join(a.get("title", "") for a in candidatas)
        return None, (
            f"Tenho mais de uma atividade parecida com {nome}: {nomes}. "
            "Pergunte qual delas."
        )

    return candidatas[0], None


# ============================================================
# ALUNOS E ENTREGAS
# ============================================================

def _mapa_de_alunos(servico, id_turma):
    alunos = {}
    pagina = None

    while True:
        resposta, erro = _executar(
            servico.courses().students().list(
                courseId=id_turma, pageSize=100, pageToken=pagina
            )
        )
        if erro:
            return {}, erro

        for aluno in resposta.get("students", []):
            perfil = aluno.get("profile", {})
            alunos[aluno["userId"]] = perfil.get("name", {}).get(
                "fullName", "aluno sem nome"
            )

        pagina = resposta.get("nextPageToken")
        if not pagina:
            break

    return alunos, None


def listar_entregas(turma, atividade):
    """Quem entregou, quem não entregou e quem já tem nota."""

    if not servicos():
        return _sem_contas()

    contexto, erro = _encontrar_turma(turma)
    if erro:
        return erro

    _, servico, _, dados_turma, aviso = contexto

    dados_atividade, erro = _encontrar_atividade(
        servico, dados_turma["id"], atividade
    )
    if erro:
        return erro

    alunos, erro = _mapa_de_alunos(servico, dados_turma["id"])
    if erro:
        return erro

    resposta, erro = _executar(
        servico.courses().courseWork().studentSubmissions().list(
            courseId=dados_turma["id"],
            courseWorkId=dados_atividade["id"],
            pageSize=200,
        )
    )
    if erro:
        return erro

    entregas = resposta.get("studentSubmissions", [])
    if not entregas:
        return "Nenhum aluno recebeu essa atividade ainda."

    entregues = []
    pendentes = []
    corrigidos = []

    for entrega in entregas:
        nome = alunos.get(entrega.get("userId", ""), "aluno desconhecido")
        estado = entrega.get("state", "")
        nota = entrega.get("assignedGrade")

        if nota is not None:
            corrigidos.append(f"{nome} ({nota:g})")
        elif estado in ("TURNED_IN", "RETURNED"):
            entregues.append(nome)
        else:
            pendentes.append(nome)

    partes = [
        f"Atividade {dados_atividade['title']}, turma {dados_turma['name']}."
    ]

    if entregues:
        partes.append(
            f"Entregaram e ainda não têm nota ({len(entregues)}): "
            + ", ".join(entregues)
        )
    if corrigidos:
        partes.append(
            f"Já corrigidos ({len(corrigidos)}): " + ", ".join(corrigidos)
        )
    if pendentes:
        partes.append(
            f"Não entregaram ({len(pendentes)}): " + ", ".join(pendentes)
        )

    partes.append(
        "Resuma isso em voz alta com os números; só liste os nomes se o "
        "usuário pedir."
    )

    if aviso:
        partes.append(aviso.strip())

    return "\n".join(partes)


def _encontrar_entrega(servico, dados_turma, dados_atividade, aluno):
    """Devolve (entrega, nome_do_aluno, erro)."""

    alunos, erro = _mapa_de_alunos(servico, dados_turma["id"])
    if erro:
        return None, None, erro

    exatos = [
        (uid, nome) for uid, nome in alunos.items() if _casa(aluno, nome)
    ]
    parciais = [
        (uid, nome) for uid, nome in alunos.items() if _contem(aluno, nome)
    ]

    candidatos = exatos or parciais

    if not candidatos:
        return None, None, (
            f"Não encontrei nenhum aluno chamado {aluno} nessa turma."
        )

    if len(candidatos) > 1:
        nomes = ", ".join(nome for _, nome in candidatos)
        return None, None, (
            f"Tenho mais de um aluno com esse nome: {nomes}. "
            "Pergunte o nome completo."
        )

    id_aluno, nome_aluno = candidatos[0]

    resposta, erro = _executar(
        servico.courses().courseWork().studentSubmissions().list(
            courseId=dados_turma["id"],
            courseWorkId=dados_atividade["id"],
            userId=id_aluno,
        )
    )
    if erro:
        return None, None, erro

    entregas = resposta.get("studentSubmissions", [])
    if not entregas:
        return None, None, f"{nome_aluno} não tem registro nessa atividade."

    return entregas[0], nome_aluno, None


def ler_entrega(turma, atividade, aluno):
    """Mostra o que o aluno entregou, incluindo o conteúdo dos anexos."""

    if not servicos():
        return _sem_contas()

    contexto, erro = _encontrar_turma(turma)
    if erro:
        return erro

    _, servico, credenciais, dados_turma, aviso = contexto

    dados_atividade, erro = _encontrar_atividade(
        servico, dados_turma["id"], atividade
    )
    if erro:
        return erro

    entrega, nome_aluno, erro = _encontrar_entrega(
        servico, dados_turma, dados_atividade, aluno
    )
    if erro:
        return erro

    partes = [f"Entrega de {nome_aluno} em {dados_atividade['title']}."]

    estado = entrega.get("state", "")
    if estado not in ("TURNED_IN", "RETURNED"):
        partes.append("Este aluno ainda não entregou a atividade.")
        return "\n".join(partes)

    if entrega.get("late"):
        partes.append("Entregue com atraso.")

    nota = entrega.get("assignedGrade")
    if nota is not None:
        partes.append(f"Já tem nota lançada: {nota:g}.")

    resposta_curta = entrega.get("shortAnswerSubmission", {}).get("answer")
    if resposta_curta:
        partes.append(f"Resposta: {resposta_curta}")

    escolha = entrega.get("multipleChoiceSubmission", {}).get("answer")
    if escolha:
        partes.append(f"Alternativa marcada: {escolha}")

    anexos = entrega.get("assignmentSubmission", {}).get("attachments", [])
    if anexos:
        from actions.drive_actions import ler_arquivo_do_drive

        for anexo in anexos:
            if "driveFile" in anexo:
                arquivo = anexo["driveFile"]
                # As credenciais são as da conta dona da turma: a outra
                # conta não tem acesso ao arquivo deste aluno.
                partes.append(
                    ler_arquivo_do_drive(
                        arquivo.get("id", ""),
                        arquivo.get("title", "arquivo"),
                        credenciais=credenciais,
                    )
                )

            elif "link" in anexo:
                partes.append("Link entregue: " + anexo["link"].get("url", ""))

            elif "youTubeVideo" in anexo:
                partes.append(
                    "Vídeo do YouTube entregue: "
                    + anexo["youTubeVideo"].get("title", "sem título")
                    + ". Não consigo assistir; o usuário precisa abrir."
                )

            elif "form" in anexo:
                partes.append(
                    "Formulário entregue: "
                    + anexo["form"].get("title", "sem título")
                    + ". Não consigo abrir formulários."
                )

        partes.append(
            "Resuma o que o aluno entregou em vez de ler tudo em voz alta. "
            "Aponte o que está certo e o que falta, e sugira uma nota, "
            "mas deixe a decisão com o professor."
        )

    if len(partes) == 1:
        partes.append("A entrega não tem conteúdo de texto que eu consiga ler.")

    if aviso:
        partes.append(aviso.strip())

    return "\n".join(partes)


# ============================================================
# CRIAR ATIVIDADE
# ============================================================
#
# A atividade é sempre criada como RASCUNHO. Publicar avisa a turma
# inteira na hora, e um erro de transcrição de voz no enunciado ou na
# data já teria chegado a todos os alunos. Como rascunho, o professor
# revisa no Classroom e publica quando quiser.
ESTADO_RASCUNHO = "DRAFT"


def _montar_prazo(prazo):
    """
    Converte "25/12/2026" ou "25/12/2026 23:59" no formato da API.

    Devolve (corpo_parcial, erro).
    """

    texto = str(prazo or "").strip()
    if not texto:
        return {}, None

    partes = texto.split()
    data = partes[0].replace("-", "/")

    try:
        dia, mes, ano = (int(p) for p in data.split("/"))
    except (ValueError, TypeError):
        return None, (
            f"Não entendi a data '{prazo}'. Diga no formato dia, mês e ano."
        )

    if ano < 100:
        ano += 2000

    hora, minuto = 23, 59
    if len(partes) > 1:
        try:
            hora_texto = partes[1].replace("h", ":").strip(":")
            pedacos = hora_texto.split(":")
            hora = int(pedacos[0])
            minuto = int(pedacos[1]) if len(pedacos) > 1 and pedacos[1] else 0
        except (ValueError, IndexError):
            return None, f"Não entendi o horário '{partes[1]}'."

    if not (1 <= mes <= 12 and 1 <= dia <= 31 and 0 <= hora <= 23):
        return None, f"A data '{prazo}' não existe. Confira com o usuário."

    # A API trata data e hora como UTC. Converter só a hora estava
    # errado: 23:59 do dia 25 virava 02:59 do MESMO dia 25, ou seja,
    # o prazo caía 24 horas antes e o aluno entregaria atrasado sem
    # ter culpa. A conversão precisa mexer na data junto.
    try:
        local = datetime(ano, mes, dia, hora, minuto)
    except ValueError:
        return None, f"A data '{prazo}' não existe. Confira com o usuário."

    # astimezone() sem argumento assume o fuso do computador, que é o
    # mesmo do professor e dos alunos.
    em_utc = local.astimezone().astimezone(timezone.utc)

    return {
        "dueDate": {
            "year": em_utc.year,
            "month": em_utc.month,
            "day": em_utc.day,
        },
        "dueTime": {"hours": em_utc.hour, "minutes": em_utc.minute},
        # Guardado só para a confirmação falada, e removido antes de ir
        # para a API. Sem isto o ALF repetia a data em UTC: o professor
        # pedia 25/12 às 23:59 e ouvia "prazo 26/12", como se ele
        # tivesse errado a data.
        "_local": local,
    }, None


# Como o aluno recebe o arquivo anexado.
MODOS_DE_ARQUIVO = {
    "ver": "VIEW",
    "visualizar": "VIEW",
    "leitura": "VIEW",
    "copia": "STUDENT_COPY",
    "cópia": "STUDENT_COPY",
    "preencher": "STUDENT_COPY",
    "responder": "STUDENT_COPY",
    "editar": "EDIT",
    "colaborar": "EDIT",
}


def criar_atividade(
    turma,
    titulo,
    descricao="",
    pontos=None,
    prazo="",
    link="",
    arquivo="",
    modo_arquivo="ver",
):
    """
    Cria uma atividade na turma, sempre como rascunho.

    Nunca publica: quem decide o que chega ao aluno é o professor.
    """

    if not servicos():
        return _sem_contas()

    titulo = " ".join(str(titulo or "").split()).strip()
    if not titulo:
        return "Qual deve ser o título da atividade?"

    contexto, erro = _encontrar_turma(turma)
    if erro:
        return erro

    email, servico, credenciais, dados_turma, aviso = contexto

    corpo = {
        "title": titulo,
        "workType": "ASSIGNMENT",
        "state": ESTADO_RASCUNHO,
    }

    descricao = str(descricao or "").strip()
    if descricao:
        corpo["description"] = descricao

    if pontos not in (None, ""):
        try:
            corpo["maxPoints"] = float(str(pontos).replace(",", "."))
        except (TypeError, ValueError):
            return f"'{pontos}' não é uma pontuação válida."

    prazo_corpo, erro = _montar_prazo(prazo)
    if erro:
        return erro

    # O campo auxiliar existe só para a confirmação falada; a API
    # recusaria um campo desconhecido no corpo.
    prazo_local = prazo_corpo.pop("_local", None)
    corpo.update(prazo_corpo)

    materiais = []

    link = str(link or "").strip()
    if link:
        materiais.append({"link": {"url": link}})

    arquivo = str(arquivo or "").strip()
    nome_anexo = ""

    if arquivo:
        from actions.drive_actions import (
            enviar_arquivo_para_drive,
            liberar_para_a_turma,
        )
        from actions.email_actions import validar_anexo

        # Mesma checagem do anexo de e-mail: nada de arquivo de senha,
        # nada de executável, e limite de tamanho.
        caminho, erro_arquivo = validar_anexo(arquivo)
        if erro_arquivo:
            return erro_arquivo

        # As credenciais são as da conta dona da turma. Enviar pela
        # primeira conta autorizada colocaria o arquivo no Drive errado,
        # e o anexo não abriria para os alunos daquela turma.
        id_arquivo, nome_anexo, erro_envio = enviar_arquivo_para_drive(
            caminho, credenciais=credenciais
        )
        if erro_envio:
            return erro_envio

        # O arquivo nasce privado: sem liberar, o aluno vê "você precisa
        # de permissão" ao abrir o anexo.
        erro_permissao = liberar_para_a_turma(id_arquivo, credenciais)
        if erro_permissao:
            return erro_permissao

        modo = MODOS_DE_ARQUIVO.get(
            _normalizar(modo_arquivo), "VIEW"
        )

        materiais.append(
            {
                "driveFile": {
                    "driveFile": {"id": id_arquivo},
                    "shareMode": modo,
                }
            }
        )

    if materiais:
        corpo["materials"] = materiais

    resposta, erro = _executar(
        servico.courses().courseWork().create(
            courseId=dados_turma["id"], body=corpo
        )
    )
    if erro:
        return erro

    detalhes = [f"Criei a atividade '{titulo}' na turma {dados_turma['name']}"]

    if corpo.get("maxPoints"):
        detalhes.append(f"valendo {corpo['maxPoints']:g} pontos")
    if prazo_local is not None:
        detalhes.append(
            "com prazo " + prazo_local.strftime("%d/%m às %H:%M")
        )
    if link:
        detalhes.append("com o link anexado")
    if nome_anexo:
        rotulo = {
            "STUDENT_COPY": "com uma cópia individual para cada aluno",
            "EDIT": "com o arquivo aberto para os alunos editarem",
        }.get(
            MODOS_DE_ARQUIVO.get(_normalizar(modo_arquivo), "VIEW"),
            "com o arquivo anexado para leitura",
        )
        detalhes.append(f"{rotulo} ({nome_anexo})")

    return (
        ", ".join(detalhes)
        + ". ELA ESTÁ COMO RASCUNHO: os alunos ainda não veem. "
        "Diga isso ao usuário e avise que ele precisa abrir o Classroom "
        "para revisar e publicar."
        + aviso
    )


def devolver_atividade(turma, atividade, aluno):
    """
    Devolve o trabalho corrigido ao aluno.

    É o gesto que fecha a correção no Classroom: só depois de devolver
    o aluno enxerga a nota.
    """

    if not servicos():
        return _sem_contas()

    contexto, erro = _encontrar_turma(turma)
    if erro:
        return erro

    _, servico, _, dados_turma, aviso = contexto

    dados_atividade, erro = _encontrar_atividade(
        servico, dados_turma["id"], atividade
    )
    if erro:
        return erro

    entrega, nome_aluno, erro = _encontrar_entrega(
        servico, dados_turma, dados_atividade, aluno
    )
    if erro:
        return erro

    if not entrega.get("associatedWithDeveloper", False):
        return MENSAGEM_ATIVIDADE_DE_FORA

    if entrega.get("assignedGrade") is None:
        return (
            f"{nome_aluno} ainda não tem nota nessa atividade. "
            "Lance a nota antes de devolver."
        )

    _, erro = _executar(
        servico.courses().courseWork().studentSubmissions().patch(
            courseId=dados_turma["id"],
            courseWorkId=dados_atividade["id"],
            id=entrega["id"],
            updateMask="draftGrade,assignedGrade",
            body={
                "draftGrade": entrega["assignedGrade"],
                "assignedGrade": entrega["assignedGrade"],
            },
        )
    )
    if erro:
        return erro

    # O método da API chama-se "return", que é palavra reservada em
    # Python; a biblioteca do Google expõe como "return_".
    _, erro = _executar(
        servico.courses().courseWork().studentSubmissions().return_(
            courseId=dados_turma["id"],
            courseWorkId=dados_atividade["id"],
            id=entrega["id"],
            body={},
        )
    )
    if erro:
        return erro

    return (
        f"Devolvi a atividade de {nome_aluno} com a nota "
        f"{entrega['assignedGrade']:g}. Agora ele consegue ver a nota."
        + aviso
    )


# ============================================================
# LANÇAR NOTA — DOIS PASSOS
# ============================================================

def preparar_nota(turma, atividade, aluno, nota):
    """
    Monta o lançamento e devolve para o ALF ler em voz alta.

    NÃO lança nada. O envio só acontece em confirmar_nota().
    """

    if not servicos():
        return _sem_contas()

    try:
        valor = float(str(nota).replace(",", "."))
    except (TypeError, ValueError):
        return f"'{nota}' não é uma nota válida. Diga um número."

    if valor < 0:
        return "A nota não pode ser negativa."

    contexto, erro = _encontrar_turma(turma)
    if erro:
        return erro

    email, servico, _, dados_turma, aviso = contexto

    dados_atividade, erro = _encontrar_atividade(
        servico, dados_turma["id"], atividade
    )
    if erro:
        return erro

    maximo = dados_atividade.get("maxPoints")
    if maximo and valor > maximo:
        return (
            f"A nota {valor:g} passa do valor máximo da atividade, que é "
            f"{maximo:g}. Confirme o valor com o usuário."
        )

    entrega, nome_aluno, erro = _encontrar_entrega(
        servico, dados_turma, dados_atividade, aluno
    )
    if erro:
        return erro

    # A API marca quais entregas pertencem a este projeto. Verificar
    # aqui evita preparar uma nota, ler tudo em voz alta, o usuário
    # confirmar, e só então descobrir que não dava.
    if not entrega.get("associatedWithDeveloper", False):
        return MENSAGEM_ATIVIDADE_DE_FORA

    nota_atual = entrega.get("assignedGrade")

    with _LOCK:
        _nota_pendente["dados"] = {
            "conta": email,
            "id_turma": dados_turma["id"],
            "id_atividade": dados_atividade["id"],
            "id_entrega": entrega["id"],
            "nome_aluno": nome_aluno,
            "turma": dados_turma["name"],
            "atividade": dados_atividade["title"],
            "nota": valor,
        }
        _nota_pendente["momento"] = time.monotonic()

    aviso_nota = ""
    if nota_atual is not None:
        aviso_nota = (
            f" ATENÇÃO: este aluno já tem a nota {nota_atual:g} lançada, "
            "que será substituída."
        )

    return (
        "Nota preparada, ainda NÃO lançada. "
        f"Aluno: {nome_aluno}. "
        f"Atividade: {dados_atividade['title']}. "
        f"Turma: {dados_turma['name']}, conta {email}. "
        f"Nota: {valor:g}."
        f"{aviso_nota}"
        f"{aviso}"
        " Leia isso em voz alta e pergunte se pode lançar. Só chame "
        "confirmar_nota depois que o usuário autorizar."
    )


def nota_pendente():
    dados = _nota_pendente["dados"]
    if dados is None:
        return None

    if time.monotonic() - _nota_pendente["momento"] > VALIDADE_NOTA_PENDENTE:
        _nota_pendente["dados"] = None
        return None

    return dados


def cancelar_nota():
    with _LOCK:
        tinha = _nota_pendente["dados"] is not None
        _nota_pendente["dados"] = None

    if tinha:
        return "Descartei a nota. Nada foi lançado."

    return "Não havia nenhuma nota esperando confirmação."


def _servico_da_conta(email):
    for atual, servico, _ in servicos():
        if atual == email:
            return servico
    return None


def confirmar_nota(lancar=None):
    """
    Lança de verdade a nota preparada, pela conta dona da turma.

    O parâmetro lancar existe para os testes trocarem a chamada real.
    """

    with _LOCK:
        dados = nota_pendente()

        if dados is None:
            return (
                "Não há nenhuma nota pronta para lançar. "
                "Prepare primeiro; se já fazia tempo, o lançamento expirou "
                "por segurança e precisa ser refeito."
            )

        if lancar is not None:
            erro = lancar(dados)
        else:
            # A nota tem que ir pela credencial da conta dona da turma:
            # a outra conta simplesmente não tem permissão nela.
            servico = _servico_da_conta(dados.get("conta", ""))

            if servico is None:
                return (
                    f"A conta {dados.get('conta', '')} não está mais "
                    "autorizada. A nota NÃO foi lançada."
                )

            erro = _lancar_na_api(servico, dados)

        if erro:
            return (
                f"Não consegui lançar a nota: {erro}. "
                "Ela NÃO foi lançada; o preparo continua guardado."
            )

        _nota_pendente["dados"] = None

    return (
        f"Nota {dados['nota']:g} lançada para {dados['nome_aluno']} "
        f"em {dados['atividade']}."
    )


def _lancar_na_api(servico, dados):
    """Devolve None em caso de sucesso, ou a mensagem de erro."""

    requisicao = servico.courses().courseWork().studentSubmissions().patch(
        courseId=dados["id_turma"],
        courseWorkId=dados["id_atividade"],
        id=dados["id_entrega"],
        updateMask="draftGrade,assignedGrade",
        body={
            "draftGrade": dados["nota"],
            "assignedGrade": dados["nota"],
        },
    )

    _, erro = _executar(requisicao)
    return erro
