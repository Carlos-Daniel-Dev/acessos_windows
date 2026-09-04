#!/usr/bin/env python3
"""AbaSshWindows — aba de terminal SSH no Windows, sem VTE.

POR QUE NAO DA PRA SO REPARENTAR O CONSOLE DO ssh.exe
-------------------------------------------------------
O RDP (rdp_windows.py) so precisa que a janela do FreeRDP APAREÇA dentro
da aba — quem digita ali é o operador, direto na janela remota. O SSH é
diferente: o Acessos PRECISA falar com o processo (mandar a senha no
login automático, detectar o aviso de troca de host key). Reparentar a
janela de um console alheio com SetParent tira exatamente esse controle
— não existe "feed_child" para uma janela de outro processo.

A saida e ConPTY (Windows 10 1809+): o Acessos cria o pseudo-terminal,
spawna o ssh.exe DENTRO dele, e fica dono dos dois lados do cano — le
tudo que sai (para desenhar a tela) e escreve tudo que entra (teclado,
senha do login automatico). E o equivalente Windows do que o VTE faz no
Linux com Vte.Pty; so que aqui quem desenha a tela e o proprio Acessos,
com pyte interpretando os codigos ANSI.

Note que no Linux o login automatico TAMBEM passa por um mecanismo de
pty: o sshpass usado em ssh.py (_argv) cria seu proprio pseudo-terminal
por baixo para conseguir "ver" o prompt "password:" e responder — o
mesmo problema, resolvido de outro jeito. No Windows nao ha porte
confiavel do sshpass, entao o Acessos assume esse papel direto via
ConPTY.

O QUE FICOU DE FORA, DE PROPOSITO (decisao registrada em conversa)
--------------------------------------------------------------------
- Menu "biblioteca de snippets": cortado. O mecanismo de injecao (write
  no pty) continua existindo por baixo — e o MESMO usado pelo login
  automatico — mas a UI de biblioteca de comandos nao foi portada.
- Clique em URL (regex + cursor de link): nao portado nesta primeira
  versao.
- Cores ANSI: o pyte interpreta os codigos, mas o Gtk.TextView aqui
  ainda desenha tudo monocromatico — os Gtk.TextTag por atributo
  (fg/bg/bold) sao o proximo passo, deixados como TODO explicito abaixo.

DEPENDENCIAS
    pip install pyte      (o ConPTY vem do proprio Windows, via ctypes —
                           ver conpty.py; nada de pywinpty)
"""

import os
import re
import shutil

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango  # noqa: E402

try:
    import conpty
    TEM_CONPTY, ERRO_CONPTY = conpty.TEM_CONPTY, conpty.ERRO_CONPTY
except ImportError as e:
    conpty = None
    TEM_CONPTY, ERRO_CONPTY = False, str(e)

try:
    import pyte
    TEM_PYTE, ERRO_PYTE = True, ""
except ImportError as e:
    pyte = None
    TEM_PYTE, ERRO_PYTE = False, str(e)

TEM_TERMINAL_WINDOWS = TEM_CONPTY and TEM_PYTE
ERRO_TERMINAL_WINDOWS = ERRO_CONPTY or ERRO_PYTE

RE_CHAVE_MUDOU = re.compile(
    r"REMOTE HOST IDENTIFICATION HAS CHANGED|HOST KEY VERIFICATION FAILED",
    re.IGNORECASE)
RE_PROMPT_SENHA = re.compile(r"password\s*:\s*$", re.IGNORECASE)
RE_PROMPT_FINGERPRINT = re.compile(
    r"are you sure you want to continue connecting", re.IGNORECASE)

# mapa de teclas especiais -> bytes que o ssh.exe espera receber. Chaves
# resolvidas so dentro de construir(), porque Gdk so existe apos o import
# do gi.repository acima — mas os keyvals sao constantes fixas, entao dá
# pra montar o dicionario aqui mesmo, no nivel do modulo.
_TECLAS = {
    Gdk.KEY_Return: "\r",
    Gdk.KEY_KP_Enter: "\r",
    Gdk.KEY_BackSpace: "\x7f",
    Gdk.KEY_Tab: "\t",
    Gdk.KEY_Escape: "\x1b",
    Gdk.KEY_Up: "\x1b[A",
    Gdk.KEY_Down: "\x1b[B",
    Gdk.KEY_Right: "\x1b[C",
    Gdk.KEY_Left: "\x1b[D",
    Gdk.KEY_Home: "\x1b[H",
    Gdk.KEY_End: "\x1b[F",
    Gdk.KEY_Delete: "\x1b[3~",
    Gdk.KEY_Page_Up: "\x1b[5~",
    Gdk.KEY_Page_Down: "\x1b[6~",
}


def _bin_ssh_windows():
    """OpenSSH vem embutido no Windows 10/11 (recurso opcional, ligado por
    padrão desde 1809) em System32\\OpenSSH\\ssh.exe. shutil.which acha
    tanto esse quanto uma instalação alternativa (Git for Windows, etc)."""
    for nome in ("ssh.exe", "ssh"):
        caminho = shutil.which(nome)
        if caminho:
            return caminho
    padrao = os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"),
        "System32", "OpenSSH", "ssh.exe")
    return padrao if os.path.exists(padrao) else None


def construir(base, capturateclado=None, **utilitarios):
    """Cria e devolve a classe AbaSshWindows. Mesmo padrão de
    ssh.construir() e rdp_windows.construir() — chamado uma vez pelo
    acessos.py, porque a classe herda de AbaBase."""
    add_class = utilitarios.get("add_class", lambda w, *_c: w)

    bases = (base, capturateclado) if capturateclado else (base,)

    class AbaSshWindows(*bases):
        tipo = "ssh"

        def __init__(self, conexao, janela):
            super().__init__(conexao, janela)
            self.pty = None
            self._senha_enviada = False
            self.perguntando_chave = False
            self.aceitar_nova_chave = False
            self._cols, self._rows = 80, 24

            self.bt_auto.set_active(getattr(self.cx, "ssh_auto", False))
            self._ligar_auto("ssh_auto")

            bt_rec = add_class(Gtk.Button(label="Reconectar"), "secundaria")
            bt_rec.connect("clicked", lambda _b: self.reconectar(manual=True))
            self.barra.pack_end(bt_rec, False, False, 0)

            if getattr(self.cx, "tem_vnc", False):
                bt = add_class(Gtk.Button(label="Tela"), "secundaria")
                bt.connect("clicked",
                          lambda _b: self.janela.abrir(self.cx, "vnc"))
                self.barra.pack_end(bt, False, False, 0)

            bt_arq = add_class(Gtk.Button(label="📁  Arquivos"), "secundaria")
            bt_arq.set_tooltip_text(
                "Enviar e baixar arquivos desta máquina (SFTP)")
            bt_arq.connect("clicked",
                          lambda _b: self.janela.abrir_sftp(self.cx))
            self.barra.pack_end(bt_arq, False, False, 0)

            if not TEM_TERMINAL_WINDOWS:
                self.pack_start(Gtk.Label(
                    label="terminal indisponível (%s)" %
                    ERRO_TERMINAL_WINDOWS), True, True, 0)
                self.pack_start(self.exp_log, False, False, 0)
                return

            self.screen = pyte.Screen(self._cols, self._rows)
            self.stream = pyte.Stream(self.screen)

            self.buf = Gtk.TextBuffer()
            self.tv = Gtk.TextView(buffer=self.buf)
            self.tv.set_monospace(True)
            self.tv.set_editable(False)   # entrada vai pro pty, não pro buffer
            self.tv.set_cursor_visible(True)
            # A fonte do terminal acompanha a ESCALA_FONTE do tema, mas
            # segue MONOESPACADA: o pyte desenha em grade de colunas, e
            # uma fonte proporcional aqui desalinharia toda saida de
            # programa de tela cheia (htop, nano) e tabelas.
            try:
                from tema import ESCALA_FONTE as _escala
            except Exception:
                _escala = 1.0
            self.tv.override_font(
                Pango.FontDescription.from_string(
                    "monospace %d" % max(8, int(round(10 * _escala)))))
            self.tv.add_events(Gdk.EventMask.KEY_PRESS_MASK)
            self.tv.connect("key-press-event", self._on_tecla)

            rolagem = Gtk.ScrolledWindow()
            rolagem.set_policy(Gtk.PolicyType.AUTOMATIC,
                               Gtk.PolicyType.AUTOMATIC)
            rolagem.add(self.tv)
            self.pack_start(rolagem, True, True, 0)
            self.tv.connect("size-allocate", self._on_redimensiona)
            self.pack_start(self.exp_log, False, False, 0)
            if hasattr(self, "_iniciar_captura"):
                self._iniciar_captura()

        # ---- linha de comando: mesmo espirito do _argv() do ssh.py
        # Linux, so que sem sshpass — o login automatico entra pelo pty
        def _argv(self):
            ssh = _bin_ssh_windows()
            if not ssh:
                return None
            argv = [ssh]
            if self.cx.ssh_porta and str(self.cx.ssh_porta) != "22":
                argv += ["-p", str(self.cx.ssh_porta)]
            if self.aceitar_nova_chave:
                argv += ["-o", "StrictHostKeyChecking=accept-new"]
            alvo = ("%s@%s" % (self.cx.ssh_usuario, self.cx.host)
                   if self.cx.ssh_usuario else self.cx.host)
            argv.append(alvo)
            return argv

        def conectar(self):
            if not TEM_TERMINAL_WINDOWS:
                self._estado("ERRO", "erro", "dependências ausentes")
                return
            argv = self._argv()
            if not argv:
                self._estado("ERRO", "erro", "ssh.exe não encontrado")
                self.reg(
                    "instale o cliente OpenSSH: Configurações > "
                    "Aplicativos > Recursos opcionais > Cliente OpenSSH")
                return
            self._senha_enviada = False
            self._estado("AGUARDE", "neutro", "abrindo %s…" % self.cx.host)
            self.reg("exec: %s" % " ".join(argv))
            try:
                self.pty = conpty.ConPty(
                    argv, cols=self._cols, rows=self._rows)
            except Exception as e:
                self._estado("ERRO", "erro", "falha ao iniciar ssh")
                self.reg("spawn falhou: %s" % e)
                return
            self._estado("ATIVO", "ok", self.cx.host)
            self.reg("ssh iniciado (pid %s)" % self.pty.pid)
            self.sucesso()
            GLib.timeout_add(30, self._bombear)

        # ---- bombeamento do pty: le o que saiu, alimenta o pyte, redesenha
        def _bombear(self):
            if self.fechando or self.pty is None:
                return False
            if not self.pty.isalive():
                self._on_saiu()
                return False
            try:
                dados = self.pty.read(4096)
            except EOFError:
                self._on_saiu()
                return False
            except Exception as e:
                self.reg("leitura do pty falhou: %s" % e)
                return True
            if dados:
                self.stream.feed(dados)
                self._redesenhar()
                self._checar_prompts()
            return True

        def _redesenhar(self):
            self.buf.set_text("\n".join(self.screen.display))
            try:
                it = self.buf.get_iter_at_line_offset(
                    self.screen.cursor.y, self.screen.cursor.x)
                self.buf.place_cursor(it)
            except Exception:
                pass
            self.tv.scroll_mark_onscreen(self.buf.get_insert())

        def _checar_prompts(self):
            """Login automatico e deteccao de chave — mesma logica do
            ssh.py Linux, so que aqui o texto vem do pyte em vez do VTE."""
            linhas = self.screen.display
            ultima = linhas[-1] if linhas else ""
            texto = "\n".join(linhas)

            if (not self._senha_enviada and self.cx.ssh_senha
                    and RE_PROMPT_SENHA.search(ultima)):
                self._senha_enviada = True
                self.pty.write(self.cx.ssh_senha + "\r")
                self.reg("senha enviada automaticamente")
                return

            if RE_PROMPT_FINGERPRINT.search(texto) and self.aceitar_nova_chave:
                self.pty.write("yes\r")
                return

            if RE_CHAVE_MUDOU.search(texto) and not self.perguntando_chave:
                self.perguntando_chave = True
                GLib.idle_add(self._oferecer_chave)

        def _oferecer_chave(self):
            try:
                if not self.janela.confirmar(
                        "A identificação de %s mudou" % self.cx.host,
                        "O ssh recusou a conexão porque a chave do host "
                        "não bate com a registrada.\n\nRemover a entrada "
                        "antiga e tentar de novo?",
                        ok="Remover e reconectar"):
                    self.reg("operador manteve a chave antiga")
                    return False
                if not self._remover_chave():
                    self.janela.avisar(
                        "Não foi possível remover",
                        "O ssh-keygen não conseguiu limpar a entrada.")
                    return False
                self.aceitar_nova_chave = True
                self.reg("chave removida; reconectando com accept-new")
                self.reconectar()
            finally:
                self.perguntando_chave = False
            return False

        def _remover_chave(self):
            kh = shutil.which("ssh-keygen") or os.path.join(
                os.environ.get("WINDIR", r"C:\Windows"),
                "System32", "OpenSSH", "ssh-keygen.exe")
            if not os.path.exists(kh):
                self.reg("ssh-keygen não encontrado")
                return False
            alvos = [self.cx.host]
            if str(self.cx.ssh_porta) != "22":
                alvos.append("[%s]:%s" % (self.cx.host, self.cx.ssh_porta))
            algum = False
            for alvo in alvos:
                try:
                    ok, saida, err, _st = GLib.spawn_sync(
                        None, [kh, "-R", alvo], None,
                        GLib.SpawnFlags.SEARCH_PATH, None)
                    msg = (err or saida or b"").decode(
                        errors="replace").strip()
                    self.reg("ssh-keygen -R %s -> %s" % (alvo, msg or "ok"))
                    algum = algum or bool(ok)
                except Exception as e:
                    self.reg("ssh-keygen -R %s falhou: %s" % (alvo, e))
            return algum

        def _on_saiu(self):
            codigo = self.pty.exitstatus if self.pty else None
            self.pty = None
            if self.fechando:
                return
            if codigo == 0:
                self._estado("ENCERRADO", "neutro", "sessão finalizada")
                return
            self._estado("ENCERRADO", "erro", "saiu com código %s" % codigo)
            self.reg("ssh terminou, código %s" % codigo)
            self._agendar_auto("código %s" % codigo)

        def reconectar(self, manual=False):
            if manual:
                self._inicio_manual()
            if self.pty:
                try:
                    self.pty.close(force=True)
                except Exception:
                    pass
                self.pty = None
            if hasattr(self, "screen"):
                self.screen.reset()
            self._agendar(300, lambda: (self.conectar(), False)[1])

        def desconectar(self):
            self.fechando = True
            if self.pty:
                try:
                    self.pty.close(force=True)
                except Exception:
                    pass
                self.pty = None

        # ---- teclado: cada tecla vira bytes escritos direto no pty — o
        # MESMO mecanismo usado acima para a senha do login automatico
        def _on_tecla(self, _w, evento):
            if self.pty is None:
                return False
            estado = evento.state
            ctrl = bool(estado & Gdk.ModifierType.CONTROL_MASK)
            chave = evento.keyval

            if chave in _TECLAS:
                self.pty.write(_TECLAS[chave])
                return True
            if ctrl and Gdk.KEY_a <= chave <= Gdk.KEY_z:
                self.pty.write(chr(chave - Gdk.KEY_a + 1))  # Ctrl+A..Z
                return True
            if ctrl and chave == Gdk.KEY_v:
                self._colar()
                return True

            unicode_val = Gdk.keyval_to_unicode(chave)
            if unicode_val:
                self.pty.write(chr(unicode_val))
                return True
            return False

        def _colar(self):
            clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            texto = clip.wait_for_text()
            if texto and self.pty:
                self.pty.write(texto)

        def _on_redimensiona(self, widget, alocacao):
            if not self.pty:
                return
            layout = widget.create_pango_layout("M")
            larg_px, alt_px = layout.get_pixel_size()
            if larg_px <= 0 or alt_px <= 0:
                return
            cols = max(10, alocacao.width // larg_px)
            rows = max(4, alocacao.height // alt_px)
            if (cols, rows) != (self._cols, self._rows):
                self._cols, self._rows = cols, rows
                self.screen.resize(rows, cols)
                try:
                    self.pty.setwinsize(rows, cols)
                except Exception:
                    pass

    return AbaSshWindows
