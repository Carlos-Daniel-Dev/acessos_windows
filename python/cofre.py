#!/usr/bin/env python3
"""Cofre de senhas do Acessos.

Cifra APENAS os campos de senha do conexoes.ini. O resto do arquivo
continua legivel e editavel a mao — host, usuario, portas, grupos. So o
que e sigiloso fica ilegivel:

    [CAIXA101]
    host        = 10.1.1.101
    ssh_usuario = zanthus
    senha       = enc:v1:gAAAAAB...
    ssh_senha   = enc:v1:gAAAAAB...

POR QUE CIFRA REVERSIVEL, E NAO HASH
------------------------------------
Estas senhas sao entregues ao servidor VNC e ao SSH, entao precisam voltar
ao texto claro. Hash nao serve. O que se protege aqui e o ARQUIVO EM
REPOUSO: copia, backup, e principalmente a sincronizacao em nuvem — no caso
deste projeto o .ini fica dentro de uma pasta do Drive, ou seja, hoje sobe
em claro. Cifrado, o que vai para a nuvem e inutil sem a senha mestra.

O que NAO se protege: quem ja executa codigo na maquina com o app aberto. A
chave esta na memoria do processo, necessariamente.

COMO O COFRE SABE QUE A SENHA MESTRA ESTA CERTA
-----------------------------------------------
Nao e "ver se o resultado ficou legivel" — isso e frouxo, texto decifrado
com chave errada pode sair parecendo texto. Duas garantias reais:

1. AES-GCM e cifra AUTENTICADA. Cada valor carrega uma etiqueta de
   autenticacao; com a chave errada a decifragem LEVANTA EXCECAO, nao
   devolve lixo silenciosamente. O mesmo vale se alguem adulterar um byte
   do arquivo.

2. Um VERIFICADOR: um texto conhecido, cifrado com a chave, guardado no
   proprio arquivo. Ao abrir o cofre tentamos decifra-lo. Da para dizer
   "senha mestra incorreta" na hora, em vez de o operador descobrir so
   quando a primeira conexao falhar.
"""

import base64
import os
import secrets

MARCA = "enc:v1:"
SECAO_COFRE = "cofre"
_VERIFICADOR = b"acessos-cofre-ok"

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    TEM_CRIPTO, ERRO_CRIPTO = True, ""
except Exception as e:                                # pragma: no cover
    AESGCM = None
    TEM_CRIPTO, ERRO_CRIPTO = False, str(e)

try:
    from argon2.low_level import hash_secret_raw, Type as ArgonType
    TEM_ARGON = True
except Exception:                                     # pragma: no cover
    TEM_ARGON = False

# Argon2id e preferivel (resiste a ataque com GPU/ASIC muito melhor que
# PBKDF2), mas nem todo empacotamento tera argon2-cffi. O KDF usado fica
# GRAVADO no arquivo, entao um cofre criado com Argon2 continua abrindo
# depois, e um criado com PBKDF2 tambem — nao ha ambiguidade.
KDF_PADRAO = "argon2id" if TEM_ARGON else "pbkdf2"

ARGON_TEMPO = 3
ARGON_MEMORIA = 64 * 1024        # 64 MB
ARGON_PARALELO = 4
PBKDF2_ITER = 600_000            # recomendacao OWASP para SHA-256


class ErroCofre(Exception):
    pass


class SenhaIncorreta(ErroCofre):
    pass


def _b64(b):
    return base64.b64encode(b).decode("ascii")


def _db64(s):
    return base64.b64decode(s.encode("ascii"))


def _derivar(senha_mestra, salt, kdf):
    """Senha mestra -> chave de 32 bytes."""
    dados = senha_mestra.encode("utf-8")
    if kdf == "argon2id":
        if not TEM_ARGON:
            raise ErroCofre(
                "este cofre foi criado com Argon2id, mas argon2-cffi não "
                "está instalado nesta máquina")
        return hash_secret_raw(
            secret=dados, salt=salt, time_cost=ARGON_TEMPO,
            memory_cost=ARGON_MEMORIA, parallelism=ARGON_PARALELO,
            hash_len=32, type=ArgonType.ID)
    if kdf == "pbkdf2":
        return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                          iterations=PBKDF2_ITER).derive(dados)
    raise ErroCofre("KDF desconhecido no arquivo: %r" % kdf)


class Cofre:
    """Guarda a chave da sessao e cifra/decifra valores.

    Uso tipico:
        c = Cofre()
        c.carregar_parametros(dict_da_secao_cofre)   # ou criar()
        c.abrir("senha mestra")
        c.decifrar(valor) / c.cifrar(valor)
    """

    def __init__(self):
        self.salt = None
        self.kdf = KDF_PADRAO
        self.verificador = None
        self._chave = None
        self.existe = False          # ha secao [cofre] no arquivo?

    # ------------------------------------------------------- parametros
    def carregar_parametros(self, secao):
        """secao: mapeamento com salt/kdf/verificador (ou vazio)."""
        if not secao:
            self.existe = False
            return False
        try:
            self.salt = _db64(secao["salt"])
            self.kdf = secao.get("kdf", "pbkdf2")
            self.verificador = _db64(secao["verificador"])
        except Exception as e:
            raise ErroCofre("seção [%s] inválida: %s" % (SECAO_COFRE, e))
        self.existe = True
        return True

    def parametros(self):
        """Devolve o que gravar na secao [cofre]."""
        return {"versao": "1", "kdf": self.kdf,
                "salt": _b64(self.salt),
                "verificador": _b64(self.verificador)}

    # ------------------------------------------------------ abrir/criar
    def criar(self, senha_mestra):
        """Inicializa um cofre novo com esta senha mestra."""
        self._exigir_cripto()
        if not senha_mestra:
            raise ErroCofre("senha mestra vazia")
        self.salt = secrets.token_bytes(16)
        self.kdf = KDF_PADRAO
        self._chave = _derivar(senha_mestra, self.salt, self.kdf)
        # verificador: texto conhecido cifrado com a chave
        self.verificador = self._selar(_VERIFICADOR)
        self.existe = True

    def abrir(self, senha_mestra):
        """Confere a senha mestra. Levanta SenhaIncorreta se nao bater."""
        self._exigir_cripto()
        if self.salt is None:
            raise ErroCofre("cofre não inicializado")
        chave = _derivar(senha_mestra, self.salt, self.kdf)
        try:
            claro = AESGCM(chave).decrypt(self.verificador[:12],
                                          self.verificador[12:], None)
        except Exception:
            # AES-GCM autenticado: chave errada NAO devolve lixo, falha.
            raise SenhaIncorreta("senha mestra incorreta")
        if claro != _VERIFICADOR:
            raise SenhaIncorreta("senha mestra incorreta")
        self._chave = chave

    def trancado(self):
        return self._chave is None

    def trancar(self):
        self._chave = None

    # --------------------------------------------------- cifrar/decifrar
    def _exigir_cripto(self):
        if not TEM_CRIPTO:
            raise ErroCofre("biblioteca cryptography ausente: %s"
                            % ERRO_CRIPTO)

    def _selar(self, dados):
        # nonce ALEATORIO por valor. Reaproveitar nonce no GCM com a mesma
        # chave quebra a cifra — por isso nunca e derivado nem sequencial.
        nonce = secrets.token_bytes(12)
        return nonce + AESGCM(self._chave).encrypt(nonce, dados, None)

    def cifrar(self, texto):
        """Texto claro -> 'enc:v1:...'. Vazio continua vazio."""
        if texto is None or texto == "":
            return texto
        if esta_cifrado(texto):
            return texto                     # ja cifrado, nao cifra 2x
        if self.trancado():
            raise ErroCofre("cofre trancado")
        return MARCA + _b64(self._selar(texto.encode("utf-8")))

    def decifrar(self, valor):
        """'enc:v1:...' -> texto claro. Texto claro passa direto.

        Deixar o texto claro passar e proposital: permite conviver com um
        arquivo em migracao, metade convertido, sem quebrar nada."""
        if valor is None or valor == "":
            return valor
        if not esta_cifrado(valor):
            return valor
        if self.trancado():
            raise ErroCofre("cofre trancado")
        bruto = _db64(valor[len(MARCA):])
        try:
            claro = AESGCM(self._chave).decrypt(bruto[:12], bruto[12:], None)
        except Exception as e:
            raise ErroCofre("valor não pôde ser decifrado (arquivo alterado "
                            "ou senha mestra trocada): %s" % e)
        return claro.decode("utf-8")


def esta_cifrado(valor):
    return isinstance(valor, str) and valor.startswith(MARCA)


def senha_do_ambiente():
    """Escape para uso nao interativo (scripts, testes).

    ACESSOS_SENHA_MESTRA=... acessos.py

    Documentado como conveniencia, com a ressalva obvia: a senha fica no
    ambiente do processo e possivelmente no historico do shell.
    """
    return os.environ.get("ACESSOS_SENHA_MESTRA") or None


def proteger_arquivo(caminho):
    """Permissao 600. Vale mesmo com o conteudo cifrado: nao ha razao para
    o arquivo de credenciais ser legivel por outros usuarios."""
    try:
        os.chmod(caminho, 0o600)
        return True
    except OSError:
        return False


# ------------------------------------------------------------- migracao
CAMPOS_SIGILOSOS = ("senha", "ssh_senha", "rdp_senha")


def migrar_para_cifrado(cp, cofre):
    """Cifra, no ConfigParser, todo campo sigiloso ainda em claro.

    Devolve quantos valores foram convertidos. Nao grava — quem chama
    decide quando escrever, para nao mexer no arquivo sem necessidade.
    """
    n = 0
    for secao in cp.sections():
        if secao == SECAO_COFRE:
            continue
        for campo in CAMPOS_SIGILOSOS:
            valor = cp[secao].get(campo)
            if valor and not esta_cifrado(valor):
                cp[secao][campo] = cofre.cifrar(valor)
                n += 1
    return n


def contar_em_claro(cp):
    """Quantos campos sigilosos ainda estao em texto claro."""
    n = 0
    for secao in cp.sections():
        if secao == SECAO_COFRE:
            continue
        for campo in CAMPOS_SIGILOSOS:
            valor = cp[secao].get(campo)
            if valor and not esta_cifrado(valor):
                n += 1
    return n


# ============================================================== interface
# Os dialogos moram aqui, e nao no acessos.py, para o cofre ser um bloco
# unico: quem integra chama destrancar() e pronto.

# O GTK e importado de forma TOLERANTE: a parte criptografica deste modulo
# nao depende de interface, e assim ela continua utilizavel em teste,
# script ou uso nao interativo, numa maquina sem GTK.
try:
    import gi  # noqa: E402
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk  # noqa: E402
    TEM_GTK = True
except Exception:                                     # pragma: no cover
    Gtk, TEM_GTK = None, False


# ESTILO: resolvido em TEMPO DE CHAMADA, nao no import.
#
# O acessos.py importa este modulo no topo, muito antes de definir
# add_class/botao_dialogo/rotulo. Um "from acessos import ..." aqui em cima
# pegaria o modulo pela metade e falharia — e a degradacao seria SILENCIOSA:
# os dialogos apareceriam sem o tema do app e ninguem entenderia por que.
# Resolvendo na primeira chamada, o acessos ja esta carregado por inteiro.
_ESTILO = {}


def _est():
    """Devolve os helpers de estilo do app, ou equivalentes neutros."""
    if _ESTILO:
        return _ESTILO
    try:
        # O app roda como script (./acessos.py), entao ele vive em
        # sys.modules["__main__"], NAO em sys.modules["acessos"]. Um
        # "import acessos" aqui carregaria uma SEGUNDA copia do modulo —
        # outro estado, outros globais — em vez de achar a que esta rodando.
        # Por isso procuramos primeiro no __main__.
        import sys as _sys
        acessos = _sys.modules.get("__main__")
        if not hasattr(acessos, "botao_dialogo"):
            acessos = _sys.modules.get("acessos")
        if acessos is None or not hasattr(acessos, "botao_dialogo"):
            raise ImportError("acessos ainda não carregado")
        _ESTILO.update(
            add_class=acessos.add_class,
            botao=acessos.botao_dialogo,
            area=acessos.marcar_area_acao,
            rotulo=acessos.rotulo,
            tem=True)
    except Exception:
        def add_class(w, *nomes):
            for n in nomes:
                w.get_style_context().add_class(n)
            return w

        def botao(dlg, texto, resposta, *classes):
            bt = dlg.add_button(texto, resposta)
            add_class(bt, *classes)
            bt.set_can_focus(False)
            return bt

        def rot(texto, *classes, **kw):
            lb = Gtk.Label(label=texto, xalign=kw.pop("xalign", 0.0))
            return add_class(lb, *classes)

        _ESTILO.update(add_class=add_class, botao=botao,
                       area=lambda _d: None, rotulo=rot, tem=False)
    return _ESTILO


def add_class(w, *nomes):
    return _est()["add_class"](w, *nomes)


def botao_dialogo(dlg, texto, resposta, *classes):
    return _est()["botao"](dlg, texto, resposta, *classes)


def marcar_area_acao(dlg):
    return _est()["area"](dlg)


def _rotulo(texto, *classes, **kw):
    return _est()["rotulo"](texto, *classes, **kw)


def _liberar_grab():
    """Desfaz gtk_grab_add() pendente — ver liberar_grab_gtk no acessos.py.

    Sem isto, um dialogo aberto enquanto ha sessao RDP ativa aparece mas nao
    aceita clique, porque o grab do GTK entrega todos os eventos a outro
    widget."""
    try:
        for _ in range(8):
            w = Gtk.grab_get_current()
            if w is None:
                break
            Gtk.grab_remove(w)
    except Exception:
        pass


def _dialogo(titulo, pai):
    """Casca no padrao das outras telas do app."""
    _liberar_grab()
    dlg = Gtk.Dialog(title=titulo, transient_for=pai, modal=True)
    add_class(dlg, "acessos-dialogo")
    marcar_area_acao(dlg)
    cx = dlg.get_content_area()
    cx.set_border_width(14)
    cx.set_spacing(6)
    return dlg, cx


def _campo_senha(caixa, texto_rotulo, dlg=None, resposta=None):
    caixa.pack_start(_rotulo(texto_rotulo, "rotulo"), False, False, 0)
    ent = Gtk.Entry()
    ent.set_visibility(False)
    ent.set_input_purpose(Gtk.InputPurpose.PASSWORD)
    if dlg is not None and resposta is not None:
        # mesmo padrao do pedir_senha(): Enter ligado direto a resposta, e
        # nao via activates_default
        ent.connect("activate", lambda _e: dlg.response(resposta))
    caixa.pack_start(ent, False, False, 0)
    return ent


def _nota(caixa, texto, *classes):
    lb = _rotulo(texto, *(classes or ("secundario",)), ellipsize=None)
    lb.set_line_wrap(True)
    lb.set_max_width_chars(52)
    caixa.pack_start(lb, False, False, 0)
    return lb


def _erro(pai, texto):
    d = Gtk.MessageDialog(transient_for=pai, modal=True,
                          message_type=Gtk.MessageType.ERROR,
                          buttons=Gtk.ButtonsType.OK, text=texto)
    add_class(d, "acessos-dialogo")
    d.run()
    d.destroy()


def _aviso(pai, texto):
    d = Gtk.MessageDialog(transient_for=pai, modal=True,
                          message_type=Gtk.MessageType.INFO,
                          buttons=Gtk.ButtonsType.OK, text=texto)
    add_class(d, "acessos-dialogo")
    d.run()
    d.destroy()


def dialogo_criar(pai=None):
    """Primeira configuracao. Devolve a senha escolhida, ou None."""
    dlg, cx = _dialogo("Proteger senhas", pai)
    botao_dialogo(dlg, "Agora não", Gtk.ResponseType.CANCEL, "perigo")
    botao_dialogo(dlg, "Proteger", Gtk.ResponseType.OK, "acao")

    cx.pack_start(_rotulo("SENHA MESTRA", "rotulo"), False, False, 0)
    _nota(cx, "As senhas gravadas no arquivo de conexões passam a ficar "
              "cifradas. Host, usuário e o resto continuam legíveis e "
              "editáveis à mão.")
    e1 = _campo_senha(cx, "SENHA", dlg, Gtk.ResponseType.OK)
    e2 = _campo_senha(cx, "REPITA", dlg, Gtk.ResponseType.OK)
    _nota(cx, "Não há recuperação: perdida esta senha, as senhas guardadas "
              "ficam inacessíveis e terão de ser digitadas de novo.",
          "secundario", "chip-erro")
    cx.show_all()

    while True:
        if dlg.run() != Gtk.ResponseType.OK:
            dlg.destroy()
            return None
        a, b = e1.get_text(), e2.get_text()
        if not a:
            _erro(dlg, "A senha mestra não pode ser vazia.")
            continue
        if a != b:
            _erro(dlg, "As duas senhas não conferem.")
            e2.set_text("")
            e2.grab_focus()
            continue
        dlg.destroy()
        return a


def dialogo_trocar(cofre_atual, pai=None):
    """Troca a senha mestra. Devolve a nova senha, ou None.

    Exige a atual: sem isso, quem chegasse na maquina com o app aberto
    trocaria a senha sem conhecer a anterior."""
    dlg, cx = _dialogo("Trocar senha mestra", pai)
    botao_dialogo(dlg, "Cancelar", Gtk.ResponseType.CANCEL, "perigo")
    botao_dialogo(dlg, "Trocar", Gtk.ResponseType.OK, "acao")

    cx.pack_start(_rotulo("TROCAR SENHA MESTRA", "rotulo"), False, False, 0)
    _nota(cx, "Todas as senhas guardadas serão recifradas com a senha nova. "
              "Uma cópia do arquivo anterior fica em conexoes.ini.bak.")
    e0 = _campo_senha(cx, "SENHA ATUAL", dlg, Gtk.ResponseType.OK)
    e1 = _campo_senha(cx, "NOVA SENHA", dlg, Gtk.ResponseType.OK)
    e2 = _campo_senha(cx, "REPITA A NOVA", dlg, Gtk.ResponseType.OK)
    cx.show_all()
    e0.grab_focus()

    while True:
        if dlg.run() != Gtk.ResponseType.OK:
            dlg.destroy()
            return None
        try:
            cofre_atual.abrir(e0.get_text())
        except Exception:
            _erro(dlg, "Senha mestra atual incorreta.")
            e0.set_text("")
            e0.grab_focus()
            continue
        a, b = e1.get_text(), e2.get_text()
        if not a:
            _erro(dlg, "A nova senha não pode ser vazia.")
            continue
        if a != b:
            _erro(dlg, "As duas senhas novas não conferem.")
            e2.set_text("")
            e2.grab_focus()
            continue
        dlg.destroy()
        return a


def dialogo_abrir(cofre, pai=None):
    """Pede a senha mestra. Devolve 'ok', 'trocar' ou None (cancelou).

    O botao de trocar fica AQUI, na primeira janela: se o operador percebe
    na hora que quer mudar, nao precisa entrar no app, achar um menu e
    voltar."""
    dlg, cx = _dialogo("Acessos", pai)
    botao_dialogo(dlg, "Sair", Gtk.ResponseType.CANCEL, "perigo")
    botao_dialogo(dlg, "Trocar senha…", Gtk.ResponseType.APPLY, "secundaria")
    botao_dialogo(dlg, "Abrir", Gtk.ResponseType.OK, "acao")

    cx.pack_start(_rotulo("SENHA MESTRA", "rotulo"), False, False, 0)
    _nota(cx, "Necessária para usar as senhas guardadas.")
    ent = _campo_senha(cx, "SENHA", dlg, Gtk.ResponseType.OK)
    cx.show_all()
    ent.grab_focus()

    while True:
        resp = dlg.run()
        if resp == Gtk.ResponseType.APPLY:
            dlg.destroy()
            return "trocar"
        if resp != Gtk.ResponseType.OK:
            dlg.destroy()
            return None
        try:
            cofre.abrir(ent.get_text())
        except SenhaIncorreta:
            _erro(dlg, "Senha mestra incorreta.")
            ent.set_text("")
            ent.grab_focus()
            continue
        except ErroCofre as e:
            _erro(dlg, str(e))
            dlg.destroy()
            return None
        dlg.destroy()
        return "ok"


def _recifrar_arquivo(caminho, cofre_velho, senha_nova):
    """Decifra tudo com a chave antiga e regrava com a nova.

    Ponto delicado: se falhar no meio, o arquivo fica metade numa chave e
    metade noutra — irrecuperavel. Por isso decifra TUDO em memoria antes de
    escrever qualquer coisa, escreve num temporario e so entao substitui.
    """
    import configparser
    import shutil

    cp = configparser.ConfigParser(interpolation=None)
    cp.read(caminho, encoding="utf-8")

    # 1. tudo em claro na memoria (se algo falhar, nada foi escrito)
    claros = {}
    for secao in cp.sections():
        if secao == SECAO_COFRE:
            continue
        for campo in CAMPOS_SIGILOSOS:
            valor = cp[secao].get(campo)
            if valor:
                claros[(secao, campo)] = cofre_velho.decifrar(valor)

    # 2. cofre novo
    novo = Cofre()
    novo.criar(senha_nova)
    for (secao, campo), claro in claros.items():
        cp[secao][campo] = novo.cifrar(claro)
    cp[SECAO_COFRE] = novo.parametros()

    # 3. escrita atomica: temporario no MESMO diretorio (para o rename nao
    #    cruzar sistema de arquivos) e backup do original antes de trocar
    pasta = os.path.dirname(os.path.abspath(caminho))
    tmp = os.path.join(pasta, ".conexoes.ini.novo")
    with open(tmp, "w", encoding="utf-8") as f:
        cp.write(f)
    proteger_arquivo(tmp)
    try:
        shutil.copy2(caminho, caminho + ".bak")
        proteger_arquivo(caminho + ".bak")
    except OSError:
        pass
    os.replace(tmp, caminho)
    proteger_arquivo(caminho)
    return novo, len(claros)


def destrancar(caminho, pai=None):
    """Ponto de entrada unico, chamado no arranque.

    Devolve (cofre, seguir):
      cofre  — instancia aberta, ou None se o arquivo nao usa cofre
      seguir — False significa que o operador desistiu; encerrar o app

    Cobre os tres casos: arquivo ainda sem cofre (oferece criar), cofre
    existente (pede a senha, com opcao de trocar ali mesmo) e ausencia da
    biblioteca (segue sem cofre, como antes).
    """
    import configparser

    if not TEM_CRIPTO:
        return None, True                 # sem cryptography: modo antigo

    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read(caminho, encoding="utf-8")
    except Exception:
        return None, True

    tem_secao = cp.has_section(SECAO_COFRE)
    c = Cofre()

    # ---- ja existe cofre
    if tem_secao:
        c.carregar_parametros(cp[SECAO_COFRE])
        senha_amb = senha_do_ambiente()
        if senha_amb:
            try:
                c.abrir(senha_amb)
                return c, True
            except Exception:
                pass                      # cai para o dialogo
        while True:
            r = dialogo_abrir(c, pai)
            if r is None:
                return None, False
            if r == "ok":
                return c, True
            # trocar senha, direto da primeira janela
            nova = dialogo_trocar(c, pai)
            if nova is None:
                continue                  # voltou; pede a senha de novo
            try:
                c2, n = _recifrar_arquivo(caminho, c, nova)
            except Exception as e:
                _erro(pai, "Falha ao trocar a senha: %s\n\nNada foi "
                           "alterado." % e)
                c = Cofre()
                c.carregar_parametros(cp[SECAO_COFRE])
                continue
            _aviso(pai, "Senha mestra trocada. %d senha(s) recifrada(s).\n"
                        "Cópia do arquivo anterior: conexoes.ini.bak" % n)
            return c2, True

    # ---- ainda nao ha cofre: oferecer
    em_claro = contar_em_claro(cp)
    if em_claro == 0:
        return None, True                 # nada a proteger; nao incomoda
    senha = dialogo_criar(pai)
    if senha is None:
        proteger_arquivo(caminho)         # ao menos o chmod 600
        return None, True                 # segue em claro, escolha do usuario
    c.criar(senha)
    n = migrar_para_cifrado(cp, c)
    cp[SECAO_COFRE] = c.parametros()
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            cp.write(f)
        proteger_arquivo(caminho)
    except Exception as e:
        _erro(pai, "Falha ao gravar: %s" % e)
        return None, True
    _aviso(pai, "%d senha(s) protegida(s)." % n)
    return c, True
