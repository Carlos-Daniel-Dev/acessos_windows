#!/usr/bin/env python3
"""conpty — pseudo-terminal do Windows (ConPTY) em ctypes puro.

SEM pywinpty, DE PROPOSITO
---------------------------
Mesmo motivo do win_embed.py: os wheels do pywinpty sao compilados contra
o CPython oficial (ABI MSVC), e o Python que traz GTK3/PyGObject no
Windows e o do MSYS2 (ABI MinGW) — o pip tenta compilar do fonte e falha.
O ConPTY e API de kernel32, entao ctypes da conta sem dependencia externa.

O QUE E, E POR QUE O SSH PRECISA DISSO
----------------------------------------
O RDP (rdp_windows.py) so precisa que a janela do FreeRDP APAREÇA dentro
da aba: quem digita ali e o operador, direto na janela remota. O SSH e
diferente — o Acessos PRECISA falar com o processo: mandar a senha no
login automatico e ler a tela para detectar o aviso de troca de host key.
Reparentar a janela de um console alheio com SetParent nao permite isso;
nao existe "feed_child" para janela de outro processo.

Com ConPTY (Windows 10 1809+) o Acessos cria o pseudo-terminal, spawna o
ssh.exe DENTRO dele, e fica dono dos dois lados do cano: le tudo que sai
(para desenhar a tela) e escreve tudo que entra (teclado e senha). E o
equivalente Windows do Vte.Pty do Linux.

Note que no Linux o login automatico TAMBEM depende de um pty: o sshpass
usado no ssh.py cria seu proprio pseudo-terminal para "ver" o prompt
"password:" e responder. Mesmo problema, resolvido de outro jeito — nao
ha porte confiavel de sshpass para Windows, entao o Acessos assume o
papel direto.

USO
    pty = ConPty(["ssh.exe", "user@host"], cols=80, rows=24)
    dados = pty.read()          # nao bloqueia: devolve "" se nada saiu
    pty.write("comando\\r")
    pty.setwinsize(rows, cols)
    pty.isalive()
    pty.close()
"""

import ctypes
import os
import sys
import threading
from ctypes import wintypes

DISPONIVEL = sys.platform == "win32"
ERRO = "" if DISPONIVEL else "ConPTY só existe no Windows"

if DISPONIVEL:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    HPCON = wintypes.HANDLE

    class COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [
            ("StartupInfo", STARTUPINFOW),
            ("lpAttributeList", ctypes.c_void_p),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", wintypes.BOOL),
        ]

    # CreatePseudoConsole so existe a partir do Windows 10 1809. Se
    # faltar, o modulo continua importavel e TEM_CONPTY fica False — o
    # ssh_windows.py checa e avisa em vez de estourar.
    TEM_CONPTY = hasattr(kernel32, "CreatePseudoConsole")
    if TEM_CONPTY:
        kernel32.CreatePseudoConsole.argtypes = [
            COORD, wintypes.HANDLE, wintypes.HANDLE, wintypes.DWORD,
            ctypes.POINTER(HPCON)]
        kernel32.CreatePseudoConsole.restype = wintypes.LONG
        kernel32.ResizePseudoConsole.argtypes = [HPCON, COORD]
        kernel32.ResizePseudoConsole.restype = wintypes.LONG
        kernel32.ClosePseudoConsole.argtypes = [HPCON]
        kernel32.ClosePseudoConsole.restype = None
        ERRO_CONPTY = ""
    else:                                          # pragma: no cover
        ERRO_CONPTY = ("este Windows não tem ConPTY (precisa do "
                       "Windows 10 1809 ou mais novo)")

    kernel32.CreatePipe.argtypes = [
        ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(SECURITY_ATTRIBUTES), wintypes.DWORD]
    kernel32.CreatePipe.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t)]
    kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    kernel32.UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
    kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
    kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    kernel32.DeleteProcThreadAttributeList.restype = None
    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOEXW), ctypes.POINTER(PROCESS_INFORMATION)]
    kernel32.CreateProcessW.restype = wintypes.BOOL
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
else:                                              # pragma: no cover
    kernel32 = None
    TEM_CONPTY, ERRO_CONPTY = False, ERRO

EXTENDED_STARTUPINFO_PRESENT = 0x00080000
PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
STILL_ACTIVE = 259


class ConPty:
    """Um processo rodando dentro de um pseudo-console.

    A leitura e feita numa THREAD, porque ReadFile num pipe bloqueia e
    travaria o laço do GTK. A thread so acumula bytes num buffer; o
    read() do lado GTK e nao-bloqueante e apenas drena esse buffer — o
    mesmo desenho que o vncwidget.py ja usa (thread de rede + idle_add).
    """

    def __init__(self, argv, cols=80, rows=24, cwd=None, env=None):
        if not DISPONIVEL:
            raise RuntimeError(ERRO)
        if not TEM_CONPTY:
            raise RuntimeError(ERRO_CONPTY)

        self._hpcon = HPCON()
        self._proc = None
        self._buffer = bytearray()
        self._trava = threading.Lock()
        self._fim = threading.Event()
        self.exitstatus = None
        self.pid = None

        sa = SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
        sa.bInheritHandle = True
        sa.lpSecurityDescriptor = None

        # Dois pipes: um para o que ENTRA no console (nos escrevemos), um
        # para o que SAI dele (nos lemos). O ConPTY fica com as pontas
        # opostas das que guardamos.
        entrada_leitura = wintypes.HANDLE()
        entrada_escrita = wintypes.HANDLE()
        saida_leitura = wintypes.HANDLE()
        saida_escrita = wintypes.HANDLE()
        if not kernel32.CreatePipe(ctypes.byref(entrada_leitura),
                                   ctypes.byref(entrada_escrita),
                                   ctypes.byref(sa), 0):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel32.CreatePipe(ctypes.byref(saida_leitura),
                                   ctypes.byref(saida_escrita),
                                   ctypes.byref(sa), 0):
            raise ctypes.WinError(ctypes.get_last_error())

        self._escrita = entrada_escrita
        self._leitura = saida_leitura

        tamanho = COORD(cols, rows)
        hr = kernel32.CreatePseudoConsole(
            tamanho, entrada_leitura, saida_escrita, 0,
            ctypes.byref(self._hpcon))
        # as pontas que agora pertencem ao ConPTY podem ser fechadas do
        # nosso lado: mante-las abertas impede o EOF quando o filho sai
        kernel32.CloseHandle(entrada_leitura)
        kernel32.CloseHandle(saida_escrita)
        if hr != 0:
            raise OSError("CreatePseudoConsole falhou (HRESULT 0x%08X)"
                          % (hr & 0xFFFFFFFF))

        self._spawn(argv, cwd, env)

        self._thread = threading.Thread(target=self._ler_sempre, daemon=True)
        self._thread.start()

    # ---- criacao do processo dentro do pseudo-console
    def _spawn(self, argv, cwd, env):
        tamanho_lista = ctypes.c_size_t(0)
        # primeira chamada so descobre o tamanho necessario; ela FALHA de
        # proposito (ERROR_INSUFFICIENT_BUFFER) e isso e esperado
        kernel32.InitializeProcThreadAttributeList(
            None, 1, 0, ctypes.byref(tamanho_lista))
        buffer_attrs = (ctypes.c_byte * tamanho_lista.value)()
        if not kernel32.InitializeProcThreadAttributeList(
                buffer_attrs, 1, 0, ctypes.byref(tamanho_lista)):
            raise ctypes.WinError(ctypes.get_last_error())

        if not kernel32.UpdateProcThreadAttribute(
                buffer_attrs, 0, PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
                self._hpcon, ctypes.sizeof(HPCON), None, None):
            raise ctypes.WinError(ctypes.get_last_error())

        si = STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        si.lpAttributeList = ctypes.cast(buffer_attrs, ctypes.c_void_p)

        pi = PROCESS_INFORMATION()

        # CreateProcessW modifica a string da linha de comando, entao ela
        # precisa ser um buffer mutavel — passar uma str constante aqui e
        # causa classica de corrupcao de memoria.
        linha = ctypes.create_unicode_buffer(_montar_linha(argv))

        bloco_env = None
        if env is not None:
            bloco_env = _montar_env(env)

        ok = kernel32.CreateProcessW(
            None, linha, None, None, False,
            EXTENDED_STARTUPINFO_PRESENT | 0x00000400,  # CREATE_UNICODE_ENVIRONMENT
            bloco_env, cwd, ctypes.byref(si), ctypes.byref(pi))

        kernel32.DeleteProcThreadAttributeList(buffer_attrs)

        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())

        self._proc = pi.hProcess
        kernel32.CloseHandle(pi.hThread)
        self.pid = pi.dwProcessId

    # ---- leitura em thread, entrega nao-bloqueante
    def _ler_sempre(self):
        buf = (ctypes.c_char * 4096)()
        lidos = wintypes.DWORD(0)
        while not self._fim.is_set():
            ok = kernel32.ReadFile(self._leitura, buf, 4096,
                                   ctypes.byref(lidos), None)
            if not ok or lidos.value == 0:
                break              # pipe fechado: o filho saiu
            with self._trava:
                self._buffer.extend(buf[:lidos.value])
        self._fim.set()

    def read(self, _max=None):
        """Nao bloqueia. Devolve str (decodificada como UTF-8, tolerante)
        ou "" se nada novo saiu. A assinatura aceita um limite para ficar
        compativel com quem chamava pty.read(4096)."""
        with self._trava:
            if not self._buffer:
                return ""
            dados = bytes(self._buffer)
            self._buffer.clear()
        return dados.decode("utf-8", errors="replace")

    def write(self, texto):
        if isinstance(texto, str):
            texto = texto.encode("utf-8")
        escritos = wintypes.DWORD(0)
        kernel32.WriteFile(self._escrita, texto, len(texto),
                           ctypes.byref(escritos), None)
        return escritos.value

    def setwinsize(self, rows, cols):
        if self._hpcon:
            kernel32.ResizePseudoConsole(self._hpcon, COORD(cols, rows))

    def isalive(self):
        if self._proc is None:
            return False
        codigo = wintypes.DWORD(0)
        if not kernel32.GetExitCodeProcess(self._proc, ctypes.byref(codigo)):
            return False
        if codigo.value == STILL_ACTIVE:
            return True
        self.exitstatus = codigo.value
        return False

    def close(self, force=True):
        self._fim.set()
        if self._proc is not None and force:
            try:
                if self.isalive():
                    kernel32.TerminateProcess(self._proc, 1)
            except Exception:
                pass
        # ClosePseudoConsole antes dos handles: ele libera as pontas que
        # o console detem, o que desbloqueia o ReadFile da thread
        if self._hpcon:
            try:
                kernel32.ClosePseudoConsole(self._hpcon)
            except Exception:
                pass
            self._hpcon = HPCON()
        for h in (self._escrita, self._leitura):
            try:
                if h:
                    kernel32.CloseHandle(h)
            except Exception:
                pass
        self._escrita = self._leitura = None
        if self._proc is not None:
            try:
                kernel32.CloseHandle(self._proc)
            except Exception:
                pass
            self._proc = None


def _montar_linha(argv):
    """Junta argv numa linha de comando com as regras de citacao do
    Windows (que sao diferentes das do shell: aspas duplas e barras
    invertidas antes de aspas precisam ser dobradas)."""
    partes = []
    for arg in argv:
        if not arg:
            partes.append('""')
            continue
        if not any(c in arg for c in ' \t"'):
            partes.append(arg)
            continue
        saida = ['"']
        barras = 0
        for ch in arg:
            if ch == "\\":
                barras += 1
                continue
            if ch == '"':
                saida.append("\\" * (barras * 2 + 1))
                saida.append('"')
            else:
                saida.append("\\" * barras)
                saida.append(ch)
            barras = 0
        saida.append("\\" * (barras * 2))
        saida.append('"')
        partes.append("".join(saida))
    return " ".join(partes)


def _montar_env(env):
    """Bloco de ambiente do Windows: pares NOME=VALOR separados por \\0 e
    terminados por \\0\\0, em UTF-16."""
    itens = "".join("%s=%s\0" % (k, v) for k, v in env.items()) + "\0"
    return ctypes.create_unicode_buffer(itens)
