"""
Devolve a atividade com o comentário particular de cada aluno.

A API do Google Classroom não tem comentário: nenhum recurso, nenhum
campo na entrega (conferido na definição da API em 10/09/2026). O único
caminho é digitar no campo "Adicionar comentário particular" da tela.

Por que na devolução e não na correção: comentário particular chega ao
aluno na hora, com notificação -- não existe comentário em rascunho. Na
correção ele chegaria antes de o professor revisar a nota. Na devolução,
nota e comentário chegam juntos, depois da revisão.

Os cuidados, porque comentário no aluno errado é vazamento de informação
particular -- pior que nota errada, e não se desfaz na cabeça de quem
leu:

1. O aluno é achado pelo nome na lista. Ao clicar, o painel da direita
   mostra o nome COMPLETO, e esse nome é conferido antes de digitar.
2. Depois de digitar e antes de enviar, confere de novo: painel no
   aluno certo e o texto certo no campo.
3. Depois de enviar, confere que o comentário apareceu.
4. Só então devolve, pela API. Qualquer divergência para tudo.
"""

import json
import re
import time
import unicodedata
from pathlib import Path
from threading import Lock

from core.arquivo_seguro import substituir_com_retentativa


# Comentários esperando a devolução. Fora do repositório: é dado de aluno.
ARQUIVO = (
    Path(__file__).resolve().parent.parent / "memory" / "comentarios_pendentes.json"
)

# Tempo para o painel do Classroom terminar de desenhar depois de um clique.
ESPERA_TELA = 1.0

_LOCK = Lock()

# Uma devolução por vez. Ver transporte_notas._EM_ANDAMENTO.
_EM_ANDAMENTO = Lock()

# Devolução em andamento. Nada acontece sem passar por aqui.
_devolucao = {
    "fila": [],
    "feitos": [],
    # Serviço e ids da atividade, para devolver pela API.
    "contexto": None,
    # Último nome clicado: fica dentro da lista, é onde a roda rola.
    "ancora": None,
    # A turma inteira. O nome encurtado precisa ser único entre TODOS os
    # alunos da tela, não só entre os que serão devolvidos.
    "nomes": [],
}


def _normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^\w\s]", " ", texto)
    return " ".join(texto.split())


# ============================================================
# COMENTÁRIOS GUARDADOS
# ============================================================

def _chave(id_turma, id_atividade):
    return f"{id_turma}|{id_atividade}"


def _carregar():
    if not ARQUIVO.exists():
        return {}

    try:
        with ARQUIVO.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except (json.JSONDecodeError, OSError):
        return {}

    atividades = dados.get("atividades", {}) if isinstance(dados, dict) else {}
    return atividades if isinstance(atividades, dict) else {}


def _salvar(atividades):
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)

    temporario = ARQUIVO.with_suffix(".tmp")
    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(
            {"versao": 1, "atividades": atividades},
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    substituir_com_retentativa(temporario, ARQUIVO)


def guardar_comentarios(conta, dados_turma, dados_atividade, comentarios):
    """
    Guarda {id_aluno: {"aluno", "texto"}} para a devolução.

    Em disco, e não só na memória do programa: o professor costuma
    revisar no dia seguinte, com o ALF já reiniciado.

    Devolve (quantos, erro).
    """

    with _LOCK:
        atividades = _carregar()
        chave = _chave(dados_turma["id"], dados_atividade["id"])

        registro = atividades.get(chave) or {}
        guardados = dict(registro.get("comentarios") or {})
        guardados.update(comentarios)

        atividades[chave] = {
            "conta": conta,
            "turma": dados_turma.get("name", ""),
            "atividade": dados_atividade.get("title", ""),
            "comentarios": guardados,
        }

        try:
            _salvar(atividades)
        except OSError as erro:
            return 0, f"Não consegui guardar os comentários: {erro}"

    return len(comentarios), None


def comentarios_da_atividade(id_turma, id_atividade):
    with _LOCK:
        registro = _carregar().get(_chave(id_turma, id_atividade)) or {}

    return dict(registro.get("comentarios") or {})


def _esquecer(id_turma, id_atividade, id_aluno):
    """Apaga o comentário já enviado, para nunca sair duas vezes."""

    with _LOCK:
        atividades = _carregar()
        chave = _chave(id_turma, id_atividade)
        registro = atividades.get(chave)
        if not registro:
            return

        registro.get("comentarios", {}).pop(id_aluno, None)
        if not registro.get("comentarios"):
            atividades.pop(chave, None)

        try:
            _salvar(atividades)
        except OSError:
            # A entrega já está devolvida, e preparar_devolucao ignora
            # devolvidas: o comentário sobrando não é reenviado.
            pass


# ============================================================
# PREPARAR — NÃO DEVOLVE NADA
# ============================================================

def preparar_devolucao(turma, atividade):
    """
    Monta a fila de quem tem nota e ainda não foi devolvido.

    Devolve o resumo para o ALF confirmar UMA vez com o professor.
    """

    from actions import classroom_actions as ca

    if not ca.servicos():
        return ca._sem_contas()

    contexto, erro = ca._encontrar_turma(turma)
    if erro:
        return erro

    _, servico, _, dados_turma, aviso = contexto

    dados_atividade, erro = ca._encontrar_atividade(
        servico, dados_turma["id"], atividade
    )
    if erro:
        return erro

    alunos, erro = ca._mapa_de_alunos(servico, dados_turma["id"])
    if erro:
        return erro

    resposta, erro = ca._executar(
        servico.courses().courseWork().studentSubmissions().list(
            courseId=dados_turma["id"],
            courseWorkId=dados_atividade["id"],
            pageSize=200,
        )
    )
    if erro:
        return erro

    entregas = resposta.get("studentSubmissions", [])

    if entregas and not any(
        e.get("associatedWithDeveloper", False) for e in entregas
    ):
        return (
            "Não posso devolver esta atividade: o Google Classroom só me "
            "deixa devolver as atividades criadas por mim. Ela precisa ser "
            "devolvida pelo próprio Classroom. Não tente de novo."
        )

    guardados = comentarios_da_atividade(dados_turma["id"], dados_atividade["id"])

    fila = []
    sem_nota = 0

    for entrega in entregas:
        if entrega.get("state") == "RETURNED":
            continue

        nota = entrega.get("assignedGrade")
        if nota is None:
            nota = entrega.get("draftGrade")

        if nota is None:
            sem_nota += 1
            continue

        id_aluno = entrega.get("userId", "")
        nome = alunos.get(id_aluno)
        if not nome:
            continue

        fila.append(
            {
                "uid": id_aluno,
                "aluno": nome,
                "nota": float(nota),
                "texto": (guardados.get(id_aluno) or {}).get("texto", ""),
                "id_entrega": entrega["id"],
            }
        )

    if not fila:
        return (
            f"Não há ninguém para devolver em '{dados_atividade['title']}': "
            "ou ninguém tem nota ainda, ou todos já foram devolvidos."
        )

    fila.sort(key=lambda item: _normalizar(item["aluno"]))

    with _LOCK:
        _devolucao["fila"] = fila
        _devolucao["feitos"] = []
        _devolucao["ancora"] = None
        _devolucao["nomes"] = list(alunos.values())
        _devolucao["contexto"] = {
            "servico": servico,
            "id_turma": dados_turma["id"],
            "id_atividade": dados_atividade["id"],
        }

    com_comentario = sum(1 for item in fila if item["texto"])

    partes = [
        f"Preparei a devolução de '{dados_atividade['title']}', turma "
        f"{dados_turma['name']}: {len(fila)} alunos, {com_comentario} com "
        f"comentário e {len(fila) - com_comentario} só com a nota."
    ]

    if sem_nota:
        partes.append(f"{sem_nota} ainda sem nota ficam de fora.")

    partes.append(
        "NADA foi devolvido ainda. Devolver faz o aluno ver a nota e o "
        "comentário, e não tem volta: diga esses números e confirme UMA "
        "vez com o professor."
    )

    if com_comentario:
        partes.append(
            "Para os comentários, a página 'Trabalhos dos estudantes' "
            "dessa atividade precisa estar aberta na tela. Peça isso antes "
            "de começar."
        )

    partes.append("Depois chame devolver_proximo_aluno, um aluno por vez.")

    return " ".join(partes) + aviso


# ============================================================
# CONFERÊNCIAS
# ============================================================

def _ler_painel():
    """Lê o painel da direita: de quem é, o que está no campo, o enviado."""

    from actions.transporte_notas import perguntar_a_tela

    esquema = {
        "type": "object",
        "properties": {
            "nome_no_painel": {"type": "string"},
            "texto_no_campo": {"type": "string"},
            "comentario_enviado": {"type": "string"},
        },
        "required": ["nome_no_painel", "texto_no_campo", "comentario_enviado"],
    }

    return perguntar_a_tela(
        (
            "Esta é a tela 'Trabalhos dos estudantes' do Google Classroom. "
            "No painel da direita, leia: "
            "nome_no_painel = o nome do aluno escrito no topo do painel; "
            "texto_no_campo = o texto digitado agora no campo 'Adicionar "
            "comentário particular' (vazio se o campo só mostra esse "
            "convite); "
            "comentario_enviado = o texto do comentário particular mais "
            "recente já enviado que aparece no painel (vazio se não houver). "
            "Se não houver painel aberto, devolva tudo vazio. "
            "Não invente: relate só o que está escrito."
        ),
        esquema,
    )


def _mesmo_aluno(no_painel, esperado):
    """
    O painel mostra o nome completo. Exige que seja o mesmo aluno.

    Só aceita nome cortado se o pedaço visível tiver pelo menos duas
    palavras e for o começo do nome esperado.
    """

    lido = str(no_painel or "").strip()
    cortado = lido.endswith("...") or lido.endswith("…")

    lido = _normalizar(lido)
    alvo = _normalizar(esperado)

    if not lido:
        return False

    if lido == alvo:
        return True

    return cortado and len(lido.split()) >= 2 and alvo.startswith(lido)


def _texto_confere(lido, esperado):
    """O começo do comentário precisa estar lá, palavra por palavra."""

    palavras = _normalizar(esperado).split()[:6]
    return bool(palavras) and " ".join(palavras) in _normalizar(lido)


def _achar(alvo):
    """Localiza um controle do painel. Devolve (localizacao, falha)."""

    from actions.transporte_notas import CONFIANCA_MINIMA
    from vision.click_locator import localizar_elemento_na_tela

    try:
        achado = localizar_elemento_na_tela(alvo)
    except Exception as erro:
        return None, str(erro)

    if not achado.get("sucesso"):
        return None, achado.get("mensagem", "não apareceu na tela")

    if achado.get("confianca", 0) < CONFIANCA_MINIMA:
        return None, "apareceu, mas com pouca certeza"

    return achado, None


def _parar(mensagem):
    with _LOCK:
        _devolucao["fila"] = []

    return mensagem + " O restante da turma NÃO foi devolvido."


def _devolver_pela_api(contexto, item):
    from actions import classroom_actions as ca

    return ca._devolver_entrega(
        contexto["servico"],
        contexto["id_turma"],
        contexto["id_atividade"],
        item["id_entrega"],
        item["nota"],
    )


# ============================================================
# UM ALUNO
# ============================================================

def _comentar_na_tela(nome, texto, outros, ancora, ler_painel):
    """
    Digita e envia o comentário. Devolve (enviado, mensagem_de_parada).

    Uma parada com enviado=False significa que nada saiu para o aluno.
    """

    from actions.mouse_actions import mover_e_clicar
    from actions.text_actions import escrever_no_campo_ativo
    from actions.transporte_notas import _prefixo_do_nome, procurar_na_lista

    prefixo = _prefixo_do_nome(nome, outros)

    local, falha = procurar_na_lista(
        (
            f"nome do aluno que começa com '{prefixo}', na lista de "
            "alunos à esquerda. O nome pode estar cortado com reticências."
        ),
        ancora,
    )
    if local is None:
        return False, (
            f"NÃO devolvi {nome}: o nome dele {falha} Nada foi digitado "
            "nem enviado. Peça ao professor para conferir se a página "
            "certa está aberta e chame de novo."
        ), None

    mover_e_clicar(local["x"], local["y"])
    time.sleep(ESPERA_TELA)
    nova_ancora = (local["x"], local["y"])

    painel, erro = ler_painel()
    if erro:
        return False, f"PAREI em {nome}: {erro} Nada foi digitado.", nova_ancora

    if not _mesmo_aluno(painel.get("nome_no_painel", ""), nome):
        return False, (
            f"PAREI: cliquei em {nome}, mas o painel mostra "
            f"'{painel.get('nome_no_painel', '')}'. Não digitei nada."
        ), nova_ancora

    campo, falha = _achar(
        "campo de texto 'Adicionar comentário particular', no rodapé do "
        "painel da direita"
    )
    if campo is None:
        return False, (
            f"PAREI em {nome}: não achei o campo de comentário ({falha}). "
            "Nada foi digitado."
        ), nova_ancora

    mover_e_clicar(campo["x"], campo["y"])
    escrever_no_campo_ativo(texto)
    time.sleep(ESPERA_TELA)

    digitado_sem_envio = (
        f"PAREI antes de enviar: o comentário de {nome} foi digitado, mas "
        "{motivo}. Ele NÃO foi enviado. Peça ao professor para apagar o "
        "texto do campo de comentário."
    )

    painel, erro = ler_painel()
    if erro:
        return False, digitado_sem_envio.format(motivo=erro), nova_ancora

    if not _mesmo_aluno(painel.get("nome_no_painel", ""), nome):
        return False, digitado_sem_envio.format(
            motivo=f"o painel passou a mostrar '{painel.get('nome_no_painel', '')}'"
        ), nova_ancora

    if not _texto_confere(painel.get("texto_no_campo", ""), texto):
        return False, digitado_sem_envio.format(
            motivo="o texto no campo não bate com o comentário"
        ), nova_ancora

    botao, falha = _achar(
        "botão de enviar o comentário particular (a seta), à direita do "
        "campo de comentário, no painel da direita"
    )
    if botao is None:
        return False, digitado_sem_envio.format(
            motivo=f"não achei o botão de enviar ({falha})"
        ), nova_ancora

    mover_e_clicar(botao["x"], botao["y"])
    time.sleep(ESPERA_TELA)

    painel, erro = ler_painel()
    if erro or not _texto_confere(painel.get("comentario_enviado", ""), texto):
        return False, (
            f"PAREI: cliquei em enviar o comentário de {nome}, mas não "
            "consegui confirmar na tela que ele foi. NÃO devolvi a "
            f"atividade. Peça ao professor para olhar o painel de {nome}."
        ), nova_ancora

    return True, None, nova_ancora


def devolver_proximo_aluno(ler_painel=None, devolver=None):
    if not _EM_ANDAMENTO.acquire(blocking=False):
        return (
            "Ainda estou devolvendo o aluno anterior. Espere eu terminar e "
            "só então chame de novo; nunca chame duas vezes seguidas."
        )

    try:
        return _devolver_proximo_aluno(ler_painel, devolver)
    finally:
        _EM_ANDAMENTO.release()


def _devolver_proximo_aluno(ler_painel=None, devolver=None):
    """
    Comenta (se houver comentário) e devolve o próximo aluno da fila.

    Um aluno por chamada, de propósito: o professor acompanha e pode
    parar a qualquer momento. ler_painel e devolver existem para os
    testes trocarem a tela e a API.
    """

    with _LOCK:
        if not _devolucao["fila"]:
            if _devolucao["feitos"]:
                return (
                    f"Terminei: {len(_devolucao['feitos'])} alunos "
                    "devolvidos."
                )
            return (
                "Não há devolução em andamento. Use preparar_devolucao "
                "primeiro."
            )

        atual = _devolucao["fila"][0]
        ancora = _devolucao["ancora"]
        contexto = _devolucao["contexto"]
        outros = (
            list(_devolucao.get("nomes") or [])
            + [item["aluno"] for item in _devolucao["fila"]]
            + [item["aluno"] for item in _devolucao["feitos"]]
        )

    nome = atual["aluno"]
    texto = atual["texto"]

    if texto:
        enviado, parada, nova_ancora = _comentar_na_tela(
            nome, texto, outros, ancora, ler_painel or _ler_painel
        )

        if nova_ancora is not None:
            with _LOCK:
                _devolucao["ancora"] = nova_ancora

        if not enviado:
            # Aluno não achado na lista: nada saiu, dá para tentar de
            # novo depois de o professor arrumar a tela. Qualquer outra
            # parada esvazia a fila.
            if parada.startswith("NÃO devolvi"):
                return parada
            return _parar(parada)

    if devolver is None:
        erro = _devolver_pela_api(contexto, atual)
    else:
        erro = devolver(atual)

    if erro:
        ja_enviado = (
            "O comentário JÁ FOI enviado e o aluno já pode vê-lo; "
            if texto
            else ""
        )
        return _parar(
            f"PAREI: {ja_enviado}a devolução de {nome} falhou: {erro}. "
            "A nota dele ainda não está visível para ele."
        )

    if texto and contexto:
        _esquecer(contexto["id_turma"], contexto["id_atividade"], atual["uid"])

    with _LOCK:
        if _devolucao["fila"] and _devolucao["fila"][0] is atual:
            _devolucao["fila"].pop(0)
        _devolucao["feitos"].append(atual)
        restam = len(_devolucao["fila"])
        feitos = len(_devolucao["feitos"])

    feito = (
        f"{nome}: comentário enviado e atividade devolvida com nota "
        f"{atual['nota']:g}."
        if texto
        else f"{nome}: devolvida com nota {atual['nota']:g}, sem comentário."
    )

    if restam:
        return (
            f"{feito} {feitos} feitos, {restam} restando. Diga só o nome, "
            "curto, e chame de novo para o próximo."
        )

    return f"{feito} Terminei: {feitos} alunos devolvidos."


def cancelar_devolucao():
    with _LOCK:
        tinha = bool(_devolucao["fila"] or _devolucao["feitos"])
        feitos = len(_devolucao["feitos"])
        _devolucao["fila"] = []
        _devolucao["feitos"] = []

    if not tinha:
        return "Não havia devolução em andamento."

    return (
        f"Parei a devolução. {feitos} alunos já tinham sido devolvidos e "
        "continuam devolvidos; os demais não foram tocados."
    )
