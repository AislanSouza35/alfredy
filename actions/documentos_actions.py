"""
Criar apresentação, documento e planilha no Google.

Até aqui o ALF só consumia material: lia entrega de aluno, lia planilha
de notas. Estas funções invertem a mão -- ele passa a produzir o que o
professor usaria horas para montar à mão.

Nenhum escopo novo foi preciso: as três APIs aceitam o drive.file, que
o Forms já trouxe. É o escopo estreito, restrito aos arquivos criados
por este app; o resto do Drive continua fora de alcance.
"""

import unicodedata

from actions.classroom_contas import falta_para_recurso, servicos


# Limites de sanidade: um erro de transcrição não pode gerar um
# material gigante por engano.
MAXIMO_SLIDES = 40
MAXIMO_TOPICOS = 12
MAXIMO_BLOCOS = 200
MAXIMO_LINHAS = 500
MAXIMO_COLUNAS = 40


def _normalizar(texto):
    texto = str(texto).lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.split())


def _servico(api, versao, conta=""):
    """Devolve (servico, email, erro) para a API pedida."""

    contas = servicos()
    if not contas:
        return None, None, "Nenhuma conta do Google está autorizada ainda."

    escolhida = None

    if conta:
        procurado = _normalizar(conta)
        for email, _, credenciais in contas:
            if procurado in _normalizar(email):
                escolhida = (email, credenciais)
                break
        if escolhida is None:
            return None, None, (
                f"Não tenho a conta {conta} autorizada. Disponíveis: "
                + ", ".join(c[0] for c in contas)
                + "."
            )
    else:
        escolhida = (contas[0][0], contas[0][2])

    pendente = falta_para_recurso(escolhida[0], "documentos")
    if pendente:
        return None, None, pendente

    try:
        from googleapiclient.discovery import build

        return (
            build(api, versao, credentials=escolhida[1], cache_discovery=False),
            escolhida[0],
            None,
        )
    except Exception as erro:
        return None, None, f"Não consegui acessar o Google {api}: {erro}"


def _traduzir_falha(erro, nome_api):
    texto = str(erro)

    if "403" in texto:
        return (
            f"O Google recusou o acesso. Confira se a API do {nome_api} "
            "está ativada no projeto do console."
        )
    if "404" in texto:
        return "Não encontrei esse arquivo."

    return f"O Google devolveu um erro: {erro}"


# ============================================================
# APRESENTAÇÃO
# ============================================================

def _validar_slides(slides):
    if not isinstance(slides, (list, tuple)) or not slides:
        return None, (
            "Nenhum slide foi informado. Diga o título de cada slide e "
            "os tópicos dele."
        )

    if len(slides) > MAXIMO_SLIDES:
        return None, (
            f"São {len(slides)} slides, acima do limite de {MAXIMO_SLIDES}. "
            "Divida em mais de uma apresentação."
        )

    limpos = []

    for numero, bruto in enumerate(slides, start=1):
        if isinstance(bruto, str):
            bruto = {"titulo": bruto, "topicos": []}

        if not isinstance(bruto, dict):
            return None, f"O slide {numero} veio em formato inválido."

        titulo = " ".join(str(bruto.get("titulo", "")).split()).strip()
        if not titulo:
            return None, f"O slide {numero} está sem título."

        topicos = bruto.get("topicos") or []
        topicos = [
            " ".join(str(t).split()).strip()
            for t in topicos
            if str(t).strip()
        ][:MAXIMO_TOPICOS]

        limpos.append({"titulo": titulo, "topicos": topicos})

    return limpos, None


def criar_apresentacao(titulo, slides, conta=""):
    """
    Monta uma apresentação com título e tópicos por slide.

    A ideia é dar uma base pronta para o professor ajustar, não uma
    aula final.
    """

    titulo = " ".join(str(titulo or "").split()).strip()
    if not titulo:
        return "Qual deve ser o título da apresentação?"

    limpos, erro = _validar_slides(slides)
    if erro:
        return erro

    servico, email, erro = _servico("slides", "v1", conta)
    if erro:
        return erro

    try:
        apresentacao = servico.presentations().create(
            body={"title": titulo}
        ).execute()
    except Exception as erro:
        return _traduzir_falha(erro, "Google Slides")

    id_apresentacao = apresentacao.get("presentationId", "")

    # A apresentação nasce com um slide em branco. Ele é apagado no
    # fim, depois que os slides de verdade já existem -- apagar antes
    # deixaria a apresentação sem nenhum slide por um instante, o que
    # a API recusa.
    slide_inicial = ""
    if apresentacao.get("slides"):
        slide_inicial = apresentacao["slides"][0].get("objectId", "")

    pedidos = []

    for indice, slide in enumerate(limpos):
        id_slide = f"alf_slide_{indice}"
        id_titulo = f"alf_titulo_{indice}"
        id_corpo = f"alf_corpo_{indice}"

        tem_topicos = bool(slide["topicos"])
        layout = "TITLE_AND_BODY" if tem_topicos else "TITLE_ONLY"

        mapeamentos = [
            {
                "layoutPlaceholder": {"type": "TITLE", "index": 0},
                "objectId": id_titulo,
            }
        ]
        if tem_topicos:
            mapeamentos.append(
                {
                    "layoutPlaceholder": {"type": "BODY", "index": 0},
                    "objectId": id_corpo,
                }
            )

        pedidos.append(
            {
                "createSlide": {
                    "objectId": id_slide,
                    "insertionIndex": indice,
                    "slideLayoutReference": {"predefinedLayout": layout},
                    "placeholderIdMappings": mapeamentos,
                }
            }
        )

        pedidos.append(
            {"insertText": {"objectId": id_titulo, "text": slide["titulo"]}}
        )

        if tem_topicos:
            pedidos.append(
                {
                    "insertText": {
                        "objectId": id_corpo,
                        "text": "\n".join(slide["topicos"]),
                    }
                }
            )

    if slide_inicial:
        pedidos.append({"deleteObject": {"objectId": slide_inicial}})

    try:
        servico.presentations().batchUpdate(
            presentationId=id_apresentacao, body={"requests": pedidos}
        ).execute()
    except Exception as erro:
        return (
            f"Criei a apresentação, mas falhei ao montar os slides: {erro}. "
            f"Ela está no Drive da conta {email}, praticamente vazia."
        )

    link = f"https://docs.google.com/presentation/d/{id_apresentacao}/edit"

    return (
        f"Criei a apresentação '{titulo}' com {len(limpos)} slides na conta "
        f"{email}. É uma base para você ajustar, não uma aula pronta. "
        f"Link: {link} "
        "Diga quantos slides foram criados e sobre o que, sem ler o "
        "conteúdo inteiro em voz alta."
    )


# ============================================================
# DOCUMENTO
# ============================================================

ESTILOS_DE_BLOCO = {
    "titulo": "HEADING_1",
    "subtitulo": "HEADING_2",
    "texto": "NORMAL_TEXT",
    "lista": "NORMAL_TEXT",
}


def _validar_blocos(blocos):
    if isinstance(blocos, str):
        blocos = [{"tipo": "texto", "texto": blocos}]

    if not isinstance(blocos, (list, tuple)) or not blocos:
        return None, "O documento está sem conteúdo. Diga o que escrever."

    if len(blocos) > MAXIMO_BLOCOS:
        return None, (
            f"São {len(blocos)} blocos, acima do limite de {MAXIMO_BLOCOS}."
        )

    limpos = []

    for bruto in blocos:
        if isinstance(bruto, str):
            bruto = {"tipo": "texto", "texto": bruto}

        if not isinstance(bruto, dict):
            continue

        texto = str(bruto.get("texto", "")).strip()
        if not texto:
            continue

        tipo = _normalizar(bruto.get("tipo", "texto"))
        if tipo not in ESTILOS_DE_BLOCO:
            tipo = "texto"

        limpos.append({"tipo": tipo, "texto": " ".join(texto.split())})

    if not limpos:
        return None, "O documento está sem conteúdo. Diga o que escrever."

    return limpos, None


def _pedidos_do_documento(blocos):
    """
    Monta o texto inteiro e as faixas de estilo de cada parágrafo.

    O texto vai numa única inserção porque cada inserção desloca os
    índices das seguintes; calcular tudo antes evita esse remendo.
    """

    completo = []
    faixas = []
    posicao = 1  # o corpo do documento começa no índice 1

    for bloco in blocos:
        linha = bloco["texto"]
        if bloco["tipo"] == "lista":
            linha = "• " + linha
        linha += "\n"

        faixas.append(
            {
                "inicio": posicao,
                "fim": posicao + len(linha),
                "estilo": ESTILOS_DE_BLOCO[bloco["tipo"]],
            }
        )

        completo.append(linha)
        posicao += len(linha)

    pedidos = [
        {"insertText": {"location": {"index": 1}, "text": "".join(completo)}}
    ]

    for faixa in faixas:
        pedidos.append(
            {
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": faixa["inicio"],
                        "endIndex": faixa["fim"],
                    },
                    "paragraphStyle": {"namedStyleType": faixa["estilo"]},
                    "fields": "namedStyleType",
                }
            }
        )

    return pedidos


def criar_documento(titulo, blocos, conta=""):
    """Cria um documento no Google Docs com títulos e parágrafos."""

    titulo = " ".join(str(titulo or "").split()).strip()
    if not titulo:
        return "Qual deve ser o título do documento?"

    limpos, erro = _validar_blocos(blocos)
    if erro:
        return erro

    servico, email, erro = _servico("docs", "v1", conta)
    if erro:
        return erro

    try:
        documento = servico.documents().create(
            body={"title": titulo}
        ).execute()
    except Exception as erro:
        return _traduzir_falha(erro, "Google Docs")

    id_documento = documento.get("documentId", "")

    try:
        servico.documents().batchUpdate(
            documentId=id_documento,
            body={"requests": _pedidos_do_documento(limpos)},
        ).execute()
    except Exception as erro:
        return (
            f"Criei o documento, mas falhei ao escrever o conteúdo: {erro}. "
            f"Ele está no Drive da conta {email}, vazio."
        )

    link = f"https://docs.google.com/document/d/{id_documento}/edit"

    return (
        f"Criei o documento '{titulo}' com {len(limpos)} parágrafos na "
        f"conta {email}. Link: {link} "
        "Resuma o que foi escrito; não leia o documento em voz alta."
    )


# ============================================================
# PLANILHA
# ============================================================

def salvar_copia_local(titulo, linhas):
    """
    Grava a planilha também na Área de Trabalho, como .xlsx.

    A planilha do Google fica no Drive da conta dona da turma. Quando o
    professor abre o link com o navegador logado em outra conta dele,
    aparece "você precisa de permissão" -- e ele não vê o próprio
    arquivo. A cópia local abre com dois cliques, sem depender de qual
    conta está no navegador, e pode ser anexada a um e-mail.

    Devolve (caminho, erro).
    """

    import re

    try:
        import openpyxl
    except ImportError:
        return None, "openpyxl não está instalado."

    from pathlib import Path

    nome = re.sub(r'[<>:"/\\|?*]', "-", str(titulo)).strip()[:120] or "planilha"

    pasta = Path.home() / "OneDrive" / "Área de Trabalho"
    if not pasta.is_dir():
        pasta = Path.home() / "Desktop"
    if not pasta.is_dir():
        pasta = Path.home()

    caminho = pasta / f"{nome}.xlsx"

    # Não sobrescreve uma correção anterior sem avisar.
    contador = 2
    while caminho.exists():
        caminho = pasta / f"{nome} ({contador}).xlsx"
        contador += 1

    try:
        planilha = openpyxl.Workbook()
        aba = planilha.active
        aba.title = "Correção"

        for linha in linhas:
            aba.append(list(linha))

        # Cabeçalho em negrito e largura ajustada, como na do Google.
        for celula in aba[1]:
            celula.font = openpyxl.styles.Font(bold=True)

        for coluna in aba.columns:
            largura = max(
                (len(str(c.value)) for c in coluna if c.value), default=10
            )
            aba.column_dimensions[coluna[0].column_letter].width = min(
                max(largura + 2, 12), 50
            )

        aba.freeze_panes = "A2"
        planilha.save(caminho)

    except Exception as erro:
        return None, f"Não consegui salvar a cópia local: {erro}"

    return caminho, None


def _validar_linhas(linhas):
    if not isinstance(linhas, (list, tuple)) or not linhas:
        return None, "A planilha está sem dados. Diga o que colocar nela."

    if len(linhas) > MAXIMO_LINHAS:
        return None, (
            f"São {len(linhas)} linhas, acima do limite de {MAXIMO_LINHAS}."
        )

    limpas = []

    for bruta in linhas:
        if isinstance(bruta, str):
            bruta = [bruta]

        if not isinstance(bruta, (list, tuple)):
            continue

        limpas.append([str(c) if c is not None else "" for c in bruta][:MAXIMO_COLUNAS])

    if not limpas:
        return None, "A planilha está sem dados. Diga o que colocar nela."

    return limpas, None


def criar_planilha(titulo, linhas, nome_aba="Página1", conta=""):
    """
    Cria uma planilha já preenchida.

    A primeira linha vira cabeçalho em negrito e fica congelada, que é
    o que se espera de qualquer planilha de trabalho.
    """

    titulo = " ".join(str(titulo or "").split()).strip()
    if not titulo:
        return "Qual deve ser o título da planilha?"

    limpas, erro = _validar_linhas(linhas)
    if erro:
        return erro

    servico, email, erro = _servico("sheets", "v4", conta)
    if erro:
        return erro

    nome_aba = " ".join(str(nome_aba or "Página1").split()).strip() or "Página1"

    try:
        planilha = servico.spreadsheets().create(
            body={
                "properties": {"title": titulo},
                "sheets": [{"properties": {"title": nome_aba}}],
            }
        ).execute()
    except Exception as erro:
        return _traduzir_falha(erro, "Google Sheets")

    id_planilha = planilha.get("spreadsheetId", "")
    id_aba = planilha["sheets"][0]["properties"]["sheetId"]

    try:
        servico.spreadsheets().values().update(
            spreadsheetId=id_planilha,
            range=f"'{nome_aba}'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": limpas},
        ).execute()

        servico.spreadsheets().batchUpdate(
            spreadsheetId=id_planilha,
            body={
                "requests": [
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": id_aba,
                                "startRowIndex": 0,
                                "endRowIndex": 1,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "textFormat": {"bold": True}
                                }
                            },
                            "fields": "userEnteredFormat.textFormat.bold",
                        }
                    },
                    {
                        "updateSheetProperties": {
                            "properties": {
                                "sheetId": id_aba,
                                "gridProperties": {"frozenRowCount": 1},
                            },
                            "fields": "gridProperties.frozenRowCount",
                        }
                    },
                    {
                        "autoResizeDimensions": {
                            "dimensions": {
                                "sheetId": id_aba,
                                "dimension": "COLUMNS",
                                "startIndex": 0,
                                "endIndex": len(limpas[0]),
                            }
                        }
                    },
                ]
            },
        ).execute()

    except Exception as erro:
        return (
            f"Criei a planilha, mas falhei ao preencher: {erro}. "
            f"Ela está no Drive da conta {email}."
        )

    link = f"https://docs.google.com/spreadsheets/d/{id_planilha}/edit"

    return (
        f"Criei a planilha '{titulo}' com {len(limpas)} linhas na conta "
        f"{email}. Link: {link} "
        "Diga quantas linhas e colunas foram criadas, sem ler os dados."
    )


def montar_planilha_de_correcao(turma, atividade, avaliacoes, conta=""):
    """
    Reúne numa planilha o que foi avaliado, aluno por aluno.

    Serve para o professor conferir tudo numa tela só e digitar as notas
    de uma vez, em vez de lembrar o que foi dito aluno por aluno durante
    a conversa.

    A turma inteira entra, não só quem foi avaliado: quem não entregou e
    quem ficou sem nota aparecem em branco, para nenhum aluno sumir da
    conferência.
    """

    from actions.classroom_actions import (
        _casa,
        _contem,
        _encontrar_atividade,
        _encontrar_turma,
        _executar,
        _mapa_de_alunos,
    )

    contexto, erro = _encontrar_turma(turma)
    if erro:
        return erro

    email, servico, _, dados_turma, aviso = contexto

    dados_atividade, erro = _encontrar_atividade(
        servico, dados_turma["id"], atividade
    )
    if erro:
        return erro

    if not isinstance(avaliacoes, (list, tuple)):
        avaliacoes = []

    maximo = dados_atividade.get("maxPoints")

    # Uma avaliação inteira em escala de 10 numa atividade que vale 1
    # não é um erro pontual: é a planilha toda errada. Recusar aqui é
    # melhor que gerar 21 linhas que o professor teria de reescrever --
    # e melhor ainda que deixar isso chegar ao transporte.
    if maximo:
        fora = []
        for bruta in avaliacoes:
            if not isinstance(bruta, dict):
                continue
            try:
                valor = float(str(bruta.get("nota", "")).replace(",", "."))
            except ValueError:
                continue
            if valor > float(maximo) + 0.001:
                fora.append(f"{bruta.get('aluno', '?')} com {valor:g}")

        if fora:
            return (
                f"A atividade '{dados_atividade['title']}' vale "
                f"{maximo:g}, mas você sugeriu notas acima disso: "
                f"{', '.join(fora[:5])}. Não montei a planilha. "
                "Refaça as notas na escala certa (de 0 a "
                f"{maximo:g}) e chame de novo. Não precisa reler as "
                "entregas: é só converter o que você já avaliou."
            )

    alunos, erro = _mapa_de_alunos(servico, dados_turma["id"])
    if erro:
        return erro

    if not alunos:
        return f"A turma {dados_turma['name']} não tem alunos matriculados."

    # Situação de cada aluno, direto da API: quem entregou, quem já tem
    # nota. Não dá para confiar só no que foi dito na conversa.
    resposta, erro = _executar(
        servico.courses().courseWork().studentSubmissions().list(
            courseId=dados_turma["id"],
            courseWorkId=dados_atividade["id"],
            pageSize=200,
        )
    )
    if erro:
        return erro

    situacao = {}
    for entrega in resposta.get("studentSubmissions", []):
        estado = entrega.get("state", "")
        situacao[entrega.get("userId", "")] = {
            "entregou": estado in ("TURNED_IN", "RETURNED"),
            "atrasado": bool(entrega.get("late")),
            "nota_atual": entrega.get("assignedGrade"),
        }

    def avaliacao_de(nome_aluno):
        for bruta in avaliacoes:
            if not isinstance(bruta, dict):
                continue
            citado = str(bruta.get("aluno", "")).strip()
            if citado and (_casa(citado, nome_aluno) or _contem(citado, nome_aluno)):
                return bruta
        return None

    cabecalho = [
        "Aluno",
        "Entregou",
        "Nota sugerida" + (f" (de {maximo:g})" if maximo else ""),
        "Observação",
        "Nota já lançada",
    ]

    linhas = [cabecalho]
    avaliados = 0

    for id_aluno, nome in sorted(alunos.items(), key=lambda item: item[1]):
        estado = situacao.get(id_aluno, {})
        avaliacao = avaliacao_de(nome)

        if estado.get("entregou"):
            entregou = "Sim com atraso" if estado.get("atrasado") else "Sim"
        else:
            entregou = "Não"

        nota = ""
        observacao = ""
        if avaliacao is not None:
            valor = str(avaliacao.get("nota", "")).strip()
            if valor:
                nota = valor.replace(".", ",")
                avaliados += 1
            observacao = " ".join(
                str(avaliacao.get("comentario", "")).split()
            ).strip()

        atual = estado.get("nota_atual")
        linhas.append(
            [
                nome,
                entregou,
                nota,
                observacao,
                f"{atual:g}" if atual is not None else "",
            ]
        )

    titulo = f"Correção - {dados_atividade['title']} - {dados_turma['name']}"

    resultado = criar_planilha(
        titulo, linhas, nome_aba="Correção", conta=email
    )

    if not resultado.startswith("Criei"):
        return resultado

    # Cópia local, para o professor abrir sem depender de qual conta
    # está logada no navegador.
    caminho, erro_copia = salvar_copia_local(titulo, linhas)

    sem_nota = len(alunos) - avaliados

    partes = [
        resultado,
        f"São {len(alunos)} alunos: {avaliados} com nota sugerida e "
        f"{sem_nota} em branco.",
    ]

    if caminho is not None:
        partes.append(
            f"Também salvei uma cópia na Área de Trabalho, como "
            f"'{caminho.name}'. Diga esse nome ao usuário: é o caminho "
            "mais simples, porque abre direto no computador. A planilha "
            f"do Google está na conta {email}; se ele abrir o link com o "
            "navegador logado em outra conta, vai pedir permissão."
        )
    elif erro_copia:
        partes.append(f"Não consegui salvar a cópia local: {erro_copia}")

    partes.append(
        "Avise que a planilha é para ele conferir e digitar; ela não "
        "lança nota nenhuma sozinha."
    )

    return " ".join(partes) + aviso


def criar_planilha_de_notas(turma, colunas="", conta=""):
    """
    Cria uma planilha de notas já com os nomes dos alunos da turma.

    Digitar trinta nomes à mão é justamente o trabalho que faz o
    professor não usar planilha nenhuma.
    """

    from actions.classroom_actions import _encontrar_turma, _mapa_de_alunos

    contexto, erro = _encontrar_turma(turma)
    if erro:
        return erro

    email, servico_sala, _, dados_turma, aviso = contexto

    alunos, erro = _mapa_de_alunos(servico_sala, dados_turma["id"])
    if erro:
        return erro

    if not alunos:
        return f"A turma {dados_turma['name']} não tem alunos matriculados."

    nomes_colunas = [
        c.strip() for c in str(colunas or "").split(",") if c.strip()
    ]
    if not nomes_colunas:
        nomes_colunas = ["Nota 1", "Nota 2", "Nota 3", "Média"]

    cabecalho = ["Aluno"] + nomes_colunas
    linhas = [cabecalho]

    for nome in sorted(alunos.values()):
        linhas.append([nome] + [""] * len(nomes_colunas))

    resultado = criar_planilha(
        f"Notas - {dados_turma['name']}",
        linhas,
        nome_aba="Notas",
        conta=email,
    )

    return resultado + aviso
