"""
Transporta notas já revisadas de uma planilha para a tela do Classroom.

Este módulo NÃO avalia nada. Ele pega notas que o professor já conferiu
numa planilha e digita cada uma no lugar certo, um aluno por vez.

A separação importa: avaliar e digitar são coisas diferentes. O ALF
avalia com ler_entrega, o professor revisa na planilha, e só então isto
aqui transporta. Assim nenhuma nota chega ao Classroom sem ter passado
pelos olhos de quem responde por ela.

Por que não pela API: o Google Classroom só deixa um projeto externo
lançar nota em atividades criadas por ele mesmo. As atividades que o
professor criou pela interface são somente leitura para a API, e
digitar na tela é o único caminho que resta.

Três cuidados, porque errar aqui significa nota errada na vida de um
aluno:

1. O campo é localizado pelo NOME do aluno, nunca pela posição da
   linha. Rolagem, linha mais alta e seção nova desalinham posição;
   nome não.
2. Depois de digitar, a tela é lida de novo para conferir que o valor
   ficou ao lado do aluno certo.
3. Divergência interrompe o transporte. Nunca segue adiante torcendo.
"""

import re
import time
import unicodedata
from pathlib import Path
from threading import Lock

from core.config import GEMINI_API_KEY


# Tempo entre digitar e conferir, para a tela terminar de desenhar.
ESPERA_ANTES_DE_CONFERIR = 1.2

# Confiança mínima do localizador visual para aceitar o clique.
CONFIANCA_MINIMA = 0.80

# Quantas vezes rolar a lista procurando um aluno que não está visível.
# A turma inteira raramente cabe na tela: sem isto o transporte só
# funcionava para os primeiros alunos e parava no primeiro que exigisse
# rolagem.
ROLAGENS_MAXIMAS = 8
PASSOS_POR_ROLAGEM = 3
ESPERA_APOS_ROLAR = 0.6

# Passos para voltar ao começo da lista. Precisa ser generoso: rolar
# demais no topo não faz nada, rolar de menos deixa alunos escondidos.
PASSOS_PARA_O_TOPO = 40

_LOCK = Lock()

# Uma digitação por vez. Quando o ALF desiste de esperar uma ferramenta,
# ela continua rodando por trás; sem esta trava, a chamada seguinte
# começaria a mexer no mouse junto com a anterior.
_EM_ANDAMENTO = Lock()

# Transporte em andamento. Nada acontece sem passar por aqui.
_transporte = {
    "pendentes": [],
    "concluidos": [],
    "turma": "",
    "atividade": "",
    "origem": "",
    # Último campo de nota clicado com sucesso. É o ponto onde a roda do
    # mouse rola a lista certa. Ver _rolar_lista.
    "ancora": None,
    # A planilha inteira, como foi lida. Sobrevive ao fim da fila para a
    # auditoria final poder comparar tudo. Ver conferir_transporte.
    "todas": [],
    # Todos os nomes que podem aparecer na tela, com ou sem nota. É
    # contra eles que o nome encurtado precisa ser único.
    "nomes": [],
}


def _normalizar(texto):
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.split())


# ============================================================
# LER A PLANILHA REVISADA
# ============================================================

def _ler_planilha_google(id_planilha, credenciais):
    from googleapiclient.discovery import build

    servico = build(
        "sheets", "v4", credentials=credenciais, cache_discovery=False
    )
    resposta = servico.spreadsheets().values().get(
        spreadsheetId=id_planilha, range="A1:Z500"
    ).execute()

    return resposta.get("values", [])


def _ler_planilha_local(caminho):
    import openpyxl

    planilha = openpyxl.load_workbook(caminho, data_only=True)
    aba = planilha.worksheets[0]

    linhas = []
    for linha in aba.iter_rows(max_row=500, values_only=True):
        linhas.append(["" if c is None else str(c) for c in linha])

    return linhas


def _maximo_do_cabecalho(titulo):
    """
    Lê o valor da atividade escrito no próprio cabeçalho.

    A planilha de correção nomeia a coluna como "Nota sugerida (de 1)".
    Isso faz o limite viajar junto com o arquivo: mesmo numa cópia
    local, offline, dá para recusar um 8 numa atividade que vale 1.
    """

    achado = re.search(r"\(de\s*([\d.,]+)\s*\)", str(titulo))
    if not achado:
        return None

    try:
        return float(achado.group(1).replace(",", "."))
    except ValueError:
        return None


def _extrair_notas(linhas, maximo=None):
    """
    Encontra as colunas de aluno e de nota e devolve a lista revisada.

    Aceita qualquer planilha com uma coluna de nome e uma de nota; não
    exige que tenha sido criada pelo ALF.

    maximo é o valor da atividade. Nota acima dele interrompe tudo: o
    caso real foi uma atividade de 1 ponto com notas sugeridas em escala
    de 10. O transporte digitaria 8 num campo que vai até 1, obediente e
    errado, aluno por aluno.
    """

    if not linhas:
        return None, "A planilha está vazia."

    cabecalho = [_normalizar(c) for c in linhas[0]]

    coluna_aluno = None
    coluna_nota = None

    for indice, titulo in enumerate(cabecalho):
        if coluna_aluno is None and ("aluno" in titulo or "nome" in titulo):
            coluna_aluno = indice
        if coluna_nota is None and "nota" in titulo and "lancada" not in titulo:
            coluna_nota = indice

    if coluna_aluno is None or coluna_nota is None:
        return None, (
            "Não achei as colunas na planilha. Ela precisa de uma coluna "
            "com o nome do aluno e outra com a nota."
        )

    # O cabeçalho carrega o valor da atividade quando a planilha veio da
    # correção. Um limite vindo da API tem precedência: é a fonte.
    if maximo is None:
        maximo = _maximo_do_cabecalho(linhas[0][coluna_nota])

    notas = []
    for linha in linhas[1:]:
        if len(linha) <= max(coluna_aluno, coluna_nota):
            continue

        nome = str(linha[coluna_aluno]).strip()
        valor = str(linha[coluna_nota]).strip().replace(",", ".")

        if not nome or not valor:
            continue

        try:
            numero = float(valor)
        except ValueError:
            return None, (
                f"A nota de {nome} está como '{linha[coluna_nota]}', que "
                "não é um número. Corrija na planilha antes."
            )

        if numero < 0:
            return None, (
                f"A nota de {nome} está negativa ({valor}). "
                "Corrija na planilha antes."
            )

        if maximo is not None and numero > maximo + 0.001:
            return None, (
                f"A atividade vale {maximo:g}, mas a nota de {nome} na "
                f"planilha é {valor}. Isso é escala errada, não um caso "
                "isolado: provavelmente a planilha inteira está em outra "
                "escala. NÃO transportei nada. Diga isso ao professor e "
                "peça para ele corrigir a coluna de notas antes."
            )

        notas.append({"aluno": nome, "nota": valor})

    if not notas:
        return None, (
            "Nenhuma linha da planilha tem nota preenchida. Preencha as "
            "notas antes de transportar."
        )

    return notas, None


def _nomes_da_planilha(linhas):
    """Todos os alunos da planilha, inclusive os que ficaram sem nota."""

    if not linhas:
        return []

    cabecalho = [_normalizar(c) for c in linhas[0]]
    coluna = next(
        (i for i, t in enumerate(cabecalho) if "aluno" in t or "nome" in t),
        None,
    )
    if coluna is None:
        return []

    return [
        str(linha[coluna]).strip()
        for linha in linhas[1:]
        if len(linha) > coluna and str(linha[coluna]).strip()
    ]


def _nomes_da_turma(turma):
    """
    A turma inteira, pela API. Vazio se não der para saber.

    Uma planilha feita à mão pode não ter todos os alunos, e a tela tem.
    """

    turma = str(turma or "").strip()
    if not turma:
        return []

    try:
        from actions.classroom_actions import _encontrar_turma, _mapa_de_alunos

        contexto, erro = _encontrar_turma(turma)
        if erro:
            return []

        _, servico, _, dados_turma, _ = contexto
        alunos, erro = _mapa_de_alunos(servico, dados_turma["id"])
        return [] if erro else list(alunos.values())

    except Exception:
        return []


def preparar_transporte(planilha, turma="", atividade=""):
    """
    Lê a planilha revisada e monta a fila. NÃO digita nada.

    Devolve o resumo para o ALF ler em voz alta e pedir confirmação.
    """

    texto = str(planilha or "").strip()
    if not texto:
        return "Diga qual planilha tem as notas revisadas."

    linhas = None

    if "spreadsheets/d/" in texto or re.fullmatch(r"[\w-]{30,}", texto):
        from actions.classroom_contas import servicos

        contas = servicos()
        if not contas:
            return "Nenhuma conta do Google está autorizada."

        id_planilha = texto
        if "spreadsheets/d/" in texto:
            id_planilha = texto.split("spreadsheets/d/")[1].split("/")[0]

        ultimo_erro = None
        for _, _, credenciais in contas:
            try:
                linhas = _ler_planilha_google(id_planilha, credenciais)
                break
            except Exception as erro:
                ultimo_erro = erro

        if linhas is None:
            return (
                f"Não consegui abrir a planilha: {ultimo_erro}. "
                "Só enxergo planilhas criadas por mim."
            )
    else:
        from actions.email_actions import localizar_arquivo

        encontrados = localizar_arquivo(texto)
        if not encontrados:
            return f"Não encontrei a planilha {texto} no computador."
        if len(encontrados) > 1:
            nomes = ", ".join(a.name for a in encontrados[:5])
            return f"Encontrei mais de uma planilha: {nomes}. Diga qual."

        try:
            linhas = _ler_planilha_local(encontrados[0])
        except Exception as erro:
            return f"Não consegui ler a planilha: {erro}"

    maximo, aviso_maximo = _valor_da_atividade(turma, atividade)

    notas, erro = _extrair_notas(linhas, maximo=maximo)
    if erro:
        return erro

    # Quem ficou sem nota não entra na fila, mas continua na tela. O nome
    # encurtado era calculado só entre os que têm nota: "Ana Beatriz"
    # parecia único, e na tela servia também para a Ana Beatriz sem nota.
    nomes = _nomes_da_planilha(linhas) + _nomes_da_turma(turma)

    with _LOCK:
        _transporte["pendentes"] = list(notas)
        _transporte["concluidos"] = []
        _transporte["todas"] = list(notas)
        _transporte["nomes"] = nomes
        _transporte["ancora"] = None
        _transporte["turma"] = str(turma or "")
        _transporte["atividade"] = str(atividade or "")
        _transporte["origem"] = texto

    primeiros = ", ".join(
        f"{n['aluno']} com {n['nota']}" for n in notas[:3]
    )

    if maximo is not None:
        escala = f"Todas cabem no valor da atividade, que é {maximo:g}. "
    else:
        escala = aviso_maximo.strip() + " "

    return (
        f"Li {len(notas)} notas na planilha. Os primeiros são: {primeiros}. "
        f"{escala}"
        "NADA foi digitado ainda. "
        "Antes de começar, o professor precisa deixar aberta na tela a "
        "página de notas da atividade no Classroom, rolada até o começo "
        "da lista. Quem estiver mais abaixo eu alcanço rolando sozinho. "
        "Leia isso em voz alta, confirme que a tela está pronta e só "
        "então comece, um aluno por vez com lancar_proxima_nota."
    )


def _valor_da_atividade(turma, atividade):
    """
    Quanto vale a atividade, direto do Classroom.

    Devolve (maximo, aviso). maximo None significa que não deu para
    saber -- sem turma e atividade, ou sem conta autorizada. Nesse caso
    ainda resta o valor escrito no cabeçalho da planilha.

    Erro de rede aqui não interrompe o transporte: o professor revisou a
    planilha, e a conferência por nome continua valendo. Só se perde a
    checagem de escala, e o aviso diz isso.
    """

    turma = str(turma or "").strip()
    atividade = str(atividade or "").strip()

    if not turma or not atividade:
        return None, (
            " Não conferi a escala das notas porque não sei de qual turma "
            "e atividade se trata. Se quiser essa conferência, diga as duas."
        )

    try:
        from actions.classroom_actions import (
            _encontrar_atividade,
            _encontrar_turma,
        )

        contexto, erro = _encontrar_turma(turma)
        if erro:
            return None, f" Não conferi a escala das notas: {erro}"

        _, servico, _, dados_turma, _ = contexto

        dados_atividade, erro = _encontrar_atividade(
            servico, dados_turma["id"], atividade
        )
        if erro:
            return None, f" Não conferi a escala das notas: {erro}"

        maximo = dados_atividade.get("maxPoints")

    except Exception as erro:
        return None, f" Não consegui conferir quanto vale a atividade: {erro}"

    if maximo is None:
        return None, " A atividade não tem pontuação definida no Classroom."

    return float(maximo), ""


def conferir_transporte(turma="", atividade=""):
    """
    Confere no Classroom quais notas existem de verdade.

    A conferência por tela é boa para pegar nota na linha errada, mas
    depende de um modelo ler uma imagem. Já aconteceu de o transporte
    parar no meio e o ALF anunciar que tinha lançado tudo.

    Isto aqui não lê tela: pergunta ao Classroom. draftGrade é a nota
    que o Classroom guardou como rascunho -- exatamente o que aparece
    escrito "Rascunho" embaixo do número. Ler é permitido em qualquer
    atividade; só escrever é que o Google bloqueia.

    Devolve aluno por aluno: o que a planilha manda e o que existe lá.
    """

    from actions.classroom_actions import (
        _casa,
        _contem,
        _encontrar_atividade,
        _encontrar_turma,
        _executar,
        _mapa_de_alunos,
    )

    with _LOCK:
        esperadas = list(_transporte["todas"])
        turma = str(turma or "").strip() or _transporte["turma"]
        atividade = str(atividade or "").strip() or _transporte["atividade"]

    if not esperadas:
        return (
            "Não tenho nenhuma planilha carregada para conferir. Use "
            "preparar_transporte primeiro."
        )

    if not turma or not atividade:
        return (
            "Para conferir eu preciso saber a turma e a atividade. "
            "Pergunte ao professor quais são."
        )

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

    # A nota vale se estiver como rascunho ou já atribuída: as duas
    # aparecem na tela do professor.
    no_classroom = {}
    for entrega in resposta.get("studentSubmissions", []):
        nome = alunos.get(entrega.get("userId", ""))
        if not nome:
            continue
        valor = entrega.get("assignedGrade")
        if valor is None:
            valor = entrega.get("draftGrade")
        no_classroom[nome] = valor

    def nota_de(nome_planilha):
        for nome, valor in no_classroom.items():
            if _casa(nome_planilha, nome) or _contem(nome_planilha, nome):
                return valor, True
        return None, False

    conferidos = []
    faltando = []
    divergentes = []
    sem_aluno = []

    for item in esperadas:
        esperada = float(item["nota"])
        valor, achou = nota_de(item["aluno"])

        if not achou:
            sem_aluno.append(item["aluno"])
        elif valor is None:
            faltando.append(f"{item['aluno']} (deveria ter {esperada:g})")
        elif abs(float(valor) - esperada) < 0.001:
            conferidos.append(item["aluno"])
        else:
            divergentes.append(
                f"{item['aluno']} está com {float(valor):g} e deveria "
                f"ter {esperada:g}"
            )

    partes = [
        f"Conferido no Classroom, não na tela: de {len(esperadas)} notas "
        f"da planilha, {len(conferidos)} estão lá certas."
    ]

    if faltando:
        partes.append(
            f"NÃO estão lançadas: {', '.join(faltando[:10])}."
        )

    if divergentes:
        partes.append(f"DIFERENTES da planilha: {', '.join(divergentes[:10])}.")

    if sem_aluno:
        partes.append(
            f"Não achei na turma: {', '.join(sem_aluno[:10])}. "
            "Confira se o nome na planilha bate com o do Classroom."
        )

    if faltando or divergentes or sem_aluno:
        partes.append(
            "Leia esses nomes em voz alta para o professor. NÃO diga que "
            "está tudo lançado."
        )
    else:
        partes.append(
            "Tudo bate. Lembre que são rascunhos: o professor ainda "
            "precisa salvar e devolver no Classroom."
        )

    return " ".join(partes) + aviso


def estado_do_transporte():
    with _LOCK:
        pendentes = list(_transporte["pendentes"])
        concluidos = list(_transporte["concluidos"])

    if not pendentes and not concluidos:
        return "Não há nenhum transporte de notas em andamento."

    partes = [
        f"{len(concluidos)} notas já lançadas, {len(pendentes)} restando."
    ]

    if pendentes:
        partes.append(f"O próximo é {pendentes[0]['aluno']}.")

    return " ".join(partes)


def cancelar_transporte():
    with _LOCK:
        tinha = bool(_transporte["pendentes"] or _transporte["concluidos"])
        feitos = len(_transporte["concluidos"])
        _transporte["pendentes"] = []
        _transporte["concluidos"] = []
        _transporte["ancora"] = None

    if not tinha:
        return "Não havia transporte em andamento."

    return (
        f"Parei o transporte. {feitos} notas já tinham sido digitadas e "
        "continuam na tela; as demais não foram tocadas."
    )


def _prefixo_do_nome(nome, outros):
    """
    O menor pedaço do nome que ainda distingue este aluno dos demais.

    A lista do Classroom corta nomes longos: "Ana Beatriz Santos da
    Silva" aparece como "Ana Beatriz Santos da ...". Procurar pelo nome
    inteiro faz o localizador ver um nome diferente do pedido e recusar
    -- e o localizador é instruído a recusar em vez de chutar, o que
    está certo. Foi assim que o transporte parou justamente nos alunos
    de nome comprido.

    Começa com duas palavras e só cresce se houver outro aluno com o
    mesmo começo: encurtar não pode custar ambiguidade.
    """

    palavras = str(nome).split()
    if len(palavras) <= 2:
        return nome

    concorrentes = [
        _normalizar(o) for o in outros if _normalizar(o) != _normalizar(nome)
    ]

    for tamanho in range(2, len(palavras)):
        prefixo = " ".join(palavras[:tamanho])
        alvo = _normalizar(prefixo)
        if not any(c.startswith(alvo) for c in concorrentes):
            return prefixo

    return nome


def _alvo_do_aluno(prefixo):
    return (
        "campo de digitar a nota, na mesma linha do aluno cujo nome "
        f"começa com '{prefixo}'. O nome pode estar cortado com "
        "reticências na tela; isso não impede de reconhecê-lo."
    )


def _rolar_lista(ancora):
    """
    Desce um pouco a lista de alunos.

    A roda do mouse age sobre a janela que estiver sob o ponteiro. Se
    ele estiver sobre a barra lateral das turmas, rola a coisa errada e
    a lista de alunos nem se mexe. Por isso o ponteiro vai primeiro para
    a âncora: o último campo de nota clicado com sucesso, que por
    definição fica dentro da lista certa.

    Sem âncora ainda (primeiro aluno já fora da tela), rola de onde o
    ponteiro estiver. O nome continua sendo conferido depois, então uma
    rolagem no lugar errado atrasa, mas não escreve nota errada.
    """

    from actions.mouse_actions import mover_mouse_para, rolar_pagina

    if ancora is not None:
        mover_mouse_para(ancora[0], ancora[1], duracao=0.1)

    rolar_pagina("baixo", PASSOS_POR_ROLAGEM)
    time.sleep(ESPERA_APOS_ROLAR)


def procurar_na_lista(alvo, ancora):
    """
    Procura um elemento da lista de alunos, rolando se precisar.

    Primeiro olha onde a tela está. Se não achar, volta ao topo e varre
    a lista inteira descendo -- só descer era uma catraca que perdia de
    vez quem tivesse ficado acima.

    Devolve (localizacao, falha). falha já diz que a lista foi varrida.
    """

    from vision.click_locator import localizar_elemento_na_tela

    rolagens = 0
    voltou_ao_topo = False

    while True:
        try:
            achado = localizar_elemento_na_tela(alvo)
        except Exception as erro:
            return None, f"não pôde ser procurado: {erro}"

        if not achado.get("sucesso"):
            motivo = (
                f"não apareceu na tela. {achado.get('mensagem', '')}"
            ).strip()
        elif achado.get("confianca", 0) < CONFIANCA_MINIMA:
            # Linha cortada no pé da tela dá exatamente esta leitura.
            # Rolar costuma resolver; clicar assim, não.
            motivo = "apareceu, mas com pouca certeza."
        else:
            return achado, None

        if not voltou_ao_topo:
            # Sem âncora, a roda rolaria onde o ponteiro estiver -- em
            # geral em cima da janela do ALF ou da lista de turmas, e a
            # lista de alunos nem se mexeria. Acha a lista primeiro.
            if ancora is None:
                ancora = _achar_a_lista()
            _voltar_ao_topo(ancora)
            voltou_ao_topo = True
            continue

        if rolagens >= ROLAGENS_MAXIMAS:
            return None, (
                f"{motivo} Varri a lista inteira desde o topo, "
                f"{rolagens} rolagens."
            )

        _rolar_lista(ancora)
        rolagens += 1


def _achar_a_lista():
    """Um ponto dentro da lista de alunos, para a roda rolar a coisa certa."""

    from vision.click_locator import localizar_elemento_na_tela

    try:
        achado = localizar_elemento_na_tela(
            "a lista de nomes de alunos, no meio da tela: o centro de "
            "qualquer nome de aluno visível"
        )
    except Exception:
        return None

    if achado.get("sucesso") and achado.get("confianca", 0) >= CONFIANCA_MINIMA:
        return (achado["x"], achado["y"])

    return None


def _voltar_ao_topo(ancora):
    """
    Sobe a lista até o começo.

    Só descer era uma catraca: falhou uma vez, a lista ficava lá
    embaixo, e a tentativa seguinte descia ainda mais. Aluno que ficou
    acima nunca mais era encontrado -- foi exatamente o que aconteceu
    com a lista ordenada por status, em que os já corrigidos sobem.

    Voltando ao topo antes de varrer, cada busca começa do mesmo lugar
    conhecido, e a ordem da lista deixa de importar.
    """

    from actions.mouse_actions import mover_mouse_para, rolar_pagina

    if ancora is not None:
        mover_mouse_para(ancora[0], ancora[1], duracao=0.1)

    # A roda aceita no máximo 10 passos por chamada.
    for _ in range(max(1, PASSOS_PARA_O_TOPO // 10)):
        rolar_pagina("cima", 10)

    time.sleep(ESPERA_APOS_ROLAR)


# ============================================================
# CONFERÊNCIA PELA TELA
# ============================================================

def perguntar_a_tela(pergunta, esquema):
    """
    Captura a tela e pergunta ao modelo de visão, com resposta em JSON.

    Devolve (dados, erro). Usada pela conferência das notas e pela
    devolução com comentário: as duas precisam ler a tela do Classroom
    e relatar o que está escrito, sem inventar.
    """

    if not GEMINI_API_KEY:
        return None, "Falta a chave da API para ler a tela."

    try:
        import json

        from google import genai
        from google.genai import types

        from core.gemini_ssl import criar_http_options_gemini
        from vision.screen_capture import capturar_tela_bytes

        imagem = capturar_tela_bytes()

        cliente = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=criar_http_options_gemini(types),
        )

        resposta = cliente.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=[
                pergunta,
                types.Part.from_bytes(data=imagem, mime_type="image/jpeg"),
            ],
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=esquema,
            ),
        )

        return json.loads(resposta.text), None

    except Exception as erro:
        return None, f"Não consegui ler a tela: {erro}"


def _conferir_na_tela(nome_aluno, nota_esperada):
    """
    Lê a tela e confere se a nota ficou ao lado do aluno certo.

    Devolve (conferido, mensagem). conferido=False interrompe tudo.
    """

    esquema = {
        "type": "object",
        "properties": {
            "encontrou_aluno": {"type": "boolean"},
            "nota_no_campo": {"type": "string"},
            "observacao": {"type": "string"},
        },
        "required": ["encontrou_aluno", "nota_no_campo", "observacao"],
    }

    dados, erro = perguntar_a_tela(
        (
            "Esta é a tela de notas de uma turma. "
            f"Encontre a linha do aluno cujo nome começa com "
            f"'{nome_aluno}' -- o nome pode estar cortado com "
            "reticências -- e diga qual valor está no campo de "
            "nota DESSA linha. "
            "Se não achar o aluno, diga encontrou_aluno=false. "
            "Se o campo estiver vazio, devolva nota_no_campo vazio. "
            "Não invente: relate o que está escrito."
        ),
        esquema,
    )
    if erro:
        return False, erro

    if not dados.get("encontrou_aluno"):
        return False, (
            f"Não encontrei {nome_aluno} na tela para conferir. "
            "Pare e peça ao professor para verificar."
        )

    encontrada = str(dados.get("nota_no_campo", "")).strip().replace(",", ".")
    esperada = str(nota_esperada).strip().replace(",", ".")

    try:
        bate = abs(float(encontrada) - float(esperada)) < 0.001
    except ValueError:
        bate = False

    if not bate:
        return False, (
            f"CONFERÊNCIA FALHOU: era para {nome_aluno} ficar com "
            f"{esperada}, mas na tela está '{encontrada}'. "
            "O transporte foi interrompido. Diga isso ao professor e não "
            "continue sem ele verificar."
        )

    return True, ""


# ============================================================
# LANÇAR UM ALUNO
# ============================================================

def lancar_proxima_nota(conferir=None):
    if not _EM_ANDAMENTO.acquire(blocking=False):
        return (
            "Ainda estou digitando a nota anterior. Espere eu terminar e "
            "só então chame de novo; nunca chame duas vezes seguidas."
        )

    try:
        return _lancar_proxima_nota(conferir)
    finally:
        _EM_ANDAMENTO.release()


def _lancar_proxima_nota(conferir=None):
    """
    Digita a nota do próximo aluno da fila e confere na tela.

    Um aluno por chamada, de propósito: o professor acompanha e pode
    parar a qualquer momento.
    """

    from actions.mouse_actions import mover_e_clicar
    from actions.text_actions import escrever_no_campo_ativo

    with _LOCK:
        if not _transporte["pendentes"]:
            if _transporte["concluidos"]:
                total = len(_transporte["concluidos"])
                return (
                    f"Terminei: {total} notas foram digitadas e conferidas. "
                    "Diga ao professor para revisar a tela e salvar no "
                    "Classroom; eu não salvo nada."
                )
            return (
                "Não há transporte em andamento. Use preparar_transporte "
                "primeiro."
            )

        atual = _transporte["pendentes"][0]
        ancora = _transporte["ancora"]
        outros = list(_transporte["nomes"]) + [
            n["aluno"] for n in _transporte["todas"]
        ]

    nome = atual["aluno"]
    nota = atual["nota"]
    procurado = _prefixo_do_nome(nome, outros)

    # Localiza pelo NOME. Posição de linha desalinha com rolagem, linha
    # mais alta ou seção nova; nome não.
    localizacao, falha = procurar_na_lista(_alvo_do_aluno(procurado), ancora)

    if localizacao is None:
        return (
            f"NÃO LANCEI a nota de {nome}: o campo dele {falha} "
            "NÃO diga que lançou: não lancei. Conte ao professor que "
            "parou neste aluno e peça para ele conferir se a página "
            "de notas certa está aberta."
        )

    mover_e_clicar(localizacao["x"], localizacao["y"])
    escrever_no_campo_ativo(str(nota).replace(".", ","))

    time.sleep(ESPERA_ANTES_DE_CONFERIR)

    verificador = conferir or _conferir_na_tela
    conferido, aviso = verificador(procurado, nota)

    if not conferido:
        with _LOCK:
            _transporte["pendentes"] = []
        return aviso

    with _LOCK:
        # Este ponto está dentro da lista de alunos: serve de âncora para
        # a roda do mouse na próxima busca.
        _transporte["ancora"] = (localizacao["x"], localizacao["y"])

        if _transporte["pendentes"] and _transporte["pendentes"][0] is atual:
            _transporte["pendentes"].pop(0)
        _transporte["concluidos"].append(atual)
        restam = len(_transporte["pendentes"])
        feitos = len(_transporte["concluidos"])

    if restam:
        return (
            f"{nome}: {nota} digitado e conferido na tela. "
            f"{feitos} feitos, {restam} restando. "
            "Diga só o nome e a nota, curto, e chame de novo para o "
            "próximo."
        )

    return (
        f"{nome}: {nota} digitado e conferido. "
        f"Terminei os {feitos} alunos. "
        "AGORA chame conferir_transporte antes de dizer qualquer coisa "
        "ao professor: ele pergunta ao Classroom quais notas existem de "
        "verdade, e é essa resposta que você deve relatar. "
        "Depois lembre que são rascunhos: ele precisa salvar e devolver."
    )
