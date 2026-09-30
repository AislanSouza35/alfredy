"""
Testa o último degrau da cadeia, sem microfone.

Três partes, cada uma podendo falhar sozinha:

1. a voz do Windows fala uma frase;
2. essa fala volta para o Whisper, que a transcreve -- é o teste do
   ouvido sem precisar de microfone;
3. a cadeia de texto responde, e com ferramenta.

    venv\\Scripts\\python.exe scripts\\testar_modo_simples.py
"""

import asyncio
import sys
import time
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from core.config import (  # noqa: E402
    CEREBRAS_API_KEY,
    CEREBRAS_CHAT_MODEL,
    GROQ_API_KEY,
    GROQ_CHAT_MODEL,
    GROQ_WHISPER_MODEL,
    MISTRAL_API_KEY,
    MISTRAL_CHAT_MODEL,
    VOZ_WINDOWS,
)
from voz.modo_simples import (  # noqa: E402
    Provedor,
    conversar_com_provedores,
    sintetizar,
    transcrever,
)


FRASE = "Bom dia. O modo simples do ALF está funcionando."


def reduzir_para_16k(pcm24):
    """De 24 kHz para 16 kHz: duas amostras a cada três."""

    amostras = array("h")
    amostras.frombytes(pcm24)

    saida = array("h")
    for i in range(0, len(amostras) - 2, 3):
        a, b, c = amostras[i], amostras[i + 1], amostras[i + 2]
        saida.append((a + b) // 2)
        saida.append((b + c) // 2)

    return saida.tobytes()


def provedores():
    return [
        Provedor("groq", "https://api.groq.com/openai/v1", GROQ_API_KEY, GROQ_CHAT_MODEL),
        Provedor("mistral", "https://api.mistral.ai/v1", MISTRAL_API_KEY, MISTRAL_CHAT_MODEL),
        Provedor("cerebras", "https://api.cerebras.ai/v1", CEREBRAS_API_KEY, CEREBRAS_CHAT_MODEL),
    ]


async def principal():
    falhas = []

    # ---------- 1. falar ----------
    print(f"1) Voz do Windows ({VOZ_WINDOWS})")
    inicio = time.monotonic()
    pcm = await asyncio.to_thread(sintetizar, FRASE, VOZ_WINDOWS)
    demora = time.monotonic() - inicio

    if not pcm:
        print("   FALHOU: não saiu áudio.")
        falhas.append("voz")
    else:
        print(f"   ok: {len(pcm)/(24000*2):.1f}s de fala em {demora:.1f}s")

    # ---------- 2. ouvir ----------
    print("\n2) Whisper transcrevendo a própria fala")
    if not pcm:
        print("   pulado: não há áudio.")
    elif not GROQ_API_KEY:
        print("   pulado: sem GROQ_API_KEY.")
        falhas.append("ouvido")
    else:
        async with httpx.AsyncClient() as cliente:
            inicio = time.monotonic()
            texto, erro = await transcrever(
                reduzir_para_16k(pcm), GROQ_API_KEY, GROQ_WHISPER_MODEL, cliente
            )
            demora = time.monotonic() - inicio

        if erro:
            print(f"   FALHOU: {erro}")
            falhas.append("ouvido")
        else:
            print(f"   ok em {demora:.1f}s: {texto!r}")
            if "modo simples" not in texto.lower():
                print("   ATENÇÃO: a transcrição não bate com a frase falada.")

    # ---------- 3. responder ----------
    print("\n3) Cadeia de texto, com ferramenta")
    ferramenta = {
        "name": "estado_do_transporte",
        "description": "Diz se há transporte de notas em andamento.",
        "parameters": {"type": "object", "properties": {}},
    }
    mensagens = [
        {"role": "system", "content": "Você é o ALF. Use as ferramentas quando couber."},
        {"role": "user", "content": "Tem transporte de notas em andamento?"},
    ]

    async with httpx.AsyncClient() as cliente:
        inicio = time.monotonic()
        mensagem, provedor, erro = await conversar_com_provedores(
            provedores(), mensagens, [ferramenta], cliente
        )
        demora = time.monotonic() - inicio

    if erro:
        print(f"   FALHOU: {erro}")
        falhas.append("texto")
    else:
        chamadas = mensagem.get("tool_calls") or []
        print(f"   ok em {demora:.1f}s pelo provedor: {provedor.nome} ({provedor.modelo})")
        if chamadas:
            print(f"   chamou a ferramenta: {chamadas[0]['function']['name']}")
        else:
            print(f"   respondeu sem ferramenta: {str(mensagem.get('content'))[:80]!r}")
            print("   ATENÇÃO: esperava uma chamada de ferramenta.")

    print("\n" + "=" * 52)
    if falhas:
        print(f"PARTES COM PROBLEMA: {', '.join(falhas)}")
        return 1

    print("MODO SIMPLES PRONTO: fala, ouve e responde.")
    print("Ele entra sozinho se Gemini e OpenAI recusarem por cota.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
