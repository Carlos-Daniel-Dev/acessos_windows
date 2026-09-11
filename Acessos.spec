# -*- mode: python ; coding: utf-8 -*-
#
# Acessos.spec — mantido A MÃO, não gerado automaticamente pelo
# PyInstaller (que sobrescreveria a parte customizada mais abaixo a cada
# build). Chamado por compilar_exe.ps1 como "pyinstaller Acessos.spec",
# com os parâmetros que variam de build pra build (ícone, DLLs do FreeRDP,
# console ou janela...) vindo de VARIÁVEIS DE AMBIENTE — um .spec não
# aceita os mesmos --flags de linha de comando que uma chamada direta ao
# pyinstaller aceitaria.
#
# POR QUE ESTE ARQUIVO EXISTE (o pré-requisito do Item 5 do backlog)
# ---------------------------------------------------------------------
# Todo módulo do PRÓPRIO PROJETO (acessos, tema, cofre...) fica, por
# padrão do PyInstaller, compactado dentro do PYZ-00.pyz — não dá pra
# trocar um .py sozinho ali sem recompilar tudo de novo. A parte de baixo
# deste arquivo tira esses módulos do PYZ e os deixa soltos em _internal\,
# do mesmo jeito que icones/acessos.svg e as DLLs de terceiros já ficam —
# isso é o que abre caminho pra uma futura auto-atualização (via GitHub)
# só sobrescrever o .py que mudou, sem rodar compilar_exe.ps1 de novo.
#
# Ver launcher.py pro outro lado dessa mesma ideia: ele é o único módulo
# que PRECISA continuar compilado dentro do .exe (é o bootstrap), e por
# isso é deliberadamente minúsculo e estável.

import os

# RAIZ: propositalmente NAO calculado a partir de SPECPATH (a global que o
# PyInstaller injeta com o diretorio do .spec) — testado na pratica e o
# valor nao veio como esperado quando invocado de dentro do bash do MSYS2
# (a mesma familia de problema de conversao de caminho que ja apareceu
# noutros pontos deste projeto — ver compilar_exe.ps1, comentario sobre
# "/mingw64/..." virando "C:/mingw64/..."). Mais robusto: compilar_exe.ps1
# passa a raiz explicita por variavel de ambiente, igual aos outros
# parametros dinamicos deste arquivo.
RAIZ = os.environ["ACESSOS_RAIZ"]
PASTA_PYTHON = os.path.join(RAIZ, "python")


def _env_bool(nome, padrao):
    valor = os.environ.get(nome)
    if valor is None or valor == "":
        return padrao
    return valor.strip() not in ("0", "false", "False", "nao", "não")


JANELA = _env_bool("ACESSOS_JANELA", True)

ICONE = os.environ.get("ACESSOS_ICONE") or None
if ICONE and not os.path.isfile(ICONE):
    ICONE = None

VNCSHIM_DLL = os.environ["ACESSOS_VNCSHIM_DLL"]
RDPSHIM_DLL = os.environ["ACESSOS_RDPSHIM_DLL"]
# GdkWin32 (typelib) SAIU: só existia pra win_embed.py achar o HWND de um
# widget pra fazer SetParent — RDP não reparenta janela nenhuma mais
# (ver RDPSHIM-interno.md, não publicado). Nenhum módulo do projeto usa
# GdkWin32 hoje.

binarios = [
    (VNCSHIM_DLL, "."),
    (RDPSHIM_DLL, "."),
]

# Fechamento de dependencias do rdpshim.dll (libfreerdp3/libwinpr3 e a
# pilha de codecs que elas linkam — ffmpeg, x264, x265, aom, opus...):
# uma lista de nomes de arquivo, um por linha, gerada por
# resolver_dlls.sh a partir do PROPRIO librdpshim.dll (nao mais do
# wfreerdp.exe, que saiu do projeto — ver RDPSHIM-interno.md, nao
# publicado). compilar_exe.ps1 escreve o caminho dessa lista em
# ACESSOS_RDPSHIM_DEPS_TXT. Ausente: RDP fica indisponivel (o shim
# carrega mas as DLLs de que ele depende nao estao no bundle) — nao ha
# mais fallback de "FreeRDP instalado a parte", como o wfreerdp.exe
# externo permitia antes.
lista_rdpshim = os.environ.get("ACESSOS_RDPSHIM_DEPS_TXT")
mingw_bin = os.environ.get("ACESSOS_MINGW64_BIN", r"C:\msys64\mingw64\bin")
if lista_rdpshim and os.path.isfile(lista_rdpshim):
    with open(lista_rdpshim, encoding="utf-8") as f:
        for linha in f:
            nome = linha.strip()
            if not nome:
                continue
            caminho = os.path.join(mingw_bin, nome)
            if os.path.isfile(caminho):
                binarios.append((caminho, "."))

# módulos do projeto — precisam bater com python\*.py (menos launcher.py,
# que fica compilado de propósito)
MODULOS_PROJETO = {
    "acessos", "tema", "cofre", "sftp", "vncwidget",
    "rdp_shim", "rdpwidget", "ssh_windows", "conpty", "bandeja_windows",
    "atualizador", "dialogo_ui", "massa", "massa_ui", "importar_rdm",
}

a = Analysis(
    [os.path.join(PASTA_PYTHON, "launcher.py")],
    pathex=[PASTA_PYTHON],
    binaries=binarios,
    # manifesto.json TAMBEM embutido: e dele que atualizador.versao_local()
    # le "qual versao este .exe e" pra comparar contra o GitHub — sem isto
    # a checagem de atualizacao nunca teria uma versao local pra comparar
    datas=[
        (os.path.join(RAIZ, "icones", "acessos.svg"), "."),
        (os.path.join(RAIZ, "manifesto.json"), "."),
    ],
    # redundante com a deteccao estatica normal do PyInstaller (os imports
    # condicionais — "if sys.platform == 'win32': import rdp_shim" — já
    # são achados sozinhos), mas custo zero manter como rede de segurança
    hiddenimports=sorted(MODULOS_PROJETO),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# ---------------------------------------------------------------------
# O CORAÇÃO DA MUDANÇA. a.pure é a lista de módulos Python puros que IRIAM
# pro PYZ compactado — cada item é (nome_do_modulo, caminho_do_arquivo,
# tipo). Tiramos os nossos de lá e os recolocamos em a.datas (arquivo
# copiado como está, sem compactar em lugar nenhum) — exatamente o mesmo
# tratamento que icones/acessos.svg já recebe algumas linhas acima.
#
# Isto roda DEPOIS que Analysis() já terminou de descobrir todos os hooks
# nativos (GTK, GdkWin32, FreeRDP, cryptography...) — só rearranja ONDE
# cada módulo Python puro vai parar, não desfaz nada do que já foi
# descoberto.
soltos = [t for t in a.pure if t[0] in MODULOS_PROJETO]
a.pure = [t for t in a.pure if t[0] not in MODULOS_PROJETO]
for nome, caminho, _tipo in soltos:
    a.datas += [(nome + ".py", caminho, "DATA")]

faltando = MODULOS_PROJETO - {nome for nome, _c, _t in soltos}
if faltando:
    # nao devia acontecer — um modulo do projeto que a Analysis nao achou
    # nem em a.pure e sinal de import quebrado ou nome errado neste .spec
    raise SystemExit(
        "Acessos.spec: modulo(s) do projeto nao encontrado(s) pela "
        "Analysis: %s" % ", ".join(sorted(faltando)))

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Acessos",
    console=not JANELA,
    icon=ICONE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="Acessos",
)
