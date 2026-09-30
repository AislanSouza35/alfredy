"""
Testa o ciclo completo de ferramenta na alternativa de voz.

O teste anterior (testar_alternativa.py) só provava que a voz sai. Este
prova a parte que mais podia quebrar: as 72 ferramentas do ALF, escritas
no formato do Gemini, traduzidas para o formato da OpenAI, aceitas pelo
servidor, chamadas pelo modelo, executadas aqui e respondidas de volta.

Não usa microfone nem mexe no mouse. A ferramenta escolhida é a mais
inofensiva que existe no ALF: perguntar se há transporte de notas em
andamento, que não toca em nada.

    venv\\Scripts\\python.exe scripts\\testar_alternativa_ferramentas.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.genai import types  # noqa: E402

from actions.transporte_notas import estado_do_transporte  # noqa: E402
from core.config import (  # noqa: E402
    OPENAI_API_KEY,
    OPENAI_REALTIME_MODEL,
    OPENAI_REALTIME_VOICE,
)
from gemini.live_client import GeminiLiveWorker  # noqa: E402
from voz.openai_realtime import conectar, converter_ferramentas  # noqa: E402


INSTRUCAO = (
    "Você é o ALF, assistente de um professor. Responda em português do "
    "Brasil, curto. Quando precisar de um dado do sistema, chame a "
    "ferramenta correspondente em vez de supor."
)

PERGUNTA = "Tem algum transporte de notas em andamento agora?"

TEMPO_MAXIMO = 45


async def principal():
    if not OPENAI_API_KEY:
        print("FALTA OPENAI_API_KEY no .env.")
        return 1

    ferramentas = GeminiLiveWorker().montar_ferramentas()
    convertidas = converter_ferramentas(ferramentas)
    print(f"Ferramentas declaradas: {len(convertidas)}")

    maior = max(convertidas, key=lambda f: len(str(f)))
    print(f"Maior declaração: {maior['name']} ({len(str(maior))} caracteres)")

    chamou = []
    bytes_de_audio = 0
    erro = None

    try:
        async with conectar(
            OPENAI_API_KEY,
            OPENAI_REALTIME_MODEL,
            INSTRUCAO,
            ferramentas,
            OPENAI_REALTIME_VOICE,
        ) as sessao:
            print("Sessão aberta com a lista inteira de ferramentas.")
            print(f"Perguntando: {PERGUNTA!r}\n")

            await sessao.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=PERGUNTA)]),
                turn_complete=True,
            )

            inicio = time.monotonic()

            async def conversar():
                nonlocal bytes_de_audio

                turnos = 0

                async for evento in sessao.receive():
                    if evento.data:
                        bytes_de_audio += len(evento.data)

                    if evento.tool_call is not None:
                        for chamada in evento.tool_call.function_calls:
                            print(
                                f"[{time.monotonic() - inicio:5.1f}s] "
                                f"o modelo chamou: {chamada.name}({chamada.args})"
                            )
                            chamou.append(chamada.name)

                            resultado = estado_do_transporte()
                            print(f"        resposta da ferramenta: {resultado}")

                            await sessao.send_tool_response(
                                function_responses=[
                                    types.FunctionResponse(
                                        id=chamada.id,
                                        name=chamada.name,
                                        response={"result": resultado},
                                    )
                                ]
                            )

                    if evento.server_content is not None:
                        turnos += 1
                        print(f"[{time.monotonic() - inicio:5.1f}s] turno {turnos}")
                        # O adaptador esconde o fim da resposta que só
                        # pediu a ferramenta: o turno termina quando o
                        # ALF fala o resultado.
                        return

            await asyncio.wait_for(conversar(), timeout=TEMPO_MAXIMO)

    except asyncio.TimeoutError:
        erro = f"nada concluiu em {TEMPO_MAXIMO}s"
    except Exception as falha:
        erro = f"{type(falha).__name__}: {falha}"

    print("\n" + "=" * 52)

    if erro:
        print(f"NÃO FUNCIONOU: {erro}")
        return 1

    segundos = bytes_de_audio / (24000 * 2)

    if not chamou:
        print("A sessão funcionou, MAS o modelo não chamou ferramenta nenhuma.")
        print(f"Áudio recebido: {segundos:.1f}s de fala.")
        print("Isso não prova que a tradução das ferramentas está certa.")
        return 1

    print(f"FUNCIONOU: ferramenta {chamou[0]} chamada, executada e respondida.")
    print(f"Áudio recebido: {segundos:.1f}s de fala.")
    print("As 72 ferramentas foram aceitas pelo servidor no formato traduzido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
