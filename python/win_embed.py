#!/usr/bin/env python3
"""win_embed — encaixa a janela (HWND) de um processo externo dentro de um
widget GTK, no Windows.

SEM pywin32, DE PROPOSITO
--------------------------
A primeira versao deste modulo usava pywin32. Nao funciona aqui: os wheels
do pywin32 sao compilados contra o CPython oficial (ABI MSVC), e o Python
que traz o GTK3/PyGObject no Windows e o do MSYS2 (ABI MinGW). O pip tenta
compilar do fonte e falha. Como tudo o que precisamos e um punhado de
chamadas de user32, ctypes — que ja vem no Python — resolve sem
dependencia externa nenhuma.

POR QUE ESTE MODULO EXISTE
---------------------------
No Linux o Acessos embute o xfreerdp usando Gtk.Socket, que fala XEmbed.
XEmbed e um protocolo do X11: nao existe em Wayland puro (o Acessos cai
para janela externa nesse caso) e tambem NAO EXISTE no Windows. GTK3 no
Windows nao publica Gtk.Socket/Gtk.Plug.

O Windows tem o proprio jeito de fazer a mesma coisa, e mais simples que
XEmbed: qualquer HWND pode ser reparentado para dentro de outro com
SetParent(), independente de quem criou a janela. E exatamente o mesmo
truque que o xfreerdp faz via /parent-window: no X11 — so que aqui e o
Acessos quem pede a reparentacao de fora, depois que o processo ja subiu,
em vez de o processo aceitar um XID na hora de abrir.

LIMITACOES CONHECIDAS (documentadas para nao virarem susto depois)
--------------------------------------------------------------------
- So funciona com janelas TOP-LEVEL de verdade. Janelas com
  CS_OWNDC/CS_CLASSDC de alguns clientes 3D podem piscar ao reparentar;
  isso ja era risco do proprio /parent-window no X11 (ver acessos.py,
  AbaRdp._on_saiu: builds que "nao suportam" reparenting e abortam) e a
  mitigacao e a mesma: se a janela nao aparecer em ATE 8s, diagnostica e
  volta para janela externa.
- Processos com integridade/elevacao diferente do Acessos NAO podem ser
  reparentados (UIPI). Isso so aconteceria se o Acessos ou o FreeRDP
  fossem abertos "como administrador" e o outro nao — evite rodar so um
  dos dois elevado.
- DPI: se o processo filho e "DPI unaware" e o Acessos e "per-monitor", o
  conteudo pode sair borrado em telas de alto DPI. Nao tratado aqui.
"""

import ctypes
import sys
import time
from ctypes import wintypes

DISPONIVEL = sys.platform == "win32"
ERRO_INDISPONIVEL = "" if DISPONIVEL else "win_embed só funciona no Windows"

if DISPONIVEL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # WNDENUMPROC: BOOL CALLBACK EnumWindowsProc(HWND, LPARAM)
    WNDENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    user32.SetParent.restype = wintypes.HWND
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR,
                                      ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL

    # GetWindowLongPtr/SetWindowLongPtr: em 64 bits os estilos ainda cabem
    # em LONG, mas os campos de PONTEIRO (GWLP_HINSTANCE etc.) nao. Usamos
    # a variante Ptr quando existe — em 32 bits ela nao e exportada e o
    # nome correto e o antigo.
    if hasattr(user32, "GetWindowLongPtrW"):
        _get_long = user32.GetWindowLongPtrW
        _set_long = user32.SetWindowLongPtrW
    else:                                     # 32 bits
        _get_long = user32.GetWindowLongW
        _set_long = user32.SetWindowLongW
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_long.restype = ctypes.c_ssize_t
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _set_long.restype = ctypes.c_ssize_t

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                     wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel32.GetProcessId.restype = wintypes.DWORD
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
else:                                          # pragma: no cover
    user32 = kernel32 = None

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000
WS_VISIBLE = 0x10000000
WS_EX_APPWINDOW = 0x00040000
WS_EX_WINDOWEDGE = 0x00000100
WS_EX_CLIENTEDGE = 0x00000200
WS_EX_DLGMODALFRAME = 0x00000001
WS_EX_STATICEDGE = 0x00020000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040

SW_SHOW = 5
WM_CLOSE = 0x0010
PROCESS_TERMINATE = 0x0001


def disponivel():
    """True se este modulo pode operar (Windows). O modulo precisa
    IMPORTAR em qualquer plataforma, para o rdp_windows.py poder checar e
    avisar em vez de estourar."""
    return DISPONIVEL


def gdk_hwnd(widget):
    """HWND nativa por tras de um widget GTK ja realizado.

    No backend Win32 do GDK, toda GdkWindow tem uma HWND de verdade —
    diferente do X11, aqui nao precisa nada equivalente a get_id()/XID.
    """
    if not widget.get_realized():
        widget.realize()
    gdkwin = widget.get_window()
    if gdkwin is None:
        return None
    try:
        import gi
        gi.require_version("GdkWin32", "3.0")
        from gi.repository import GdkWin32
        return GdkWin32.Win32Window.get_handle(gdkwin)
    except Exception:
        pass
    if hasattr(gdkwin, "get_handle"):
        return gdkwin.get_handle()
    raise RuntimeError(
        "não consegui a HWND do widget — typelib GdkWin32 ausente. "
        "Confira se o pacote mingw-w64-x86_64-python-gobject inclui "
        "GdkWin32 (normalmente vem junto do gtk3 no MSYS2).")


def pid_real(gpid):
    """Converte o 'pid' devolvido pelo GLib no PID de verdade.

    PEGADINHA QUE CUSTOU O REPARENTAMENTO DO RDP:
    no Windows o GPid do GLib NAO e um identificador de processo — e um
    HANDLE (documentado: "on Windows, GPid is a process handle"). Passar
    esse valor para o find_hwnd_by_pid fazia a comparacao contra os PIDs
    reais do EnumWindows falhar SEMPRE; depois de 8s o rdp_windows.py
    concluia "o cliente nao reparentou" e caia para janela separada. O
    FreeRDP estava certo o tempo todo: quem procurava errado era o
    Acessos.

    GetProcessId() extrai o PID do handle. Se o valor recebido ja for um
    PID (Linux, ou algum caminho que nao passe pelo GLib), a chamada
    falha e devolvemos o proprio valor — assim a funcao e segura nos dois
    casos.
    """
    if not DISPONIVEL or not gpid:
        return gpid
    try:
        obtido = kernel32.GetProcessId(wintypes.HANDLE(int(gpid)))
        return obtido or gpid
    except Exception:
        return gpid


def find_hwnd_by_pid(pid, titulo_contem=None, tentativas=40, intervalo=0.2):
    """Procura uma janela TOP-LEVEL visivel do processo `pid` e devolve a
    HWND. None se nao achar dentro das tentativas.

    `titulo_contem`: filtro opcional de titulo, util quando o processo
    abre mais de uma janela (splash, dialogos) antes da principal — o
    FreeRDP as vezes abre um aviso de certificado antes da tela real.
    """
    if not DISPONIVEL:
        raise RuntimeError(ERRO_INDISPONIVEL)

    achada = []

    def visitar(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetParent(hwnd):
            return True          # ja e filho de algo: nao e a top-level
        dono = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(dono))
        if dono.value != pid:
            return True
        if titulo_contem:
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            if titulo_contem.lower() not in buf.value.lower():
                return True
        achada.append(hwnd)
        return False              # achou: interrompe a varredura

    callback = WNDENUMPROC(visitar)
    for _ in range(tentativas):
        achada.clear()
        user32.EnumWindows(callback, 0)
        if achada:
            return achada[0]
        if tentativas > 1:
            time.sleep(intervalo)
    return None


def embed_hwnd(hwnd_filho, hwnd_pai, largura=None, altura=None):
    """Tira a moldura da janela filha e a encaixa dentro de hwnd_pai.

    Equivalente ao que o Gtk.Socket faz ao aceitar um 'plug-added': o
    filho deixa de ser uma janela do desktop e passa a ser desenhado
    dentro da area do pai.
    """
    if not DISPONIVEL:
        raise RuntimeError(ERRO_INDISPONIVEL)
    if not hwnd_filho or not hwnd_pai:
        raise RuntimeError("HWND inválida (filho=%s, pai=%s)"
                           % (hwnd_filho, hwnd_pai))

    estilo = _get_long(hwnd_filho, GWL_STYLE)
    estilo &= ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME |
                WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
    estilo |= WS_CHILD | WS_VISIBLE
    _set_long(hwnd_filho, GWL_STYLE, estilo)

    estilo_ex = _get_long(hwnd_filho, GWL_EXSTYLE)
    estilo_ex &= ~(WS_EX_APPWINDOW | WS_EX_WINDOWEDGE |
                   WS_EX_CLIENTEDGE | WS_EX_DLGMODALFRAME |
                   WS_EX_STATICEDGE)
    _set_long(hwnd_filho, GWL_EXSTYLE, estilo_ex)

    if not user32.SetParent(hwnd_filho, hwnd_pai):
        raise ctypes.WinError(ctypes.get_last_error())

    flags = SWP_NOZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW
    if largura and altura:
        user32.SetWindowPos(hwnd_filho, None, 0, 0,
                            max(1, largura), max(1, altura), flags)
    else:
        user32.SetWindowPos(hwnd_filho, None, 0, 0, 0, 0,
                            flags | SWP_NOSIZE | SWP_NOMOVE)
    user32.ShowWindow(hwnd_filho, SW_SHOW)
    return True


def redimensionar(hwnd_filho, largura, altura):
    """Chamar no 'size-allocate' do widget hospedeiro — sem isso a janela
    embutida fica com o tamanho do primeiro encaixe para sempre."""
    if not DISPONIVEL or not hwnd_filho:
        return
    try:
        user32.SetWindowPos(hwnd_filho, None, 0, 0,
                            max(1, largura), max(1, altura), SWP_NOZORDER)
    except Exception:
        pass          # janela pode ter fechado entre o resize e aqui


def esta_viva(hwnd):
    if not DISPONIVEL or not hwnd:
        return False
    try:
        return bool(user32.IsWindow(hwnd))
    except Exception:
        return False


def encerrar_processo(pid, forcar=False):
    """Equivalente ao os.kill(pid, 15) do Linux — no Windows nao existe
    SIGTERM de verdade. Tentamos WM_CLOSE primeiro (saida limpa) e caimos
    para TerminateProcess."""
    if not DISPONIVEL or not pid:
        return False
    if not forcar:
        hwnd = find_hwnd_by_pid(pid, tentativas=1)
        if hwnd:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return True
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(kernel32.TerminateProcess(handle, 1))
    finally:
        kernel32.CloseHandle(handle)
