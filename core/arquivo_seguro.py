"""
Substituição atômica de arquivo tolerante ao Windows.

O projeto fica dentro de uma pasta do OneDrive. Enquanto o OneDrive
sincroniza memory.json ou agenda.json, o arquivo de destino fica aberto
por alguns instantes e Path.replace() falha com PermissionError. O mesmo
acontece com antivírus e com o Windows Search.

O erro derrubava a gravação de memórias e de compromissos de forma
aleatória: o usuário pedia para lembrar algo, o ALF respondia que não
tinha conseguido e nada explicava o motivo.

A função abaixo repete a troca algumas vezes antes de desistir, o que
resolve praticamente todos esses bloqueios, que duram milissegundos.
"""

import time

# Quantidade de tentativas antes de desistir.
TENTATIVAS = 5

# Espera inicial entre as tentativas, em segundos.
ESPERA_INICIAL = 0.05


def substituir_com_retentativa(
    origem,
    destino,
    tentativas=TENTATIVAS,
    espera_inicial=ESPERA_INICIAL,
    pausa=time.sleep,
):
    """
    Move origem para destino repetindo a operação em caso de bloqueio.

    Devolve None em caso de sucesso e levanta o último PermissionError
    quando todas as tentativas falham, mantendo o comportamento
    esperado por quem chama.
    """

    espera = espera_inicial

    for tentativa in range(tentativas):
        try:
            origem.replace(destino)
            return

        except PermissionError:
            if tentativa == tentativas - 1:
                raise

            pausa(espera)
            espera *= 2
