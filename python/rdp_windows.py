#!/usr/bin/env python3
"""AbaRdpWindows — RDP embutido na aba, no Windows, via FreeRDP + win_embed.

Espelha a AbaRdp do acessos.py (Linux/X11, que usa Gtk.Socket +
/parent-window:), mas troca o mecanismo de encaixe: aqui não existe XID
nem XEmbed, então a janela do FreeRDP é reparentada DEPOIS de subir, com
SetParent (ver win_embed.py) — mesma ideia, ordem invertida.

POR QUE FREERDP E NAO mstsc.exe
--------------------------------
O LEIAME do projeto pede ramos opensource quando possível, e o resto do
Acessos já depende do vocabulário de flags do xfreerdp (/cert:ignore,
/d:, /u:, /p:) — usar o wfreerdp.exe (FreeRDP para Windows) mantém a
MESMA linha de comando e o MESMO tratamento de erro do lado Linux, só
trocando o binário. O mstsc.exe é fechado e não tem /cert:ignore
equivalente, então quebraria justamente o caso do parque com certificado
autoassinado / certificado por IP que o projeto já tem que tratar hoje.

INTEGRACAO
----------
Segue o MESMO padrão de fábrica que o ssh.py já usa (construir(base,
**utilitarios)), porque a classe herda de AbaBase — que só existe dentro
de acessos.py. No acessos.py:

    if sys.platform == "win32":
        import rdp_windows as _rdp_win
        AbaRdpWindows = _rdp_win.construir(
            AbaBase, CapturaTeclado, add_class=add_class, rotulo=rotulo)

FLUXO
-----
    1. cria um Gtk.DrawingArea vazio como "palco" (não é mais Gtk.Socket)
    2. spawna o wfreerdp.exe (GLib.spawn_async, igual ao Linux)
    3. espera a janela dele aparecer (win_embed.find_hwnd_by_pid)
    4. reparenta com SetParent (win_embed.embed_hwnd)
    5. redimensiona a janela filha a cada 'size-allocate' do palco
    6. se não aparecer em 8s, ou a build não aceitar reparenting, cai
       para janela externa — mesma degradação do lado Linux quando o
       cliente "não suporta /parent-window".

O QUE FICOU DE FORA, DE PROPOSITO
------------------------------------
Captura total de teclado (CapturaTeclado/GrabNativo): implementada com
XGrabKeyboard no Linux, sem equivalente aqui ainda. O botão ⌨ fica
desabilitado com um tooltip explicando. Portar isso é SetWindowsHookEx
de baixo nível — trabalho de outra ordem, deixado para depois.
"""

import os
import shutil
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # noqa: E402

import win_embed

DEBUG = "--debug" in sys.argv


def _bin_rdp_windows():
    """Acha o FreeRDP para Windows. Nome do binário varia por forma de
    instalação: build oficial gera 'wfreerdp.exe'; pacotes do MSYS2/vcpkg
    às vezes só têm 'freerdp.exe'. Tenta os dois, nessa ordem.

    EMPACOTADO (PyInstaller): o compilar_exe.ps1 embute o wfreerdp.exe e
    toda a cadeia de DLLs dele dentro do bundle (sys._MEIPASS), pra abrir
    RDP sem exigir FreeRDP instalado à parte na máquina. Por isso a busca
    olha lá PRIMEIRO — shutil.which() só acha o que está no PATH do
    sistema, e o bundle não entra no PATH sozinho."""
    if getattr(sys, "frozen", False):
        aqui = getattr(sys, "_MEIPASS", None)
        if aqui:
            for nome in ("wfreerdp.exe", "freerdp.exe", "xfreerdp.exe"):
                caminho = os.path.join(aqui, nome)
                if os.path.isfile(caminho):
                    return caminho, nome
    for nome in ("wfreerdp.exe", "freerdp.exe", "xfreerdp.exe"):
        caminho = shutil.which(nome)
        if caminho:
            return caminho, nome
    return None, None


def construir(base, capturateclado=None, **utilitarios):
    """Cria e devolve a classe AbaRdpWindows. Chamado uma vez pelo
    acessos.py, mesmo padrão do ssh.construir()."""
    add_class = utilitarios.get("add_class", lambda w, *_c: w)
    rotulo = utilitarios.get("rotulo", lambda t, *_c, **_k: Gtk.Label(label=t))

    bases = (base, capturateclado) if capturateclado else (base,)

    class AbaRdpWindows(*bases):
        tipo = "rdp"

        def __init__(self, conexao, janela):
            super().__init__(conexao, janela)
            self.pid = None
            self.pid_janela = None    # PID real; ver win_embed.pid_real
            self.hwnd = None
            self.embutido = win_embed.disponivel()
            self.sem_encaixe = False
            self.modo_seguro = False
            self.encaixe_ok = False
            self.sem_dominio = False
            self._tent_encaixe = 0
            self._tent_pronto = 0

            self.bt_auto.set_active(getattr(self.cx, "rdp_auto", False))
            self._ligar_auto("rdp_auto")

            bt_rec = add_class(Gtk.Button(label="Reconectar"), "secundaria")
            bt_rec.connect("clicked", lambda _b: self.reconectar(manual=True))
            self.barra.pack_end(bt_rec, False, False, 0)

            self.bt_teclado = Gtk.ToggleButton(label="⌨")
            add_class(self.bt_teclado, "tog", "tog-ok", "tog-glifo")
            self.bt_teclado.set_tooltip_text(
                "Captura total de teclado ainda não portada para o "
                "Windows. Use os atalhos do próprio FreeRDP por enquanto.")
            self.bt_teclado.set_sensitive(False)
            self.barra.pack_end(self.bt_teclado, False, False, 0)

            self.palco = Gtk.DrawingArea()
            self.palco.set_size_request(1, 1)
            self.palco.set_hexpand(True)
            self.palco.set_vexpand(True)
            self.pack_start(self.palco, True, True, 0)
            self.palco.connect("size-allocate", self._on_redimensiona)
            if hasattr(self, "_iniciar_captura"):
                self._iniciar_captura()
            self.pack_start(self.exp_log, False, False, 0)

            if not self.embutido:
                self.pack_start(
                    self._aviso_externo(win_embed.ERRO_INDISPONIVEL),
                    True, True, 0)

        def _aviso_externo(self, motivo=""):
            caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            caixa.set_valign(Gtk.Align.CENTER)
            caixa.set_halign(Gtk.Align.CENTER)
            caixa.pack_start(
                rotulo("Sessão RDP em janela separada", "hero-titulo",
                      xalign=0.5), False, False, 0)
            texto = ("reparentação indisponível (%s)" % motivo if motivo else
                    "esta build do FreeRDP não reparentou a tempo")
            caixa.pack_start(rotulo(texto, "hero-sub", xalign=0.5),
                             False, False, 0)
            return caixa

        def _on_redimensiona(self, _w, alocacao):
            if self.hwnd:
                win_embed.redimensionar(self.hwnd, alocacao.width,
                                        alocacao.height)

        # ---- linha de comando: mesmo vocabulário do xfreerdp no Linux
        def _argv(self):
            binario, nome = _bin_rdp_windows()
            if not binario:
                return None, None
            argv = [binario,
                    "/v:%s:%s" % (self.cx.host, self.cx.rdp_porta),
                    "/cert:ignore"]
            if DEBUG:
                argv.append("/log-level:INFO")
            if self.cx.rdp_usuario:
                argv.append("/u:%s" % self.cx.rdp_usuario)
            if self.cx.rdp_dominio and not self.sem_dominio:
                argv.append("/d:%s" % self.cx.rdp_dominio)
            if self.cx.rdp_senha:
                argv.append("/p:%s" % self.cx.rdp_senha)

            al = self.palco.get_allocation()
            larg = al.width if al.width > 1 else 1280
            alt = al.height if al.height > 1 else 800
            argv.append("/size:%dx%d" % (max(larg, 640), max(alt, 480)))

            if not self.modo_seguro:
                if ("+clipboard" not in self.cx.rdp_extras
                        and "-clipboard" not in self.cx.rdp_extras):
                    argv.append("+clipboard")
                for extra in self.cx.rdp_extras:
                    argv.append(extra)
            return argv, nome

        def linha_comando(self, ocultar_senha=True):
            argv, _n = self._argv()
            if not argv:
                return ""
            return " ".join(
                "/p:***" if (ocultar_senha and a.startswith("/p:")) else a
                for a in argv)

        # ---- ciclo de conexão
        def conectar(self):
            if self.embutido and not self.get_mapped():
                self._estado("AGUARDE", "neutro", "preparando…")
                self._agendar(50, self._conectar_quando_pronto)
                return
            self._conectar_agora()

        def _conectar_quando_pronto(self):
            if self.fechando:
                return False
            al = self.palco.get_allocation()
            if self.get_mapped() and al.width > 1:
                self._tent_pronto = 0
                self._conectar_agora()
                return False
            self._tent_pronto += 1
            if self._tent_pronto > 40:
                self._tent_pronto = 0
                self.reg("aba em segundo plano: usando 1280x800 como tamanho")
                self._conectar_agora()
                return False
            return True

        def _conectar_agora(self):
            argv, nome = self._argv()
            if not argv:
                self._estado("ERRO", "erro", "FreeRDP não encontrado")
                self.reg("instale o FreeRDP para Windows — winget install "
                        "FreeRDP.FreeRDP, ou via MSYS2: pacman -S "
                        "mingw-w64-x86_64-freerdp")
                self.janela.avisar(
                    "FreeRDP ausente",
                    "winget install FreeRDP.FreeRDP\n"
                    "ou, dentro do MSYS2:\n"
                    "pacman -S mingw-w64-x86_64-freerdp")
                return

            self._estado("AGUARDE", "neutro", "abrindo %s…" % self.cx.host)
            self.reg("exec (%s): %s" % (nome, " ".join(
                "/p:***" if a.startswith("/p:") else a for a in argv)))

            try:
                pid, _i, _o, _e = GLib.spawn_async(
                    argv, flags=GLib.SpawnFlags.DO_NOT_REAP_CHILD |
                    GLib.SpawnFlags.SEARCH_PATH)
            except Exception as e:
                self._estado("ERRO", "erro", "falha ao iniciar")
                self.reg("spawn falhou: %s" % e)
                return

            self.pid = pid
            # O GLib devolve um HANDLE no Windows, nao um PID (ver
            # win_embed.pid_real). Guardamos os DOIS: o handle e o que o
            # child_watch_add e o encerramento esperam; o PID real e o que
            # o EnumWindows compara ao procurar a janela.
            self.pid_janela = win_embed.pid_real(pid)
            if self.pid_janela != pid:
                self.reg("pid real da janela: %s (handle %s)"
                         % (self.pid_janela, pid))
            GLib.child_watch_add(GLib.PRIORITY_DEFAULT, pid, self._on_saiu)

            if self.embutido and not self.sem_encaixe:
                self.encaixe_ok = False
                self._tent_encaixe = 0
                self._estado("AGUARDE", "atencao",
                             "aguardando a janela remota…")
                self._agendar_encaixe(pid)
            else:
                self._estado("ATIVO", "ok", self.cx.host)
            self.sucesso()

        def _agendar_encaixe(self, pid):
            """find_hwnd_by_pid já espera sozinho em passos curtos; aqui só
            controla quando desistir (~8s) sem travar a interface.

            `pid` aqui e o HANDLE do GLib, usado so para saber se a sessao
            ainda e a mesma; quem vai para o EnumWindows e o PID real
            (self.pid_janela)."""
            def procurar():
                if self.fechando or self.pid != pid:
                    return False
                hwnd = win_embed.find_hwnd_by_pid(self.pid_janela,
                                                  tentativas=1)
                if hwnd:
                    GLib.idle_add(self._encaixar, hwnd)
                    return False
                self._tent_encaixe += 1
                if self._tent_encaixe > 40:       # ~8s em passos de 200ms
                    GLib.idle_add(self._encaixe_falhou)
                    return False
                return True
            GLib.timeout_add(200, procurar)

        def _encaixar(self, hwnd):
            if self.fechando:
                return False
            pai = win_embed.gdk_hwnd(self.palco)
            al = self.palco.get_allocation()
            try:
                win_embed.embed_hwnd(hwnd, pai, al.width, al.height)
            except Exception as e:
                self.reg("SetParent falhou: %s" % e)
                self._encaixe_falhou()
                return False
            self.hwnd = hwnd
            self.encaixe_ok = True
            self.reg("janela do FreeRDP acoplada (HWND %s)" % hwnd)
            self._estado("ATIVO", "ok", self.cx.host)
            return False

        def _encaixe_falhou(self):
            self.reg("8s sem achar a janela do FreeRDP; deixando em "
                     "janela externa (a aba continua controlando pid/log)")
            self.sem_encaixe = True
            self._estado("EXTERNO", "atencao", "janela separada")
            self.pack_start(self._aviso_externo(), True, True, 0)
            self.show_all()
            return False

        def _on_saiu(self, pid, status, *_a):
            GLib.spawn_close_pid(pid)
            self.pid = None
            self.pid_janela = None
            self.hwnd = None
            if self.fechando:
                return
            codigo = status if os.name == "nt" else (
                status >> 8 if status > 255 else status)
            if codigo == 0:
                self._estado("ENCERRADO", "neutro", "sessão finalizada")
                return
            self._estado("ENCERRADO", "erro", "saiu com código %s" % codigo)
            self.reg("FreeRDP terminou, código %s" % codigo)
            # 131/132: credenciais recusadas (mesmos codigos do xfreerdp) —
            # insistir nao ajuda
            if codigo in (131, 132):
                self.reg("credenciais recusadas — auto desligado")
                self.bt_auto.set_active(False)
                return
            self._agendar_auto("código %s" % codigo)

        def reconectar(self, manual=False):
            if manual:
                self._inicio_manual()
            if self.pid:
                win_embed.encerrar_processo(self.pid_janela or self.pid)
                self.pid = None
            self.hwnd = None
            self._agendar(300, lambda: (self.conectar(), False)[1])

        def desconectar(self):
            self.fechando = True
            if self.pid:
                win_embed.encerrar_processo(self.pid_janela or self.pid)
                self.pid = None

    return AbaRdpWindows
