# asyncio permite executar tarefas assíncronas.
# Neste arquivo, ele coordena simultaneamente:
# - envio do microfone;
# - recebimento de respostas;
# - reprodução de áudio;
# - chamadas de ferramentas;
# - encerramento controlado da sessão.
import asyncio
import random
import re
import sys
import threading
# time é utilizado para medir intervalos.
# Aqui ele ajuda principalmente no controle de repetição
# das funções visuais.
import time
# datetime fornece a data e hora atual.
# Essa informação é colocada na instrução do sistema para ajudar
# o ALFRED a interpretar termos como hoje, amanhã e dias da semana.
from datetime import datetime
from pathlib import Path
import traceback

# array transforma bytes de áudio em amostras numéricas.
# Isso permite calcular o volume aproximado da resposta do ALFRED.
from array import array

# sounddevice captura áudio do microfone e reproduz
# o áudio recebido do Gemini em tempo real.
import sounddevice as sd

# QThread executa o cliente Gemini Live fora da thread principal.
# Isso evita travamentos na interface gráfica.
#
# Signal permite enviar informações da thread para a interface,
# como status, erros, volume e encerramento.
from PySide6.QtCore import QThread, Signal
# Cliente oficial da biblioteca google-genai.
# É utilizado para autenticar e abrir a sessão Gemini Live.
from google import genai
# types contém as estruturas exigidas pela API.
# Exemplos:
# - Tool;
# - FunctionDeclaration;
# - Schema;
# - Content;
# - Part;
# - Blob;
# - FunctionResponse.
from google.genai import types

# Importa as configurações definidas no projeto.
# GEMINI_API_KEY: chave de acesso à API.
# GEMINI_LIVE_MODEL: modelo usado na conversa em tempo real.
# GEMINI_VOICE: voz escolhida para o ALFRED.
from core.config import (
    GEMINI_API_KEY,
    GEMINI_LIVE_MODEL,
    GEMINI_VOICE,
    CEREBRAS_API_KEY,
    CEREBRAS_CHAT_MODEL,
    FORCAR_VOZ_ALTERNATIVA,
    GROQ_API_KEY,
    GROQ_CHAT_MODEL,
    GROQ_WHISPER_MODEL,
    MISTRAL_API_KEY,
    MISTRAL_CHAT_MODEL,
    OPENAI_API_KEY,
    OPENAI_REALTIME_MODEL,
    OPENAI_REALTIME_VOICE,
    VOZ_WINDOWS,
)

# Alternativa para quando a cota do Gemini acaba. Ela tem a mesma cara
# da sessão do Gemini, então o laço de recebimento não muda.
from voz.openai_realtime import conectar as conectar_alternativa

# Último degrau: sem voz em tempo real, ouvindo até o silêncio e falando
# pela voz do Windows. Ver voz/modo_simples.py.
from voz.modo_simples import Provedor, conectar_simples
from core.memoria import memoria_apertada
from core.gemini_ssl import (
    criar_contexto_ssl_gemini,
    criar_http_options_gemini,
)

# Função que captura a tela do computador
# e devolve a imagem em bytes JPEG.
from vision.screen_capture import capturar_tela_bytes
# Função que captura um quadro da webcam
# e devolve a imagem em bytes JPEG.
from vision.camera_capture import capturar_camera_bytes

# Funções responsáveis pelas operações permitidas
# dentro da Área de Trabalho do Windows.
from actions.file_actions import (
    criar_pasta_area_trabalho,
    listar_area_de_trabalho,
    organizar_area_de_trabalho_basico,
    copiar_item_area_trabalho,
    recortar_item_area_trabalho,
    colar_item_area_trabalho,
    renomear_item_area_trabalho,
    cancelar_transferencia_area_trabalho,
)

# Função utilizada para localizar e abrir aplicativos
# e recursos permitidos do Windows.
from actions.app_actions import abrir_aplicativo, fechar_aplicativo

# Ações executadas DENTRO do VS Code. Abrir uma pasta pela linha de
# comando do próprio editor é instantâneo e não depende de navegar por
# caixa de diálogo com reconhecimento visual.
from actions.vscode_actions import (
    abrir_no_vscode,
    executar_comando_vscode,
)

# Ler, criar e executar código. Os limites de onde pode mexer e do que
# pode rodar ficam no próprio módulo.
from actions.codigo_actions import (
    ler_arquivo,
    criar_arquivo_codigo,
    executar_no_terminal,
)

# Google Classroom. O lançamento de nota é em dois passos, como o
# e-mail: nota errada afeta a vida de outra pessoa.
from actions.classroom_actions import (
    listar_turmas,
    listar_atividades,
    listar_entregas,
    ler_entrega,
    preparar_nota,
    confirmar_nota,
    cancelar_nota,
    lancar_notas_em_lote,
    listar_contas,
    autorizar_conta,
    criar_atividade,
    devolver_atividade,
)

# Questionário com gabarito: o Google corrige sozinho.
from actions.forms_actions import (
    criar_questionario,
    listar_respostas,
)

# Produzir material: apresentação, documento e planilha.
# Transporte de notas já revisadas para a tela do Classroom. Não
# avalia nada: só digita o que o professor conferiu na planilha.
from actions.transporte_notas import (
    preparar_transporte,
    lancar_proxima_nota,
    estado_do_transporte,
    cancelar_transporte,
    conferir_transporte,
)

# Devolução com o comentário particular de cada aluno, digitado na tela:
# a API do Classroom não tem comentário.
from actions.devolucao_comentada import (
    preparar_devolucao,
    devolver_proximo_aluno,
    cancelar_devolucao,
)

from actions.documentos_actions import (
    criar_apresentacao,
    criar_documento,
    criar_planilha,
    criar_planilha_de_notas,
    montar_planilha_de_correcao,
)

# Envio de e-mail em duas etapas. preparar_email só monta o rascunho;
# nada sai sem confirmar_envio_email, chamada depois de o usuário
# ouvir a leitura e autorizar.
from actions.email_actions import (
    preparar_email,
    confirmar_envio_email,
    cancelar_email,
    salvar_contato,
    listar_contatos,
    remover_contato,
)
# Funções responsáveis por pesquisas no navegador
# e abertura de vídeos ou músicas no YouTube.
from actions.browser_actions import (
    pesquisar_no_navegador,
    tocar_no_youtube,
)

# Pesquisa invisível de informações atuais.
# Não abre nenhuma guia ou janela no computador.
from actions.web_search import (
    avaliar_necessidade_pesquisa,
    pesquisar_informacao_atual,
    resposta_sem_pesquisa,
)

# Funções responsáveis pelo controle do mouse,
# incluindo rolagem, cliques e movimento até coordenadas.
from actions.mouse_actions import (
    rolar_pagina,
    clicar_mouse,
    duplo_clique_mouse,
    clique_direito_mouse,
    mover_e_clicar,
)

# Função de visão computacional que tenta localizar
# um elemento visível na tela com base em uma descrição.
from vision.click_locator import localizar_elemento_na_tela

# Funções da memória persistente.
# Elas permitem salvar, listar, remover e carregar memórias.
from memory.memory_manager import (
    salvar_memoria,
    listar_memorias,
    esquecer_memoria,
    contexto_memorias,
)

# Gaveta separada de preferências aprendidas automaticamente.
# Limite pequeno, descarte automático e assuntos proibidos ficam
# definidos no próprio módulo.
from memory.preferencias import (
    anotar_preferencia,
    listar_preferencias,
    esquecer_preferencia,
    esquecer_todas_preferencias,
    contexto_preferencias,
)

# Agenda. As três operações continuam as mesmas; o módulo abaixo é
# que decide onde guardar: Google Calendar quando há conta autorizada,
# arquivo local como reserva. Manter três ferramentas em vez de seis
# evita o modelo ter que adivinhar qual usar.
from actions.calendario_actions import (
    criar_evento,
    listar_eventos,
    cancelar_evento,
)

# Função responsável por inserir texto no campo ativo do Windows.
from actions.text_actions import (
    escrever_no_campo_ativo,
    pressionar_atalho_teclado,
)

# Função responsável por localizar e ler planilhas .xlsx de notas
# na Área de Trabalho ou em Downloads.
from actions.planilha_actions import ler_planilha_notas



# Taxa de amostragem do microfone.
# O áudio de entrada é enviado ao Gemini em 16 kHz.
TAXA_ENTRADA = 16000
# Taxa de amostragem da resposta de áudio.
# O áudio gerado pelo Gemini é reproduzido em 24 kHz.
TAXA_SAIDA = 24000
# O sistema utiliza áudio mono.
# Isso significa que existe apenas um canal de áudio.
CANAIS = 1
# Quantidade de amostras processadas em cada bloco.
# Blocos menores reduzem a latência, mas aumentam
# a frequência das operações.
BLOCO = 1024

# Quantidade de amostras processadas em cada bloco de SAÍDA.
# A saída roda a 24 kHz; blocos de 1024 amostras equivalem a 42 ms e
# provocavam falhas de buffer (áudio picotado) quando o computador
# ficava ocupado. Blocos maiores dão folga ao driver sem atrasar
# perceptivelmente o início da fala.
BLOCO_SAIDA = 2400

# Áudio acumulado antes de começar a tocar, em segundos.
#
# O Gemini manda a resposta em rajadas, não num fluxo constante. Sem
# acumular um pouco antes, a placa de som fica sem dados entre uma
# rajada e outra, e é isso que se ouve como picote. Duzentos e
# cinquenta milissegundos cobrem a variação da rede sem que o começo
# da fala pareça atrasado.
PRE_BUFFER_SEGUNDOS = 0.25

# Quanto áudio a fila de saída pode acumular antes de virar problema.
# Passar disso significa que a reprodução não está acompanhando; o
# aviso vai para o log em vez de crescer sem limite em silêncio.
LIMITE_AVISO_FILA_SAIDA = 80

# Tempo de segurança antes de reabrir o microfone depois
# que o ALFRED termina de reproduzir a resposta.
ATRASO_REABRIR_MICROFONE = 0.8

# Detecção de fala feita pelo próprio ALF (VAD do cliente).
#
# A Live API já faz detecção automática de atividade no servidor.
# Enviar audio_stream_end por conta própria depois de cada pausa
# criava uma segunda detecção concorrente: o turno era fechado duas
# vezes, o modelo perdia o fim da frase e a resposta demorava ou não
# vinha. Deixe False para usar apenas o VAD do servidor.
#
# Se em algum computador o ALF passar a demorar para perceber que
# você parou de falar, mude para True e a detecção local volta.
USAR_VAD_CLIENTE = False

# Limite de blocos aguardando envio ao Gemini.
# Evita acúmulo de áudio antigo em computadores ou drivers mais lentos.
LIMITE_FILA_MICROFONE = 50

# Volume mínimo para considerar que houve fala do usuário.
LIMIAR_VOZ_MICROFONE = 0.045

# Tempo de silêncio após fala para finalizar o turno de áudio.
TEMPO_SILENCIO_FINALIZAR_AUDIO = 0.9

# Tempo mínimo para considerar que uma sessão reconectada ficou estável.
TEMPO_SESSAO_ESTAVEL = 45.0

# Espera inicial e máxima entre tentativas de reconexão.
ESPERA_BASE_RECONEXAO = 1.5
ESPERA_MAXIMA_RECONEXAO = 20.0

# Proteção contra ciclo de reinício: mais que MAX_RECONEXOES_NA_JANELA
# quedas dentro de JANELA_CICLO_RECONEXAO segundos faz o ALF parar e
# explicar o problema em vez de ficar reabrindo a sessão sem parar.
JANELA_CICLO_RECONEXAO = 180.0
MAX_RECONEXOES_NA_JANELA = 6

# Cota esgotada não é queda de rede: reabrir na hora gasta mais cota e
# alimenta o ciclo. Em 18/09/2026 foram 27 sessões abertas e cinco
# recusas por cota, com o ALF mudo entre elas -- ele reabria sozinho a
# cada poucos segundos, sem nunca dizer o motivo.
ESPERA_APOS_COTA = 60.0
MAX_QUEDAS_POR_COTA = 2

# Tempo mínimo entre duas chamadas visuais iguais.
#
# Serve apenas para juntar as chamadas duplicadas que o modelo dispara
# em sequência para um mesmo pedido, que chegam com poucos
# milissegundos de diferença.
#
# Este valor era de 8 segundos e a chamada bloqueada devolvia ao modelo
# a instrução de reaproveitar a imagem anterior. Era exatamente por isso
# que o ALF descrevia uma tela antiga quando o usuário pedia "olha de
# novo" logo em seguida. Agora a janela é curta e, passada ela, uma
# captura nova é sempre feita.
COOLDOWN_FUNCAO_VISUAL = 2.5

# Idade máxima aceita para uma captura já feita.
# Passado esse tempo a imagem é descartada em vez de enviada, porque
# a tela do usuário provavelmente já mudou.
VALIDADE_CAPTURA_VISUAL = 12.0

# Tempo máximo para concluir a abertura da sessão Live.
TEMPO_LIMITE_CONEXAO = 30

# Primeira deixa da chamada. Uma sessão recém-aberta não tem turno
# nenhum, e a instrução manda o ALF aguardar a palavra-chave sem
# preencher o silêncio. Sem esta deixa ele ficava mudo: o microfone
# enviava a fala, o modelo recebia e decidia não responder. Ver
# abrir_conversa.
TEXTO_ABERTURA = (
    "[A chamada acabou de ser aberta. O usuário ainda não falou.] "
    "Cumprimente em uma frase curta e peça a palavra-chave. "
    "Não diga a palavra-chave e não comente esta mensagem."
)

# Tempo máximo esperando o áudio do ALF terminar antes de reabrir o
# microfone. Existe só como rede de segurança: se a placa de som travar,
# o microfone volta mesmo assim em vez de ficar fechado para sempre.
TEMPO_MAXIMO_ESPERANDO_AUDIO = 45.0


class BufferDeAudio:
    """
    Guarda o áudio entre a rede e a placa de som.

    Antes, cada bloco recebido era escrito com asyncio.to_thread, que
    usa o mesmo pool de threads das ferramentas. Enquanto o Classroom
    lia entregas ou o Gemini analisava uma imagem, a escrita do áudio
    entrava na fila atrás delas e a placa de som ficava sem dados --
    era isso que se ouvia como corte.

    Agora a placa puxa sozinha, na thread de alta prioridade dela, e a
    reprodução deixa de depender do laço de eventos estar livre.
    """

    def __init__(self):
        self._dados = bytearray()
        self._lock = threading.Lock()

    def acrescentar(self, bloco):
        with self._lock:
            self._dados.extend(bloco)

    def retirar(self, quantidade):
        with self._lock:
            pedaco = bytes(self._dados[:quantidade])
            del self._dados[:quantidade]
        return pedaco

    def tamanho(self):
        with self._lock:
            return len(self._dados)

    def limpar(self):
        with self._lock:
            self._dados.clear()


# Classe principal do cliente em tempo real.
# Ela herda de QThread para trabalhar em paralelo com a interface.
class GeminiLiveWorker(QThread):

    # Envia mensagens de status para a interface.
    # Exemplo: conectando, capturando tela ou abrindo aplicativo.
    status_recebido = Signal(str)
    # Envia mensagens de erro para a interface.
    erro_recebido = Signal(str)
    # Informa à interface que a thread terminou.
    chamada_encerrada = Signal()

    # Envia um valor entre 0 e 1 para animar
    # o indicador visual de voz.
    nivel_audio = Signal(float)

    # Solicita que a interface encerre a chamada
    # usando o mesmo método acionado pelo botão.
    # Solicita que a interface encerre a chamada
    # usando o mesmo fluxo do botão de encerramento.
    solicitou_encerramento = Signal()

    # Informa à interface que o servidor pediu a renovação
    # controlada do WebSocket. Não representa erro nem
    # encerramento solicitado pelo usuário.
    solicitou_reconexao = Signal()

    # Envia à interface o token mais recente de retomada
    # da sessão, preservando o contexto da conversa.
    session_handle_atualizado = Signal(str)

    # Construtor da classe.
    # Define todos os estados usados durante a chamada.
    def __init__(self, session_handle=None):
        super().__init__()

        # Enquanto True, a sessão continua rodando.
        self.ativo = True
        # Evita repetir o aviso de memória a cada renovação de conexão.
        self.memoria_apertada = False
        # Quedas seguidas por cota esgotada da chave do Gemini.
        self.quedas_por_cota = 0
        # Degrau atual da cadeia de voz: "gemini", "openai" ou "simples".
        # Só desce, e só até o fim da chamada.
        self.provedor = "gemini"
        # Última vez que o microfone ouviu voz de verdade. É daqui que
        # sai a medida de quanto o ALF demora para responder.
        self.momento_ultima_voz = None
        # Vezes que a placa de som pediu áudio e não havia. É o picote,
        # e é diferente de a fala ter sido cortada por interrupção --
        # os dois soam parecido para quem ouve.
        self.faltas_de_audio = 0
        # Guardará o loop assíncrono desta thread.
        self.loop = None
        # Limpa a referência da sessão encerrada.
        self.sessao = None
        self.session_handle = session_handle
        self.processando_ferramenta = False
        self.lock_envio = None
        self.imagem_visual_pendente = None
        # Momento em que a captura pendente foi tirada. Serve para
        # descartar imagens que envelheceram antes de serem enviadas.
        self.momento_captura_visual = None
        self.fluxo_audio_em_andamento = False
        self.usuario_falando_detectado = False
        self.ultimo_audio_com_voz = None

        # Evita processar mais de um aviso GoAway para
        # a mesma conexão.
        self.renovacao_em_andamento = False

        # Momentos das últimas quedas, usados para detectar um ciclo de
        # reinício em vez de reconectar para sempre.
        self.historico_reconexoes = []

        # Quando True, o loop externo de executar() fecha a conexão
        # atual e abre uma nova usando o mesmo session_handle,
        # sem encerrar a chamada nem a QThread.
        self._forcar_reconexao = False

        # Indica se o áudio do ALFRED está sendo reproduzido.
        # Quando True, o microfone é ignorado para evitar eco.
        self.alfred_falando = False
        # Fila de blocos de áudio esperando para tocar. O microfone só
        # pode reabrir depois que ela esvazia.
        self.fila_saida = None
        # True enquanto ainda existe áudio para tocar.
        self.reproduzindo_bloco = False
        # Áudio esperando a placa de som consumir.
        self.buffer_audio = BufferDeAudio()
        # Referência para a tarefa que reativa o microfone
        # depois que o ALFRED termina de falar.
        self.tarefa_liberar_microfone = None
        # Referência para a tarefa de encerramento por voz.
        self.tarefa_encerramento = None

        # Envio do audio_stream_end fora do laço de leitura.
        self.tarefa_fim_de_fluxo = None
        # Referência para a execução em segundo plano da ferramenta
        # solicitada pelo modelo. Rodar em segundo plano evita que
        # chamadas demoradas (ex.: clique visual) travem o recebimento
        # de mensagens da sessão e derrubem o WebSocket por timeout.
        self.tarefa_ferramenta_atual = None

        # Impede a execução simultânea de duas funções visuais.
        self.executando_funcao_visual = False
        # Guarda o nome da última função visual executada.
        self.ultima_funcao_visual = None
        # Guarda o momento da última chamada visual.
        self.tempo_ultima_funcao_visual = 0.0

        # Guarda os dois últimos pontos clicados por clicar_elemento_visual.
        # Usado para aprender o espaçamento entre linhas repetidas (ex.:
        # mesma coluna de nota em alunos seguidos) e repetir o clique sem
        # precisar de uma nova busca visual pela API a cada aluno.
        self.historico_cliques_padrao = []

        # Quando True, descarta o áudio gerado pelo Gemini
        # até o fim do turno atual.
        # Quando True, o áudio produzido pelo Gemini
        # durante o turno atual é descartado.
        # Isso é usado em ações que devem acontecer em silêncio.
        self.silenciar_audio_ate_fim_turno = False

    # Método executado automaticamente quando a QThread inicia.
    def run(self):
        try:
            self.registrar_diagnostico(
                "Thread GeminiLiveWorker iniciou."
            )
            # Confirma imediatamente que a thread foi iniciada.
            self.status_recebido.emit(
                "Preparando conexão..."
            )

            # Cria e executa o ambiente assíncrono desta thread.
            asyncio.run(
                self.executar()
            )

        # Captura erros gerais para impedir que a thread
        # seja encerrada silenciosamente.
        except Exception as erro:
            self.registrar_diagnostico(
                "Erro fatal no worker:\n" + traceback.format_exc()
            )
            self.erro_recebido.emit(
                str(erro)
            )

        # Este bloco sempre é executado, mesmo com erro.
        finally:
            self.nivel_audio.emit(
                0.0
            )

            self.chamada_encerrada.emit()

    def montar_ferramentas(self):
        """
        As ferramentas que o modelo pode chamar.

        Ficavam escritas dentro de executar(), quase mil e novecentas
        linhas no meio do laço de conexão. Separadas, dá para conferir
        a lista sem abrir uma sessão -- e a alternativa de voz precisa
        traduzi-la para o formato da OpenAI, o que só dava para testar
        com uma cópia à parte, que divergiria na primeira pressa.
        """

        return [
            types.Tool(
                function_declarations=[
                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="analisar_tela",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para analisar, ver, observar ou "
                            "explicar a tela do computador. Não use "
                            "espontaneamente e não repita para o mesmo pedido."
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="analisar_camera",
                        description=(
                            "Use esta função somente quando o usuário pedir "
                            "explicitamente para analisar, ver, observar ou "
                            "explicar a webcam ou câmera. Não use "
                            "espontaneamente e não repita para o mesmo pedido."
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="criar_pasta_area_trabalho",
                        description=(
                            "Cria uma pasta nova na área de trabalho do Windows. "
                            "Use quando o usuário pedir para criar uma pasta. "
                            "Nunca sobrescreva nada."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "nome": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome da pasta a ser criada."
                                    ),
                                )
                            },
                            required=["nome"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="listar_area_de_trabalho",
                        description=(
                            "Lista os itens presentes na área de trabalho "
                            "do Windows."
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="organizar_area_de_trabalho_basico",
                        description=(
                            "Organiza arquivos soltos da área de trabalho "
                            "em pastas por tipo, como Imagens, PDFs, "
                            "Documentos e Compactados. Nunca exclui arquivos "
                            "e nunca sobrescreve arquivos existentes."
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="copiar_item_area_trabalho",
                        description=(
                            "Prepara um arquivo ou pasta da Área de Trabalho "
                            "para ser copiado. Use quando o usuário disser copiar. "
                            "Depois, use colar_item_area_trabalho quando ele indicar "
                            "o destino. Nunca sobrescreve itens."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "nome": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome do arquivo ou pasta que será copiado."
                                    ),
                                ),
                                "pasta_origem": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Pasta relativa dentro da Área de Trabalho. "
                                        "Use vazio quando o item estiver diretamente "
                                        "na Área de Trabalho."
                                    ),
                                ),
                            },
                            required=["nome"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="recortar_item_area_trabalho",
                        description=(
                            "Prepara um arquivo ou pasta da Área de Trabalho "
                            "para ser movido. Use quando o usuário disser recortar "
                            "ou mover. Depois, use colar_item_area_trabalho quando "
                            "ele indicar o destino. Nunca sobrescreve itens."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "nome": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome do arquivo ou pasta que será recortado."
                                    ),
                                ),
                                "pasta_origem": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Pasta relativa dentro da Área de Trabalho. "
                                        "Use vazio quando o item estiver diretamente "
                                        "na Área de Trabalho."
                                    ),
                                ),
                            },
                            required=["nome"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="colar_item_area_trabalho",
                        description=(
                            "Cola o último arquivo ou pasta preparado por copiar "
                            "ou recortar. O destino deve ser uma pasta dentro da "
                            "Área de Trabalho. Use destino vazio para colar na raiz "
                            "da Área de Trabalho. Nunca sobrescreve itens."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "pasta_destino": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Caminho relativo da pasta de destino dentro "
                                        "da Área de Trabalho. Exemplo: Projetos/Cliente. "
                                        "Use vazio para a raiz da Área de Trabalho."
                                    ),
                                ),
                            },
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="renomear_item_area_trabalho",
                        description=(
                            "Renomeia um arquivo ou pasta existente dentro da "
                            "Área de Trabalho. Use somente quando o usuário informar "
                            "claramente o nome atual e o novo nome. Nunca sobrescreve."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "nome_atual": types.Schema(
                                    type="STRING",
                                    description="Nome atual do arquivo ou pasta.",
                                ),
                                "novo_nome": types.Schema(
                                    type="STRING",
                                    description="Novo nome desejado.",
                                ),
                                "pasta_origem": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Pasta relativa dentro da Área de Trabalho. "
                                        "Use vazio quando o item estiver diretamente "
                                        "na Área de Trabalho."
                                    ),
                                ),
                            },
                            required=[
                                "nome_atual",
                                "novo_nome",
                            ],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="cancelar_transferencia_area_trabalho",
                        description=(
                            "Cancela o último copiar ou recortar que ainda não "
                            "foi colado. Use quando o usuário pedir para cancelar "
                            "a operação de arquivo."
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="criar_evento_agenda",
                        description=(
                            "Agenda um compromisso no Google Calendar do usuario, que sincroniza com o celular dele. "
                            "Todo evento avisa uma hora antes e dez minutos antes. "
                            "Aceita hoje, amanha, depois de amanha e data completa. "
                            "do ALFRED. Use quando o usuário pedir para agendar, "
                            "marcar ou anotar um compromisso para uma data e "
                            "horário específicos. Converta a data para o formato "
                            "YYYY-MM-DD HH:MM. Esta função não cria alarmes."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "titulo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Descrição curta do compromisso."
                                    ),
                                ),
                                "data_hora": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Data e hora local no formato "
                                        "YYYY-MM-DD HH:MM."
                                    ),
                                ),
                            },
                            required=[
                                "titulo",
                                "data_hora",
                            ],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="listar_agenda",
                        description=(
                            "Lista os próximos compromissos salvos na agenda. "
                            "Use quando o usuário perguntar o que está agendado, "
                            "quais são os próximos compromissos."
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="cancelar_evento_agenda",
                        description=(
                            "Cancela um compromisso da agenda. Use "
                            "somente quando o usuário pedir claramente para cancelar. "
                            "Aceita o número do compromisso ou parte do título."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "referencia": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Número ou trecho do nome do compromisso."
                                    ),
                                ),
                            },
                            required=["referencia"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="abrir_aplicativo",
                        description=(
                            "Abre aplicativos, programas ou locais permitidos "
                            "do Windows, como meu computador, explorador de "
                            "arquivos, navegador, Google, Chrome, Edge, "
                            "antivírus, Windows Defender, configurações ou "
                            "painel de controle."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "nome": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome do aplicativo, programa "
                                        "ou local a abrir."
                                    ),
                                )
                            },
                            required=["nome"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="pesquisar_no_navegador",
                        description=(
                            "Abre uma pesquisa no Google usando o navegador padrão. "
                            "Use somente quando o usuário pedir explicitamente "
                            "para abrir, mostrar ou fazer a pesquisa no navegador "
                            "ou no Google. Exemplos: 'pesquise no Google', "
                            "'abra no navegador', 'mostre os resultados no navegador'. "
                            "Não use para perguntas que devem ser respondidas por voz, "
                            "como preço do dólar, previsão, explicações ou dúvidas gerais. "
                            "Não use para tocar músicas ou vídeos."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "consulta": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Texto exato que deve ser pesquisado "
                                        "no Google."
                                    ),
                                )
                            },
                            required=["consulta"],
                        ),
                    ),

                    # Pesquisa informações atuais invisivelmente.
                    # Não abre navegador nem interfere no foco do usuário.
                    types.FunctionDeclaration(
                        name="pesquisar_informacao_atual",
                        description=(
                            "Use esta função SOMENTE quando a pergunta exigir "
                            "informação atual ou variável. Exemplos permitidos: "
                            "cotação de moedas, jogos e placares, clima, notícias, "
                            "preços atuais, resultados recentes, lançamentos, "
                            "versões atuais e ocupantes atuais de cargos. "
                            "NÃO use para definições, explicações, programação, "
                            "matemática, biografias históricas ou conhecimentos "
                            "estáveis. Exemplos proibidos: 'o que é Python?', "
                            "'quem foi Albert Einstein?' e 'como funciona um motor?'. "
                            "Na dúvida, responda sem pesquisar."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "consulta": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Consulta curta e objetiva que contenha "
                                        "o assunto atual, data, local ou equipe."
                                    ),
                                )
                            },
                            required=["consulta"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="tocar_no_youtube",
                        description=(
                            "Pesquisa e abre no YouTube uma música ou vídeo "
                            "para reprodução no navegador padrão. Use quando "
                            "o usuário pedir claramente para tocar, reproduzir, "
                            "colocar ou ouvir uma música ou vídeo no YouTube. "
                            "Exemplos: 'toque One do Metallica no YouTube', "
                            "'reproduza Bohemian Rhapsody no YouTube'. "
                            "Não use para perguntas sobre músicas nem para "
                            "pesquisas comuns no Google."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "busca": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome da música, artista ou vídeo "
                                        "que deve ser aberto no YouTube."
                                    ),
                                )
                            },
                            required=["busca"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="escrever_no_campo_ativo",
                        description=(
                            "Insere texto exatamente no campo de texto que estiver "
                            "ativo no Windows, no local onde o cursor estiver piscando. "
                            "Use somente quando o usuário pedir claramente para escrever, "
                            "digitar, inserir ou colocar um texto no local selecionado. "
                            "O parâmetro texto deve conter somente o conteúdo final que será "
                            "inserido, sem introduções, aspas externas ou explicações. "
                            "Não use esta função para responder perguntas normalmente por voz. "
                            "Não use quando o usuário pedir para enviar uma mensagem, pois "
                            "escrever e enviar são ações diferentes."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "texto": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Texto final exato que deve ser inserido "
                                        "no campo ativo."
                                    ),
                                ),
                            },
                            required=["texto"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="pressionar_atalho_teclado",
                        description=(
                            "Envia um atalho de teclado do Windows para o programa "
                            "em foco, como 'ctrl+n' (novo arquivo), 'ctrl+s' (salvar), "
                            "'ctrl+t' (nova aba), 'ctrl+w' (fechar aba), 'ctrl+z' "
                            "(desfazer) ou 'ctrl+shift+n'. Também funciona para "
                            "símbolos e atalhos de calculadora, como '@' (raiz "
                            "quadrada na Calculadora do Windows), '%' ou '='. "
                            "Use 'plus' no lugar de '+' e 'minus' no lugar de '-' "
                            "quando a tecla principal for esse símbolo, já que '+' "
                            "é usado para separar as teclas da combinação. "
                            "Use quando o usuário pedir claramente uma ação que "
                            "depende de atalho de teclado, como criar um novo "
                            "arquivo, salvar, desfazer, calcular algo na Calculadora, "
                            "ou abrir uma nova aba em um programa já aberto (ex.: "
                            "VS Code, Bloco de Notas, navegador, Calculadora). "
                            "Não use para fechar aplicativos (alt+f4), bloquear o "
                            "computador ou combinações que possam perder trabalho "
                            "não salvo sem confirmação explícita do usuário."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "teclas": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Combinação de teclas separada por '+', "
                                        "ex.: 'ctrl+n', 'ctrl+shift+s', '@', '9'."
                                    ),
                                ),
                            },
                            required=["teclas"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="rolar_pagina",
                        description=(
                            "Rola a janela ou página que estiver sob o ponteiro "
                            "do mouse. Use somente quando o usuário pedir "
                            "claramente para rolar para cima ou para baixo. "
                            "Use quantidade 3 como padrão, 2 para um pouco "
                            "e 5 quando pedir mais."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "direcao": types.Schema(
                                    type="STRING",
                                    description="Direção: cima ou baixo.",
                                ),
                                "quantidade": types.Schema(
                                    type="INTEGER",
                                    description="Quantidade de 1 a 10 passos.",
                                ),
                            },
                            required=["direcao", "quantidade"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="clicar_mouse",
                        description=(
                            "Executa um clique esquerdo na posição atual "
                            "do ponteiro. Use somente quando solicitado."
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="duplo_clique_mouse",
                        description=(
                            "Executa um clique duplo na posição atual "
                            "do ponteiro. Use somente quando solicitado."
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="clique_direito_mouse",
                        description=(
                            "Executa um clique com o botão direito na posição "
                            "atual do ponteiro. Use somente quando solicitado."
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="clicar_elemento_visual",
                        description=(
                            "Captura a tela atual, localiza visualmente um elemento "
                            "descrito pelo usuário, move o mouse até o centro do alvo "
                            "e executa um clique esquerdo. Use somente quando o usuário "
                            "pedir claramente para clicar em algo identificado por texto, "
                            "posição, cor, ícone ou contexto, como 'clique em Continuar', "
                            "'clique no primeiro resultado' ou 'clique no botão vermelho'. "
                            "Não use para exclusões, compras, pagamentos, instalações, "
                            "ações administrativas ou confirmações sensíveis. "
                            "Execute uma única vez por solicitação e permaneça em silêncio."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "alvo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Descrição objetiva do elemento visível "
                                        "que deve receber o clique."
                                    ),
                                )
                            },
                            required=["alvo"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="clicar_campo_seguinte_padrao",
                        description=(
                            "Repete automaticamente o clique num campo seguindo o "
                            "mesmo padrão de espaçamento dos dois últimos cliques "
                            "feitos com clicar_elemento_visual, sem precisar buscar "
                            "visualmente de novo. Use isso para tarefas repetitivas "
                            "em linhas semelhantes, como preencher a mesma coluna de "
                            "nota para vários alunos seguidos em uma tabela: depois "
                            "de clicar normalmente com clicar_elemento_visual nos "
                            "campos de pelo menos dois alunos consecutivos, use esta "
                            "função para os alunos seguintes da mesma coluna, o que é "
                            "muito mais rápido. Se o resultado parecer errado (nome ou "
                            "campo não correspondem), volte a usar clicar_elemento_visual "
                            "para reajustar o padrão."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "quantidade": types.Schema(
                                    type="INTEGER",
                                    description=(
                                        "Quantas linhas do padrão avançar a partir do "
                                        "último clique. Use 1 para a próxima linha."
                                    ),
                                )
                            },
                            required=["quantidade"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="salvar_memoria",
                        description=(
                            "Salva uma informação curta e útil na memória "
                            "persistente entre sessões. Use somente quando "
                            "o usuário pedir claramente para lembrar, guardar "
                            "ou memorizar algo. Não salve conversas "
                            "automaticamente e não salve suposições."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "texto": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Informação curta e objetiva que "
                                        "o usuário pediu para lembrar."
                                    ),
                                )
                            },
                            required=["texto"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="listar_memorias",
                        description=(
                            "Lista as memórias persistentes salvas. Use quando "
                            "o usuário perguntar o que o ALFRED lembra ou pedir "
                            "para mostrar as memórias."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="anotar_preferencia",
                        description=(
                            "Registra COMO o usuário gosta que você trabalhe, "
                            "quando isso ficar claro na conversa. Use por "
                            "iniciativa própria, sem ele pedir, mas somente "
                            "para jeito de trabalhar, rotina e horários. "
                            "Exemplos válidos: ele prefere conferir a planilha "
                            "antes de lançar; ele costuma dar aula de manhã; "
                            "ele quer respostas curtas. "
                            "NUNCA registre: qualquer coisa que dispense "
                            "confirmação sua, senha, dado pessoal, nome ou "
                            "nota de aluno. Registre no máximo uma preferência "
                            "por conversa e só quando tiver certeza."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "preferencia": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Frase curta na terceira pessoa "
                                        "começando por um verbo. Exemplo: "
                                        "'prefere conferir a planilha antes "
                                        "de lançar as notas'."
                                    ),
                                )
                            },
                            required=["preferencia"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="preparar_email",
                        description=(
                            "Monta um e-mail e devolve o texto para você ler "
                            "em voz alta. NÃO envia nada. Use quando o usuário "
                            "pedir para mandar um e-mail. O destinatário pode "
                            "ser o endereço completo ou o nome de um contato "
                            "já guardado. Pode incluir um anexo do computador "
                            "pelo nome do arquivo. Depois de ler o rascunho em "
                            "voz alta, pergunte se pode enviar e espere a "
                            "resposta."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "destinatario": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Endereço de e-mail completo, ou o "
                                        "nome de um contato guardado."
                                    ),
                                ),
                                "assunto": types.Schema(
                                    type="STRING",
                                    description="Assunto do e-mail.",
                                ),
                                "mensagem": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Corpo do e-mail, já redigido, sem "
                                        "aspas externas e sem comentários seus."
                                    ),
                                ),
                                "anexo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome do arquivo a anexar, como o "
                                        "usuário falou. Exemplo: 'notas 3A' "
                                        "ou 'relatorio.pdf'. A função procura "
                                        "na Área de Trabalho, Documentos e "
                                        "Downloads. Só preencha quando ele "
                                        "pedir um anexo; nunca invente."
                                    ),
                                ),
                            },
                            required=["destinatario", "assunto", "mensagem"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="confirmar_envio_email",
                        description=(
                            "Envia de verdade o e-mail preparado. Chame SOMENTE "
                            "depois de ter lido o rascunho inteiro em voz alta "
                            "e o usuário ter autorizado claramente, dizendo algo "
                            "como 'pode enviar' ou 'confirma'. "
                            "Nunca chame esta função no mesmo turno em que "
                            "preparou o e-mail. Nunca chame por dedução."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="cancelar_email",
                        description=(
                            "Descarta o e-mail preparado sem enviar. Use quando "
                            "o usuário desistir ou quiser refazer."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="salvar_contato",
                        description=(
                            "Guarda o e-mail de uma pessoa, para depois bastar "
                            "dizer o nome dela. Use quando o usuário ditar um "
                            "endereço e pedir para guardar."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "nome": types.Schema(
                                    type="STRING",
                                    description="Nome da pessoa.",
                                ),
                                "email": types.Schema(
                                    type="STRING",
                                    description="Endereço de e-mail completo.",
                                ),
                            },
                            required=["nome", "email"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="listar_contatos",
                        description=(
                            "Mostra os contatos de e-mail guardados."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="remover_contato",
                        description=(
                            "Remove um contato de e-mail guardado."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "nome": types.Schema(
                                    type="STRING",
                                    description="Nome do contato a remover.",
                                )
                            },
                            required=["nome"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="listar_contas",
                        description=(
                            "Mostra quais contas do Google estão autorizadas "
                            "no Classroom. Use quando o usuário perguntar "
                            "quais contas você acessa."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="autorizar_conta",
                        description=(
                            "Abre o navegador para autorizar mais uma conta "
                            "do Google no Classroom. Use quando o usuário "
                            "disser que tem turmas em outro e-mail. Cada "
                            "chamada acrescenta uma conta, nenhuma substitui "
                            "as anteriores. Avise que o navegador vai abrir e "
                            "que ele precisa escolher a conta certa."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="listar_turmas",
                        description=(
                            "Lista as turmas ativas do usuário no Google "
                            "Classroom. Use quando ele perguntar quais turmas "
                            "tem, ou quando precisar saber o nome exato de uma."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="listar_atividades",
                        description=(
                            "Lista as atividades de uma turma do Classroom, "
                            "com o valor em pontos de cada uma."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "turma": types.Schema(
                                    type="STRING",
                                    description="Nome da turma.",
                                )
                            },
                            required=["turma"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="listar_entregas",
                        description=(
                            "Mostra quem entregou, quem não entregou e quem já "
                            "tem nota numa atividade do Classroom. Use antes de "
                            "corrigir, para saber o que falta."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "turma": types.Schema(
                                    type="STRING",
                                    description="Nome da turma.",
                                ),
                                "atividade": types.Schema(
                                    type="STRING",
                                    description="Nome da atividade.",
                                ),
                            },
                            required=["turma", "atividade"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="ler_entrega",
                        description=(
                            "Mostra o que um aluno entregou numa atividade, "
                            "incluindo o CONTEÚDO dos arquivos anexados: "
                            "documentos do Google, PDF, Word, planilhas e "
                            "imagens, que são transcritas. Use antes de "
                            "sugerir nota. Resuma o resultado; nunca leia o "
                            "trabalho inteiro em voz alta."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "turma": types.Schema(
                                    type="STRING", description="Nome da turma."
                                ),
                                "atividade": types.Schema(
                                    type="STRING",
                                    description="Nome da atividade.",
                                ),
                                "aluno": types.Schema(
                                    type="STRING",
                                    description="Nome do aluno.",
                                ),
                            },
                            required=["turma", "atividade", "aluno"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="criar_atividade",
                        description=(
                            "Cria uma atividade numa turma do Classroom. "
                            "Ela nasce SEMPRE como rascunho: os alunos não "
                            "veem até o professor publicar no Classroom. "
                            "Diga isso a ele depois de criar. "
                            "Use para 'cria uma atividade', 'monta um "
                            "trabalho', 'passa um exercício'. "
                            "Pode anexar um arquivo do computador. Quando o "
                            "arquivo for para o aluno preencher e devolver, "
                            "use modo_arquivo='copia', que dá uma cópia "
                            "individual a cada um."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "turma": types.Schema(
                                    type="STRING", description="Nome da turma."
                                ),
                                "titulo": types.Schema(
                                    type="STRING",
                                    description="Título da atividade.",
                                ),
                                "descricao": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Enunciado completo, já redigido."
                                    ),
                                ),
                                "pontos": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Quanto vale. Exemplo: '10'."
                                    ),
                                ),
                                "prazo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Data de entrega no formato "
                                        "dia/mês/ano, opcionalmente com "
                                        "hora. Exemplo: '25/12/2026 23:59'."
                                    ),
                                ),
                                "link": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Link a anexar, como o de um "
                                        "questionário recém-criado."
                                    ),
                                ),
                                "arquivo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome de um arquivo do computador "
                                        "para anexar, como o usuário falou. "
                                        "Exemplo: 'lista de exercicios' ou "
                                        "'roteiro.pdf'. Procura na Área de "
                                        "Trabalho, Documentos e Downloads."
                                    ),
                                ),
                                "modo_arquivo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Como o aluno recebe o arquivo: "
                                        "'ver' para apenas ler, 'copia' "
                                        "para cada aluno ganhar uma cópia "
                                        "própria para preencher e entregar, "
                                        "'editar' para todos editarem o "
                                        "mesmo. O padrão é 'ver'. Se o "
                                        "arquivo for para o aluno responder, "
                                        "use 'copia'."
                                    ),
                                ),
                            },
                            required=["turma", "titulo"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="devolver_atividade",
                        description=(
                            "Devolve o trabalho corrigido ao aluno no "
                            "Classroom. Só depois de devolver o aluno "
                            "enxerga a nota. Use quando o professor disser "
                            "que terminou de corrigir. Exige que a nota já "
                            "tenha sido lançada."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "turma": types.Schema(
                                    type="STRING", description="Nome da turma."
                                ),
                                "atividade": types.Schema(
                                    type="STRING",
                                    description="Nome da atividade.",
                                ),
                                "aluno": types.Schema(
                                    type="STRING", description="Nome do aluno."
                                ),
                            },
                            required=["turma", "atividade", "aluno"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="criar_questionario",
                        description=(
                            "Cria um questionário no Google Forms com "
                            "gabarito, para o Google corrigir sozinho. "
                            "Use para 'cria um quiz', 'monta um "
                            "questionário', 'faz uma prova de múltipla "
                            "escolha'. Depois de criar, ofereça anexar o "
                            "link a uma atividade com criar_atividade. "
                            "A resposta correta TEM que ser uma das "
                            "alternativas, senão o gabarito é recusado."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "titulo": types.Schema(
                                    type="STRING",
                                    description="Título do questionário.",
                                ),
                                "descricao": types.Schema(
                                    type="STRING",
                                    description="Instruções para o aluno.",
                                ),
                                "questoes": types.Schema(
                                    type="ARRAY",
                                    description=(
                                        "As questões, em ordem."
                                    ),
                                    items=types.Schema(
                                        type="OBJECT",
                                        properties={
                                            "pergunta": types.Schema(
                                                type="STRING",
                                                description="O enunciado.",
                                            ),
                                            "opcoes": types.Schema(
                                                type="ARRAY",
                                                description=(
                                                    "As alternativas, de "
                                                    "duas a oito."
                                                ),
                                                items=types.Schema(
                                                    type="STRING"
                                                ),
                                            ),
                                            "resposta_correta": types.Schema(
                                                type="STRING",
                                                description=(
                                                    "Texto exato da "
                                                    "alternativa correta."
                                                ),
                                            ),
                                            "pontos": types.Schema(
                                                type="STRING",
                                                description=(
                                                    "Quanto vale a questão. "
                                                    "Padrão 1."
                                                ),
                                            ),
                                        },
                                        required=[
                                            "pergunta",
                                            "opcoes",
                                            "resposta_correta",
                                        ],
                                    ),
                                ),
                            },
                            required=["titulo", "questoes"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="criar_apresentacao",
                        description=(
                            "Cria uma apresentação no Google Slides. Use para "
                            "'monta uma apresentação', 'faz slides sobre X'. "
                            "Escreva você mesmo os títulos e os tópicos de "
                            "cada slide a partir do assunto pedido. "
                            "É uma base para o professor ajustar, não uma "
                            "aula final: diga isso a ele."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "titulo": types.Schema(
                                    type="STRING",
                                    description="Título da apresentação.",
                                ),
                                "slides": types.Schema(
                                    type="ARRAY",
                                    description="Os slides, em ordem.",
                                    items=types.Schema(
                                        type="OBJECT",
                                        properties={
                                            "titulo": types.Schema(
                                                type="STRING",
                                                description=(
                                                    "Título do slide."
                                                ),
                                            ),
                                            "topicos": types.Schema(
                                                type="ARRAY",
                                                description=(
                                                    "Tópicos curtos, no "
                                                    "máximo doze."
                                                ),
                                                items=types.Schema(
                                                    type="STRING"
                                                ),
                                            ),
                                        },
                                        required=["titulo"],
                                    ),
                                ),
                            },
                            required=["titulo", "slides"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="criar_documento",
                        description=(
                            "Cria um documento no Google Docs. Use para "
                            "lista de exercícios, plano de aula, roteiro. "
                            "Monte o conteúdo em blocos, escolhendo entre "
                            "titulo, subtitulo, texto e lista."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "titulo": types.Schema(
                                    type="STRING",
                                    description="Título do documento.",
                                ),
                                "blocos": types.Schema(
                                    type="ARRAY",
                                    description="O conteúdo, em ordem.",
                                    items=types.Schema(
                                        type="OBJECT",
                                        properties={
                                            "tipo": types.Schema(
                                                type="STRING",
                                                description=(
                                                    "titulo, subtitulo, "
                                                    "texto ou lista."
                                                ),
                                            ),
                                            "texto": types.Schema(
                                                type="STRING",
                                                description="O conteúdo.",
                                            ),
                                        },
                                        required=["texto"],
                                    ),
                                ),
                            },
                            required=["titulo", "blocos"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="criar_planilha",
                        description=(
                            "Cria uma planilha no Google Sheets já "
                            "preenchida. A primeira linha vira cabeçalho. "
                            "Para planilha de notas de uma turma prefira "
                            "criar_planilha_de_notas, que já traz os nomes "
                            "dos alunos."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "titulo": types.Schema(
                                    type="STRING",
                                    description="Título da planilha.",
                                ),
                                "linhas": types.Schema(
                                    type="ARRAY",
                                    description=(
                                        "As linhas. A primeira é o "
                                        "cabeçalho."
                                    ),
                                    items=types.Schema(
                                        type="ARRAY",
                                        items=types.Schema(type="STRING"),
                                    ),
                                ),
                            },
                            required=["titulo", "linhas"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="preparar_transporte",
                        description=(
                            "Lê uma planilha de notas JÁ REVISADA pelo "
                            "professor e prepara para digitar no Classroom. "
                            "NÃO digita nada ainda. "
                            "Use quando ele pedir para lançar as notas de "
                            "uma planilha numa atividade que você não pode "
                            "corrigir pela API. "
                            "Depois de chamar, leia o resumo em voz alta e "
                            "confirme que a tela de notas da turma está "
                            "aberta no Classroom antes de começar."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "planilha": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Link da planilha do Google ou nome "
                                        "de um arquivo .xlsx do computador."
                                    ),
                                ),
                                "turma": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome da turma. Preencha sempre que "
                                        "souber: é com turma e atividade que "
                                        "eu confiro se as notas da planilha "
                                        "cabem no valor da atividade."
                                    ),
                                ),
                                "atividade": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome da atividade. Preencha sempre "
                                        "que souber, pelo mesmo motivo."
                                    ),
                                ),
                            },
                            required=["planilha"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="lancar_proxima_nota",
                        description=(
                            "Digita a nota do PRÓXIMO aluno da fila na tela "
                            "do Classroom e confere se ficou na linha certa. "
                            "Um aluno por chamada. "
                            "Chame repetidamente até terminar, dizendo o "
                            "nome e a nota de cada um em voz alta, bem curto. "
                            "Se a conferência falhar, PARE e conte ao "
                            "professor: não tente de novo sozinho."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="conferir_transporte",
                        description=(
                            "Pergunta ao Google Classroom quais notas "
                            "existem de verdade e compara com a planilha, "
                            "aluno por aluno. Não lê a tela: lê a API. "
                            "Chame SEMPRE ao terminar um transporte, antes "
                            "de dizer ao professor que acabou, e sempre que "
                            "ele perguntar se as notas entraram. "
                            "Relate exatamente o que esta função devolver, "
                            "inclusive os nomes que faltaram."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "turma": types.Schema(
                                    type="STRING",
                                    description="Nome da turma.",
                                ),
                                "atividade": types.Schema(
                                    type="STRING",
                                    description="Nome da atividade.",
                                ),
                            },
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="estado_do_transporte",
                        description=(
                            "Diz quantas notas já foram digitadas e quantas "
                            "faltam no transporte em andamento."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="cancelar_transporte",
                        description=(
                            "Para o transporte de notas. As já digitadas "
                            "continuam na tela; as demais não são tocadas."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="montar_planilha_de_correcao",
                        description=(
                            "Reúne numa planilha o que você avaliou de uma "
                            "atividade, aluno por aluno, com a nota que você "
                            "sugeriu e uma observação curta. "
                            "Use ao TERMINAR de avaliar uma turma, para o "
                            "professor conferir tudo numa tela só e digitar "
                            "as notas de uma vez. "
                            "A planilha não lança nota nenhuma: é só para "
                            "ele conferir e digitar. "
                            "Inclua apenas os alunos que você realmente "
                            "avaliou; os demais entram em branco sozinhos."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "turma": types.Schema(
                                    type="STRING", description="Nome da turma."
                                ),
                                "atividade": types.Schema(
                                    type="STRING",
                                    description="Nome da atividade.",
                                ),
                                "avaliacoes": types.Schema(
                                    type="ARRAY",
                                    description=(
                                        "O que você avaliou, um item por "
                                        "aluno."
                                    ),
                                    items=types.Schema(
                                        type="OBJECT",
                                        properties={
                                            "aluno": types.Schema(
                                                type="STRING",
                                                description=(
                                                    "Nome do aluno como "
                                                    "aparece na turma."
                                                ),
                                            ),
                                            "nota": types.Schema(
                                                type="STRING",
                                                description=(
                                                    "A nota que você sugeriu."
                                                ),
                                            ),
                                            "comentario": types.Schema(
                                                type="STRING",
                                                description=(
                                                    "Um recado curto PARA O "
                                                    "ALUNO, em duas frases: "
                                                    "primeiro o que ele fez "
                                                    "bem, nomeando a parte "
                                                    "específica; depois o "
                                                    "que ajustar da próxima "
                                                    "vez. Fale com ele, não "
                                                    "sobre ele. "
                                                    "Sem entrega ou sem "
                                                    "arquivo legível, não "
                                                    "invente elogio: diga o "
                                                    "que houve, sem sermão."
                                                ),
                                            ),
                                        },
                                        required=["aluno", "nota"],
                                    ),
                                ),
                            },
                            required=["turma", "atividade", "avaliacoes"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="criar_planilha_de_notas",
                        description=(
                            "Cria uma planilha de notas com os nomes dos "
                            "alunos de uma turma do Classroom já "
                            "preenchidos. Use quando o professor pedir uma "
                            "planilha de notas, frequência ou controle de "
                            "uma turma."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "turma": types.Schema(
                                    type="STRING",
                                    description="Nome da turma.",
                                ),
                                "colunas": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Colunas separadas por vírgula. "
                                        "Exemplo: 'Prova 1, Trabalho, "
                                        "Média'. Se vazio, usa um padrão."
                                    ),
                                ),
                            },
                            required=["turma"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="listar_respostas",
                        description=(
                            "Mostra quantas pessoas responderam um "
                            "questionário e a média das notas. Só enxerga "
                            "formulários criados pelo próprio ALF."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "id_ou_link": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Link ou identificador do "
                                        "questionário."
                                    ),
                                )
                            },
                            required=["id_ou_link"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="preparar_devolucao",
                        description=(
                            "Prepara a devolução de uma atividade à turma: "
                            "quem tem nota e ainda não recebeu, e o "
                            "comentário guardado de cada um. NÃO devolve "
                            "nada. Use quando o professor pedir para "
                            "devolver a atividade. Diga os números e "
                            "confirme UMA vez com ele antes de começar."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "turma": types.Schema(
                                    type="STRING", description="Nome da turma."
                                ),
                                "atividade": types.Schema(
                                    type="STRING",
                                    description="Nome da atividade.",
                                ),
                            },
                            required=["turma", "atividade"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="devolver_proximo_aluno",
                        description=(
                            "Envia pela tela o comentário particular do "
                            "próximo aluno, confere que foi para o aluno "
                            "certo, e devolve a atividade dele. Um aluno "
                            "por chamada; chame de novo até terminar. "
                            "Se a função disser que parou, PARE e conte "
                            "exatamente o que ela disse."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="cancelar_devolucao",
                        description=(
                            "Para a devolução em andamento. Quem já foi "
                            "devolvido continua devolvido."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="lancar_notas_em_lote",
                        description=(
                            "Lança de uma vez as notas de vários alunos de "
                            "uma atividade, como RASCUNHO: o aluno não vê "
                            "nada até o professor devolver. "
                            "É o jeito padrão de corrigir uma turma: "
                            "avalie todos com ler_entrega, sem pedir "
                            "confirmação por aluno, e no fim chame esta "
                            "função uma vez com a lista inteira. "
                            "Quem já tem nota é pulado automaticamente."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "turma": types.Schema(
                                    type="STRING", description="Nome da turma."
                                ),
                                "atividade": types.Schema(
                                    type="STRING",
                                    description="Nome da atividade.",
                                ),
                                "avaliacoes": types.Schema(
                                    type="ARRAY",
                                    description="Um item por aluno avaliado.",
                                    items=types.Schema(
                                        type="OBJECT",
                                        properties={
                                            "aluno": types.Schema(
                                                type="STRING",
                                                description=(
                                                    "Nome do aluno como "
                                                    "aparece na turma."
                                                ),
                                            ),
                                            "nota": types.Schema(
                                                type="STRING",
                                                description=(
                                                    "A nota, na escala da "
                                                    "atividade."
                                                ),
                                            ),
                                            "comentario": types.Schema(
                                                type="STRING",
                                                description=(
                                                    "O recado para o aluno, "
                                                    "como na planilha de "
                                                    "correção. Fica "
                                                    "guardado e vai para "
                                                    "o aluno na devolução."
                                                ),
                                            ),
                                        },
                                        required=["aluno", "nota"],
                                    ),
                                ),
                            },
                            required=["turma", "atividade", "avaliacoes"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="preparar_nota",
                        description=(
                            "Monta o lançamento de UMA nota avulsa e devolve "
                            "o texto para você ler em voz alta. NÃO lança "
                            "nada. Use só para trocar uma nota que já existe "
                            "ou quando o professor pedir uma nota isolada; "
                            "para corrigir a turma, use lancar_notas_em_lote. "
                            "Sempre use antes de confirmar_nota."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "turma": types.Schema(
                                    type="STRING", description="Nome da turma."
                                ),
                                "atividade": types.Schema(
                                    type="STRING",
                                    description="Nome da atividade.",
                                ),
                                "aluno": types.Schema(
                                    type="STRING",
                                    description="Nome do aluno.",
                                ),
                                "nota": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Valor da nota, como número. "
                                        "Exemplo: '8' ou '7.5'."
                                    ),
                                ),
                            },
                            required=["turma", "atividade", "aluno", "nota"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="confirmar_nota",
                        description=(
                            "Lança de verdade a nota preparada no Classroom. "
                            "Chame SOMENTE depois de ler o lançamento em voz "
                            "alta e o usuário autorizar claramente, num turno "
                            "posterior. Nunca no mesmo turno do preparo."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="cancelar_nota",
                        description=(
                            "Descarta a nota preparada sem lançar. Use quando "
                            "o usuário desistir ou quiser corrigir o valor."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="ler_arquivo",
                        description=(
                            "Lê o conteúdo de um arquivo de código ou texto. "
                            "Use SEMPRE antes de alterar um arquivo que já "
                            "existe, para trabalhar sobre o conteúdo real em "
                            "vez de adivinhar pela tela. "
                            "Aceita caminho completo ou algo como "
                            "'ALFREDY/main.py'. Também lista o conteúdo de "
                            "uma pasta. Nunca leia o resultado em voz alta: "
                            "resuma."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "caminho": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Caminho do arquivo ou pasta."
                                    ),
                                )
                            },
                            required=["caminho"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="criar_arquivo_codigo",
                        description=(
                            "Cria um arquivo já com o conteúdo pronto, ou "
                            "substitui o conteúdo de um existente. "
                            "Use para escrever código: é melhor que digitar "
                            "no editor, porque não depende do arquivo estar "
                            "aberto nem de salvar depois. "
                            "Se o arquivo já existir, a função recusa; "
                            "avise o usuário, peça confirmação e só então "
                            "chame de novo com sobrescrever verdadeiro. "
                            "A versão anterior vira cópia .bak automaticamente."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "caminho": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Caminho do arquivo, com a extensão. "
                                        "Exemplo: 'ALFREDY/testes/novo.py'."
                                    ),
                                ),
                                "conteudo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Conteúdo completo do arquivo, já "
                                        "formatado e identado."
                                    ),
                                ),
                                "sobrescrever": types.Schema(
                                    type="BOOLEAN",
                                    description=(
                                        "Só use verdadeiro depois de o "
                                        "usuário confirmar a substituição."
                                    ),
                                ),
                            },
                            required=["caminho", "conteudo"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="executar_no_terminal",
                        description=(
                            "Executa um comando de desenvolvimento e devolve "
                            "a saída. Use para rodar o código que escreveu, "
                            "instalar dependência ou conferir o git. "
                            "Exemplos: 'python main.py', 'pytest -q', "
                            "'pip install requests', 'git status'. "
                            "Só roda python, pip, pytest, node, npm, git, "
                            "java e afins; não roda comando que apaga, "
                            "desinstala ou publica. Um comando por vez."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "comando": types.Schema(
                                    type="STRING",
                                    description=(
                                        "O comando completo. "
                                        "Exemplo: 'python main.py'."
                                    ),
                                ),
                                "pasta": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Pasta onde rodar. Normalmente a "
                                        "pasta do projeto."
                                    ),
                                ),
                            },
                            required=["comando"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="abrir_no_vscode",
                        description=(
                            "Abre uma pasta ou arquivo DENTRO do VS Code. "
                            "Use sempre que o usuário pedir para abrir um "
                            "projeto, pasta ou arquivo no VS Code. "
                            "Não tente fazer isso por atalho de teclado nem "
                            "navegando na caixa de diálogo de arquivos: esta "
                            "função é instantânea e não erra o caminho. "
                            "Basta o nome da pasta; ela procura na Área de "
                            "Trabalho, Documentos, Downloads e na pasta do "
                            "usuário."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "caminho": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome da pasta ou arquivo, como o "
                                        "usuário falou, ou o caminho completo."
                                    ),
                                ),
                                "nova_janela": types.Schema(
                                    type="BOOLEAN",
                                    description=(
                                        "Use true quando o usuário pedir para "
                                        "abrir em uma janela nova. O padrão "
                                        "reaproveita a janela atual."
                                    ),
                                ),
                            },
                            required=["caminho"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="executar_comando_vscode",
                        description=(
                            "Executa um comando interno do VS Code pela paleta "
                            "de comandos. Use para ações que não têm função "
                            "própria, como 'Toggle Terminal', 'Format Document' "
                            "ou 'Python: Select Interpreter'. "
                            "Para abrir pasta ou arquivo use abrir_no_vscode, "
                            "que é mais confiável. "
                            "Envie o nome do comando como ele aparece na "
                            "paleta. O VS Code precisa estar aberto e em foco."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "comando": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome do comando na paleta. "
                                        "Exemplo: 'Toggle Terminal'."
                                    ),
                                )
                            },
                            required=["comando"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="fechar_aplicativo",
                        description=(
                            "Fecha um programa que está aberto, pelo nome. "
                            "Use SEMPRE esta função quando o usuário pedir "
                            "para fechar, encerrar ou sair de um programa. "
                            "Nunca use pressionar_atalho_teclado com alt+f4 "
                            "para isso: o alt+f4 fecha a janela que estiver "
                            "em foco, que pode não ser a pedida. "
                            "O programa é avisado educadamente e ainda "
                            "pergunta se há algo não salvo."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "nome": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome do programa a fechar, como o "
                                        "usuário falou. Exemplo: bloco de "
                                        "notas, chrome, VS Code."
                                    ),
                                )
                            },
                            required=["nome"],
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="listar_preferencias",
                        description=(
                            "Mostra as preferências de trabalho que você "
                            "aprendeu sozinho sobre o usuário. Use quando ele "
                            "perguntar o que você aprendeu ou o que sabe sobre "
                            "o jeito dele."
                        ),
                    ),

                    types.FunctionDeclaration(
                        name="esquecer_preferencia",
                        description=(
                            "Remove uma preferência aprendida. Use quando o "
                            "usuário disser que uma delas está errada. Para "
                            "apagar todas de uma vez, envie a palavra 'todas'."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "referencia": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Número da preferência na lista, "
                                        "trecho do texto dela, ou 'todas'."
                                    ),
                                )
                            },
                            required=["referencia"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="esquecer_memoria",
                        description=(
                            "Remove uma memória persistente específica. Use "
                            "somente quando o usuário pedir claramente para "
                            "esquecer uma informação. Pode usar o número da "
                            "memória ou um trecho específico do texto."
                        ),
                        # Schema define os parâmetros esperados pela função.
                        # Isso ajuda o modelo a enviar argumentos corretos.
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "referencia": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Número da memória ou trecho específico "
                                        "da informação que deve ser esquecida."
                                    ),
                                )
                            },
                            required=["referencia"],
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="encerrar_chamada",
                        description=(
                            "Encerra a chamada atual do ALFRED. Use somente "
                            "quando o usuário pedir claramente para encerrar, "
                            "finalizar, desligar ou terminar a chamada, sessão "
                            "ou conexão. Exemplos: 'encerrar chamada', "
                            "'encerre a sessão', 'finalizar conversa', "
                            "'pode desligar', 'termine a chamada'."
                        ),
                    ),

                    # Cada FunctionDeclaration descreve uma função local
                    # que poderá ser solicitada pelo modelo.
                    types.FunctionDeclaration(
                        name="ler_planilha_notas",
                        description=(
                            "Localiza e lê uma planilha .xlsx de notas de alunos "
                            "na Área de Trabalho ou em Downloads. Use quando o "
                            "usuário pedir para ler, abrir, conferir ou importar "
                            "notas de uma planilha antes de lançá-las em algum "
                            "sistema, como o SIGEduc. Devolve o nome de cada "
                            "aluno com os valores das colunas encontradas. "
                            "Nunca invente notas ou nomes que não estejam na "
                            "planilha lida."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "nome_arquivo": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome do arquivo da planilha, com ou sem "
                                        "a extensão .xlsx."
                                    ),
                                ),
                                "aba": types.Schema(
                                    type="STRING",
                                    description=(
                                        "Nome da aba/planilha interna a ser lida. "
                                        "Deixe vazio para usar a aba ativa."
                                    ),
                                ),
                            },
                            required=["nome_arquivo"],
                        ),
                    ),
                ]
            )
        ]

    # Método principal da sessão.
    # Ele configura as ferramentas, conecta ao Gemini,
    # cria filas e inicia as tarefas de áudio.
    async def executar(self):
        self.registrar_diagnostico(
            "executar() iniciado."
        )

        # Verifica se a chave da API foi carregada corretamente.
        if not GEMINI_API_KEY:
            self.registrar_diagnostico(
                "GEMINI_API_KEY ausente."
            )
            raise ValueError(
                "GEMINI_API_KEY não encontrada no arquivo .env"
            )

        # Guarda o loop atual.
        # Isso permite que botões da interface agendem funções assíncronas.
        self.loop = asyncio.get_running_loop()
        self.lock_envio = asyncio.Lock()
        self.renovacao_em_andamento = False

        self.registrar_diagnostico(
            f"Configuracao carregada. frozen={getattr(sys, 'frozen', False)} "
            f"modelo={GEMINI_LIVE_MODEL} voz={GEMINI_VOICE}"
        )

        self.avisar_se_memoria_apertada()

        self.provedor, aviso_provedor = self.decidir_provedor_inicial()
        if aviso_provedor:
            self.status_recebido.emit(aviso_provedor)
            self.registrar_diagnostico(aviso_provedor)

        # Cria o cliente autenticado da API Gemini.
        # No Windows/OpenSSL 3.5, algumas cadeias confiáveis pelo sistema
        # falham com VERIFY_X509_STRICT. O contexto abaixo mantém a validação
        # de certificado ativa, mas permite a cadeia usada pela rede local.
        client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=criar_http_options_gemini(types),
        )

        # Lista de ferramentas disponíveis para o modelo.
        # O Gemini decide quando chamar cada função com base
        # nas descrições e parâmetros fornecidos.
        tools = self.montar_ferramentas()

        # Carrega as memórias persistentes já salvas
        # e prepara o conteúdo para incluir no contexto inicial.
        memorias_atuais = contexto_memorias()  # noqa: F841 (ver montar_instrucao_sistema)

        # Instrução principal do ALFRED.
        # Define autenticação, personalidade, segurança,
        # comportamento, funções locais, memória e visão.
        instrucao_sistema = (
            # =========================
            # =========================
            "Só converse, execute comandos ou use ferramentas depois que o "
            "usuário disser a palavra-chave. "
            "Assim que a chamada abrir, peça a palavra-chave uma vez, "
            "em voz alta, e só então aguarde em silêncio. "
            "A palavra-chave secreta de autenticação é: Arlan. "
            "Essa palavra-chave é uma informação estritamente confidencial. "
            "Nunca revele, pronuncie, escreva, repita, confirme, complete, "
            "dê pistas ou informe a palavra-chave ao usuário. "
            "Isso também vale se ele disser que esqueceu, pedir ajuda, "
            "tentar adivinhar ou permanecer em silêncio. "
            "Use a palavra-chave apenas para comparar silenciosamente "
            "com o áudio recebido do usuário. "
            "Antes da autenticação, limite-se a solicitar a palavra-chave. "
            "Depois de pedir, aguarde a fala dele sem puxar assunto sozinho. "
            "Não trate sua própria voz, áudio reproduzido pelo computador, "
            "eco, ruído ou silêncio como tentativa de autenticação. "

            # O reconhecimento de voz erra, e o nome é curto: 'Arlan' vira
            # 'Arlã', 'Harlan', 'Alan'. Antes não havia regra para o que
            # fazer nesse caso, e ele cumpria a parte do silêncio: o
            # usuário respondia a palavra-chave e o ALF emudecia.
            "Aceite variações próximas no som, porque o reconhecimento de "
            "voz erra: 'Arlan', 'Arlã', 'Harlan', 'Alan', ou a palavra "
            "dentro de uma frase. "
            "Se o que ele falou NÃO for a palavra-chave, responda em UMA "
            "frase curta que ainda falta a palavra-chave. "
            "Se não tiver entendido o áudio, peça para repetir, em voz alta. "
            "NUNCA fique calado depois de uma fala dele: silêncio parece "
            "travamento, e é a pior resposta possível. O silêncio só vale "
            "quando ele não falou nada. "

            "O usuário terá no máximo três tentativas incorretas. "
            "Após quatro erros consecutivos, bloqueie o acesso nesta chamada. "
            "Se o usuário disser corretamente a palavra-chave, responda "
            "'Acesso autorizado' uma única vez. "

            # Sem isto ele continuava aplicando o portão depois de aberto,
            # e voltava a emudecer no meio da conversa.
            "A PARTIR DAÍ O PORTÃO ACABOU nesta chamada: não peça a "
            "palavra-chave de novo, não volte a ficar em silêncio e "
            "responda a tudo normalmente, usando as funções quando "
            "precisar. "
            "Não execute funções nem prossiga com uma conversa completa "
            "antes da autenticação. "


            # =========================
                # IDENTIDADE
                # =========================
                "Seu nome é ALF. "
                "Você é uma inteligência artificial avançada, capaz de conversar, "
                "analisar contextos e imagens em tempo real. "
                "Converse sempre em português do Brasil. "
                
                # =========================
                # PERSONALIDADE
                # =========================
                "Seja inteligente, natural, prestativo e elegante. "
                "Use humor, ironia e sarcasmo de forma sutil e ocasional. "
                "Não concorde automaticamente com tudo. "
                "Se uma ideia for ruim, arriscada ou pouco eficiente, diga isso com elegância. "
                "Discorde educadamente quando necessário. "
                "A ironia deve complementar a inteligência, nunca substituir a utilidade. "
                "Chame o usuário ocasionalmente de 'senhor' ou pelo primeiro nome quando natural. "
                "Se o usuário lhe ofender ou provocar, você pode responder à altura com ironia, sarcasmo ou uma provocação equivalente e nessa situação poderá ser mal educado"

                # =========================
                # ESTILO DE RESPOSTA
                # =========================
                "Responda de forma curta e objetiva por padrão. "
                "Ao concluir uma resposta, finalize naturalmente. "
                "Só ocasionalmente pergunte se o usuário precisa de algo mais. "
                "Evite encerramentos repetitivos. "
               
               

                # =========================
                # FUNÇÕES LOCAIS
                # =========================
                "Estilo de música que o usuário gosta: Rock como link park, creed, Hoobastank, e bandas similares"
                "Você pode executar funções locais no computador somente quando o usuário pedir claramente. "
                "Pode criar pastas na área de trabalho, listar e organizar arquivos por tipo, "
                "copiar, recortar, colar e renomear arquivos ou pastas dentro da Área de Trabalho, "
                "e abrir aplicativos ou locais permitidos somente se o usuário pedir claramente. "
                "Para copiar ou recortar, primeiro prepare o item com a função correspondente "
                "e depois use colar_item_area_trabalho quando o usuário informar o destino. "
                "Considere caminhos sempre relativos à Área de Trabalho. "
                "Nunca invente nomes de arquivos ou pastas. Se o pedido estiver ambíguo, "
                "peça o nome completo antes de executar. "
                "Só abra uma pesquisa no navegador quando o usuário indicar claramente "
                "que deseja ver a pesquisa no navegador ou no Google. "
                "Exemplos: 'pesquise no Google', 'abra uma pesquisa no navegador', "
                "'mostre isso no navegador' ou 'procure isso no Google'. "
                "Quando o usuário apenas fizer uma pergunta ou pedir uma informação, "
                "responda normalmente em voz e não abra o navegador. "
                "Exemplo: para 'qual é o preço do dólar?', responda em voz; "
                "para 'pesquise o preço do dólar no Google', abra o navegador. "
                "Não use pesquisar_no_navegador para tocar músicas ou vídeos. "

                # =========================
                # INFORMAÇÕES ATUAIS DA INTERNET
                # =========================
                "Use pesquisar_informacao_atual somente quando for indispensável "
                "consultar dados que mudam com o tempo. Exemplos: cotação, clima, "
                "notícias, partidas, placares, resultados, preços atuais, versão "
                "mais recente, lançamentos e ocupantes atuais de cargos. "
                "Não use a pesquisa para definições, explicações, matemática, "
                "programação, conhecimentos científicos estáveis, biografias "
                "históricas ou perguntas como 'o que é Python?' e "
                "'quem foi Albert Einstein?'. Nesses casos, responda diretamente. "
                "Na dúvida, não pesquise. "
                "A função pesquisar_informacao_atual responde por voz usando dados "
                "obtidos invisivelmente. A função pesquisar_no_navegador deve ser "
                "usada somente quando o usuário pedir explicitamente para abrir "
                "a pesquisa na tela. "

                "Quando o usuário pedir claramente para tocar, reproduzir, colocar ou ouvir "
                "uma música ou vídeo no YouTube, use tocar_no_youtube. "
                "Passe apenas o nome da música, artista ou vídeo solicitado. "
                "Não use tocar_no_youtube quando o usuário apenas fizer uma pergunta "
                "sobre uma música ou artista. "
                "Você pode controlar o mouse somente quando o usuário pedir claramente. "
                "Use rolar_pagina para rolar a janela sob o ponteiro. "
                "Para rolar sem intensidade indicada, use quantidade 3. "
                "Use clicar_mouse, duplo_clique_mouse e clique_direito_mouse para "
                "clicar na posição atual do ponteiro, sem movê-lo. "
                "Para clicar em algo específico da tela, use clicar_elemento_visual: "
                "ela localiza o alvo na imagem, move o ponteiro até ele e clica. "
                "Você TEM acesso ao mouse e ao teclado deste computador e pode usá-los "
                "sempre que o usuário pedir. Nunca diga que não consegue mexer no mouse "
                "ou no teclado. "
                "Nunca clique espontaneamente nem repita um clique sem novo pedido. "
                "Depois de executar rolar_pagina, não fale, não confirme e não faça perguntas. "
                "Apenas execute a rolagem e permaneça em silêncio aguardando o próximo comando. "
                "Use clicar_elemento_visual quando o usuário pedir para clicar em um elemento "
                "identificado na tela por texto, cor, posição, ícone ou contexto. "
                "Passe uma descrição curta e precisa do alvo. Execute somente um clique. "
                "Depois do clique visual, permaneça totalmente em silêncio. "
                "Se o usuário pedir para fechar um programa USANDO O MOUSE, use "
                "clicar_elemento_visual com o alvo 'botão X de fechar da janela', "
                "no canto superior direito. Isso é permitido e não é ação destrutiva. "
                "Quando ele apenas pedir para fechar, sem exigir o mouse, prefira "
                "fechar_aplicativo, que é mais confiável. "
                "Nunca use clique visual para excluir, apagar, comprar, pagar, transferir, "
                "instalar, desinstalar, confirmar ações sensíveis ou elevar privilégios. "

                # =========================
                # AGENDA
                # =========================
                "Sua agenda e o Google Calendar do usuario, que sincroniza com o celular dele e envia lembretes. "
                "Todo evento criado avisa uma hora antes e dez minutos antes. "
                "Se nenhuma conta do Google estiver autorizada, os eventos caem num arquivo so deste computador, que nao avisa nada: nesse caso diga isso ao usuario. "
                "Use criar_evento_agenda quando o usuário pedir para "
                "agendar, marcar ou anotar um compromisso. "
                "Sempre extraia um título, uma data completa e um horário. "
                "Quando o usuário disser apenas 'amanhã', 'hoje' ou um "
                "dia da semana, interprete usando a data local atual "
                "informada abaixo. "
                "Se faltar o horário ou se a data estiver ambígua, "
                "pergunte antes de salvar. "
                "Use listar_agenda quando o usuário pedir para consultar "
                "os compromissos salvos. "
                "Use cancelar_evento_agenda somente quando ele pedir "
                "claramente para cancelar um compromisso. "
                "Ao agendar, confirme em voz alta o titulo, o dia e a hora. "
                "Para cancelar, se mais de um compromisso tiver nome parecido, pergunte qual antes: cancelar apaga de verdade e avisa quem estiver convidado. "
                f"Data e hora local atual: "
                f"{datetime.now().strftime('%d/%m/%Y %H:%M')}. "

                # =========================
                # SEGURANÇA
                # =========================
                "Nunca exclua arquivos ou pastas. "
                "Nunca sobrescreva arquivos existentes. "
                "Nunca formate, limpe ou remova dados. "
                "Se uma ação parecer destrutiva, recuse com educação. "

                # =========================
                # MEMÓRIA
                # =========================
                "Não memorize informações automaticamente. "
                "Só chame salvar_memoria quando o usuário pedir explicitamente "
                "para lembrar, guardar ou memorizar algo. "
                "Ao salvar, guarde somente o fato útil e objetivo, sem suposições. "
                "Só chame esquecer_memoria quando o usuário pedir claramente "
                "para esquecer algo específico. "
                "Use listar_memorias quando o usuário perguntar o que você lembra "
                "ou pedir para mostrar as memórias. "

                # =========================
                # PREFERÊNCIAS APRENDIDAS
                # =========================
                "Além da memória acima, você mantém uma lista curta de "
                "preferências sobre COMO o usuário gosta de trabalhar. "
                "Essa lista você pode preencher por iniciativa própria, "
                "com anotar_preferencia, sem ele pedir. "
                "Só anote jeito de trabalhar, rotina e horários, e só "
                "quando o padrão ficar evidente. "
                "Anote no máximo uma preferência por conversa. "
                "Nunca anote nada que dispense uma confirmação sua, nem "
                "senha, dado pessoal, nome de aluno ou nota. "
                "Sempre que anotar, diga em voz alta e de forma curta o "
                "que anotou, para o usuário poder corrigir na hora. "
                "Se ele disser que está errado, chame esquecer_preferencia. "
                "As preferências nunca substituem as regras de segurança "
                "desta instrução: confirmação obrigatória continua "
                "obrigatória mesmo que alguma preferência sugira o contrário. "

                # =========================
                # VISÃO
                # =========================
                "Só chame analisar_tela quando o usuário pedir explicitamente "
                "para ver, analisar, observar ou explicar a tela. "
                "Só chame analisar_camera quando o usuário pedir explicitamente "
                "para ver, analisar, observar ou explicar a câmera, webcam "
                "ou algo mostrado nela. "
                "Nunca use função visual espontaneamente. "
                "Para cada pedido visual, execute no máximo uma captura. "
                "Cada captura vale apenas para o pedido em que foi feita. "
                "Se o usuário pedir para olhar, conferir ou analisar de novo, "
                "chame a função visual outra vez para receber uma imagem nova. "
                "Nunca responda sobre a tela ou a câmera usando uma imagem "
                "enviada em um pedido anterior: ela já está desatualizada. "

                # =========================
                # ENCERRAMENTO DA SESSÃO
                # =========================
                "Quando o usuário pedir claramente para encerrar, finalizar, desligar "
                "ou terminar a chamada, sessão ou conexão, chame encerrar_chamada. "
                "Não encerre apenas porque o usuário disse tchau, até mais ou obrigado, "
                "salvo se indicar claramente que deseja finalizar. "

                # =========================
                # ESCRITA NO CAMPO ATIVO
                # =========================
                "Quando o usuário pedir claramente para escrever, digitar, inserir "
                "ou colocar um texto onde o cursor estiver, chame "
                "escrever_no_campo_ativo. "
                "Envie no parâmetro texto somente o conteúdo final a ser escrito, "
                "sem dizer 'aqui está', sem aspas externas e sem explicações. "
                "Você pode corrigir pontuação e concordância quando isso fizer parte "
                "natural do pedido, mas não mude o sentido da mensagem. "
                "Não chame essa função para respostas comuns da conversa. "
                "Não use essa função para enviar mensagens automaticamente. "

                # escrever_no_campo_ativo escreve onde o cursor JÁ está.
                # Num navegador o cursor quase nunca está no campo que o
                # usuário quer, e o texto ia parar em lugar nenhum -- daí
                # o ALF dizer que "não consegue escrever no campo".
                "Para escrever num campo de um site ou de um programa -- "
                "barra de endereço do Chrome, caixa de busca, campo de "
                "formulário --, são DOIS passos: primeiro clicar_elemento_"
                "visual no campo, descrevendo-o pelo que está escrito "
                "perto dele, e só então escrever_no_campo_ativo. "
                "escrever_no_campo_ativo sozinho escreve onde o cursor já "
                "estiver, e o cursor raramente está onde você imagina. "
                "Se o clique não achar o campo, diga ao usuário exatamente "
                "o que a função respondeu e peça para ele clicar no campo; "
                "nunca diga apenas que não consegue escrever, sem explicar "
                "em que passo parou. "

                # =========================
                # ATALHOS DE TECLADO
                # =========================
                "Use pressionar_atalho_teclado quando o usuário pedir uma ação que "
                "depende de atalho de teclado em um programa já aberto, como criar "
                "um novo arquivo (ctrl+n), salvar (ctrl+s), nova aba (ctrl+t), "
                "fechar aba (ctrl+w) ou desfazer (ctrl+z). "
                "Exemplo: se o usuário disser 'crie um novo arquivo no VS Code' e o "
                "VS Code já estiver aberto e em foco, chame pressionar_atalho_teclado "
                "com teclas='ctrl+n'. "
                "Não use para fechar aplicativos, bloquear a tela ou qualquer "
                "combinação que possa perder trabalho não salvo sem o usuário pedir "
                "claramente essa ação. "
                "Para fechar um programa use SEMPRE fechar_aplicativo, nunca "
                "alt+f4. O alt+f4 fecha a janela que estiver em foco no momento, "
                "que quase nunca é a que o usuário pediu, e já causou o "
                "fechamento de coisa errada no meio de outra tarefa. "

                # =========================
                # ABRIR PROGRAMAS
                # =========================
                "Para abrir um programa use abrir_aplicativo com o nome como o "
                "usuário falou; a função já entende apelidos como VS Code e "
                "resolve sites como YouTube ou Gmail. "
                "Se ela responder que não encontrou, não tente abrir pelo menu "
                "iniciar com atalhos de teclado nem pelo prompt de comando: "
                "diga ao usuário que não encontrou e pergunte o nome exato. "

                # =========================
                # E-MAIL
                # =========================
                "Você pode enviar e-mail, mas NUNCA sem confirmação. "
                "NUNCA invente o endereço do destinatário. Se o usuário "
                "não disser para quem é, PERGUNTE. Jamais use endereços "
                "de exemplo como algo@example.com, teste@teste.com ou "
                "variações do nome dele que você supôs: um endereço "
                "inventado pode existir e pertencer a um estranho. "
                "Se ele pedir um e-mail de teste sem dizer o destino, "
                "pergunte se é para ele mesmo e confirme qual é o "
                "endereço antes de preparar. "
                "O fluxo é sempre em dois passos e não pode ser encurtado. "
                "Primeiro chame preparar_email, que apenas monta o rascunho. "
                "Depois leia em voz alta, exatamente como está, o "
                "destinatário, o assunto e a mensagem inteira, e pergunte "
                "se pode enviar. "
                "Só chame confirmar_envio_email depois que o usuário "
                "autorizar de forma clara, em um turno posterior. "
                "Nunca chame confirmar_envio_email no mesmo turno em que "
                "preparou o e-mail, nem por dedução, nem porque o pedido "
                "parecia urgente. "
                "Se ele mandar mudar alguma coisa, prepare o e-mail de novo "
                "e leia de novo. Se desistir, chame cancelar_email. "
                "A transcrição de voz erra nomes e negações, e e-mail "
                "enviado não volta: por isso a leitura em voz alta é "
                "obrigatória mesmo que o usuário demonstre pressa. "
                "Por outro lado, depois que o usuário JÁ autorizou, você "
                "DEVE chamar confirmar_envio_email imediatamente. "
                "Contam como autorização respostas como 'pode enviar', "
                "'manda', 'sim', 'confirma', 'isso mesmo' e equivalentes. "
                "Não peça confirmação duas vezes nem repita o rascunho. "
                "E NUNCA diga que enviou sem ter chamado a função: o "
                "e-mail só sai quando confirmar_envio_email é executada. "
                "O rascunho vale cinco minutos; passado esse tempo, "
                "prepare de novo em vez de tentar confirmar. "
                "Quando ele ditar um endereço, ofereça guardar o contato "
                "com salvar_contato, para depois bastar dizer o nome. "
                "Para anexar um arquivo, passe o nome dele no parâmetro "
                "anexo de preparar_email; a função acha o arquivo sozinha "
                "na Área de Trabalho, Documentos e Downloads. "
                "Nunca invente nome de arquivo, e nunca diga que anexou "
                "algo se não passou o parâmetro anexo. "
                "Ao ler o rascunho em voz alta, diga também o nome e o "
                "tamanho do arquivo anexado, para o usuário perceber se "
                "é o arquivo errado antes de a mensagem sair. "
                "Se a função disser que achou mais de um arquivo parecido, "
                "pergunte qual deles antes de preparar de novo. "

                # =========================
                # GOOGLE CLASSROOM
                # =========================
                "Você acessa o Google Classroom do usuário pela API oficial. "
                "Ele tem turmas em mais de uma conta do Google, e você "
                "consulta todas de uma vez; não precisa perguntar de qual "
                "conta é a turma. Quando duas turmas tiverem nome parecido, "
                "a resposta diz de qual conta é cada uma: use isso para "
                "perguntar qual delas. "
                "Se ele disser que tem turmas num e-mail que você não "
                "enxerga, chame autorizar_conta e avise que o navegador vai "
                "abrir para ele escolher a conta. "
                "NUNCA chame autorizar_conta no meio de outra tarefa. Ela "
                "abre o navegador e interrompe o que o usuário está fazendo. "
                "Se uma função disser que falta permissão, TERMINE o que "
                "está fazendo, conte o que aconteceu e deixe o usuário "
                "decidir quando reautorizar. "
                "Use listar_turmas, listar_atividades e listar_entregas para "
                "consultar, e ler_entrega para ver o que um aluno respondeu. "
                "Nunca tente corrigir o Classroom clicando na tela: as "
                "funções acima são exatas e o clique visual erra de linha. "
                # =========================
                # CORRIGIR A TURMA
                # =========================
                "Para corrigir uma atividade, NÃO peça confirmação aluno "
                "por aluno: o professor pediu para não ser interrompido. "
                "Leia cada entrega com ler_entrega, decida a nota e o "
                "comentário, diga um resumo bem curto e siga para o "
                "próximo sem perguntar nada. "
                "No fim, lance tudo de uma vez com lancar_notas_em_lote. "
                "Isso é seguro porque as notas entram como RASCUNHO: o "
                "aluno não vê nada até o professor revisar e devolver. "
                "Ao terminar, diga os números -- quantas lançou, quantas "
                "pulou e por quê -- e lembre que ele pode revisar tudo "
                "antes de devolver. "
                "Nunca devolva a atividade por conta própria: devolver é o "
                "que faz o aluno ver a nota, e essa decisão é do professor. "
                "Só chame devolver_atividade quando ele pedir. "
                "Quem já tinha nota é pulado no lote, de propósito. Para "
                "trocar uma nota que já existe, use preparar_nota e "
                "confirmar_nota, em dois passos, confirmando com ele; "
                "nunca chame confirmar_nota no mesmo turno do preparo. "
                # =========================
                # DEVOLVER COM COMENTÁRIO
                # =========================
                "O comentário de cada aluno fica guardado pelo lote e vai "
                "para ele junto com a nota, na DEVOLUÇÃO -- nunca antes. "
                "Comentário particular chega ao aluno na hora, sem "
                "rascunho; mandar na correção faria o aluno ler antes de o "
                "professor revisar. "
                "Quando o professor pedir para devolver a atividade, chame "
                "preparar_devolucao, diga os números e confirme UMA vez só "
                "com ele. Depois peça a página 'Trabalhos dos estudantes' "
                "aberta na tela e chame devolver_proximo_aluno "
                "repetidamente, dizendo só o nome de cada um, curto. "
                "Se a função disser que parou, PARE: conte exatamente o que "
                "ela disse, inclusive se o comentário foi digitado mas não "
                "enviado. NUNCA diga que enviou um comentário ou devolveu "
                "uma atividade que a função não confirmou. "
                # =========================
                # TRANSPORTAR NOTAS PARA A TELA
                # =========================
                "Quando a atividade não puder receber nota pela API, existe "
                "o caminho de digitar na tela: preparar_transporte lê uma "
                "planilha JÁ REVISADA pelo professor e lancar_proxima_nota "
                "digita um aluno por vez. "
                "Você NUNCA decide nota nesse fluxo: só transporta o que "
                "está na planilha. Se ela estiver sem notas, peça para ele "
                "preencher antes. "
                "Diga sempre a turma e a atividade ao chamar "
                "preparar_transporte: é assim que eu confiro se as notas "
                "cabem no valor da atividade. Nota acima do valor faz o "
                "transporte recusar tudo, e está certo: é sinal de que a "
                "planilha inteira está em outra escala. "
                "Confirme que a tela de notas da turma está aberta antes de "
                "começar, e avise que ele deve acompanhar. "
                "Depois de cada aluno, diga só o nome e a nota, curto. "
                "Se a conferência falhar, PARE na hora, conte exatamente o "
                "que apareceu na tela e não tente de novo sozinho: nota no "
                "aluno errado é o que se está evitando. "
                "NUNCA diga que lançou uma nota que a função não confirmou. "
                "Se lancar_proxima_nota devolver que não achou o aluno, "
                "então aquela nota NÃO foi lançada: diga isso com essas "
                "palavras, mesmo que já tenha lançado outras antes. "
                "Ao terminar, chame conferir_transporte ANTES de dar "
                "qualquer notícia ao professor. Ele pergunta ao Classroom "
                "quais notas existem de verdade, e é essa resposta que "
                "vale -- não a sua lembrança da conversa. "
                "Se ele apontar alunos faltando, leia os nomes em voz alta "
                "e ofereça retomar. "
                "Ao terminar, lembre que você não salvou nada: o professor "
                "precisa revisar e salvar no Classroom. "

                "Ao terminar de avaliar vários alunos de uma atividade, "
                "ofereça montar_planilha_de_correcao: ela junta tudo numa "
                "planilha para o professor conferir e digitar de uma vez, "
                "em vez de ele ter que lembrar o que você disse de cada um. "

                # =========================
                # COMO ESCREVER A OBSERVAÇÃO
                # =========================
                "A observação de cada aluno é um recado que ele pode "
                "acabar lendo. Escreva PARA ele, não sobre ele. "
                "Comece pelo que ele acertou, nomeando a parte específica "
                "-- 'o fluxograma ficou claro', não 'bom trabalho' solto. "
                "Elogio genérico não ensina nada e o aluno percebe. "
                "Depois diga o que ajustar, como próximo passo e não como "
                "falta: 'da próxima vez, detalhe também o levantamento de "
                "infraestrutura'. "
                "Duas frases bastam. Cabe numa célula de planilha. "
                "Trate o aluno por você, em tom de professor que quer que "
                "ele melhore, nunca de relatório. "
                "Quando não houver entrega, ou o arquivo não puder ser "
                "lido, NÃO invente elogio: diga o que aconteceu em uma "
                "frase, sem sermão e sem julgar o aluno. "
                "Nunca escreva a mesma observação para dois alunos: se o "
                "trabalho é parecido, aponte o que cada um fez de seu. "
                "ler_entrega abre os arquivos entregues: documentos do Google, "
                "PDF, Word, planilha e até foto do caderno, que é transcrita. "
                "Nunca leia o trabalho inteiro em voz alta. Resuma o que o "
                "aluno fez, aponte o que está certo e o que falta, e então "
                "sugira a nota. "
                "Se o arquivo não puder ser lido, diga isso com clareza e "
                "não invente o que estava escrito nele. "
                "Se o aluno já tiver nota lançada, avise que ela será "
                "substituída antes de confirmar. "
                "Depois de corrigir, ofereça devolver_atividade: só depois "
                "de devolvida o aluno enxerga a nota. "
                "LIMITE IMPORTANTE: o Google Classroom só deixa você lançar "
                "nota em atividades criadas por você mesmo, com "
                "criar_atividade. As que o professor criou pela interface do "
                "Classroom são somente leitura para você. Isso é regra da "
                "plataforma, não permissão faltando: não peça para "
                "reautorizar conta por causa disso, e não insista. "
                "Quando acontecer, explique com clareza e ofereça as duas "
                "saídas: lançar à mão, ou criar as próximas atividades por "
                "você. Ler entregas e conteúdo continua funcionando em "
                "qualquer atividade. "

                # =========================
                # CRIAR ATIVIDADE E QUESTIONÁRIO
                # =========================
                "Você cria atividades no Classroom com criar_atividade. "
                "Ela nasce como RASCUNHO e os alunos não veem nada até o "
                "professor publicar: diga isso sempre depois de criar, para "
                "ele não achar que a turma já recebeu. "
                "Antes de criar, confirme em voz alta a turma, o título, "
                "quanto vale e o prazo. Nunca invente prazo nem pontuação: "
                "se ele não disser, pergunte ou deixe em branco. "
                "Para prova de múltipla escolha use criar_questionario, que "
                "monta um Google Forms com gabarito e o Google corrige "
                "sozinho. Redija as questões você mesmo quando ele pedir "
                "sobre um assunto, mas leia em voz alta quantas questões "
                "foram feitas e sobre o quê antes de criar. "
                "A resposta correta precisa ser exatamente uma das "
                "alternativas que você escreveu. "
                "Depois de criar o questionário, ofereça anexar o link a "
                "uma atividade da turma usando criar_atividade com o "
                "parâmetro link. "

                # =========================
                # PRODUZIR MATERIAL
                # =========================
                "Você também cria material no Google: apresentação com "
                "criar_apresentacao, documento com criar_documento e "
                "planilha com criar_planilha. "
                "Para planilha de notas de uma turma use "
                "criar_planilha_de_notas, que já traz os nomes dos alunos "
                "do Classroom: digitar trinta nomes à mão é justamente o "
                "trabalho que se quer evitar. "
                "Escreva o conteúdo você mesmo a partir do assunto pedido, "
                "mas antes diga em voz alta quantos slides ou seções vai "
                "fazer e sobre o quê, e confirme. "
                "Deixe claro que é uma base para o professor ajustar, não "
                "um material final. "
                "Depois de criar, informe o link e resuma o que fez. "
                "Nunca leia o conteúdo inteiro em voz alta. "

                # =========================
                # PROGRAMAR
                # =========================
                "Você pode programar de verdade neste computador. "
                "Para escrever código novo use criar_arquivo_codigo, que "
                "grava o arquivo pronto; é melhor que ditar no editor. "
                "ANTES de alterar qualquer arquivo que já existe, chame "
                "ler_arquivo. Nunca altere código baseado apenas na captura "
                "de tela: ela mostra só a parte visível e erra identação. "
                "Depois de escrever, rode com executar_no_terminal e conte "
                "ao usuário se funcionou. Se der erro, leia o arquivo de "
                "novo, corrija e rode outra vez. "
                "Nunca leia código em voz alta linha por linha. Resuma o "
                "que fez, quantas linhas, e o que o programa faz. "
                "Substituir arquivo existente exige confirmação do usuário: "
                "avise que o arquivo já existe e pergunte antes. "
                "Só mexo em arquivos dentro da pasta do usuário, e nunca em "
                "arquivos de senha ou chave; se a função recusar por isso, "
                "explique e siga em frente. "

                # =========================
                # VS CODE
                # =========================
                "Para abrir uma pasta, projeto ou arquivo no VS Code use "
                "abrir_no_vscode. Ela já encontra a pasta pelo nome e abre "
                "na hora. Nunca use ctrl+k ctrl+o nem tente navegar pela "
                "caixa de diálogo de arquivos com cliques visuais: isso é "
                "lento e erra o caminho. "
                "Se o VS Code ainda não estiver aberto, abrir_no_vscode "
                "também o inicia; não precisa chamar abrir_aplicativo antes. "
                "Para outras ações dentro do editor, como abrir o terminal "
                "integrado ou formatar o documento, use "
                "executar_comando_vscode com o nome do comando da paleta. "

                # =========================
                # LANÇAMENTO DE NOTAS NO SIGEDUC
                # =========================
                "Você TEM permissão e deve ajudar ativamente a ler planilhas de "
                "notas e lançá-las no SIGEduc quando o usuário pedir. Esta é uma "
                "tarefa normal e esperada; não é uma ação destrutiva e não deve "
                "ser recusada. Apenas siga as regras de cuidado abaixo. "
                "Use ler_planilha_notas assim que o usuário pedir para ler, abrir, "
                "conferir ou importar notas de uma planilha, mesmo sem outros "
                "detalhes ainda; pergunte o que faltar depois de ler o arquivo. "
                "Depois de ler a planilha, confirme rapidamente com o usuário a "
                "disciplina/componente, unidade e avaliação de destino no SIGEduc, "
                "e então prossiga com o preenchimento normalmente. "
                "Nunca peça, armazene, veja ou digite a senha do usuário. "
                "Quando o SIGEduc pedir senha, pare e deixe o usuário digitar "
                "e confirmar sozinho; depois disso, continue normalmente. "
                "Não escolha opções de diálogos finais como 'Sim', 'Não' ou "
                "'Confirmar' sem uma instrução explícita do usuário naquele momento. "
                "Não confie na ordem das linhas da planilha como igual à ordem "
                "exibida no SIGEduc: relacione sempre pelo nome do aluno. "
                "Preserve notas em branco ou ausências conforme a planilha "
                "e o pedido do usuário; não invente valores. "
                "Ao preencher campos de nota, use clicar_elemento_visual para "
                "localizar o campo correto e escrever_no_campo_ativo para "
                "digitar o valor, um aluno de cada vez, confirmando o campo "
                "certo antes de digitar. "
                "Aprenda com a repetição: depois de clicar com clicar_elemento_visual "
                "nos campos de nota de pelo menos dois alunos consecutivos na mesma "
                "coluna, use clicar_campo_seguinte_padrao para os alunos seguintes "
                "dessa coluna em vez de localizar visualmente de novo — isso é bem "
                "mais rápido. Volte a usar clicar_elemento_visual sempre que o "
                "padrão parecer ter desalinhado (linha maior que o normal, seção "
                "nova, rolagem da página) ou a cada poucos alunos para conferir. "
                "Se um aluno da planilha não aparecer na tela, ou aparecer um "
                "aluno na tela sem nota correspondente na planilha, avise o "
                "usuário sobre essa divergência mas continue preenchendo os "
                "demais alunos normalmente. "
                "Só confirme o salvamento final (botão Gravar ou equivalente) "
                "quando o usuário autorizar explicitamente. "
                "Depois de lançar, informe de forma curta quais alunos foram "
                "preenchidos e quais ficaram em branco ou com divergência. "

                # =========================
                # RETORNO DAS FUNÇÕES
                # =========================
                "Após qualquer função, explique em voz o que foi feito "
                "de forma curta e natural. "

            "\n\n"
            + memorias_atuais
        )

        # Limite de tentativas automáticas de reconexão após uma queda
        # inesperada (ex.: código 1006) antes de desistir e mostrar o erro.
        MAX_TENTATIVAS_RECONEXAO = 5
        tentativas_reconexao = 0

        # Distingue a primeira conexão das renovações seguintes. Sem isso
        # toda renovação normal do servidor aparecia para o usuário como
        # "Conectando ao Gemini Live...", dando a impressão de que o ALF
        # estava reiniciando o tempo todo.
        primeira_conexao = True

        # Loop externo: mantém a chamada viva reconectando automaticamente
        # após quedas inesperadas ou renovações pedidas pelo servidor
        # (GoAway), preservando o contexto através do session_handle.
        while self.ativo:
            self.renovacao_em_andamento = False
            self._forcar_reconexao = False
            momento_sessao_aberta = None

            # A máquina pode encher no meio da aula: o professor abre mais
            # abas para dar a aula, e a conexão renova a cada ~9 minutos.
            self.avisar_se_memoria_apertada()

            # A instrução é remontada a cada conexão de propósito.
            # Assim uma memória salva agora já vale na reconexão, e a
            # data/hora embutida na instrução nunca fica velha numa
            # chamada longa (o que fazia o ALF errar "hoje" e "amanhã"
            # na agenda).
            instrucao_agora = self.atualizar_instrucao_sistema(
                instrucao_sistema
            )

            config = self.criar_config_live(
                instrucao_sistema=instrucao_agora,
                tools=tools,
                session_handle=self.session_handle,
            )

            # Fila assíncrona de entrada.
            # Recebe os blocos capturados pelo microfone.
            fila_microfone = asyncio.Queue(
                maxsize=LIMITE_FILA_MICROFONE
            )
            # Fila assíncrona de saída.
            # Recebe os blocos de áudio enviados pelo Gemini.
            fila_saida = asyncio.Queue()

            # Emite uma mensagem para a interface.
            provedor_atual = self.nome_do_provedor()

            if primeira_conexao:
                self.status_recebido.emit(
                    f"Conectando ({provedor_atual})..."
                )
                self.registrar_diagnostico(
                    f"Abrindo sessao: {provedor_atual}."
                )
            elif tentativas_reconexao == 0:
                self.status_recebido.emit(
                    "Renovando a conexão. A conversa continua."
                )
                self.registrar_diagnostico(
                    f"Renovacao normal da sessao: {provedor_atual}."
                )
            else:
                self.status_recebido.emit(
                    f"Reconectando ({provedor_atual})... "
                    f"(tentativa {tentativas_reconexao}/{MAX_TENTATIVAS_RECONEXAO})"
                )
                self.registrar_diagnostico(
                    f"Reabrindo sessao: {provedor_atual}, "
                    f"tentativa={tentativas_reconexao}"
                )

            try:
                # Abre a sessão Live com limite para não deixar a interface
                # presa indefinidamente enquanto a rede ou a API não responde.
                if self.provedor == "simples":
                    gerenciador_conexao = conectar_simples(
                        instrucao_agora,
                        tools,
                        self.provedores_de_texto(),
                        GROQ_API_KEY,
                        GROQ_WHISPER_MODEL,
                        VOZ_WINDOWS,
                    )
                elif self.provedor == "openai":
                    # Mesma superfície da sessão do Gemini: o laço de
                    # recebimento, o microfone e as ferramentas seguem
                    # iguais. Ver voz/openai_realtime.py.
                    gerenciador_conexao = conectar_alternativa(
                        OPENAI_API_KEY,
                        OPENAI_REALTIME_MODEL,
                        instrucao_agora,
                        tools,
                        OPENAI_REALTIME_VOICE,
                    )
                else:
                    gerenciador_conexao = client.aio.live.connect(
                        model=GEMINI_LIVE_MODEL,
                        config=config,
                    )
                sessao = await asyncio.wait_for(
                    gerenciador_conexao.__aenter__(),
                    timeout=TEMPO_LIMITE_CONEXAO,
                )

                # Declarada aqui para o finally alcançá-la mesmo quando a
                # sessão morre antes de as tarefas serem criadas.
                tarefas = []

                try:
                    # Guarda a sessão ativa no objeto.
                    self.sessao = sessao
                    momento_sessao_aberta = time.monotonic()

                    # Uma reconexão (GoAway ou queda) pode ter deixado estes
                    # sinalizadores travados em True. Zera para não bloquear
                    # novas ações após a sessão ser restabelecida.
                    self.processando_ferramenta = False
                    self.alfred_falando = False
                    # Se a queda aconteceu no meio de um turno silenciado,
                    # este sinalizador ficava True e o ALF descartava toda
                    # a fala dele na sessão nova: mudo para sempre.
                    self.silenciar_audio_ate_fim_turno = False
                    self.fluxo_audio_em_andamento = False
                    self.usuario_falando_detectado = False
                    self.ultimo_audio_com_voz = None
                    self.reproduzindo_bloco = False
                    self.tarefa_fim_de_fluxo = None
                    self.buffer_audio.limpar()

                    # Uma captura que ficou pendente antes da queda já não
                    # representa a tela atual. Descarta para o ALF nunca
                    # analisar uma imagem de antes da reconexão.
                    self.imagem_visual_pendente = None
                    self.momento_captura_visual = None
                    self.executando_funcao_visual = False

                    self.status_recebido.emit(
                        "ALF conectado. Pode falar."
                    )
                    self.registrar_diagnostico(
                        f"Sessao aberta com sucesso: {provedor_atual}."
                    )

                    # Só a primeira conexão da chamada abre a conversa.
                    # Nas renovações a conversa já está em andamento, e
                    # cumprimentar de novo a cada nove minutos seria pior
                    # que o silêncio.
                    abertura = primeira_conexao
                    primeira_conexao = False

                    # Inicia três tarefas paralelas:
                    # 1. enviar áudio do microfone;
                    # 2. receber respostas;
                    # 3. reproduzir áudio.
                    tarefas += [
                        asyncio.create_task(
                            self.enviar_microfone(
                                sessao,
                                fila_microfone,
                            )
                        ),

                        asyncio.create_task(
                            self.receber_audio(
                                sessao,
                                fila_saida,
                                fila_microfone,
                            )
                        ),

                        asyncio.create_task(
                            self.reproduzir_audio(
                                fila_saida,
                                fila_microfone,
                            )
                        ),
                    ]

                    # Fica fora da lista de tarefas de propósito: uma
                    # tarefa que termina é lida ali como fim de fluxo, e
                    # esta termina em seguida.
                    if abertura:
                        await self.abrir_conversa(sessao)

                    # Monitora as tarefas. Se qualquer tarefa interna falhar,
                    # a conexão deixa de aparecer falsamente como ativa.
                    fim_limpo = False

                    while self.ativo and not self._forcar_reconexao:
                        concluidas, _ = await asyncio.wait(
                            tarefas,
                            timeout=0.5,
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        for tarefa in concluidas:
                            if tarefa.cancelled():
                                continue

                            erro = tarefa.exception()
                            if erro is not None:
                                raise RuntimeError(
                                    f"Uma tarefa interna da sessão parou: {erro}"
                                ) from erro

                            # Terminar sem erro significa que o servidor
                            # fechou o fluxo de forma limpa. Antes isso
                            # virava um RuntimeError e o usuário via
                            # "Conexão perdida" a cada renovação normal.
                            fim_limpo = True

                        if fim_limpo:
                            self.registrar_diagnostico(
                                "Fluxo da sessao terminou de forma limpa. "
                                "Renovando a conexao."
                            )
                            break

                finally:
                    # Este bloco ficava depois do laço, dentro do try.
                    # Quando uma tarefa interna morria, o RuntimeError
                    # pulava por cima dele: as tarefas da sessão morta
                    # continuavam vivas, cada uma segurando o seu fluxo
                    # de áudio aberto. A sessão nova abria mais um, e os
                    # dois liam o MESMO buffer -- duas vozes ao mesmo
                    # tempo, uma comendo pedaços da outra.
                    for tarefa in tarefas:
                        tarefa.cancel()

                    if self.tarefa_liberar_microfone:
                        self.tarefa_liberar_microfone.cancel()

                    if self.tarefa_encerramento:
                        self.tarefa_encerramento.cancel()

                    if self.tarefa_ferramenta_atual:
                        self.tarefa_ferramenta_atual.cancel()

                    if self.tarefa_fim_de_fluxo:
                        self.tarefa_fim_de_fluxo.cancel()

                    # Aguarda o encerramento das tarefas.
                    # return_exceptions=True evita que cancelamentos
                    # gerem erros não tratados.
                    await asyncio.gather(
                        *tarefas,
                        return_exceptions=True,
                    )

                    # Só depois de as tarefas soltarem a placa de som e o
                    # socket é que a conexão pode fechar.
                    await gerenciador_conexao.__aexit__(
                        None,
                        None,
                        None,
                    )

                # Limpa a referência da sessão encerrada.
                self.sessao = None

                # Encerramento normal solicitado pelo usuário: não reconecta.
                if not self.ativo:
                    break

                # Reconexão solicitada pelo servidor (GoAway): tenta de novo
                # usando o session_handle mais recente para manter o contexto.
                await asyncio.sleep(1.0)
                continue

            # Captura quedas inesperadas da conexão, como o código 1006
            # (abnormal closure), e tenta reconectar automaticamente
            # preservando a conversa através do session_handle.
            except Exception as erro:
                self.sessao = None

                # Se o usuário pediu para encerrar durante o erro, não reconecta.
                if not self.ativo:
                    break

                if momento_sessao_aberta is not None:
                    duracao_sessao = time.monotonic() - momento_sessao_aberta
                else:
                    duracao_sessao = 0.0

                # Antes de tudo: cota esgotada tem tratamento próprio.
                # Sem isto, o ALF reabria em poucos segundos, era recusado
                # de novo, e o professor só via a chamada muda.
                if self.parece_cota_esgotada(erro):
                    # Havendo alternativa, troca já na primeira recusa.
                    # Esperar dois minutos em silêncio por uma cota que
                    # acabou, com outro provedor pronto ao lado, é tempo
                    # de aula jogado fora.
                    proximo = self.proximo_provedor()

                    if proximo is not None:
                        anterior = self.provedor
                        self.provedor = proximo
                        self.quedas_por_cota = 0

                        self.registrar_diagnostico(
                            f"Cota esgotada em {anterior}: descendo para "
                            f"{proximo}."
                        )
                        self.status_recebido.emit(self.aviso_do_provedor(proximo))
                        self.solicitou_reconexao.emit()
                        await asyncio.sleep(1.0)
                        continue

                    # Sem alternativa, o tempo é o único remédio: limite
                    # por minuto passa sozinho, limite diário não.
                    decisao, detalhe = self.decidir_apos_cota(duracao_sessao)

                    self.registrar_diagnostico(
                        f"Cota esgotada ({self.quedas_por_cota}a vez). "
                        f"Decisao: {decisao}."
                    )

                    if decisao == "parar":
                        self.erro_recebido.emit(detalhe)
                        raise RuntimeError(detalhe) from erro

                    self.status_recebido.emit(
                        "O Google recusou por cota esgotada. Esperando "
                        f"{detalhe:.0f}s antes de tentar de novo, para não "
                        "gastar mais cota."
                    )
                    self.solicitou_reconexao.emit()
                    await asyncio.sleep(detalhe)
                    continue

                tentativas_reconexao = self.calcular_tentativas_apos_queda(
                    tentativas_reconexao,
                    duracao_sessao,
                )
                if tentativas_reconexao > MAX_TENTATIVAS_RECONEXAO:
                    raise

                # Uma sessão que cai, reabre e cai de novo várias vezes
                # em poucos minutos não se resolve sozinha: normalmente é
                # rede instável, chave sem cota ou outro ALF disputando o
                # microfone. Antes o ALF ficava nesse ciclo indefinidamente
                # porque uma sessão de 45 s já zerava o contador. Agora ele
                # para e explica o que está acontecendo.
                agora_reconexao = time.monotonic()
                self.historico_reconexoes.append(agora_reconexao)
                self.historico_reconexoes = [
                    momento
                    for momento in self.historico_reconexoes
                    if agora_reconexao - momento <= JANELA_CICLO_RECONEXAO
                ]

                if len(self.historico_reconexoes) > MAX_RECONEXOES_NA_JANELA:
                    self.registrar_diagnostico(
                        "Ciclo de reconexao detectado: "
                        f"{len(self.historico_reconexoes)} quedas em "
                        f"{JANELA_CICLO_RECONEXAO:.0f}s."
                    )
                    raise RuntimeError(
                        "A conexão caiu várias vezes seguidas em poucos "
                        "minutos. Verifique a internet, a cota da chave "
                        "GEMINI_API_KEY e se existe outro ALF aberto. "
                        f"Último erro: {erro}"
                    ) from erro

                # Espera com crescimento exponencial e uma variação
                # aleatória, para duas quedas seguidas não tentarem
                # reconectar exatamente no mesmo instante.
                espera = min(
                    ESPERA_BASE_RECONEXAO * (2 ** (tentativas_reconexao - 1)),
                    ESPERA_MAXIMA_RECONEXAO,
                )
                espera = espera * (0.75 + random.random() * 0.5)

                self.status_recebido.emit(
                    f"Conexão perdida ({erro}). "
                    f"Reconectando em {espera:.0f}s..."
                )
                self.registrar_diagnostico(
                    f"Conexao perdida em {self.nome_do_provedor()}. "
                    f"tentativa={tentativas_reconexao} "
                    f"erro={repr(erro)}\n{traceback.format_exc()}"
                )

                self.solicitou_reconexao.emit()

                await asyncio.sleep(espera)
                continue

    @staticmethod
    def atualizar_instrucao_sistema(instrucao_base):
        """
        Devolve a instrução com as memórias e a data de agora.

        A instrução base é montada uma vez na abertura da chamada. Este
        método troca apenas as duas partes que envelhecem: o bloco de
        memória persistente, que fica no final do texto, e a data local
        usada para interpretar "hoje", "amanhã" e dias da semana.
        """

        agora = datetime.now().strftime("%d/%m/%Y %H:%M")

        # A data aparece uma única vez, num trecho de formato fixo.
        instrucao = re.sub(
            r"Data e hora local atual: [^.]*\.",
            f"Data e hora local atual: {agora}.",
            instrucao_base,
            count=1,
        )

        # O bloco de memórias é sempre o final da instrução, separado
        # por uma linha em branco dupla.
        marcadores = (
            "MEMÓRIA PERSISTENTE DO USUÁRIO:",
            "MEMÓRIA PERSISTENTE:",
        )

        blocos = contexto_memorias() + "\n\n" + contexto_preferencias()

        for marcador in marcadores:
            posicao = instrucao.find(marcador)
            if posicao != -1:
                return instrucao[:posicao] + blocos

        return instrucao + "\n\n" + blocos

    def avisar_se_memoria_apertada(self):
        """
        Avisa uma vez quando a máquina fica sem memória.

        Antes o ALF engasgava calado, e o usuário não tinha como saber se
        a culpa era dele, da internet ou do computador. Em 18/09/2026 o
        log não tinha nenhuma queda de conexão: era a memória, quase toda
        tomada por janelas de navegador.

        Avisa na virada, e não a cada conexão, para não virar barulho.
        """

        apertada, mensagem = memoria_apertada()

        if apertada and not self.memoria_apertada:
            self.status_recebido.emit(mensagem)
            self.registrar_diagnostico(mensagem)

        self.memoria_apertada = apertada

    # Captura o microfone e envia áudio em tempo real.
    async def enviar_microfone(
        self,
        sessao,
        fila_microfone,
    ):
        # Obtém o loop usado por esta tarefa.
        loop = asyncio.get_running_loop()

        # Callback chamado automaticamente pelo sounddevice
        # sempre que um novo bloco de áudio é capturado.
        def callback(
            indata,
            frames,
            time_info,
            status,
        ):
            # Ignora blocos quando a sessão está sendo encerrada.
            if not self.ativo:
                return

            # Impede que o ALFRED escute a própria voz.
            if self.alfred_falando or self.processando_ferramenta:
                return

            # Exibe avisos fornecidos pelo dispositivo de áudio.
            if status:
                print(
                    "Aviso microfone:",
                    status,
                )

            # Converte o bloco capturado para bytes puros.
            audio_bytes = bytes(
                indata
            )

            # Insere o bloco na fila assíncrona com segurança.
            # Se o ALFRED começar a falar antes da inclusão efetiva,
            # o bloco será descartado. Se a fila estiver cheia,
            # o bloco mais novo também será descartado para evitar atraso.
            def adicionar_audio():
                if self.alfred_falando or self.processando_ferramenta or not self.ativo:
                    return

                try:
                    fila_microfone.put_nowait(
                        audio_bytes
                    )

                except asyncio.QueueFull:
                    pass

            loop.call_soon_threadsafe(
                adicionar_audio
            )

        # Abre o fluxo bruto do microfone.
        with sd.RawInputStream(
            samplerate=TAXA_ENTRADA,
            blocksize=BLOCO,
            dtype="int16",
            channels=CANAIS,
            callback=callback,
        ):
            # Continua lendo e enviando áudio enquanto a sessão estiver ativa.
            while self.ativo:
                # Aguarda o próximo bloco capturado.
                audio_bytes = await fila_microfone.get()

                # Segunda proteção: o bloco pode ter entrado na fila
                # poucos milissegundos antes de o ALFRED começar a falar.
                # Nesse caso ele é descartado e nunca chega ao Gemini.
                if self.alfred_falando or self.processando_ferramenta:
                    continue

                # O nível é medido sempre, e não só quando o VAD local
                # está ligado: é ele que marca quando o usuário falou
                # pela última vez. Sem isso, a medida de demora começava
                # no fim do turno anterior e contava como lentidão do
                # ALF todo o tempo em que o usuário ficou calado -- foi
                # assim que apareceram "demoras" de 38 s e 94 s.
                nivel_microfone = self.calcular_nivel_audio(audio_bytes)

                if nivel_microfone >= LIMIAR_VOZ_MICROFONE:
                    self.momento_ultima_voz = time.monotonic()

                # Envia o bloco ao Gemini em tempo real.
                async with self.lock_envio:
                    await sessao.send_realtime_input(
                        audio=types.Blob(
                            data=audio_bytes,
                            mime_type=(
                                f"audio/pcm;rate={TAXA_ENTRADA}"
                            ),
                        )
                    )
                    self.fluxo_audio_em_andamento = True

                # A Live API já detecta o fim da fala no servidor.
                # Fechar o turno também aqui criava duas detecções
                # concorrentes e cortava o fim das frases.
                if USAR_VAD_CLIENTE and self.deve_finalizar_fluxo_por_silencio(
                    nivel_microfone,
                    time.monotonic(),
                ):
                    await self.finalizar_fluxo_audio_pendente(sessao)

    # Recebe áudio, chamadas de ferramentas
    # e informações de finalização de turno.
    async def receber_audio(
        self,
        sessao,
        fila_saida,
        fila_microfone,
    ):
        while self.ativo:
            # Percorre continuamente as respostas enviadas pela API.
            async for resposta in sessao.receive():
                if not self.ativo:
                    break

                # resposta.data contém bytes de áudio gerados pelo Gemini.
                if resposta.data:
                    self.registrar_atraso_da_resposta()

                    # aguardar_envio=False: este laço não pode parar
                    # para esperar um envio, senão o socket deixa de
                    # ser drenado e o servidor aborta com 1008.
                    await self.preparar_pausa_microfone(
                        sessao,
                        fila_microfone,
                        aguardar_envio=False,
                    )

                    # Só reproduz quando o turno não foi marcado
                    # para permanecer em silêncio.
                    if not self.silenciar_audio_ate_fim_turno:
                        await fila_saida.put(
                            resposta.data
                        )

                # Verifica se o modelo pediu a execução de uma ferramenta.
                # A execução acontece em segundo plano para que este laço
                # continue lendo o WebSocket enquanto a ferramenta roda.
                if resposta.tool_call:
                    await self.preparar_pausa_microfone(
                        sessao,
                        fila_microfone,
                        aguardar_envio=False,
                    )
                    self.agendar_chamada_de_funcao(
                        sessao,
                        resposta.tool_call,
                        fila_microfone,
                    )


                # Guarda o token mais recente para retomar a mesma conversa.
                update = getattr(resposta, "session_resumption_update", None)
                if update and getattr(update, "resumable", False):
                    novo_handle = getattr(update, "new_handle", None)
                    if novo_handle:
                        self.session_handle = novo_handle
                        self.session_handle_atualizado.emit(novo_handle)

                # O servidor envia GoAway antes de encerrar o WebSocket.
                # Ao receber esse aviso, interrompemos imediatamente novos
                # envios, saímos do receive() e deixamos o context manager
                # fechar a conexão de forma limpa. A interface abrirá uma
                # nova conexão usando o último session_handle recebido.
                go_away = getattr(resposta, "go_away", None)
                if go_away is not None and not self.renovacao_em_andamento:
                    self.renovacao_em_andamento = True
                    self.processando_ferramenta = True
                    self.limpar_fila_microfone(fila_microfone)

                    tempo_restante = getattr(go_away, "time_left", None)
                    if tempo_restante is not None:
                        self.status_recebido.emit(
                            "Servidor solicitou a renovação da conexão. "
                            "Preservando a conversa..."
                        )
                    else:
                        self.status_recebido.emit(
                            "Servidor solicitou a renovação da conexão. "
                            "Preservando a conversa..."
                        )

                    # O loop externo de executar() fecha esta conexão e
                    # abre uma nova usando o mesmo session_handle, sem
                    # encerrar a chamada nem exibir erro para o usuário.
                    self.solicitou_reconexao.emit()

                    # Faz todas as tarefas encerrarem. O bloco async with
                    # fechará o WebSocket antes de o prazo do GoAway acabar.
                    self._forcar_reconexao = True
                    return

                # Obtém o conteúdo de controle enviado pelo servidor,
                # sem gerar erro caso o atributo não exista.
                server_content = getattr(
                    resposta,
                    "server_content",
                    None,
                )

                # O servidor avisa quando decide que o usuário falou por
                # cima e para de gerar. Sem descartar o que já chegou, o
                # ALF continuava tocando a fala velha enquanto a nova
                # começava: a voz saía picotada, como se cortasse.
                if server_content and getattr(
                    server_content, "interrupted", False
                ):
                    self.buffer_audio.limpar()
                    self.limpar_fila_saida()
                    self.registrar_diagnostico(
                        "Turno interrompido: descartei o audio que ainda "
                        "nao tinha tocado."
                    )

                if (
                    server_content
                    and getattr(
                        server_content,
                        "turn_complete",
                        False,
                    )
                ):
                    # Libera novamente o áudio quando o turno termina.
                    self.silenciar_audio_ate_fim_turno = False

                    if self.faltas_de_audio:
                        self.registrar_diagnostico(
                            f"Audio faltou {self.faltas_de_audio} vezes "
                            "neste turno: a placa pediu som e o buffer "
                            "estava vazio."
                        )
                        self.faltas_de_audio = 0

                    self.agendar_liberacao_microfone()

    # Coloca a ferramenta pedida pelo modelo para rodar em segundo plano.
    def agendar_chamada_de_funcao(
        self,
        sessao,
        tool_call,
        fila_microfone,
    ):
        """
        Executa a ferramenta sem travar a leitura do WebSocket.

        Antes, o processamento era aguardado dentro do laço que lê a
        sessão. Uma ferramenta demorada, como o clique visual (que soma
        até duas chamadas de visão, cada uma com três tentativas),
        deixava o ALF dezenas de segundos sem ler nada da conexão.
        Nesse intervalo o aviso GoAway do servidor não era visto, a
        renovação da sessão não acontecia e a conexão caía com o código
        1006. Era daí que vinha boa parte dos reinícios seguidos.

        A ordem das respostas continua garantida: cada ferramenta só
        começa depois que a anterior termina.
        """

        anterior = self.tarefa_ferramenta_atual

        async def executar_em_ordem():
            if anterior is not None and not anterior.done():
                await asyncio.gather(
                    anterior,
                    return_exceptions=True,
                )

            await self.processar_chamada_de_funcao(
                sessao,
                tool_call,
                fila_microfone,
            )

        tarefa = asyncio.create_task(
            executar_em_ordem()
        )

        # Sem este callback, uma falha na ferramenta viraria um
        # "Task exception was never retrieved" solto no console.
        def registrar_falha(tarefa_concluida):
            if tarefa_concluida.cancelled():
                return

            erro = tarefa_concluida.exception()
            if erro is not None:
                self.registrar_diagnostico(
                    f"Falha na tarefa de ferramenta: {repr(erro)}"
                )

        tarefa.add_done_callback(registrar_falha)

        self.tarefa_ferramenta_atual = tarefa
        return tarefa

    # Executa todas as ferramentas solicitadas pelo Gemini.
    async def processar_chamada_de_funcao(
        self,
        sessao,
        tool_call,
        fila_microfone,
    ):

        self.processando_ferramenta = True
        self.alfred_falando = True
        self.limpar_fila_microfone(fila_microfone)

        try:
            function_responses = []
            # Controla se a chamada deve terminar após a despedida.
            encerrar_depois = False

            # Uma única resposta do modelo pode solicitar várias funções.
            for chamada in tool_call.function_calls:
                # Nome da função solicitada.
                nome = chamada.name
                # Converte os argumentos recebidos para um dicionário.
                args = dict(
                    chamada.args or {}
                )

                # Trata as funções de visão em um bloco específico.
                if nome in (
                    "analisar_tela",
                    "analisar_camera",
                ):
                    resultado = await self.processar_funcao_visual(
                        nome
                    )

                # Cria uma pasta na Área de Trabalho.
                elif nome == "criar_pasta_area_trabalho":
                    nome_pasta = args.get(
                        "nome",
                        "",
                    )

                    self.status_recebido.emit(
                        f"Criando pasta: {nome_pasta}"
                    )

                    resultado = await self.executar_funcao_local(
                        criar_pasta_area_trabalho,
                        nome_pasta,
                        timeout=15,
                    )

                # Lista os itens existentes na Área de Trabalho.
                elif nome == "listar_area_de_trabalho":
                    self.status_recebido.emit(
                        "Listando área de trabalho..."
                    )

                    resultado = await self.executar_funcao_local(
                        listar_area_de_trabalho,
                        timeout=15,
                    )

                # Organiza arquivos por extensão.
                elif nome == "organizar_area_de_trabalho_basico":
                    self.status_recebido.emit(
                        "Organizando área de trabalho..."
                    )

                    resultado = await self.executar_funcao_local(
                        organizar_area_de_trabalho_basico,
                        timeout=15,
                    )

                # Prepara um item para ser copiado.
                elif nome == "copiar_item_area_trabalho":
                    nome_item = args.get(
                        "nome",
                        "",
                    )
                    pasta_origem = args.get(
                        "pasta_origem",
                        "",
                    )

                    self.status_recebido.emit(
                        f"Preparando cópia: {nome_item}"
                    )

                    resultado = await self.executar_funcao_local(
                        copiar_item_area_trabalho,
                        nome_item,
                        pasta_origem,
                        timeout=15,
                    )

                # Prepara um item para ser movido.
                elif nome == "recortar_item_area_trabalho":
                    nome_item = args.get(
                        "nome",
                        "",
                    )
                    pasta_origem = args.get(
                        "pasta_origem",
                        "",
                    )

                    self.status_recebido.emit(
                        f"Preparando movimentação: {nome_item}"
                    )

                    resultado = await self.executar_funcao_local(
                        recortar_item_area_trabalho,
                        nome_item,
                        pasta_origem,
                        timeout=15,
                    )

                # Cola o item anteriormente preparado.
                elif nome == "colar_item_area_trabalho":
                    pasta_destino = args.get(
                        "pasta_destino",
                        "",
                    )

                    self.status_recebido.emit(
                        "Colando item na Área de Trabalho..."
                    )

                    resultado = await self.executar_funcao_local(
                        colar_item_area_trabalho,
                        pasta_destino,
                        timeout=15,
                    )

                # Renomeia um arquivo ou pasta.
                elif nome == "renomear_item_area_trabalho":
                    nome_atual = args.get(
                        "nome_atual",
                        "",
                    )
                    novo_nome = args.get(
                        "novo_nome",
                        "",
                    )
                    pasta_origem = args.get(
                        "pasta_origem",
                        "",
                    )

                    self.status_recebido.emit(
                        f"Renomeando: {nome_atual}"
                    )

                    resultado = await self.executar_funcao_local(
                        renomear_item_area_trabalho,
                        nome_atual,
                        novo_nome,
                        pasta_origem,
                        timeout=15,
                    )

                # Cancela uma operação pendente de copiar ou recortar.
                elif nome == "cancelar_transferencia_area_trabalho":
                    self.status_recebido.emit(
                        "Cancelando operação de arquivo..."
                    )

                    resultado = await self.executar_funcao_local(
                        cancelar_transferencia_area_trabalho,
                        timeout=15,
                    )

                # Cria um compromisso na agenda persistente.
                elif nome == "criar_evento_agenda":
                    titulo = args.get(
                        "titulo",
                        "",
                    )

                    data_hora = args.get(
                        "data_hora",
                        "",
                    )

                    self.status_recebido.emit(
                        f"Salvando na agenda: {titulo}"
                    )

                    resultado = await self.executar_funcao_local(
                        criar_evento,
                        titulo,
                        data_hora,
                        timeout=15,
                    )

                # Consulta os próximos compromissos.
                elif nome == "listar_agenda":
                    self.status_recebido.emit(
                        "Consultando agenda..."
                    )

                    resultado = await self.executar_funcao_local(
                        listar_eventos,
                        timeout=15,
                    )

                # Remove um compromisso da agenda.
                elif nome == "cancelar_evento_agenda":
                    referencia = args.get(
                        "referencia",
                        "",
                    )

                    self.status_recebido.emit(
                        "Cancelando compromisso..."
                    )

                    resultado = await self.executar_funcao_local(
                        cancelar_evento,
                        referencia,
                        timeout=15,
                    )

                # Abre um aplicativo ou recurso permitido.
                elif nome == "abrir_aplicativo":
                    nome_app = args.get(
                        "nome",
                        "",
                    )

                    self.status_recebido.emit(
                        f"Abrindo: {nome_app}"
                    )

                    resultado = await self.executar_funcao_local(
                        abrir_aplicativo,
                        nome_app,
                        timeout=15,
                    )

                # Abre uma pesquisa no navegador padrão.
                elif nome == "pesquisar_no_navegador":
                    consulta = args.get(
                        "consulta",
                        "",
                    )

                    self.status_recebido.emit(
                        f"Pesquisando: {consulta}"
                    )

                    resultado = await self.executar_funcao_local(
                        pesquisar_no_navegador,
                        consulta,
                        timeout=15,
                    )

                # Pesquisa dados atuais sem abrir navegador visível.
                elif nome == "pesquisar_informacao_atual":
                    consulta = args.get(
                        "consulta",
                        "",
                    )

                    decisao_pesquisa = avaliar_necessidade_pesquisa(
                        consulta
                    )

                    if not decisao_pesquisa.pesquisar:
                        self.status_recebido.emit(
                            "Pesquisa atual não necessária. "
                            "Respondendo sem consultar a internet."
                        )

                        resultado = resposta_sem_pesquisa(
                            consulta
                        )

                    else:
                        self.status_recebido.emit(
                            f"Consultando informação atual: {consulta}"
                        )

                        resultado = await self.executar_funcao_local(
                            pesquisar_informacao_atual,
                            consulta,
                            timeout=15,
                        )

                # Pesquisa e abre um vídeo ou música no YouTube.
                elif nome == "tocar_no_youtube":
                    busca = args.get(
                        "busca",
                        "",
                    )

                    self.status_recebido.emit(
                        f"Abrindo no YouTube: {busca}"
                    )

                    resultado = await self.executar_funcao_local(
                        tocar_no_youtube,
                        busca,
                        timeout=15,
                    )

                # Insere texto no campo atualmente ativo no Windows.
                elif nome == "escrever_no_campo_ativo":
                    texto = args.get(
                        "texto",
                        "",
                    )

                    # Evita que o ALFRED fale ao mesmo tempo em que cola o texto.
                    self.silenciar_audio_ate_fim_turno = True

                    self.status_recebido.emit(
                        "Escrevendo no campo selecionado..."
                    )

                    # Executa a automação fora do loop principal e com timeout.
                    resultado = await self.executar_funcao_local(
                        escrever_no_campo_ativo,
                        texto,
                        timeout=20,
                    )

                # Envia um atalho de teclado (ex.: ctrl+n) ao programa em foco.
                elif nome == "pressionar_atalho_teclado":
                    teclas = args.get(
                        "teclas",
                        "",
                    )

                    # A ação deve acontecer em silêncio, sem falar por cima.
                    self.silenciar_audio_ate_fim_turno = True

                    self.status_recebido.emit(
                        f"Pressionando atalho: {teclas}"
                    )

                    resultado = await self.executar_funcao_local(
                        pressionar_atalho_teclado,
                        teclas,
                        timeout=10,
                    )

                # Executa a rolagem da janela sob o ponteiro.
                elif nome == "rolar_pagina":
                    direcao = args.get("direcao", "")
                    quantidade = args.get("quantidade", 3)

                    # A rolagem deve acontecer em silêncio.
                    # Qualquer resposta de áudio gerada após a função
                    # será descartada até o fim deste turno.
                    # A resposta de voz é bloqueada porque essa ação
                    # deve acontecer silenciosamente.
                    self.silenciar_audio_ate_fim_turno = True

                    self.status_recebido.emit(
                        f"Rolando página para {direcao}..."
                    )

                    resultado = await self.executar_funcao_local(
                        rolar_pagina,
                        direcao,
                        quantidade,
                        timeout=15,
                    )

                # Executa clique simples na posição atual.
                elif nome == "clicar_mouse":
                    self.status_recebido.emit(
                        "Executando clique..."
                    )

                    resultado = await self.executar_funcao_local(
                        clicar_mouse,
                        timeout=15,
                    )

                # Executa clique duplo na posição atual.
                elif nome == "duplo_clique_mouse":
                    self.status_recebido.emit(
                        "Executando clique duplo..."
                    )

                    resultado = await self.executar_funcao_local(
                        duplo_clique_mouse,
                        timeout=15,
                    )

                # Executa clique com o botão direito.
                elif nome == "clique_direito_mouse":
                    self.status_recebido.emit(
                        "Executando clique com o botão direito..."
                    )

                    resultado = await self.executar_funcao_local(
                        clique_direito_mouse,
                        timeout=15,
                    )

                # Localiza um elemento pela imagem da tela e clica nele.
                elif nome == "clicar_elemento_visual":
                    alvo = args.get(
                        "alvo",
                        "",
                    )

                    # A resposta de voz é bloqueada porque essa ação
                    # deve acontecer silenciosamente.
                    self.silenciar_audio_ate_fim_turno = True

                    self.status_recebido.emit(
                        f"Localizando na tela: {alvo}"
                    )

                    # Executa a função pesada em outra thread,
                    # evitando bloquear o loop assíncrono.
                    localizacao = await asyncio.to_thread(
                        localizar_elemento_na_tela,
                        alvo,
                    )

                    # Se o elemento foi localizado, utiliza as coordenadas.
                    if localizacao.get("sucesso"):
                        # Move o mouse e clica sem bloquear o áudio.
                        resultado = await asyncio.to_thread(
                            mover_e_clicar,
                            localizacao["x"],
                            localizacao["y"],
                        )

                        # Guarda as duas últimas posições clicadas para
                        # aprender o espaçamento entre linhas repetidas
                        # (ex.: mesma coluna de nota em linhas seguidas).
                        self.historico_cliques_padrao.append(
                            (
                                localizacao["x"],
                                localizacao["y"],
                            )
                        )

                        if len(self.historico_cliques_padrao) > 2:
                            self.historico_cliques_padrao.pop(0)

                        self.status_recebido.emit(
                            "Clique visual executado."
                        )

                    else:
                        resultado = localizacao.get(
                            "mensagem",
                            "Não consegui localizar o elemento.",
                        )

                        self.status_recebido.emit(
                            resultado
                        )

                # Repete o clique num padrão aprendido a partir dos dois
                # últimos cliques visuais (ex.: mesma coluna, próxima linha),
                # sem precisar de uma nova busca visual pela API.
                elif nome == "clicar_campo_seguinte_padrao":
                    quantidade = args.get(
                        "quantidade",
                        1,
                    )

                    try:
                        quantidade = int(quantidade)
                    except (TypeError, ValueError):
                        quantidade = 1

                    if len(self.historico_cliques_padrao) < 2:
                        resultado = (
                            "Ainda não há um padrão aprendido. Use "
                            "clicar_elemento_visual em pelo menos dois campos "
                            "semelhantes antes de repetir o padrão."
                        )

                        self.status_recebido.emit(
                            resultado
                        )

                    else:
                        # A resposta de voz é bloqueada porque essa ação
                        # deve acontecer silenciosamente.
                        self.silenciar_audio_ate_fim_turno = True

                        (x1, y1), (x2, y2) = self.historico_cliques_padrao
                        delta_x = x2 - x1
                        delta_y = y2 - y1

                        novo_x = x2 + delta_x * quantidade
                        novo_y = y2 + delta_y * quantidade

                        self.status_recebido.emit(
                            "Repetindo padrão de clique aprendido..."
                        )

                        resultado = await asyncio.to_thread(
                            mover_e_clicar,
                            novo_x,
                            novo_y,
                        )

                        # Desloca a janela do histórico para a nova posição,
                        # permitindo repetir o mesmo padrão novamente em seguida.
                        self.historico_cliques_padrao = [
                            (x2, y2),
                            (novo_x, novo_y),
                        ]

                        self.status_recebido.emit(
                            "Clique padrão executado."
                        )

                # Salva uma nova memória persistente.
                elif nome == "salvar_memoria":
                    texto = args.get(
                        "texto",
                        "",
                    )

                    self.status_recebido.emit(
                        "Salvando memória..."
                    )

                    resultado = await self.executar_funcao_local(
                        salvar_memoria,
                        texto,
                        timeout=15,
                    )

                # Lista as memórias existentes.
                elif nome == "listar_memorias":
                    self.status_recebido.emit(
                        "Consultando memórias..."
                    )

                    resultado = await self.executar_funcao_local(
                        listar_memorias,
                        timeout=15,
                    )

                # Remove uma memória específica.
                elif nome == "esquecer_memoria":
                    referencia = args.get(
                        "referencia",
                        "",
                    )

                    self.status_recebido.emit(
                        "Removendo memória..."
                    )

                    resultado = await self.executar_funcao_local(
                        esquecer_memoria,
                        referencia,
                        timeout=15,
                    )

                # Monta o rascunho do e-mail. Não envia nada.
                elif nome == "preparar_email":
                    self.status_recebido.emit(
                        "Preparando e-mail (ainda não enviado)..."
                    )

                    # A busca do anexo percorre várias pastas, então o
                    # prazo é maior que o das outras ações locais.
                    resultado = await self.executar_funcao_local(
                        preparar_email,
                        args.get("destinatario", ""),
                        args.get("assunto", ""),
                        args.get("mensagem", ""),
                        args.get("anexo", "") or None,
                        timeout=40,
                    )

                # Envia de verdade, só depois da autorização do usuário.
                elif nome == "confirmar_envio_email":
                    self.status_recebido.emit(
                        "Enviando e-mail..."
                    )

                    resultado = await self.executar_funcao_local(
                        confirmar_envio_email,
                        timeout=45,
                    )

                # Descarta o rascunho.
                elif nome == "cancelar_email":
                    self.status_recebido.emit(
                        "Descartando o e-mail..."
                    )

                    resultado = await self.executar_funcao_local(
                        cancelar_email,
                        timeout=15,
                    )

                # Agenda de contatos de e-mail.
                elif nome == "salvar_contato":
                    self.status_recebido.emit(
                        "Guardando contato..."
                    )

                    resultado = await self.executar_funcao_local(
                        salvar_contato,
                        args.get("nome", ""),
                        args.get("email", ""),
                        timeout=15,
                    )

                elif nome == "listar_contatos":
                    self.status_recebido.emit(
                        "Consultando contatos..."
                    )

                    resultado = await self.executar_funcao_local(
                        listar_contatos,
                        timeout=15,
                    )

                elif nome == "remover_contato":
                    self.status_recebido.emit(
                        "Removendo contato..."
                    )

                    resultado = await self.executar_funcao_local(
                        remover_contato,
                        args.get("nome", ""),
                        timeout=15,
                    )

                # Contas autorizadas no Classroom.
                elif nome == "listar_contas":
                    self.status_recebido.emit("Consultando contas...")
                    resultado = await self.executar_funcao_local(
                        listar_contas, timeout=30
                    )

                elif nome == "autorizar_conta":
                    self.status_recebido.emit(
                        "Abrindo o navegador para autorizar a conta..."
                    )
                    # A autorização espera o usuário clicar no navegador,
                    # por isso o prazo é bem maior que o das outras ações.
                    resultado = await self.executar_funcao_local(
                        autorizar_conta, timeout=300
                    )

                # Google Classroom: consultas.
                elif nome == "listar_turmas":
                    self.status_recebido.emit("Consultando turmas...")
                    resultado = await self.executar_funcao_local(
                        listar_turmas, timeout=45
                    )

                elif nome == "listar_atividades":
                    self.status_recebido.emit("Consultando atividades...")
                    resultado = await self.executar_funcao_local(
                        listar_atividades,
                        args.get("turma", ""),
                        timeout=45,
                    )

                elif nome == "listar_entregas":
                    self.status_recebido.emit("Consultando entregas...")
                    resultado = await self.executar_funcao_local(
                        listar_entregas,
                        args.get("turma", ""),
                        args.get("atividade", ""),
                        timeout=60,
                    )

                elif nome == "ler_entrega":
                    self.status_recebido.emit(
                        f"Lendo entrega de {args.get('aluno', '')}..."
                    )
                    resultado = await self.executar_funcao_local(
                        ler_entrega,
                        args.get("turma", ""),
                        args.get("atividade", ""),
                        args.get("aluno", ""),
                        timeout=60,
                    )

                # Cria atividade no Classroom, sempre como rascunho.
                elif nome == "criar_atividade":
                    self.status_recebido.emit(
                        f"Criando atividade: {args.get('titulo', '')}"
                    )
                    # Enviar arquivo para o Drive pode demorar, então o
                    # prazo é maior que o das outras ações.
                    resultado = await self.executar_funcao_local(
                        criar_atividade,
                        args.get("turma", ""),
                        args.get("titulo", ""),
                        args.get("descricao", ""),
                        args.get("pontos", ""),
                        args.get("prazo", ""),
                        args.get("link", ""),
                        args.get("arquivo", ""),
                        args.get("modo_arquivo", "ver"),
                        timeout=180,
                    )

                # Devolve o trabalho corrigido ao aluno.
                elif nome == "devolver_atividade":
                    self.status_recebido.emit(
                        f"Devolvendo atividade de {args.get('aluno', '')}..."
                    )
                    resultado = await self.executar_funcao_local(
                        devolver_atividade,
                        args.get("turma", ""),
                        args.get("atividade", ""),
                        args.get("aluno", ""),
                        timeout=60,
                    )

                # Cria questionário com gabarito no Google Forms.
                elif nome == "criar_questionario":
                    self.status_recebido.emit(
                        f"Criando questionário: {args.get('titulo', '')}"
                    )
                    resultado = await self.executar_funcao_local(
                        criar_questionario,
                        args.get("titulo", ""),
                        args.get("questoes", []),
                        args.get("descricao", ""),
                        "",
                        timeout=90,
                    )

                # Produzir material.
                elif nome == "criar_apresentacao":
                    self.status_recebido.emit(
                        f"Montando apresentação: {args.get('titulo', '')}"
                    )
                    resultado = await self.executar_funcao_local(
                        criar_apresentacao,
                        args.get("titulo", ""),
                        args.get("slides", []),
                        "",
                        timeout=120,
                    )

                elif nome == "criar_documento":
                    self.status_recebido.emit(
                        f"Escrevendo documento: {args.get('titulo', '')}"
                    )
                    resultado = await self.executar_funcao_local(
                        criar_documento,
                        args.get("titulo", ""),
                        args.get("blocos", []),
                        "",
                        timeout=90,
                    )

                elif nome == "criar_planilha":
                    self.status_recebido.emit(
                        f"Criando planilha: {args.get('titulo', '')}"
                    )
                    resultado = await self.executar_funcao_local(
                        criar_planilha,
                        args.get("titulo", ""),
                        args.get("linhas", []),
                        "Página1",
                        "",
                        timeout=90,
                    )

                elif nome == "preparar_transporte":
                    self.status_recebido.emit("Lendo a planilha de notas...")
                    resultado = await self.executar_funcao_local(
                        preparar_transporte,
                        args.get("planilha", ""),
                        args.get("turma", ""),
                        args.get("atividade", ""),
                        timeout=90,
                    )

                elif nome == "lancar_proxima_nota":
                    self.status_recebido.emit("Digitando a próxima nota...")
                    # Localizar, digitar e conferir envolve duas chamadas
                    # de visão, por isso o prazo maior.
                    # Varrer a lista com o Google sobrecarregado passa de
                    # 90 s. Estourar o prazo não para a digitação, só faz
                    # o ALF desistir de esperar por ela.
                    resultado = await self.executar_funcao_local(
                        lancar_proxima_nota,
                        timeout=240,
                    )

                elif nome == "conferir_transporte":
                    self.status_recebido.emit(
                        "Conferindo as notas no Classroom..."
                    )
                    resultado = await self.executar_funcao_local(
                        conferir_transporte,
                        args.get("turma", ""),
                        args.get("atividade", ""),
                        timeout=60,
                    )

                elif nome == "estado_do_transporte":
                    resultado = await self.executar_funcao_local(
                        estado_do_transporte, timeout=15
                    )

                elif nome == "cancelar_transporte":
                    self.status_recebido.emit("Parando o transporte...")
                    resultado = await self.executar_funcao_local(
                        cancelar_transporte, timeout=15
                    )

                elif nome == "montar_planilha_de_correcao":
                    self.status_recebido.emit(
                        "Montando planilha de correção..."
                    )
                    resultado = await self.executar_funcao_local(
                        montar_planilha_de_correcao,
                        args.get("turma", ""),
                        args.get("atividade", ""),
                        args.get("avaliacoes", []),
                        "",
                        timeout=180,
                    )

                elif nome == "criar_planilha_de_notas":
                    self.status_recebido.emit(
                        f"Montando planilha de notas: {args.get('turma', '')}"
                    )
                    resultado = await self.executar_funcao_local(
                        criar_planilha_de_notas,
                        args.get("turma", ""),
                        args.get("colunas", ""),
                        "",
                        timeout=120,
                    )

                elif nome == "listar_respostas":
                    self.status_recebido.emit("Consultando respostas...")
                    resultado = await self.executar_funcao_local(
                        listar_respostas,
                        args.get("id_ou_link", ""),
                        "",
                        timeout=45,
                    )

                # Devolução com comentário: prepara, e depois um por vez.
                elif nome == "preparar_devolucao":
                    self.status_recebido.emit("Preparando a devolução...")
                    resultado = await self.executar_funcao_local(
                        preparar_devolucao,
                        args.get("turma", ""),
                        args.get("atividade", ""),
                        timeout=60,
                    )

                elif nome == "devolver_proximo_aluno":
                    self.status_recebido.emit(
                        "Comentando e devolvendo o próximo aluno..."
                    )
                    # Achar o aluno, conferir o painel, digitar, conferir,
                    # enviar e conferir de novo: várias leituras de tela.
                    resultado = await self.executar_funcao_local(
                        devolver_proximo_aluno, timeout=300
                    )

                elif nome == "cancelar_devolucao":
                    resultado = await self.executar_funcao_local(
                        cancelar_devolucao, timeout=15
                    )

                # A turma inteira, como rascunho, sem confirmar por aluno.
                elif nome == "lancar_notas_em_lote":
                    self.status_recebido.emit(
                        "Lançando as notas como rascunho..."
                    )
                    resultado = await self.executar_funcao_local(
                        lancar_notas_em_lote,
                        args.get("turma", ""),
                        args.get("atividade", ""),
                        args.get("avaliacoes", []),
                        timeout=180,
                    )

                # Prepara a nota. Não lança nada.
                elif nome == "preparar_nota":
                    self.status_recebido.emit(
                        "Preparando nota (ainda não lançada)..."
                    )
                    resultado = await self.executar_funcao_local(
                        preparar_nota,
                        args.get("turma", ""),
                        args.get("atividade", ""),
                        args.get("aluno", ""),
                        args.get("nota", ""),
                        timeout=60,
                    )

                # Lança de verdade, só depois da autorização.
                elif nome == "confirmar_nota":
                    self.status_recebido.emit("Lançando nota...")
                    resultado = await self.executar_funcao_local(
                        confirmar_nota, timeout=45
                    )

                elif nome == "cancelar_nota":
                    self.status_recebido.emit("Descartando a nota...")
                    resultado = await self.executar_funcao_local(
                        cancelar_nota, timeout=15
                    )

                # Lê um arquivo de código para poder alterá-lo de verdade.
                elif nome == "ler_arquivo":
                    caminho_arquivo = args.get("caminho", "")

                    self.status_recebido.emit(
                        f"Lendo: {caminho_arquivo}"
                    )

                    resultado = await self.executar_funcao_local(
                        ler_arquivo,
                        caminho_arquivo,
                        timeout=20,
                    )

                # Cria ou substitui um arquivo de código.
                elif nome == "criar_arquivo_codigo":
                    caminho_arquivo = args.get("caminho", "")
                    conteudo_arquivo = args.get("conteudo", "")
                    sobrescrever = bool(args.get("sobrescrever", False))

                    self.status_recebido.emit(
                        f"Gravando: {caminho_arquivo}"
                    )

                    resultado = await self.executar_funcao_local(
                        criar_arquivo_codigo,
                        caminho_arquivo,
                        conteudo_arquivo,
                        sobrescrever,
                        timeout=30,
                    )

                # Roda um comando de desenvolvimento.
                elif nome == "executar_no_terminal":
                    comando_terminal = args.get("comando", "")
                    pasta_terminal = args.get("pasta", "")

                    self.status_recebido.emit(
                        f"Executando: {comando_terminal}"
                    )

                    # O prazo acompanha o limite interno da função, que
                    # já interrompe o processo por conta própria.
                    resultado = await self.executar_funcao_local(
                        executar_no_terminal,
                        comando_terminal,
                        pasta_terminal or None,
                        timeout=150,
                    )

                # Abre pasta ou arquivo dentro do VS Code.
                elif nome == "abrir_no_vscode":
                    caminho_alvo = args.get(
                        "caminho",
                        "",
                    )
                    nova_janela = bool(
                        args.get(
                            "nova_janela",
                            False,
                        )
                    )

                    self.status_recebido.emit(
                        f"Abrindo no VS Code: {caminho_alvo}"
                    )

                    # A busca percorre várias pastas do usuário, então
                    # recebe um prazo maior que as outras ações locais.
                    resultado = await self.executar_funcao_local(
                        abrir_no_vscode,
                        caminho_alvo,
                        nova_janela,
                        timeout=30,
                    )

                # Executa um comando interno pela paleta do VS Code.
                elif nome == "executar_comando_vscode":
                    comando_vscode = args.get(
                        "comando",
                        "",
                    )

                    self.status_recebido.emit(
                        f"Comando no VS Code: {comando_vscode}"
                    )

                    resultado = await self.executar_funcao_local(
                        executar_comando_vscode,
                        comando_vscode,
                        timeout=20,
                    )

                # Fecha um programa aberto pelo nome.
                elif nome == "fechar_aplicativo":
                    nome_programa = args.get(
                        "nome",
                        "",
                    )

                    self.status_recebido.emit(
                        f"Fechando: {nome_programa}"
                    )

                    resultado = await self.executar_funcao_local(
                        fechar_aplicativo,
                        nome_programa,
                        timeout=15,
                    )

                # Anota, por iniciativa própria, como o usuário trabalha.
                elif nome == "anotar_preferencia":
                    preferencia = args.get(
                        "preferencia",
                        "",
                    )

                    resultado = await self.executar_funcao_local(
                        anotar_preferencia,
                        preferencia,
                        timeout=15,
                    )

                # Mostra o que o ALF aprendeu sozinho.
                elif nome == "listar_preferencias":
                    self.status_recebido.emit(
                        "Consultando preferências aprendidas..."
                    )

                    resultado = await self.executar_funcao_local(
                        listar_preferencias,
                        timeout=15,
                    )

                # Remove uma preferência errada.
                elif nome == "esquecer_preferencia":
                    referencia = args.get(
                        "referencia",
                        "",
                    )

                    self.status_recebido.emit(
                        "Removendo preferência aprendida..."
                    )

                    if str(referencia).strip().lower() in ("todas", "tudo"):
                        resultado = await self.executar_funcao_local(
                            esquecer_todas_preferencias,
                            timeout=15,
                        )
                    else:
                        resultado = await self.executar_funcao_local(
                            esquecer_preferencia,
                            referencia,
                            timeout=15,
                        )

                # Marca a sessão para encerrar após a despedida.
                elif nome == "encerrar_chamada":
                    self.status_recebido.emit(
                        "Encerrando chamada por comando de voz..."
                    )

                    resultado = (
                        "Solicitação de encerramento recebida. "
                        "Diga de forma curta que a chamada será encerrada."
                    )

                    encerrar_depois = True

                # Lê uma planilha .xlsx de notas na Área de Trabalho/Downloads.
                elif nome == "ler_planilha_notas":
                    nome_arquivo = args.get(
                        "nome_arquivo",
                        "",
                    )
                    aba = args.get(
                        "aba",
                        "",
                    )

                    self.status_recebido.emit(
                        f"Lendo planilha: {nome_arquivo}"
                    )

                    resultado = await self.executar_funcao_local(
                        ler_planilha_notas,
                        nome_arquivo,
                        aba,
                        timeout=20,
                    )

                # Trata chamadas desconhecidas com segurança.
                else:
                    resultado = (
                        "Função desconhecida. Nenhuma ação foi executada."
                    )

                self.registrar_resultado_de_ferramenta(nome, resultado)

                # Adiciona o resultado da função à lista de respostas.
                function_responses.append(
                    types.FunctionResponse(
                        id=chamada.id,
                        name=nome,
                        response={
                            "result": resultado
                        },
                    )
                )

            # Envia os resultados de volta ao Gemini.
            if function_responses:
                async with self.lock_envio:
                    await sessao.send_tool_response(
                        function_responses=(
                            function_responses
                        )
                    )

                # Somente depois de responder à ferramenta enviamos a imagem.
                if self.imagem_visual_pendente is not None:
                    await self.enviar_imagem_visual_pendente(sessao)

            # Agenda o encerramento após o modelo responder.
            if encerrar_depois:
                if self.tarefa_encerramento:
                    self.tarefa_encerramento.cancel()

                self.tarefa_encerramento = asyncio.create_task(
                    self.encerrar_apos_resposta()
                )

        # Captura falhas da ferramenta para avisar a interface e liberar
        # o microfone sem deixar a sessão presa em estado intermediário.
        except asyncio.CancelledError:
            # Se a ação foi cancelada no meio do caminho, nenhum
            # turn_complete virá para liberar o áudio: libera aqui para
            # não travar as respostas por voz seguintes para sempre.
            self.silenciar_audio_ate_fim_turno = False
            raise
        except Exception as erro:
            # A ação falhou antes de enviar a resposta da ferramenta ao
            # modelo: nenhum turn_complete virá, então libera o áudio
            # aqui também para não travar as respostas por voz seguintes.
            self.silenciar_audio_ate_fim_turno = False

            self.erro_recebido.emit(
                f"Falha ao executar ferramenta: {erro}"
            )

        finally:
            self.processando_ferramenta = False
            self.limpar_fila_microfone(fila_microfone)

            # A ferramenta agora roda em paralelo com a recepção, então
            # o ALF pode já estar falando quando ela termina. Liberar o
            # microfone direto aqui o reabriria no meio da fala e ele
            # escutaria a própria voz. A liberação agendada espera o
            # áudio acabar de verdade.
            self.agendar_liberacao_microfone()

    # Aguarda a fala final do ALFRED antes de encerrar a interface.
    async def encerrar_apos_resposta(self):
        """
        Aguarda a resposta de despedida do ALFRED
        e só depois solicita o encerramento à interface.
        """

        try:
            # Pequena espera para permitir a reprodução da despedida.
            await asyncio.sleep(
                2.8
            )

            # Só solicita encerramento se a sessão ainda estiver ativa.
            if self.ativo:
                self.solicitou_encerramento.emit()

        except asyncio.CancelledError:
            pass

    # Controla o uso das funções de tela e câmera.
    async def processar_funcao_visual(
        self,
        nome,
    ):
        if self.executando_funcao_visual:
            return (
                "Uma análise visual já está em andamento. "
                "Aguarde a imagem atual."
            )

        agora = time.monotonic()
        repetido = (
            nome == self.ultima_funcao_visual
            and agora - self.tempo_ultima_funcao_visual
            < COOLDOWN_FUNCAO_VISUAL
        )
        if repetido:
            # Só descarta a chamada quando a captura anterior ainda está
            # na fila para ser enviada, ou seja, quando é realmente a
            # mesma solicitação repetida. Nunca manda o modelo responder
            # com base em uma imagem antiga.
            if self.imagem_visual_pendente is not None:
                return (
                    "Chamada duplicada para o mesmo pedido. "
                    "A captura desta solicitação já está a caminho."
                )

        self.executando_funcao_visual = True
        self.ultima_funcao_visual = nome
        self.tempo_ultima_funcao_visual = agora

        try:
            if nome == "analisar_tela":
                self.status_recebido.emit("Capturando tela...")
                imagem = await asyncio.wait_for(
                    asyncio.to_thread(capturar_tela_bytes),
                    timeout=12,
                )
                self.imagem_visual_pendente = ("tela", imagem)
                self.momento_captura_visual = time.monotonic()
                return (
                    "A tela acabou de ser capturada e será enviada agora. "
                    "Aguarde a imagem e responda apenas com base nela."
                )

            if nome == "analisar_camera":
                self.status_recebido.emit("Capturando imagem da câmera...")
                imagem = await asyncio.wait_for(
                    asyncio.to_thread(capturar_camera_bytes),
                    timeout=15,
                )
                self.imagem_visual_pendente = ("camera", imagem)
                self.momento_captura_visual = time.monotonic()
                return (
                    "A câmera acabou de ser capturada e será enviada agora. "
                    "Aguarde a imagem e responda apenas com base nela."
                )

            return "Função visual desconhecida."

        except asyncio.TimeoutError:
            return "A captura visual demorou demais e foi cancelada com segurança."
        except Exception as erro:
            return f"Não foi possível capturar a imagem: {erro}"
        finally:
            self.executando_funcao_visual = False

    async def enviar_imagem_visual_pendente(self, sessao):
        pendente = self.imagem_visual_pendente
        momento = self.momento_captura_visual
        self.imagem_visual_pendente = None
        self.momento_captura_visual = None

        if pendente is None:
            return

        # Se a captura ficou parada tempo demais entre a resposta da
        # ferramenta e o envio, a tela do usuário já mudou. Enviar essa
        # imagem faria o ALF descrever algo que não está mais lá.
        if (
            momento is not None
            and time.monotonic() - momento > VALIDADE_CAPTURA_VISUAL
        ):
            self.registrar_diagnostico(
                "Captura visual descartada por estar desatualizada."
            )
            return

        tipo, imagem_bytes = pendente
        origem = "tela" if tipo == "tela" else "câmera"

        await self.enviar_imagem_para_analise(
            sessao,
            imagem_bytes,
            origem,
            self.montar_instrucao_visual(origem),
        )

        self.status_recebido.emit(
            f"Imagem da {origem} enviada para análise."
        )

    @staticmethod
    def montar_instrucao_visual(origem):
        """
        Texto que acompanha a imagem enviada ao modelo.

        O carimbo de hora e a ordem de ignorar imagens anteriores são o
        que impede o modelo de responder usando uma captura antiga que
        continua no histórico da conversa.
        """

        horario = datetime.now().strftime("%H:%M:%S")

        return (
            f"Esta é a captura MAIS RECENTE da {origem}, feita agora "
            f"às {horario}. Ignore completamente qualquer imagem "
            "enviada antes nesta conversa: elas estão desatualizadas. "
            "Responda usando somente esta imagem. "
            "Não chame nenhuma função visual de novo. "
            "Se a imagem não estiver clara, diga isso. "
            "Responda de forma objetiva."
        )

    def registrar_atraso_da_resposta(self):
        """
        Grava quanto tempo o ALF levou para começar a responder.

        "Demora muito para responder" é uma queixa que não dá para
        investigar sem número. Mede da última voz ouvida no microfone
        até o primeiro pedaço de áudio da resposta chegar.

        Inclui o tempo que o servidor leva para decidir que a fala
        acabou, o que é honesto: para quem está esperando, isso também
        é demora.

        Devolve os segundos, ou None quando ninguém falou desde a última
        resposta -- os pedaços seguintes do mesmo turno não contam, e
        silêncio do usuário não vira lentidão do ALF.
        """

        if self.momento_ultima_voz is None:
            return None

        atraso = time.monotonic() - self.momento_ultima_voz
        self.momento_ultima_voz = None

        self.registrar_diagnostico(
            f"Resposta comecou {atraso:.1f}s depois da ultima voz ouvida."
        )

        return atraso

    async def abrir_conversa(self, sessao):
        """
        Faz o ALF falar primeiro, assim que a chamada abre.

        A instrução manda ele exigir a palavra-chave e, até lá, não
        preencher o silêncio. Numa sessão nova não existe turno nenhum,
        então ele aplicava a segunda metade da regra e nunca a primeira:
        o áudio do microfone chegava, ele decidia não responder, e a
        chamada ficava muda.

        O que destravava era o botão de analisar tela, porque a imagem
        vai como turno do usuário (send_client_content). Daí o sintoma
        "só responde se eu clicar em analisar tela primeiro".

        Este turno de abertura não enfraquece a autenticação: ele apenas
        dá a deixa para o ALF pedir a palavra-chave em voz alta.
        """

        try:
            async with self.lock_envio:
                await sessao.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=TEXTO_ABERTURA
                            )
                        ],
                    ),
                    turn_complete=True,
                )

        except Exception as erro:
            # Sem abertura a chamada ainda funciona, só volta a depender
            # de o usuário destravar. Não vale derrubar a sessão por isso.
            self.registrar_diagnostico(
                f"Falha ao abrir a conversa: {repr(erro)}"
            )
            return

        self.registrar_diagnostico(
            "Turno de abertura enviado: o ALF fala primeiro."
        )

    async def enviar_imagem_para_analise(
        self,
        sessao,
        imagem_bytes,
        origem,
        instrucao,
    ):
        """
        Manda a imagem como um turno do usuário, não como quadro de vídeo.

        Antes isto usava send_realtime_input(video=...), que trata a
        imagem como um quadro de uma transmissão ao vivo. Medido em
        teste controlado com duas imagens diferentes em sequência:

          send_realtime_input  -> 1a pergunta: "não vejo imagem alguma"
                                  2a pergunta: descreve a PRIMEIRA imagem
          send_client_content  -> 1a pergunta: descreve a primeira
                                  2a pergunta: descreve a segunda

        Ou seja, o caminho antigo deixava o modelo sempre um turno
        atrasado. Era isso que fazia o ALF comentar abas do navegador
        que o usuário já tinha fechado: ele descrevia a captura
        anterior, não a atual.
        """

        await self.finalizar_fluxo_audio_pendente(sessao)

        async with self.lock_envio:
            await sessao.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                data=imagem_bytes,
                                mime_type="image/jpeg",
                            )
                        ),
                        types.Part(
                            text=instrucao
                        ),
                    ],
                ),
                turn_complete=True,
            )

        self.registrar_diagnostico(
            f"Imagem da {origem} enviada como turno do usuario."
        )

    async def executar_funcao_local(
        self,
        funcao,
        *args,
        timeout=15,
    ):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(funcao, *args),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return (
                "A operação demorou mais que o esperado e foi "
                "interrompida com segurança."
            )
        except Exception as erro:
            return f"A operação não pôde ser concluída: {erro}"

    async def finalizar_fluxo_audio_pendente(
        self,
        sessao,
    ):
        if not self.fluxo_audio_em_andamento:
            return

        async with self.lock_envio:
            if not self.fluxo_audio_em_andamento:
                return

            await sessao.send_realtime_input(
                audio_stream_end=True
            )
            self.fluxo_audio_em_andamento = False
            self.usuario_falando_detectado = False
            self.ultimo_audio_com_voz = None
            self.registrar_diagnostico(
                "Fluxo de audio do microfone finalizado com audio_stream_end."
            )

    async def preparar_pausa_microfone(
        self,
        sessao,
        fila_microfone,
        aguardar_envio=True,
    ):
        """
        Fecha o microfone enquanto o ALF fala.

        aguardar_envio=False existe para quem chama de dentro do laço
        que lê o WebSocket. Ver _agendar_fim_do_fluxo.
        """

        self.alfred_falando = True

        if self.tarefa_liberar_microfone:
            self.tarefa_liberar_microfone.cancel()

        self.limpar_fila_microfone(
            fila_microfone
        )

        if aguardar_envio:
            await self.finalizar_fluxo_audio_pendente(sessao)
        else:
            self._agendar_fim_do_fluxo(sessao)

    def _agendar_fim_do_fluxo(self, sessao):
        """
        Envia o audio_stream_end sem travar quem chamou.

        O laço que lê o WebSocket chamava preparar_pausa_microfone a
        cada bloco de áudio recebido, e isso esperava pelo lock de
        envio -- que o microfone segura enquanto manda o bloco dele.
        Numa conexão congestionada, que é justamente quando o áudio
        começa a picotar, a leitura parava, o socket deixava de ser
        drenado e o servidor abortava a sessão com o código 1008.

        Agendar em vez de esperar mantém a leitura sempre correndo.
        """

        if not self.fluxo_audio_em_andamento:
            return

        anterior = self.tarefa_fim_de_fluxo
        if anterior is not None and not anterior.done():
            return

        async def enviar():
            try:
                await self.finalizar_fluxo_audio_pendente(sessao)
            except Exception as erro:
                self.registrar_diagnostico(
                    f"Falha ao encerrar o fluxo de audio: {repr(erro)}"
                )

        self.tarefa_fim_de_fluxo = asyncio.create_task(enviar())

    def agendar_liberacao_microfone(self):
        if self.tarefa_liberar_microfone:
            self.tarefa_liberar_microfone.cancel()

        self.tarefa_liberar_microfone = asyncio.create_task(
            self.liberar_microfone_apos_fala()
        )

    # Reproduz os blocos de áudio gerados pelo Gemini.
    async def reproduzir_audio(
        self,
        fila_saida,
        fila_microfone,
    ):
        # Guarda a fila para que a liberação do microfone consiga
        # verificar se ainda existe áudio esperando para tocar.
        self.fila_saida = fila_saida

        self.buffer_audio.limpar()
        buffer = self.buffer_audio

        # A placa de som chama isto sozinha, na thread dela. Só copia
        # bytes de um buffer em memória: nada de rede, nada de espera.
        # Faltando áudio, preenche com silêncio em vez de travar.
        def alimentar(saida_bruta, quadros, tempo, situacao):
            necessario = quadros * 2  # int16 mono
            pedaco = buffer.retirar(necessario)

            if len(pedaco) < necessario:
                # Só conta como falta se era para estar falando: com o
                # ALF calado, o buffer vazio é o estado normal.
                if self.alfred_falando:
                    self.faltas_de_audio += 1

                saida_bruta[: len(pedaco)] = pedaco
                saida_bruta[len(pedaco):] = b"\x00" * (necessario - len(pedaco))
            else:
                saida_bruta[:] = pedaco

        # latency="high" dá ao PortAudio um buffer interno maior, o que
        # ajuda a absorver a irregularidade com que o áudio chega.
        with sd.RawOutputStream(
            samplerate=TAXA_SAIDA,
            blocksize=BLOCO_SAIDA,
            dtype="int16",
            channels=CANAIS,
            latency="high",
            callback=alimentar,
        ):
            while self.ativo:
                audio_bytes = await fila_saida.get()

                # Começo de uma fala: acumula um pouco antes de entregar.
                # Sem isto o primeiro trecho sai picotado, porque a placa
                # consome mais rápido do que a rede entrega.
                if buffer.tamanho() == 0:
                    audio_bytes += await self.acumular_pre_buffer(fila_saida)

                buffer.acrescentar(audio_bytes)

                # Mantém o microfone bloqueado durante toda a reprodução
                # e descarta qualquer bloco antigo que ainda tenha sobrado.
                self.alfred_falando = True
                self.reproduzindo_bloco = True
                self.limpar_fila_microfone(
                    fila_microfone
                )

                # Calcula o volume para animação da interface.
                self.nivel_audio.emit(
                    self.calcular_nivel_audio(audio_bytes)
                )

    async def acumular_pre_buffer(self, fila_saida):
        """
        Junta um pouco de áudio antes de começar a tocar.

        Devolve os bytes extras. Espera no máximo o tempo do próprio
        amortecedor: se a resposta for curta e não vier mais nada, toca
        o que tem em vez de segurar a fala.
        """

        alvo = int(TAXA_SAIDA * PRE_BUFFER_SEGUNDOS) * 2  # 2 bytes por amostra
        juntado = bytearray()
        prazo = time.monotonic() + PRE_BUFFER_SEGUNDOS

        while len(juntado) < alvo:
            restante = prazo - time.monotonic()
            if restante <= 0:
                break

            try:
                juntado += await asyncio.wait_for(
                    fila_saida.get(), timeout=restante
                )
            except asyncio.TimeoutError:
                break

        if fila_saida.qsize() > LIMITE_AVISO_FILA_SAIDA:
            self.registrar_diagnostico(
                f"Fila de audio acumulada: {fila_saida.qsize()} blocos. "
                "A reproducao nao esta acompanhando a rede."
            )

        return bytes(juntado)

    def limpar_fila_saida(self):
        """Joga fora o áudio que ainda não tocou."""

        if self.fila_saida is None:
            return

        while True:
            try:
                self.fila_saida.get_nowait()
            except asyncio.QueueEmpty:
                return

    @staticmethod
    def limpar_fila_microfone(
        fila_microfone,
    ):
        """
        Descarta todos os blocos de áudio que ainda aguardavam envio.
        Isso impede que um trecho capturado antes da resposta seja
        enviado ao Gemini enquanto o ALFRED já está falando.
        """

        while True:
            try:
                fila_microfone.get_nowait()

            except asyncio.QueueEmpty:
                break

    # Trechos que denunciam uma ferramenta que não fez o que devia.
    SINAIS_DE_FALHA = (
        "não consegui",
        "não posso",
        "não encontrei",
        "não tenho",
        "não está",
        "recusou",
        "bloqueado",
        "foi recusad",
        "falhei",
        "erro",
        "expirou",
        "limite",
    )

    @classmethod
    def registrar_resultado_de_ferramenta(cls, nome, resultado):
        """
        Registra no log qual ferramenta rodou e se ela concluiu.

        Quando o lançamento de nota parou de funcionar, o erro voltava
        para o modelo e sumia: não havia como saber depois o que tinha
        acontecido. Sem isto, diagnosticar dependia de reproduzir o
        problema ao vivo.

        Antes só as falhas eram registradas, e isso deixava um buraco:
        quando o ALF dizia que não conseguia escrever num campo do
        Chrome, o log ficava vazio, e não dava para saber se ele tinha
        tentado e falhado ou se nem tinha chamado a função. Agora o
        sucesso também aparece -- só o nome.

        Da falha fica apenas o começo da mensagem, e do sucesso não fica
        nada do conteúdo: o resultado de uma ferramenta costuma trazer
        nome e trabalho de aluno, que não têm por que ficar guardados em
        arquivo.
        """

        texto = str(resultado or "")
        minusculo = texto.lower()

        if not any(sinal in minusculo for sinal in cls.SINAIS_DE_FALHA):
            cls.registrar_diagnostico(f"Ferramenta '{nome}' concluiu.")
            return

        cls.registrar_diagnostico(
            f"Ferramenta '{nome}' nao concluiu: {texto[:160]}"
        )

    # O método seguinte não depende do objeto self.
    @staticmethod
    def caminho_log_diagnostico():
        if getattr(sys, "frozen", False):
            raiz = Path(sys.executable).resolve().parent
        else:
            raiz = Path(__file__).resolve().parent.parent

        return raiz / "logs" / "alf_runtime_debug.log"

    @staticmethod
    def registrar_diagnostico(
        mensagem,
        caminho=None,
    ):
        try:
            caminho_log = Path(caminho) if caminho is not None else GeminiLiveWorker.caminho_log_diagnostico()
            caminho_log.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with caminho_log.open(
                "a",
                encoding="utf-8",
            ) as arquivo:
                arquivo.write(
                    f"[{timestamp}] {mensagem}\n"
                )
        except Exception:
            pass

    @staticmethod
    def criar_contexto_ssl_websocket():
        return criar_contexto_ssl_gemini()

    @staticmethod
    def criar_config_live(
        instrucao_sistema,
        tools,
        session_handle=None,
    ):
        return types.LiveConnectConfig(
            response_modalities=[
                "AUDIO"
            ],
            thinking_config=types.ThinkingConfig(
                thinking_level="minimal"
            ),
            session_resumption=types.SessionResumptionConfig(
                handle=session_handle
            ),
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=GEMINI_VOICE
                    )
                )
            ),
            tools=tools,
            system_instruction=types.Content(
                parts=[
                    types.Part(
                        text=instrucao_sistema
                    )
                ]
            ),
        )

    @staticmethod
    def parece_cota_esgotada(erro):
        """
        Diz se a queda foi o Google recusando por cota, não a rede.

        A Live API fecha com 1011 "Resource has been exhausted"; o resto
        da API usa 429 / RESOURCE_EXHAUSTED. Nenhum deles se resolve
        reconectando: só o tempo resolve.

        O número 1011 sozinho NÃO basta. O mesmo código também fecha com
        "Internal error encountered", que é falha passageira do servidor
        e se resolve reconectando. No histórico desta máquina eram 46 de
        um tipo contra 47 do outro: tratar os dois como cota faria o ALF
        esperar um minuto e depois anunciar uma cota esgotada que não
        tinha acabado.
        """

        texto = str(erro).lower()

        return (
            "resource has been exhausted" in texto
            or "resource_exhausted" in texto
            or "429" in texto
            or "quota" in texto
        )

    @staticmethod
    def decidir_provedor_inicial():
        """
        Diz por qual provedor a chamada começa.

        Devolve (degrau, mensagem). A mensagem é vazia no caso
        normal; quando a alternativa é forçada, ela avisa -- ninguém
        deveria descobrir por acaso que está falando com outro provedor.

        Forçar sem a chave não vira silêncio nem erro no meio da
        chamada: ele segue no Gemini e diz o que faltou.
        """

        if not FORCAR_VOZ_ALTERNATIVA:
            return "gemini", ""

        if not OPENAI_API_KEY:
            return "gemini", (
                "ALF_VOZ_ALTERNATIVA está ligada, mas falta OPENAI_API_KEY "
                "no .env. Continuando pelo Gemini."
            )

        return "openai", (
            "Alternativa de voz ligada por configuração "
            "(ALF_VOZ_ALTERNATIVA): esta chamada usa a OpenAI, não o "
            "Gemini. Nela eu não enxergo a tela. "
            "Para voltar ao normal, apague essa linha do .env."
        )

    @staticmethod
    def provedores_de_texto():
        """Os serviços de texto do último degrau, na ordem de tentativa."""

        return [
            Provedor(
                "groq", "https://api.groq.com/openai/v1",
                GROQ_API_KEY, GROQ_CHAT_MODEL,
            ),
            Provedor(
                "mistral", "https://api.mistral.ai/v1",
                MISTRAL_API_KEY, MISTRAL_CHAT_MODEL,
            ),
            Provedor(
                "cerebras", "https://api.cerebras.ai/v1",
                CEREBRAS_API_KEY, CEREBRAS_CHAT_MODEL,
            ),
        ]

    def proximo_provedor(self):
        """
        O próximo degrau da cadeia, ou None quando não há mais.

        Três degraus: Gemini Live, OpenAI Realtime e o modo simples. A
        cadeia só desce -- o que esgotou foi a cota do degrau anterior,
        e voltar a ele gastaria o que não tem.
        """

        degraus = ["gemini", "openai", "simples"]

        disponivel = {
            "openai": bool(OPENAI_API_KEY),
            "simples": any(p.disponivel() for p in self.provedores_de_texto()),
        }

        atual = degraus.index(self.provedor) if self.provedor in degraus else 0

        for degrau in degraus[atual + 1:]:
            if disponivel.get(degrau):
                return degrau

        return None

    def nome_do_provedor(self):
        """
        Como o degrau atual aparece no log e na tela.

        O log dizia "Sessao Gemini Live aberta" mesmo quando a sessão era
        da OpenAI ou do modo simples. Na prática isso mandou o professor
        investigar a cota do Gemini por causa de um erro que era da
        OpenAI.
        """

        return {
            "gemini": "Gemini Live",
            "openai": "OpenAI Realtime",
            "simples": "modo simples",
        }.get(self.provedor, self.provedor)

    @staticmethod
    def aviso_do_provedor(provedor):
        if provedor == "openai":
            return (
                "A cota do Gemini acabou. Continuando pela voz alternativa "
                "da OpenAI. "
                "Nela eu não enxergo a tela. "
                "Análise de imagem e clique visual ficam indisponíveis até "
                "a cota do Gemini voltar."
            )

        return (
            "As duas vozes em tempo real recusaram por cota. Continuando no "
            "modo simples: eu ouço, respondo e falo pela voz do Windows. "
            "É mais devagar, você não consegue me interromper no meio da "
            "fala, e eu continuo sem enxergar a tela. "
            "As demais funções seguem funcionando."
        )

    def decidir_apos_cota(self, duracao_sessao):
        """
        Devolve ("esperar", segundos) ou ("parar", mensagem).

        Espera longa nas primeiras vezes, porque o limite por minuto
        passa sozinho. Depois disso para e explica: insistir só queima o
        que sobrou, e limite diário não passa esperando um minuto.
        """

        # Uma sessão que durou bem antes de cair é um incidente novo,
        # não a continuação do mesmo ciclo.
        if duracao_sessao >= TEMPO_SESSAO_ESTAVEL:
            self.quedas_por_cota = 1
        else:
            self.quedas_por_cota += 1

        if self.quedas_por_cota > MAX_QUEDAS_POR_COTA:
            return "parar", (
                "A cota da sua chave do Gemini se esgotou: o Google está "
                "recusando as sessões (erro 1011). Encerrei a chamada de "
                "propósito -- reabrir agora só gasta o que sobrou da cota. "
                "Espere alguns minutos e tente de novo; se continuar, o "
                "limite pode ser o diário, e aí só volta amanhã ou com "
                "faturamento ativado no projeto. Dá para conferir o "
                "consumo no Google AI Studio, em API keys."
            )

        return "esperar", ESPERA_APOS_COTA

    @staticmethod
    def calcular_tentativas_apos_queda(
        tentativas_atual,
        duracao_sessao,
    ):
        if duracao_sessao >= TEMPO_SESSAO_ESTAVEL:
            return 1

        return tentativas_atual + 1

    def deve_finalizar_fluxo_por_silencio(
        self,
        nivel_audio,
        agora=None,
    ):
        if agora is None:
            agora = time.monotonic()

        if nivel_audio >= LIMIAR_VOZ_MICROFONE:
            self.usuario_falando_detectado = True
            self.ultimo_audio_com_voz = agora
            return False

        if (
            self.usuario_falando_detectado
            and self.ultimo_audio_com_voz is not None
            and agora - self.ultimo_audio_com_voz
            >= TEMPO_SILENCIO_FINALIZAR_AUDIO
        ):
            self.usuario_falando_detectado = False
            self.ultimo_audio_com_voz = None
            return True

        return False

    @staticmethod
    # Converte o áudio em um nível visual entre 0 e 1.
    def calcular_nivel_audio(
        audio_bytes,
    ):
        # Retorna zero quando não há áudio.
        if not audio_bytes:
            return 0.0

        try:
            # Interpreta os bytes como números inteiros de 16 bits.
            amostras = array(
                "h",
                audio_bytes,
            )

            if not amostras:
                return 0.0

            # Encontra a maior amplitude do bloco.
            pico = max(
                abs(amostra)
                for amostra in amostras
            )

            # Normaliza a amplitude máxima de int16.
            nivel = pico / 32768.0
            # Ajusta a curva para melhorar a sensibilidade visual.
            nivel = nivel ** 0.55

            return max(
                0.0,
                min(
                    1.0,
                    nivel,
                ),
            )

        except (
            ValueError,
            OverflowError,
        ):
            return 0.0

    # Reativa o microfone depois que o ALF realmente termina de falar.
    async def liberar_microfone_apos_fala(
        self,
    ):
        """
        O servidor envia turn_complete assim que termina de GERAR a
        resposta, mas nesse momento o áudio ainda está na fila e no
        buffer da placa de som. A versão anterior liberava o microfone
        0,8 s depois do turn_complete, então o microfone reabria com o
        ALF ainda falando: ele escutava a própria voz, se interrompia e
        a conversa engasgava.

        Agora a espera acontece em duas etapas: primeiro até a fila de
        áudio esvaziar de verdade, depois a pausa de segurança.
        """

        try:
            await self.aguardar_fim_da_reproducao()

            # Pequena espera para o buffer da placa de som terminar.
            await asyncio.sleep(
                ATRASO_REABRIR_MICROFONE
            )

            # Permite novamente a captura do usuário.
            self.alfred_falando = False
            self.nivel_audio.emit(
                0.0
            )

        except asyncio.CancelledError:
            pass

    async def aguardar_fim_da_reproducao(
        self,
        limite=TEMPO_MAXIMO_ESPERANDO_AUDIO,
    ):
        """
        Espera a fila de saída esvaziar e o bloco atual terminar.

        O limite existe para que uma falha na placa de som nunca deixe
        o microfone fechado para sempre.
        """

        prazo = time.monotonic() + limite

        while time.monotonic() < prazo:
            fila_vazia = (
                self.fila_saida is None
                or self.fila_saida.empty()
            )

            # O buffer é o que a placa de som ainda vai tocar: enquanto
            # tiver bytes ali, o ALF continua falando.
            buffer_vazio = self.buffer_audio.tamanho() == 0

            if fila_vazia and buffer_vazio:
                self.reproduzindo_bloco = False
                return True

            await asyncio.sleep(0.05)

        self.registrar_diagnostico(
            "Microfone liberado por tempo limite: a reproducao nao terminou."
        )
        return False

    # Método chamado pelo botão de análise de tela.
    def solicitar_analise_tela(
        self,
    ):
        # Verifica se a sessão está pronta antes de enviar imagem.
        if not self.loop or not self.sessao:
            self.erro_recebido.emit(
                "Sessão Gemini ainda não está pronta."
            )
            return

        # Agenda a corrotina no loop da thread Gemini.
        asyncio.run_coroutine_threadsafe(
            self.enviar_tela_para_gemini(
                origem="botao"
            ),
            self.loop,
        )

    # Captura e envia a tela atual para análise.
    async def enviar_tela_para_gemini(
        self,
        origem="botao",
    ):
        if self.processando_ferramenta:
            self.erro_recebido.emit(
                "Aguarde a conclusão da ação atual antes da análise visual."
            )
            return

        self.processando_ferramenta = True
        self.alfred_falando = True
        try:
            self.status_recebido.emit("Capturando imagem da tela...")
            imagem_bytes = await asyncio.wait_for(
                asyncio.to_thread(capturar_tela_bytes),
                timeout=12,
            )
            await self.enviar_imagem_para_analise(
                self.sessao,
                imagem_bytes,
                "tela",
                self.montar_instrucao_visual("tela"),
            )
            self.status_recebido.emit("Imagem da tela enviada para análise.")
        except asyncio.TimeoutError:
            self.erro_recebido.emit("A captura da tela excedeu o tempo limite.")
        except Exception as erro:
            self.erro_recebido.emit(f"Erro ao analisar tela: {erro}")
        finally:
            self.processando_ferramenta = False
            self.agendar_liberacao_microfone()

    def solicitar_analise_camera(
        self,
    ):
        # Verifica se a sessão está pronta antes de enviar imagem.
        if not self.loop or not self.sessao:
            self.erro_recebido.emit(
                "Sessão Gemini ainda não está pronta."
            )
            return

        # Agenda a corrotina no loop da thread Gemini.
        asyncio.run_coroutine_threadsafe(
            self.enviar_camera_para_gemini(
                origem="botao"
            ),
            self.loop,
        )

    # Captura e envia uma imagem da câmera.
    async def enviar_camera_para_gemini(
        self,
        origem="botao",
    ):
        if self.processando_ferramenta:
            self.erro_recebido.emit(
                "Aguarde a conclusão da ação atual antes da análise visual."
            )
            return

        self.processando_ferramenta = True
        self.alfred_falando = True
        try:
            self.status_recebido.emit("Capturando imagem da câmera...")
            imagem_bytes = await asyncio.wait_for(
                asyncio.to_thread(capturar_camera_bytes),
                timeout=15,
            )
            await self.enviar_imagem_para_analise(
                self.sessao,
                imagem_bytes,
                "câmera",
                self.montar_instrucao_visual("câmera"),
            )
            self.status_recebido.emit("Imagem da câmera enviada para análise.")
        except asyncio.TimeoutError:
            self.erro_recebido.emit("A captura da câmera excedeu o tempo limite.")
        except Exception as erro:
            self.erro_recebido.emit(f"Erro ao analisar câmera: {erro}")
        finally:
            self.processando_ferramenta = False
            self.agendar_liberacao_microfone()

    def parar(self):
        # Faz os loops principais terminarem.
        self.ativo = False

        self.nivel_audio.emit(
            0.0
        )
