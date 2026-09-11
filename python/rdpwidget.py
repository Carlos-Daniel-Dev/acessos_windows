#!/usr/bin/env python3
"""RdpWidget — Gtk.DrawingArea que fala RDP via libfreerdp, sem processo
externo.

Substitui (quando maduro — ver RDPSHIM-interno.md, não publicado) o
esquema atual de rdp_windows.py, que abre wfreerdp.exe como processo
externo e reparenta a janela dele (SetParent). Aqui o RDP desenha num
framebuffer nosso — mesmo padrão do vncwidget.py/vncshim.c, só que contra
libfreerdp/libwinpr em vez de libvncclient.

ARQUITETURA
-----------
    thread de rede            thread principal (GTK)
    --------------            ----------------------
    rs_esperar            -->   GLib.idle_add(...) so na conexao/queda
    rs_processar               (atualizacao de tela NAO agenda idle_add
    escreve em gdi->            por callback — mesmo motivo do VNC:
    primary_buffer               disputa de GIL entre sessoes trava a
                                  interface. Um relogio de ~60/s decide
                                  quando repintar, olhando so a area
                                  suja acumulada.)

O acesso a libfreerdp/libwinpr nao e ctypes direto: passa pelo shim em C
(rdpshim.c), porque rdpContext/rdpSettings tambem tem forma que muda por
build — mesma razao do vncshim.c existir pro VNC. Ver rdpshim.c e
RDPSHIM-interno.md (nao publicado, so nesta maquina) para o fluxo
completo.

ESTADO: em construcao, NAO usado por acessos.py ainda. rdp_windows.py
continua sendo o caminho de producao.

Sinais emitidos (mesmo vocabulario do vncwidget.py, pra facilitar troca):
    rdp-connected      — TCP + TLS + NLA completos
    rdp-initialized    — framebuffer pronto (gdi_init concluido)
    rdp-disconnected   — sessao terminou
    rdp-error(str)     — falhou; o texto explica
"""

import ctypes
import os
import sys
import threading

import cairo
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GObject  # noqa: E402


# --------------------------------------------------------------- shim
#
# Mesmo padrao do vncwidget.py: nome/carregador variam por plataforma,
# mas este modulo so existe no Windows (RDP embutido no Linux usa
# gtk-frdp/Gtk.Socket, ver acessos.py) — carregamento sempre via WinDLL.
_NOME_SHIM = "librdpshim.dll"


def _carregar_shim():
    """Mesma logica de _carregar_shim() em vncwidget.py — ver ali o
    porque de sys._MEIPASS entrar na conta quando empacotado."""
    aqui = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        aqui = getattr(sys, "_MEIPASS", aqui)
    for caminho in (os.path.join(aqui, _NOME_SHIM), _NOME_SHIM):
        try:
            return ctypes.WinDLL(caminho)
        except OSError:
            continue
    raise OSError(
        "%s nao encontrada. Compile com compilar_exe.ps1/instalar.ps1 — "
        "ela precisa ficar ao lado de rdpwidget.py." % _NOME_SHIM)


_lib = _carregar_shim()

CB_ATUALIZOU = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int)
CB_REDIMENSIONOU = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int,
                                    ctypes.c_int)
CB_DESCONECTOU = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32,
                                  ctypes.c_char_p)

_lib.rs_criar.restype = ctypes.c_void_p
_lib.rs_criar.argtypes = [ctypes.c_void_p, CB_ATUALIZOU, CB_REDIMENSIONOU,
                          CB_DESCONECTOU]
_lib.rs_definir_credenciais.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                        ctypes.c_char_p, ctypes.c_char_p]
_lib.rs_definir_tela.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
_lib.rs_definir_ignorar_certificado.argtypes = [ctypes.c_void_p, ctypes.c_int]
_lib.rs_conectar.restype = ctypes.c_int
_lib.rs_conectar.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
_lib.rs_esperar.restype = ctypes.c_int
_lib.rs_esperar.argtypes = [ctypes.c_void_p, ctypes.c_int]
_lib.rs_processar.restype = ctypes.c_int
_lib.rs_processar.argtypes = [ctypes.c_void_p]
_lib.rs_framebuffer.restype = ctypes.c_void_p
_lib.rs_framebuffer.argtypes = [ctypes.c_void_p]
_lib.rs_largura.restype = ctypes.c_int
_lib.rs_largura.argtypes = [ctypes.c_void_p]
_lib.rs_altura.restype = ctypes.c_int
_lib.rs_altura.argtypes = [ctypes.c_void_p]
_lib.rs_morto.restype = ctypes.c_int
_lib.rs_morto.argtypes = [ctypes.c_void_p]
_lib.rs_tecla.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int]
_lib.rs_ponteiro.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int]
_lib.rs_destruir.argtypes = [ctypes.c_void_p]


# ------------------------------------------------------- flags do winpr
#
# winpr/input.h — repetidos aqui porque so existem do lado C; o shim so
# repassa inteiros crus (mesma disciplina do vncshim.c/ATALHOS do VNC).
KBD_FLAGS_EXTENDED = 0x0100
KBD_FLAGS_RELEASE = 0x8000

PTR_FLAGS_WHEEL_NEGATIVE = 0x0100
PTR_FLAGS_WHEEL = 0x0200
PTR_FLAGS_MOVE = 0x0800
PTR_FLAGS_DOWN = 0x8000
PTR_FLAGS_BUTTON1 = 0x1000     # esquerdo
PTR_FLAGS_BUTTON2 = 0x2000     # direito
PTR_FLAGS_BUTTON3 = 0x4000     # meio

# Teclas "estendidas" no PS/2 Set 1 — o GDK nao expoe esse bit separado
# do hardware_keycode (ver RDPSHIM-interno.md), entao a lista e estatica.
# hardware_keycode do GDK no backend Win32 JA E o scancode cru; so este
# bit precisa de decisao em Python.
_TECLAS_ESTENDIDAS = {
    Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right,
    Gdk.KEY_Insert, Gdk.KEY_Delete, Gdk.KEY_Home, Gdk.KEY_End,
    Gdk.KEY_Page_Up, Gdk.KEY_Page_Down,
    Gdk.KEY_Num_Lock, Gdk.KEY_KP_Divide, Gdk.KEY_KP_Enter,
    Gdk.KEY_Control_R, Gdk.KEY_Alt_R,
    Gdk.KEY_Super_L, Gdk.KEY_Super_R, Gdk.KEY_Menu, Gdk.KEY_Print,
}


class RdpWidget(Gtk.DrawingArea):
    __gsignals__ = {
        "rdp-connected": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "rdp-initialized": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "rdp-disconnected": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "rdp-error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self._sessao = None
        self._surface = None
        self._remoto = (0, 0)
        self._parar = threading.Event()
        self._sujo_rect = None
        self._lock_sujo = threading.Lock()
        self._lock = threading.Lock()
        self._timer_bate = None
        self._thread = None

        # Mesma regra do vncwidget.py: instancias de CFUNCTYPE PRECISAM
        # ficar referenciadas em self, senao o GC coleta e o C chama
        # endereco morto -> segfault.
        self._cb_at = CB_ATUALIZOU(self._c_atualizou)
        self._cb_rz = CB_REDIMENSIONOU(self._c_redimensionou)
        self._cb_desc = CB_DESCONECTOU(self._c_desconectou)

        self.set_can_focus(True)
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
            | Gdk.EventMask.KEY_RELEASE_MASK
            | Gdk.EventMask.FOCUS_CHANGE_MASK)

        self.connect("draw", self._desenhar)
        self.connect("button-press-event", self._botao)
        self.connect("button-release-event", self._botao)
        self.connect("motion-notify-event", self._movimento)
        self.connect("scroll-event", self._roda)
        self.connect("key-press-event", self._tecla)
        self.connect("key-release-event", self._tecla)
        self.connect("focus-out-event", self._perdeu_foco)
        self.connect("destroy", lambda *_a: self.desconectar())

    # ---------------------------------------------------- ciclo de vida
    def conectar(self, host, porta, usuario=None, senha=None, dominio=None,
                largura=1024, altura=768, ignorar_certificado=True):
        if self._sessao is not None:
            self.desconectar()
        self._parar.clear()
        self._sessao = _lib.rs_criar(None, self._cb_at, self._cb_rz,
                                     self._cb_desc)
        if not self._sessao:
            self.emit("rdp-error", "falha ao criar sessão RDP")
            return

        _lib.rs_definir_credenciais(
            self._sessao,
            (usuario or "").encode("utf-8"),
            (senha or "").encode("utf-8"),
            (dominio or "").encode("utf-8"))
        _lib.rs_definir_tela(self._sessao, int(largura), int(altura))
        _lib.rs_definir_ignorar_certificado(
            self._sessao, 1 if ignorar_certificado else 0)

        if self._timer_bate is None:
            self._timer_bate = GLib.timeout_add(16, self._bater)
        self._thread = threading.Thread(
            target=self._rodar, args=(host, porta), daemon=True)
        self._thread.start()

    def _rodar(self, host, porta):
        """Thread de rede. Nada de GTK aqui — tudo volta por idle_add,
        mesma disciplina do vncwidget.py._rodar.

        Em falha, NAO reporta erro genérico aqui: cb_post_disconnect (ver
        rdpshim.c) já é chamado pelo próprio FreeRDP em qualquer caminho
        de falha de conexão — mesmo antes do handshake terminar — e
        dispara _c_desconectou() com o motivo REAL (ex.: "Logon failed").
        Emitir os dois era ruído: testado ao vivo, os dois sinais
        chegavam juntos pra uma unica falha."""
        sessao = self._sessao
        if not _lib.rs_conectar(sessao, host.encode("utf-8"), int(porta)):
            return
        GLib.idle_add(self._conectou)

        while not self._parar.is_set():
            n = _lib.rs_esperar(sessao, 200)     # 200ms
            if n < 0:
                break
            if n == 0:
                continue
            if not _lib.rs_processar(sessao):
                break
        GLib.idle_add(self._caiu)

    def desconectar(self):
        if self._timer_bate is not None:
            try:
                GLib.source_remove(self._timer_bate)
            except Exception:
                pass
            self._timer_bate = None
        self._parar.set()
        t, self._thread = self._thread, None

        with self._lock:
            sessao, self._sessao = self._sessao, None
            self._surface = None
        if sessao is None:
            return

        # NAO DESTRUIR COM A THREAD VIVA — mesmo cuidado do vs_destruir
        # no VNC. rs_destruir chama freerdp_disconnect/freerdp_free; se a
        # thread de rede ainda estiver dentro de rs_processar (ela pode
        # estar, ha sempre uma janela), e uso-apos-liberacao.
        if t is None or t is threading.current_thread():
            _lib.rs_destruir(sessao)
            return

        t.join(timeout=0.5)
        if not t.is_alive():
            _lib.rs_destruir(sessao)
            return

        tentativas = [0]

        def _tentar():
            tentativas[0] += 1
            if t.is_alive() and tentativas[0] < 60:      # ate ~30s
                return True
            try:
                _lib.rs_destruir(sessao)
            except Exception:
                pass
            return False

        GLib.timeout_add(500, _tentar)

    # ------------------------------------------------ vindos do C/thread
    def _c_atualizou(self, _ctx, x, y, w, h):
        """THREAD DE REDE. So anota a area suja — ver _bater(). Mesma
        razao do vncwidget.py: idle_add por callback disputa o GIL entre
        sessoes e congela a interface."""
        with self._lock_sujo:
            if self._sujo_rect is None:
                self._sujo_rect = [x, y, x + w, y + h]
            else:
                r = self._sujo_rect
                r[0] = min(r[0], x)
                r[1] = min(r[1], y)
                r[2] = max(r[2], x + w)
                r[3] = max(r[3], y + h)

    def _c_redimensionou(self, _ctx, w, h):
        """THREAD DE REDE — chamado por cb_post_connect, uma vez, quando
        gdi_init() termina e o framebuffer passa a existir."""
        GLib.idle_add(self._aplicar_redimensionamento, w, h)

    def _c_desconectou(self, _ctx, codigo, motivo):
        """THREAD DE REDE — cb_post_disconnect."""
        texto = motivo.decode("utf-8", "replace") if motivo else ""
        GLib.idle_add(self._reportar_desconexao, codigo, texto)

    def _aplicar_redimensionamento(self, w, h):
        with self._lock:
            self._remoto = (w, h)
            self._surface = None      # recriada no proximo _desenhar
        self.set_size_request(w, h)
        self.emit("rdp-initialized")
        return False

    def _reportar_desconexao(self, codigo, texto):
        self.emit("rdp-disconnected")
        if codigo and texto:
            self.emit("rdp-error", "%s (0x%08X)" % (texto, codigo))
        return False

    def _bater(self):
        """Relogio de repintura (~60/s), mesma logica do vncwidget.py."""
        if not self.get_mapped():
            with self._lock_sujo:
                self._sujo_rect = None
            return True

        with self._lock_sujo:
            r = self._sujo_rect
            self._sujo_rect = None
        if r is None:
            return True
        with self._lock:
            if self._sessao is None:
                return True
            lw, lh = self._remoto
            x0, y0, x1, y1 = r
            x0 = max(0, min(x0, lw)); x1 = max(x0, min(x1, lw))
            y0 = max(0, min(y0, lh)); y1 = max(y0, min(y1, lh))
            larg = max(1, x1 - x0)
            alt = max(1, y1 - y0)
        self.queue_draw_area(x0, y0, larg, alt)
        return True

    def _garantir_surface(self):
        """Cria (ou recria, apos redimensionar) a Gtk.ImageSurface que
        aponta DIRETO pro gdi->primary_buffer — sem copia por quadro,
        mesma tecnica do vncwidget.py com o frameBuffer da libvncclient.

        FORMATO: pedimos PIXEL_FORMAT_BGRX32 no shim (ver cb_post_connect
        em rdpshim.c) — casa com cairo.FORMAT_RGB24 em little-endian
        (bytes B,G,R,X na memoria), mesma logica de canal que o vncshim.c
        documenta pro VNC."""
        if self._sessao is None or _lib.rs_morto(self._sessao):
            return None
        if self._surface is not None:
            return self._surface
        w = _lib.rs_largura(self._sessao)
        h = _lib.rs_altura(self._sessao)
        if w <= 0 or h <= 0:
            return None
        ptr = _lib.rs_framebuffer(self._sessao)
        if not ptr:
            return None
        stride = cairo.ImageSurface.format_stride_for_width(
            cairo.FORMAT_RGB24, w)
        buf = (ctypes.c_uint8 * (stride * h)).from_address(ptr)
        self._surface = cairo.ImageSurface.create_for_data(
            buf, cairo.FORMAT_RGB24, w, h, stride)
        return self._surface

    def _desenhar(self, _widget, cr):
        with self._lock:
            surf = self._garantir_surface()
            if surf is None:
                return False
            try:
                surf.mark_dirty()
            except Exception:
                pass
            cr.set_source_surface(surf, 0, 0)
            cr.paint()
        return False

    def _conectou(self):
        self.emit("rdp-connected")
        return False

    def _caiu(self):
        self.emit("rdp-disconnected")
        return False

    # ---------------------------------------------------------- entrada
    def _tecla(self, _widget, ev):
        pressionada = (ev.type == Gdk.EventType.KEY_PRESS)
        estendida = ev.keyval in _TECLAS_ESTENDIDAS
        if self._sessao is not None:
            _lib.rs_tecla(self._sessao, int(ev.hardware_keycode),
                         1 if estendida else 0, 1 if pressionada else 0)
        return True

    def _perdeu_foco(self, _widget, _ev):
        # Sem captura total de teclado nesta v1 (ver TODO em
        # RDPSHIM-interno.md) — nada de modificador pra soltar aqui
        # ainda, mas o handler fica pronto pro dia que precisar (mesmo
        # cuidado que o VNC tem hoje com Ctrl/Alt presos).
        return False

    def _botao_flags(self, ev):
        if ev.button == 1:
            return PTR_FLAGS_BUTTON1
        if ev.button == 2:
            return PTR_FLAGS_BUTTON3
        if ev.button == 3:
            return PTR_FLAGS_BUTTON2
        return 0

    def _botao(self, _widget, ev):
        self.grab_focus()
        flags = self._botao_flags(ev)
        if not flags:
            return False
        if ev.type == Gdk.EventType.BUTTON_PRESS:
            flags |= PTR_FLAGS_DOWN
        if self._sessao is not None:
            _lib.rs_ponteiro(self._sessao, int(ev.x), int(ev.y), flags)
        return True

    def _movimento(self, _widget, ev):
        if self._sessao is not None:
            _lib.rs_ponteiro(self._sessao, int(ev.x), int(ev.y),
                            PTR_FLAGS_MOVE)
        return True

    def _roda(self, _widget, ev):
        if self._sessao is None:
            return True
        # magnitude 120 = um "clique" de roda (MS-RDPBCGR); sem suporte a
        # rolagem fina (SMOOTH_SCROLL) nesta v1.
        flags = PTR_FLAGS_WHEEL | 0x78
        if ev.direction == Gdk.ScrollDirection.DOWN:
            flags |= PTR_FLAGS_WHEEL_NEGATIVE
        elif ev.direction != Gdk.ScrollDirection.UP:
            return True
        _lib.rs_ponteiro(self._sessao, int(ev.x), int(ev.y), flags)
        return True
