# -*- mode: python ; coding: utf-8 -*-

from fnmatch import fnmatch


a = Analysis(
    ['main_basic.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('memory/memory.json', 'memory'),
        ('memory/agenda.json', 'memory'),
        # O ícone também é lido em tempo de execução para a barra de
        # título e a barra de tarefas, não só embutido no .exe.
        ('ICONE ALFRED.ico', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Evita empacotar DLLs ICU externas, como as do Poppler usado pelo ambiente
# do Codex. O Qt/PySide6 no Windows deve usar as ICU do sistema; DLLs ICU
# versionadas no pacote quebram o import de PySide6.QtCore.
a.binaries = TOC(
    binary
    for binary in a.binaries
    if not fnmatch(binary[0].lower(), "icu*.dll")
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ALF',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX comprime o executável e é um gatilho conhecido de falso
    # positivo em antivírus. Num teste real, logo após uma recompilação,
    # o Windows abortou localmente as conexões TLS do ALF.exe
    # (WinError 1236 -> queda 1006) enquanto o mesmo código rodando por
    # python.exe ficava estável. Sem UPX o binário também abre mais
    # rápido, e o ganho de tamanho não compensava o risco.
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['ICONE ALFRED.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ALF',
)
