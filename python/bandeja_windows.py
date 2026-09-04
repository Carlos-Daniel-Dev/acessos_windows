#!/usr/bin/env python3
"""bandeja_windows — esconde o console do lançador e representa o Acessos
por um ícone na bandeja do sistema, em ctypes puro (sem pywin32).

POR QUE ESTE MODULO EXISTE
---------------------------
O `acessos.cmd` (gerado pelo instalar.ps1) chama o python.exe do MSYS2
direto, sem `start` nem pythonw — por isso a janela do console fica aberta
durante toda a sessão, do lado da janela GTK, na barra de tarefas. Além de
poluir visualmente, ela é um risco operacional: um Ctrl+C sem querer
NAQUELA janela mata o processo inteiro, porque é o console quem entrega o
sinal e só entrega para quem tem foco de teclado nele.

A saída escolhida NÃO é pythonw.exe (o MSYS2 não empacota um — ver LEIAME)
e NÃO é fechar o console (perderia o stdout/stderr, único jeito de
diagnosticar um travamento sem anexar debugger). É: esconder a janela da
barra de tarefas e do Alt+Tab, e representar o processo por um ícone na
bandeja (system tray) com um menu para reabrir o console quando precisar
olhar o log, ou encerrar o programa.

Escondida, a janela do console não pode receber foco de teclado — é assim
que o Windows entrega Ctrl+C (o conhost só reage a ele com o console em
primeiro plano). Esconder resolve o pedido por si só; o ícone de bandeja é
o que evita perder o acesso ao log de vez.

QUANDO CHAMAR
    iniciar() deve ser chamado depois que o login no cofre for aceito (ver
    main(), em acessos.py) — esconder ANTES faria o operador digitar a
    senha mestra sem o console por perto para acompanhar um erro de
    carregamento, por exemplo. Depois do login, só a janela GTK importa.

LIMITAÇÃO CONHECIDA: Windows Terminal
---------------------------------------
GetConsoleWindow() devolve a HWND do host de console clássico
(conhost.exe). Quando o lançador roda dentro do Windows Terminal (comum no
Windows 11, que o adota como padrão), o conhost por trás de cada aba já
fica sempre oculto por design — a HWND que pegamos é um "proxy" invisível,
e escondê-lo não fecha a ABA do Windows Terminal que o operador vê. Nesse
caso a aba continua visível e o ícone de bandeja é um extra, não um
substituto. Não há solução sem tocar a API própria do Windows Terminal.
Documentado para não virar surpresa: quem roda via `acessos.cmd` num
cmd.exe/console-host clássico tem o comportamento completo.
"""

import ctypes
import sys
from ctypes import wintypes

DISPONIVEL = sys.platform == "win32"

if DISPONIVEL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HANDLE),
            ("hIcon", wintypes.HANDLE),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HANDLE),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", wintypes.HANDLE),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HANDLE),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uTimeoutOrVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", ctypes.c_byte * 16),
            ("hBalloonIcon", wintypes.HANDLE),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", POINT),
        ]

    # ---- so para rasterizar icones/acessos.svg num HICON de verdade
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", BITMAPINFOHEADER),
            # BI_RGB de 32bpp nao usa tabela de cores; o campo existe so
            # para o struct ter o tamanho que CreateDIBSection espera.
            ("bmiColors", wintypes.DWORD * 3),
        ]

    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", wintypes.BOOL),
            ("xHotspot", wintypes.DWORD),
            ("yHotspot", wintypes.DWORD),
            ("hbmMask", wintypes.HANDLE),
            ("hbmColor", wintypes.HANDLE),
        ]

    gdi32.CreateDIBSection.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = wintypes.HANDLE
    gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.UINT,
                                   wintypes.UINT, ctypes.c_void_p]
    gdi32.CreateBitmap.restype = wintypes.HANDLE
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL
    user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
    user32.CreateIconIndirect.restype = wintypes.HANDLE
    user32.DestroyIcon.argtypes = [wintypes.HANDLE]
    user32.DestroyIcon.restype = wintypes.BOOL

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_long
    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.WORD
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HANDLE, wintypes.HANDLE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND,
                                    wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = ctypes.c_long
    user32.LoadIconW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR]
    user32.LoadIconW.restype = wintypes.HANDLE
    user32.CreatePopupMenu.argtypes = []
    user32.CreatePopupMenu.restype = wintypes.HANDLE
    user32.AppendMenuW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                   ctypes.c_size_t, wintypes.LPCWSTR]
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.DestroyMenu.argtypes = [wintypes.HANDLE]
    user32.DestroyMenu.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [
        wintypes.HANDLE, wintypes.UINT, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
    user32.TrackPopupMenu.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL

    kernel32.GetConsoleWindow.argtypes = []
    kernel32.GetConsoleWindow.restype = wintypes.HWND
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HANDLE

    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD,
                                          ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
else:                                              # pragma: no cover
    user32 = kernel32 = shell32 = gdi32 = None

# ---- constantes Win32 usadas aqui
DIB_RGB_COLORS = 0
BI_RGB = 0
SW_HIDE, SW_SHOW = 0, 5
WS_OVERLAPPED = 0x00000000
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1          # mensagem de callback do nosso icone
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_NULL = 0x0000
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x01, 0x02, 0x04
MF_STRING, MF_SEPARATOR, MF_GRAYED = 0x0000, 0x0800, 0x0001
TPM_RIGHTBUTTON, TPM_BOTTOMALIGN = 0x0002, 0x0020
PM_REMOVE = 0x0001
IDI_APPLICATION = 32512
ID_TOGGLE, ID_SAIR = 1001, 1002

_CLASSE = "AcessosBandeja"

# ---- estado do modulo (um unico icone, um unico HWND — o app tem so um)
_hwnd = None
_console_hwnd = None
_escondido = False
_ativo = False
_ao_sair = None
_timer_id = None
_wndproc_ref = None      # mantem o CFUNCTYPE vivo (ver conpty.py/vncwidget.py)
_hicone_proprio = None   # HICON criado por nos (precisa DestroyIcon); None
                         # se caiu no IDI_APPLICATION (icone do sistema,
                         # compartilhado — nao se destroi)


def disponivel():
    return DISPONIVEL


def _icone_da_svg(caminho_svg, tamanho=32):
    """Rasteriza icones/acessos.svg num HICON de verdade, via GdkPixbuf —
    a mesma biblioteca que Gtk.Window.set_default_icon_from_file() ja usa
    em acessos.py, entao nao ha dependencia nova aqui.

    Devolve None em qualquer falha (arquivo ausente, loader de SVG faltando
    no GTK, etc.) — quem chama cai de volta no icone generico do sistema.

    COMO UM PIXBUF VIRA UM HICON
    ------------------------------
    O Win32 nao aceita SVG nem PNG diretamente num HICON: precisa de um DIB
    de 32 bits (BGRA, nao RGBA — os canais saem invertidos do GdkPixbuf) e
    de uma mascara monocromatica, mesmo que ela nao va ser usada de fato.
    Com o canal alfa de verdade no DIB de cor, o Windows moderno (Vista+)
    ja desenha a transparencia certa e ignora o conteudo da mascara — por
    isso ela pode ser toda zero. E o mesmo truque usado por qualquer
    biblioteca de icone de bandeja que nao depende de um .ico pronto.
    """
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
    except Exception:
        return None

    try:
        pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            caminho_svg, tamanho, tamanho, False)
        if not pix.get_has_alpha():
            pix = pix.add_alpha(False, 0, 0, 0)
        largura, altura = pix.get_width(), pix.get_height()
        stride = pix.get_rowstride()
        canais = pix.get_n_channels()
        dados = pix.get_pixels()

        # RGBA (GdkPixbuf) -> BGRA (DIB do Windows), linha por linha para
        # descartar o padding de fim de linha que o rowstride pode ter.
        bgra = bytearray(largura * altura * 4)
        for y in range(altura):
            base_o = y * stride
            base_d = y * largura * 4
            for x in range(largura):
                po = base_o + x * canais
                pd = base_d + x * 4
                r, g, b = dados[po], dados[po + 1], dados[po + 2]
                a = dados[po + 3] if canais >= 4 else 255
                bgra[pd] = b
                bgra[pd + 1] = g
                bgra[pd + 2] = r
                bgra[pd + 3] = a

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = largura
        bmi.bmiHeader.biHeight = -altura     # negativo: DIB top-down, sem
                                              # inverter linha a linha
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        ppv_bits = ctypes.c_void_p()
        hbm_cor = gdi32.CreateDIBSection(
            None, ctypes.byref(bmi), DIB_RGB_COLORS,
            ctypes.byref(ppv_bits), None, 0)
        if not hbm_cor or not ppv_bits.value:
            return None
        ctypes.memmove(ppv_bits, bytes(bgra), len(bgra))

        # mascara monocromatica "vazia": cada linha alinhada em 2 bytes,
        # exigencia do CreateBitmap para bitmaps de 1 bit por pixel.
        passo_mascara = ((largura + 15) // 16) * 2
        buf_mascara = bytes(passo_mascara * altura)
        hbm_mascara = gdi32.CreateBitmap(largura, altura, 1, 1, buf_mascara)
        if not hbm_mascara:
            gdi32.DeleteObject(hbm_cor)
            return None

        info = ICONINFO()
        info.fIcon = True
        info.xHotspot = 0
        info.yHotspot = 0
        info.hbmMask = hbm_mascara
        info.hbmColor = hbm_cor
        hicone = user32.CreateIconIndirect(ctypes.byref(info))

        # o CreateIconIndirect copia o que precisa; os bitmaps originais
        # nao servem mais depois disso.
        gdi32.DeleteObject(hbm_cor)
        gdi32.DeleteObject(hbm_mascara)
        return hicone or None
    except Exception:
        return None


def _wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_TRAYICON:
        evento = lparam & 0xFFFF
        if evento in (WM_LBUTTONUP, WM_RBUTTONUP, WM_LBUTTONDBLCLK):
            _abrir_menu(hwnd)
        return 0
    if msg == WM_COMMAND:
        _tratar_comando(wparam & 0xFFFF)
        return 0
    if msg == WM_DESTROY:
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _abrir_menu(hwnd):
    # SetForegroundWindow ANTES do TrackPopupMenu, e um WM_NULL depois: sem
    # isto o menu as vezes nao fecha sozinho ao clicar fora dele — e um
    # comportamento documentado do proprio TrackPopupMenu, nao um bug daqui.
    menu = user32.CreatePopupMenu()
    if not menu:
        return
    try:
        texto_toggle = ("Mostrar terminal (diagnóstico)" if _escondido
                        else "Ocultar terminal")
        user32.AppendMenuW(menu, MF_STRING, ID_TOGGLE, texto_toggle)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_SAIR, "Sair do Acessos")

        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)
        user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_BOTTOMALIGN,
                              pt.x, pt.y, 0, hwnd, None)
        user32.PostMessageW(hwnd, WM_NULL, 0, 0)
    finally:
        user32.DestroyMenu(menu)


def _tratar_comando(cmd):
    if cmd == ID_TOGGLE:
        if _escondido:
            mostrar_console()
        else:
            esconder_console()
    elif cmd == ID_SAIR:
        if _ao_sair is not None:
            _ao_sair()


def _notificar(mensagem, **campos):
    dados = NOTIFYICONDATAW()
    dados.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    dados.hWnd = _hwnd
    dados.uID = 1
    for chave, valor in campos.items():
        setattr(dados, chave, valor)
    shell32.Shell_NotifyIconW(mensagem, ctypes.byref(dados))


def _atualizar_dica():
    dica = ("Acessos — terminal oculto" if _escondido
            else "Acessos — terminal visível")
    _notificar(NIM_MODIFY, uFlags=NIF_TIP, szTip=dica)


def esconder_console():
    global _escondido
    if _console_hwnd:
        user32.ShowWindow(_console_hwnd, SW_HIDE)
    _escondido = True
    if _ativo:
        _atualizar_dica()


def mostrar_console():
    global _escondido
    if _console_hwnd:
        user32.ShowWindow(_console_hwnd, SW_SHOW)
        user32.SetForegroundWindow(_console_hwnd)
    _escondido = False
    if _ativo:
        _atualizar_dica()


def definir_ao_sair(fn):
    """Troca o callback do item 'Sair' do menu.

    Chamado de novo depois que a Janela principal existe — em iniciar()
    ela ainda não foi criada, então o callback inicial é None."""
    global _ao_sair
    _ao_sair = fn


def _bombear_mensagens():
    """Drena a fila de mensagens da nossa janela, sem bloquear.

    Roda num GLib.timeout_add, no MESMO thread do Gtk.main() — PeekMessage
    sem PM_REMOVE bloqueante devolve na hora se nao ha nada, entao nao ha
    risco de travar o loop de eventos do GTK (mesmo raciocinio do _bater()
    em vncwidget.py, so que aqui e a fila do Win32 e nao um timer de
    redesenho)."""
    msg = MSG()
    for _ in range(32):           # teto por tick: nunca monopoliza o loop
        if not user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            break
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return True


def iniciar(ao_sair=None, caminho_icone=None):
    """Esconde o console do lançador e sobe o ícone de bandeja no lugar.

    Chamar 1x, depois que o login no cofre for aceito. Sem efeito (devolve
    False) fora do Windows, sem console para esconder (GetConsoleWindow()
    devolve NULL — ex.: já rodando destacado) ou se o setup Win32 falhar
    por qualquer motivo: o app segue com o console visível, que é o
    comportamento de sempre. Nunca interrompe a inicialização por causa
    disto — é conveniência, não requisito.

    `caminho_icone`: caminho do icones/acessos.svg (ver caminho_icone() em
    acessos.py — não é importado daqui para não criar um import circular).
    Rasterizado via GdkPixbuf para o ícone da bandeja sair igual ao da
    barra de título, em vez do ícone genérico do Windows. Se vier None, ou
    a rasterização falhar por qualquer motivo, cai no genérico mesmo.
    """
    global _hwnd, _console_hwnd, _ativo, _timer_id, _wndproc_ref, _escondido
    global _hicone_proprio

    if not DISPONIVEL or _ativo:
        return False

    try:
        from gi.repository import GLib
    except Exception:
        return False

    console = kernel32.GetConsoleWindow()
    if not console:
        return False           # nada para esconder (ex.: ja sem console)

    try:
        _wndproc_ref = WNDPROC(_wndproc)
        hinst = kernel32.GetModuleHandleW(None)

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = _wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = _CLASSE
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            return False       # ja registrada de uma corrida anterior, ou falhou

        hwnd = user32.CreateWindowExW(
            0, _CLASSE, "Acessos (bandeja)", WS_OVERLAPPED,
            0, 0, 0, 0, None, None, hinst, None)
        if not hwnd:
            return False
        # NUNCA chamamos ShowWindow nesta janela: sem WS_VISIBLE e sem
        # show, ela nao aparece na barra de tarefas nem no Alt+Tab — so
        # existe para receber mensagens (WndProc) e ser dona do icone.

        hicon = None
        if caminho_icone:
            hicon = _icone_da_svg(caminho_icone)
            _hicone_proprio = hicon
        if not hicon:
            hicon = user32.LoadIconW(
                None, ctypes.cast(IDI_APPLICATION, wintypes.LPCWSTR))

        _hwnd = hwnd
        _console_hwnd = console

        dados = NOTIFYICONDATAW()
        dados.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        dados.hWnd = hwnd
        dados.uID = 1
        dados.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        dados.uCallbackMessage = WM_TRAYICON
        dados.hIcon = hicon
        dados.szTip = "Acessos — terminal oculto"
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(dados)):
            user32.DestroyWindow(hwnd)
            _hwnd = None
            return False

        _ativo = True
        definir_ao_sair(ao_sair)
        esconder_console()
        _timer_id = GLib.timeout_add(30, _bombear_mensagens)
        return True
    except Exception:
        # qualquer falha aqui e cosmetica: o console so continua visivel
        return False


def encerrar():
    """Remove o ícone da bandeja e devolve o console, se estava escondido.

    Chamar no fechamento do app (Janela._sair), ANTES do Gtk.main_quit —
    sem isto o ícone fica 'fantasma' na bandeja até o Explorer notar que o
    processo morreu (mesmo problema clássico de qualquer app de bandeja
    que não limpa Shell_NotifyIcon(NIM_DELETE) na saída)."""
    global _ativo, _hwnd, _timer_id, _escondido, _hicone_proprio

    if not _ativo:
        return
    try:
        from gi.repository import GLib
        if _timer_id is not None:
            GLib.source_remove(_timer_id)
    except Exception:
        pass
    _timer_id = None
    try:
        if _console_hwnd and _escondido:
            user32.ShowWindow(_console_hwnd, SW_SHOW)
        _notificar(NIM_DELETE)
        if _hwnd:
            user32.DestroyWindow(_hwnd)
        # so o icone que NOS criamos (via _icone_da_svg) precisa ser
        # destruido — o IDI_APPLICATION e um recurso do sistema, e
        # compartilhado, e destrui-lo derrubaria outros usos dele
        if _hicone_proprio:
            user32.DestroyIcon(_hicone_proprio)
    except Exception:
        pass
    _hwnd = None
    _hicone_proprio = None
    _escondido = False
    _ativo = False
