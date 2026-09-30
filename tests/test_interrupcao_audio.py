"""
Fala cortada: interrupção e falta de áudio soam parecido.

Sintoma de 30/09/2026: "o áudio começou a picotar, como se tivesse
cortando a fala do ALF". O log não tinha nenhum sinal de fila de áudio
acumulada, que é o aviso clássico de falta de dados -- e o código não
tratava o aviso de interrupção que a Live API manda.

Sem esse tratamento, o ALF seguia tocando a fala antiga enquanto a nova
chegava. Para quem ouve, é igual a picote.

Agora as duas coisas são tratadas e ficam separadas no log.
"""

import asyncio
from pathlib import Path

from gemini.live_client import GeminiLiveWorker


CODIGO = Path("gemini/live_client.py").read_text(encoding="utf-8")


def test_interrupcao_descarta_o_audio_que_nao_tocou():
    """Tocar a fala velha depois da interrupção é o que soa picotado."""
    trecho = CODIGO.split('"interrupted", False', 1)[1][:400]

    assert "self.buffer_audio.limpar()" in trecho
    assert "self.limpar_fila_saida()" in trecho


def test_a_fila_de_saida_esvazia_sem_sobrar_nada():
    async def executar():
        worker = GeminiLiveWorker()
        worker.fila_saida = asyncio.Queue()
        for _ in range(5):
            worker.fila_saida.put_nowait(b"som")

        worker.limpar_fila_saida()

        assert worker.fila_saida.empty()

    asyncio.run(executar())


def test_limpar_fila_sem_fila_nao_quebra():
    """A interrupção pode chegar antes de a reprodução começar."""
    worker = GeminiLiveWorker()
    worker.fila_saida = None

    worker.limpar_fila_saida()


def test_falta_de_audio_so_conta_com_o_alf_falando():
    """Com o ALF calado, buffer vazio é o estado normal, não defeito."""
    trecho = CODIGO.split("def alimentar(", 1)[1][:500]

    assert "if self.alfred_falando:" in trecho
    assert "self.faltas_de_audio += 1" in trecho


def test_a_contagem_comeca_zerada():
    assert GeminiLiveWorker().faltas_de_audio == 0


def test_o_fim_do_turno_relata_a_falta_e_zera():
    trecho = CODIGO.split("Libera novamente o áudio quando o turno termina.", 1)[1][:600]

    assert "faltou" in trecho
    assert "self.faltas_de_audio = 0" in trecho
