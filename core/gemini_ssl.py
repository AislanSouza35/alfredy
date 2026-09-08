import ssl

import certifi


def criar_contexto_ssl_compativel():
    """
    Contexto TLS que valida o certificado, mas tolera cadeias imperfeitas.

    Antivírus que inspecionam tráfego (aqui, o Avast Web/Mail Shield)
    substituem o certificado do servidor por um gerado na hora, assinado
    por uma raiz própria instalada no Windows. Essa raiz é confiável do
    ponto de vista do sistema, mas costuma violar detalhes do RFC --
    "Basic Constraints of CA cert not marked critical" é o caso visto
    aqui -- e o OpenSSL 3.x rejeita isso sob VERIFY_X509_STRICT.

    A verificação de certificado continua ATIVA: só a checagem estrita
    de formato é afrouxada. Sem isso, nem o Gemini nem o envio de e-mail
    funcionam em máquinas com esse tipo de antivírus.
    """

    contexto = ssl.create_default_context(
        cafile=certifi.where()
    )

    # Carrega também as raízes do Windows, onde fica a raiz do antivírus.
    contexto.load_default_certs()

    if hasattr(ssl, "VERIFY_X509_STRICT"):
        contexto.verify_flags &= ~ssl.VERIFY_X509_STRICT

    return contexto


def criar_contexto_ssl_gemini():
    return criar_contexto_ssl_compativel()


def criar_http_options_gemini(types):
    contexto = criar_contexto_ssl_gemini()
    return types.HttpOptions(
        client_args={
            "verify": contexto,
        },
        async_client_args={
            "ssl": contexto,
        },
    )
