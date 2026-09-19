"""
Testa a alternativa de voz sem precisar da cota do Gemini acabar.

Abre uma sessão na API Realtime da OpenAI, manda uma frase e conta o
áudio que volta. Não usa microfone, não mexe no mouse e não abre a
janela do ALF: dá para rodar no meio de qualquer coisa.

    venv\\Scripts\\python.exe scripts\\testar_alternativa.py

Precisa de OPENAI_API_KEY no .env. O teste falha de forma explicada se
faltar, em vez de travar.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import (  # noqa: E402
    OPENAI_API_KEY,
    OPENAI_REALTIME_MODEL,
    OPENAI_REALTIME_VOICE,
)
from voz.openai_realtime import conectar  # noqa: E402


FRASE = (
    "Responda apenas, em português: alternativa de voz funcionando. "
    "Nada além disso."
)

TEMPO_MAXIMO = 30


async def principal():
    if not OPENAI_API_KEY:
        print("FALTA A CHAVE.")
        print()
        print("Acrescente ao .env do ALF, sem aspas e sem espaços:")
        print("    OPENAI_API_KEY=<a chave>")
        print()
        print("A mesma chave que está no .env do JARVIS serve.")
        return 1

    print(f"Modelo: {OPENAI_REALTIME_MODEL}   Voz: {OPENAI_REALTIME_VOICE}")
    print("Abrindo a sessão...")

    inicio = time.monotonic()
    bytes_de_audio = 0
    turnos = 0
    erro = None

    try:
        async with conectar(
            OPENAI_API_KEY,
            OPENAI_REALTIME_MODEL,
            "Você é o ALF. Responda em português do Brasil, curto.",
            [],
            OPENAI_REALTIME_VOICE,
        ) as sessao:
            print(f"Conectou em {time.monotonic() - inicio:.1f}s. Mandando a frase...")

            from google.genai import types

            await sessao.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=FRASE)]),
                turn_complete=True,
            )

            pedido = time.monotonic()
            primeiro_audio = None

            async def ouvir():
                nonlocal bytes_de_audio, turnos, primeiro_audio

                async for evento in sessao.receive():
                    if evento.data:
                        if primeiro_audio is None:
                            primeiro_audio = time.monotonic() - pedido
                            print(f"Primeiro áudio em {primeiro_audio:.1f}s.")
                        bytes_de_audio += len(evento.data)

                    if evento.server_content is not None:
                        turnos += 1
                        if turnos >= 1:
                            return

            await asyncio.wait_for(ouvir(), timeout=TEMPO_MAXIMO)

    except asyncio.TimeoutError:
        erro = f"A resposta não chegou em {TEMPO_MAXIMO}s."
    except Exception as falha:
        erro = f"{type(falha).__name__}: {falha}"

    print()
    print("=" * 50)

    if erro:
        print(f"NÃO FUNCIONOU: {erro}")
        print()
        print("Se falar em modelo inexistente, ajuste OPENAI_REALTIME_MODEL")
        print("no .env. Se falar em cota ou faturamento, é a conta da OpenAI.")
        return 1

    segundos = bytes_de_audio / (24000 * 2)
    print(f"FUNCIONOU: {bytes_de_audio} bytes de áudio ({segundos:.1f}s de fala).")
    print()
    print("Para usar a alternativa numa chamada inteira, acrescente ao .env:")
    print("    ALF_VOZ_ALTERNATIVA=1")
    print("e reinicie o ALF. Lembre que nela ele não enxerga a tela.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
