#!/usr/bin/env python3
"""AbaRdpShim — RDP embutido na aba via rdpwidget.py/rdpshim.c.

Substitui rdp_windows.py: em vez de abrir wfreerdp.exe como PROCESSO
EXTERNO e reparentar a janela dele (SetParent, ver win_embed.py — os
dois saíram do projeto junto com este arquivo), linka libfreerdp/libwinpr
DIRETO via shim em C, desenhando num framebuffer nosso — mesmo padrão do
VNC (vncwidget.py/vncshim.c). Ver RDPSHIM-interno.md (não publicado,
local) para o fluxo completo, referência de função e os bugs já achados
e corrigidos no caminho.

INTEGRACAO
----------
Mesmo padrão de fábrica que rdp_windows.py já usava (construir(base,
**utilitarios)), porque a classe herda de AbaBase — que só existe dentro
de acessos.py:

    if sys.platform == "win32":
        import rdp_shim as _rdp_win
        AbaRdpWindows = _rdp_win.construir(
            AbaBase, CapturaTeclado, add_class=add_class, rotulo=rotulo)

O QUE FICOU DE FORA, DE PROPOSITO (igual ao rdp_windows.py antes)
-------------------------------------------------------------------
- Captura total de teclado: sem equivalente aqui ainda (era
  SetWindowsHookEx no rdp_windows.py também — nunca foi portado). Botão
  ⌨ desabilitado com tooltip explicando.
- Canais dinâmicos (clipboard, redirecionamento de unidade/impressora):
  o rdpshim.c de hoje só faz tela + teclado + mouse. `rdp_extras`
  (opções cruas do xfreerdp no Linux) não se aplica aqui — não há linha
  de comando, é tudo via freerdp_settings_set_*() no shim.
- `rdp_tela` = janela/cheia (modo janela separada do FreeRDP): não existe
  mais "janela separada" — a sessão SEMPRE desenha dentro da aba. Só
  "dinamico" (tamanho segue o palco) faz sentido aqui; os outros dois
  valores são tratados como "dinamico" também, silenciosamente.
"""

import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # noqa: E402

import rdpwidget

DEBUG = "--debug" in sys.argv


def construir(base, capturateclado=None, **utilitarios):
    """Cria e devolve a classe AbaRdpShim. Chamado uma vez pelo
    acessos.py, mesmo padrão do rdp_windows.construir()/ssh.construir()."""
    add_class = utilitarios.get("add_class", lambda w, *_c: w)
    rotulo = utilitarios.get("rotulo", lambda t, *_c, **_k: Gtk.Label(label=t))

    bases = (base, capturateclado) if capturateclado else (base,)

    class AbaRdpShim(*bases):
        tipo = "rdp"

        def __init__(self, conexao, janela):
            super().__init__(conexao, janela)
            self._tent_pronto = 0

            self.bt_auto.set_active(getattr(self.cx, "rdp_auto", False))
            self._ligar_auto("rdp_auto")

            bt_rec = add_class(Gtk.Button(label="Reconectar"), "secundaria")
            bt_rec.connect("clicked", lambda _b: self.reconectar(manual=True))
            self.barra.pack_end(bt_rec, False, False, 0)

            self.bt_teclado = Gtk.ToggleButton(label="⌨")
            add_class(self.bt_teclado, "tog", "tog-ok", "tog-glifo")
            self.bt_teclado.set_tooltip_text(
                "Captura total de teclado ainda não portada. Use os "
                "atalhos padrão do sistema por enquanto.")
            self.bt_teclado.set_sensitive(False)
            self.barra.pack_end(self.bt_teclado, False, False, 0)

            self.palco = rdpwidget.RdpWidget()
            self.palco.set_hexpand(True)
            self.palco.set_vexpand(True)
            self.palco.connect("rdp-connected", self._on_conectado)
            self.palco.connect("rdp-initialized", self._on_iniciado)
            self.palco.connect("rdp-disconnected", self._on_desconectado)
            self.palco.connect("rdp-error", self._on_erro)
            self.pack_start(self.palco, True, True, 0)
            if hasattr(self, "_iniciar_captura"):
                self._iniciar_captura()
            self.pack_start(self.exp_log, False, False, 0)

        # ---- ciclo de conexão
        def conectar(self):
            if not self.get_mapped():
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
            if self._tent_pronto > 40:      # ~2s em passos de 50ms
                self._tent_pronto = 0
                self.reg("aba em segundo plano: usando 1024x768 como tamanho")
                self._conectar_agora()
                return False
            return True

        def _conectar_agora(self):
            al = self.palco.get_allocation()
            larg = al.width if al.width > 1 else 1024
            alt = al.height if al.height > 1 else 768

            self._estado("AGUARDE", "neutro", "abrindo %s…" % self.cx.host)
            self.reg("conectando em %s:%s (%dx%d)"
                     % (self.cx.host, self.cx.rdp_porta, larg, alt))

            self.palco.conectar(
                self.cx.host, int(self.cx.rdp_porta),
                usuario=self.cx.rdp_usuario or None,
                senha=self.cx.rdp_senha or None,
                dominio=self.cx.rdp_dominio or None,
                largura=larg, altura=alt,
                ignorar_certificado=True)

        # ---- vindos do RdpWidget (já na thread principal — ver
        # rdpwidget.py, os sinais só disparam via GLib.idle_add)
        def _on_conectado(self, _w):
            self._estado("ATIVO", "ok", self.cx.host)
            self.sucesso()

        def _on_iniciado(self, _w):
            self.reg("tela pronta")

        def _on_desconectado(self, _w):
            if self.fechando:
                return
            self._estado("ENCERRADO", "neutro", "sessão finalizada")
            self._agendar_auto("sessão encerrada")

        def _on_erro(self, _w, msg):
            self.reg("erro: %s" % msg)
            if self.fechando:
                return
            self._estado("ERRO", "erro", msg)

        def reconectar(self, manual=False):
            if manual:
                self._inicio_manual()
            self.palco.desconectar()
            self._agendar(300, lambda: (self.conectar(), False)[1])

        def desconectar(self):
            self.fechando = True
            self.palco.desconectar()

    return AbaRdpShim
