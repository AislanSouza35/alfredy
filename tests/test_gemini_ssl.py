import ssl

from google.genai import types

from core.gemini_ssl import criar_contexto_ssl_gemini, criar_http_options_gemini


def test_criar_contexto_ssl_gemini_remove_validacao_estrita():
    contexto = criar_contexto_ssl_gemini()

    assert isinstance(contexto, ssl.SSLContext)
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        assert not contexto.verify_flags & ssl.VERIFY_X509_STRICT


def test_criar_http_options_gemini_configura_clientes_sync_e_async():
    http_options = criar_http_options_gemini(types)

    assert http_options.client_args["verify"] is not None
    assert http_options.async_client_args["ssl"] is not None
