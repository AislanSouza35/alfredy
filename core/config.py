import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def _carregar_configuracao():
	caminhos_env = []

	if getattr(sys, "frozen", False):
		caminhos_env.append(
			Path(sys.executable).resolve().parent / ".env"
		)

	caminhos_env.append(
		Path(__file__).resolve().parent.parent / ".env"
	)

	caminhos_env.append(
		Path.cwd() / ".env"
	)

	for caminho_env in caminhos_env:
		if caminho_env.is_file():
			load_dotenv(
				dotenv_path=caminho_env
			)
			return

	load_dotenv()


_carregar_configuracao()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ============================================================
# ENVIO DE E-MAIL (SMTP)
# ============================================================
#
# EMAIL_SENHA_APP precisa ser uma SENHA DE APP, nunca a senha normal
# da conta. No Google: Conta > Segurança > Verificação em duas etapas
# > Senhas de app. São 16 letras, e podem ser revogadas a qualquer
# momento sem trocar a senha da conta.
#
# Servidor e porta são deduzidos pelo domínio do remetente para os
# provedores comuns; só preencha se usar um provedor diferente.
EMAIL_REMETENTE = os.getenv("EMAIL_REMETENTE")
EMAIL_SENHA_APP = os.getenv("EMAIL_SENHA_APP")
EMAIL_NOME_REMETENTE = os.getenv("EMAIL_NOME_REMETENTE")
EMAIL_SMTP_SERVIDOR = os.getenv("EMAIL_SMTP_SERVIDOR")
EMAIL_SMTP_PORTA = os.getenv("EMAIL_SMTP_PORTA")

# Modelo usado pelo ALFRED
GEMINI_LIVE_MODEL = "gemini-3.1-flash-live-preview"

# ============================================================
# ALTERNATIVA DE VOZ — usada quando a cota do Gemini acaba
# ============================================================
#
# Em 18/09/2026 a cota do Gemini esgotou no meio da manhã e o ALF parou:
# um provedor só, sem para onde ir. Com OPENAI_API_KEY preenchida no
# .env, ele passa para a API Realtime da OpenAI em vez de encerrar.
#
# Sem a chave, nada muda: ele continua encerrando com a explicação de
# sempre. Nesta alternativa ele NÃO enxerga a tela; a visão é do Gemini.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Liga a alternativa desde o começo da chamada, sem esperar a cota do
# Gemini acabar. Serve para testar o caminho alternativo com calma: o
# primeiro uso de verdade não deveria acontecer no meio de uma aula,
# justamente quando tudo já deu errado.
#
# No .env: ALF_VOZ_ALTERNATIVA=1  (aceita 1, sim, true, on)
FORCAR_VOZ_ALTERNATIVA = os.getenv("ALF_VOZ_ALTERNATIVA", "").strip().lower() in (
    "1",
    "sim",
    "true",
    "on",
)
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
OPENAI_REALTIME_VOICE = os.getenv("OPENAI_REALTIME_VOICE", "alloy")

# ============================================================
# MODELOS DISPONÍVEIS PARA TESTE
# ============================================================
#MODELO = "gemini-2.5-flash-native-audio-preview-12-2025"
#MODELO = “gemini-2.5-flash-native-audio-preview-09-2025”
#MODELO = "gemini-3.1-flash-live-preview"


# Voz usada pelo ALFRED
GEMINI_VOICE = "Charon"

# ============================================================
# VOZES DISPONÍVEIS PARA TESTE
# ============================================================
#
# Zephyr   - brilhante
# Puck     - animada
# Charon   - informativa
# Kore     - feminia e firme
# Fenrir   - empolgada
# Leda     - jovem
# Orus     - firme
# Aoede    - leve
# Callirrhoe - descontraída
# Autonoe  - brilhante
# Enceladus - suave/sussurrante
# Iapetus  - clara
# Umbriel  - descontraída
# Algieba  - suave
# Despina  - suave
# Erinome  - clara
# Algenib  - rouca
# Rasalgethi - informativa
# Laomedeia - animada
# Achernar - suave
# Alnilam  - firme
# Schedar  - equilibrada
# Gacrux   - madura
# Pulcherrima - direta
# Achird   - amigável
# Zubenelgenubi - casual
# Vindemiatrix - feminina gentil
# Sadachbia - animada
# Sadaltager - experiente
# Sulafat  - calorosa