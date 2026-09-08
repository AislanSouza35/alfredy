from pathlib import Path


def test_spec_exclui_icu_incompativel_do_pacote():
    spec = Path("ALF.spec").read_text(encoding="utf-8")

    assert "icu*.dll" in spec
    assert "a.binaries = TOC(" in spec


def test_spec_nao_usa_upx():
    """
    UPX é gatilho conhecido de falso positivo em antivírus.

    Num teste real logo após uma recompilação, o Windows abortou
    localmente as conexões TLS do ALF.exe (WinError 1236, que chega à
    aplicação como queda 1006), enquanto o mesmo código executado por
    python.exe permanecia estável.
    """
    conteudo = Path("ALF.spec").read_text(encoding="utf-8")

    assert "upx=True" not in conteudo
    assert conteudo.count("upx=False") == 2
