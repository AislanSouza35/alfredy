import ctypes
import time
from ctypes import wintypes

_USER32 = ctypes.windll.user32
_KERNEL32 = ctypes.windll.kernel32
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
_VK_CONTROL = 0x11
_VK_V = 0x56
_KEYEVENTF_KEYUP = 0x0002
_MAXIMO_CARACTERES = 10000

_KERNEL32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_KERNEL32.GlobalAlloc.restype = wintypes.HGLOBAL
_KERNEL32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_KERNEL32.GlobalLock.restype = wintypes.LPVOID
_KERNEL32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_KERNEL32.GlobalUnlock.restype = wintypes.BOOL
_KERNEL32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_KERNEL32.GlobalFree.restype = wintypes.HGLOBAL
_USER32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_USER32.SetClipboardData.restype = wintypes.HANDLE
_USER32.VkKeyScanW.argtypes = [wintypes.WCHAR]
_USER32.VkKeyScanW.restype = ctypes.c_short


def _copiar_para_area_transferencia(texto):
    abriu = False
    for _ in range(10):
        if _USER32.OpenClipboard(None):
            abriu = True
            break
        time.sleep(0.05)
    if not abriu:
        raise RuntimeError("Não foi possível acessar a área de transferência do Windows.")
    memoria = None
    transferida = False
    try:
        if not _USER32.EmptyClipboard():
            raise RuntimeError("Não foi possível limpar a área de transferência do Windows.")
        texto_completo = texto + "\0"
        tamanho = len(texto_completo) * ctypes.sizeof(ctypes.c_wchar)
        memoria = _KERNEL32.GlobalAlloc(_GMEM_MOVEABLE, tamanho)
        if not memoria:
            raise MemoryError("Não foi possível reservar memória para o texto.")
        ponteiro = _KERNEL32.GlobalLock(memoria)
        if not ponteiro:
            raise MemoryError("Não foi possível acessar a memória reservada.")
        try:
            ctypes.memmove(ponteiro, ctypes.create_unicode_buffer(texto_completo), tamanho)
        finally:
            _KERNEL32.GlobalUnlock(memoria)
        if not _USER32.SetClipboardData(_CF_UNICODETEXT, memoria):
            raise RuntimeError("Não foi possível copiar o texto para a área de transferência.")
        transferida = True
    finally:
        _USER32.CloseClipboard()
        if memoria and not transferida:
            _KERNEL32.GlobalFree(memoria)


def _colar_no_campo_ativo():
    _USER32.keybd_event(_VK_CONTROL, 0, 0, 0)
    _USER32.keybd_event(_VK_V, 0, 0, 0)
    _USER32.keybd_event(_VK_V, 0, _KEYEVENTF_KEYUP, 0)
    _USER32.keybd_event(_VK_CONTROL, 0, _KEYEVENTF_KEYUP, 0)


def escrever_no_campo_ativo(texto):
    texto = str(texto or "")
    if not texto.strip():
        return "Nenhum texto foi informado. Nada foi escrito."
    if len(texto) > _MAXIMO_CARACTERES:
        return f"O texto ultrapassa o limite de {_MAXIMO_CARACTERES} caracteres. Nada foi escrito."
    try:
        _copiar_para_area_transferencia(texto)
        time.sleep(0.12)
        _colar_no_campo_ativo()
        return "Texto inserido no campo ativo com sucesso."
    except Exception as erro:
        return f"Não foi possível inserir o texto: {erro}"


# ============================================================
# ATALHOS DE TECLADO GENÉRICOS
# ============================================================

_VK_SHIFT = 0x10
_VK_MENU = 0x12  # Alt
_VK_LWIN = 0x5B

_TECLAS_MODIFICADORAS = {
    "ctrl": _VK_CONTROL,
    "control": _VK_CONTROL,
    "shift": _VK_SHIFT,
    "alt": _VK_MENU,
    "win": _VK_LWIN,
    "windows": _VK_LWIN,
}

_TECLAS_NOMEADAS = {
    "enter": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "espaco": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    **{f"f{n}": 0x70 + (n - 1) for n in range(1, 13)},
}

# Combinações bloqueadas por segurança: fecham o app abruptamente,
# bloqueiam a sessão do Windows ou desligam o computador.
_ATALHOS_BLOQUEADOS = {
    "alt+f4",
    "win+l",
    "ctrl+alt+delete",
    "ctrl+shift+esc",
}


# Apelidos para caracteres que não podem ser digitados diretamente no
# parâmetro (o "+" é o separador da combinação de teclas).
_APELIDOS_CARACTERE = {
    "plus": "+",
    "mais": "+",
    "minus": "-",
    "menos": "-",
}


def _codigo_tecla(nome_tecla):
    """
    Retorna (codigo_vk, modificadores_extras) para a tecla principal.

    Teclas nomeadas (enter, f5, etc.) não precisam de modificador extra.
    Caracteres imprimíveis (letras, números, símbolos como '@', '+', '%')
    usam VkKeyScanW, que traduz o caractere para a tecla física e os
    modificadores certos de acordo com o layout de teclado atual do
    Windows (ex.: ABNT2 no Brasil), em vez de assumir o layout dos EUA.
    """
    nome_tecla = nome_tecla.strip().lower()
    nome_tecla = _APELIDOS_CARACTERE.get(nome_tecla, nome_tecla)

    if nome_tecla in _TECLAS_NOMEADAS:
        return _TECLAS_NOMEADAS[nome_tecla], []

    if len(nome_tecla) != 1:
        return None, []

    resultado = _USER32.VkKeyScanW(nome_tecla)
    # Byte alto = código de erro (-1) quando o caractere não existe no layout atual.
    if resultado == -1 or (resultado >> 8) & 0xFF == 0xFF:
        return None, []

    codigo_vk = resultado & 0xFF
    estado_modificadores = (resultado >> 8) & 0xFF

    modificadores_extras = []
    if estado_modificadores & 0x01:
        modificadores_extras.append(_VK_SHIFT)
    if estado_modificadores & 0x02:
        modificadores_extras.append(_VK_CONTROL)
    if estado_modificadores & 0x04:
        modificadores_extras.append(_VK_MENU)

    return codigo_vk, modificadores_extras


def pressionar_atalho_teclado(teclas):
    """
    Envia uma combinação de teclas ao Windows, ex.: "ctrl+n", "ctrl+s",
    "ctrl+shift+n". A última tecla informada é a tecla principal;
    as anteriores são tratadas como modificadoras (ctrl/shift/alt/win).
    """
    teclas = str(teclas or "").strip().lower()
    if not teclas:
        return "Informe qual atalho de teclado deve ser pressionado."

    partes = [parte.strip() for parte in teclas.split("+") if parte.strip()]
    if not partes:
        return "Atalho de teclado inválido."

    combinacao_normalizada = "+".join(partes)
    if combinacao_normalizada in _ATALHOS_BLOQUEADOS:
        return "Esse atalho foi bloqueado por segurança. Nenhuma ação foi executada."

    *modificadores, tecla_principal = partes

    codigos_modificadores = []
    for modificador in modificadores:
        codigo = _TECLAS_MODIFICADORAS.get(modificador)
        if codigo is None:
            return f"Tecla modificadora desconhecida: '{modificador}'."
        codigos_modificadores.append(codigo)

    codigo_principal, modificadores_extras = _codigo_tecla(tecla_principal)
    if codigo_principal is None:
        return (
            f"Tecla desconhecida: '{tecla_principal}'. Ela pode não existir "
            "no layout de teclado atual."
        )

    # Combina os modificadores pedidos explicitamente (ex.: 'ctrl') com os
    # exigidos pelo próprio caractere no layout atual (ex.: Shift para '@').
    # Mantém a ordem e evita segurar a mesma tecla modificadora duas vezes.
    for codigo_extra in modificadores_extras:
        if codigo_extra not in codigos_modificadores:
            codigos_modificadores.append(codigo_extra)

    try:
        for codigo in codigos_modificadores:
            _USER32.keybd_event(codigo, 0, 0, 0)

        _USER32.keybd_event(codigo_principal, 0, 0, 0)
        _USER32.keybd_event(codigo_principal, 0, _KEYEVENTF_KEYUP, 0)

        for codigo in reversed(codigos_modificadores):
            _USER32.keybd_event(codigo, 0, _KEYEVENTF_KEYUP, 0)

        return f"Atalho '{combinacao_normalizada}' executado com sucesso."
    except Exception as erro:
        return f"Não foi possível executar o atalho: {erro}"

