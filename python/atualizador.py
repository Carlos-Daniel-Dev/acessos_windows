#!/usr/bin/env python3
"""atualizador — verifica se há uma versão mais nova do Acessos no GitHub
e, com confirmação do operador, baixa e aplica os arquivos que mudaram —
SEM reinstalar o `.exe` inteiro (decisão de 2026-09-08, ver BACKLOG-exe.md,
Item 5: notificar e pedir confirmação, nunca auto-aplicar sozinho, pra um
push ruim na `main` não derrubar todo mundo instantaneamente).

FONTE DA VERDADE: a última GitHub Release publicada, não o HEAD cru da
`main` — um push no meio do dia, ainda incompleto, não deve virar "a
versão mais nova" pro app. Publicar uma release é o momento explícito de
"isto está pronto pra todo mundo".

REPOSITÓRIO PÚBLICO (decidido em 2026-09-08): sem repositório privado, não
há token/credencial nenhum pra gerenciar — a checagem e o download usam
`raw.githubusercontent.com`/API pública do GitHub, sem autenticação.

COMO O "APLICAR SEM REINSTALAR" FUNCIONA
-------------------------------------------
Só é possível porque os módulos do PRÓPRIO PROJETO ficam soltos dentro do
bundle (ver `launcher.py`/`Acessos.spec`) — não compactados no `PYZ`.
Baixar um `.py` novo do GitHub e sobrescrever o arquivo já instalado é
suficiente pra mudar o comportamento do app; só não tem efeito imediato
na sessão JÁ ABERTA (o Python já importou o módulo antigo pra memória) —
por isso a aplicação sempre pede reinício depois.

O QUE NÃO É COBERTO: o `.dll` compilado do shim VNC (`src/vncshim.c`, a
seção "compilar" do manifesto.json) não pode ser regerado por este
módulo — o app não tem compilador C embutido. Se esse arquivo mudar,
`listar_diferencas()` nem avalia essa seção (só olha "copiar"); uma
mudança ali continua exigindo reinstalar via um `.exe` novo.
"""
import hashlib
import json
import os
import shutil
import sys
import threading
import urllib.request

# Repositório real, confirmado em 2026-09-08 (ver BACKLOG-exe.md, Item 5).
# ATENÇÃO: hoje (2026-09-08) este repositório ainda está PRIVADO no
# GitHub — a checagem sem autenticação daqui só vai funcionar depois que
# ele for tornado público nas configurações do GitHub. Até lá,
# versao_remota() recebe 404 da API/raw.githubusercontent.com e devolve
# None graciosamente (mesmo comportamento de "repositório não configurado"
# — não quebra nada, só não encontra nenhuma atualização).
DONO_REPO = "Carlos-Daniel-Dev"
NOME_REPO = "acessos_windows"

TIMEOUT_SEG = 8
_AGENTE = "Acessos-atualizador (https://github.com/%s/%s)" % (DONO_REPO, NOME_REPO)
_NOME_BACKUP = ".backup_atualizacao"


def _repo_configurado():
    return not DONO_REPO.startswith("PREENCHER")


def _pasta_base():
    """Onde os arquivos soltos do bundle vivem: sys._MEIPASS (compilado,
    é o `_internal\\` de hoje) ou, rodando de fonte, a pasta `python\\`
    deste próprio arquivo — mesma convenção que caminho_icone()/
    _carregar_shim() (acessos.py/vncwidget.py) já usam."""
    aqui = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", aqui)
    return aqui


def _caminho_manifesto_local():
    """manifesto.json DESTE processo: dentro do bundle (mesma pasta dos
    .py soltos) ou, rodando de fonte, um nível acima de python\\ (raiz do
    pacote — é onde gerar_manifesto.ps1 grava)."""
    base = _pasta_base()
    if not getattr(sys, "frozen", False):
        base = os.path.dirname(base)
    return os.path.join(base, "manifesto.json")


def versao_local():
    """A versão que ESTE processo é, lida do manifesto.json embutido.
    None se o arquivo não existir ou não puder ser lido — nunca levanta
    exceção pro chamador.

    "utf-8-sig", não "utf-8": TESTADO NA PRÁTICA — gerar_manifesto.ps1
    grava o arquivo via `Set-Content -Encoding UTF8` do PowerShell 5.1, que
    SEMPRE inclui um BOM. `json.load` com "utf-8" puro rejeita esse BOM
    (`JSONDecodeError: Unexpected UTF-8 BOM`); "utf-8-sig" o descarta se
    presente e funciona igual se não tiver — mais seguro pra qualquer
    arquivo que possa ter passado por uma ferramenta do Windows."""
    try:
        with open(_caminho_manifesto_local(), encoding="utf-8-sig") as f:
            return json.load(f).get("versao")
    except Exception:
        return None


def _sha256(dados):
    return hashlib.sha256(dados).hexdigest()


def _buscar_json(url):
    pedido = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json",
                      "User-Agent": _AGENTE})
    with urllib.request.urlopen(pedido, timeout=TIMEOUT_SEG) as resp:
        # utf-8-sig pelo mesmo motivo de versao_local(): o manifesto.json
        # commitado no repositorio pode ter vindo com BOM (gerado pelo
        # gerar_manifesto.ps1, que sempre inclui um) — decode("utf-8") NAO
        # descarta o BOM sozinho, so decodifica ele como um caractere
        # literal no inicio da string, e o json.loads() quebra nele.
        return json.loads(resp.read().decode("utf-8-sig"))


def _baixar_bytes(url):
    pedido = urllib.request.Request(
        url, headers={"User-Agent": _AGENTE})
    with urllib.request.urlopen(pedido, timeout=TIMEOUT_SEG) as resp:
        return resp.read()


def versao_remota():
    """Devolve (versao, manifesto_dict, tag) da última Release publicada
    no GitHub, ou None em QUALQUER falha — sem repositório configurado,
    sem rede, API fora do ar, release inexistente, o que for. Uma
    checagem de atualização que falha não pode nunca travar ou atrasar o
    arranque do app; por isso nenhuma exceção escapa desta função."""
    if not _repo_configurado():
        return None
    try:
        release = _buscar_json(
            "https://api.github.com/repos/%s/%s/releases/latest"
            % (DONO_REPO, NOME_REPO))
        tag = release.get("tag_name")
        if not tag:
            return None
        manifesto = _buscar_json(
            "https://raw.githubusercontent.com/%s/%s/%s/manifesto.json"
            % (DONO_REPO, NOME_REPO, tag))
        versao = manifesto.get("versao")
        if not versao:
            return None
        return versao, manifesto, tag
    except Exception:
        # sem rede, DNS, repo/release inexistente, JSON malformado, o que
        # for — checagem de atualizacao e sempre best-effort, nunca
        # motivo pra propagar erro pro chamador
        return None


def verificar_async(callback):
    """Roda a checagem numa THREAD separada — chamadas de rede nunca devem
    rodar na thread principal do GTK, travariam a interface enquanto
    esperam resposta (mesmo cuidado que vncwidget.py já tem com a rede do
    VNC).

    `callback(tem_atualizacao, versao_local, versao_nova, manifesto_remoto,
    tag)` é chamado de volta na thread principal via GLib.idle_add — é lá,
    e não aqui, que fica seguro mexer em qualquer widget. `manifesto_remoto`
    e `tag` vêm prontos pra uma eventual chamada de `aplicar_async()`
    depois, sem precisar buscar tudo de novo."""
    from gi.repository import GLib

    def trabalhar():
        local = versao_local()
        resultado_remoto = versao_remota()
        if resultado_remoto:
            versao_nova, manifesto_remoto, tag = resultado_remoto
        else:
            versao_nova, manifesto_remoto, tag = None, None, None
        tem_atualizacao = bool(versao_nova and local and versao_nova != local)
        GLib.idle_add(callback, tem_atualizacao, local, versao_nova,
                      manifesto_remoto, tag)

    threading.Thread(target=trabalhar, daemon=True).start()


def listar_diferencas(manifesto_remoto):
    """Compara os arquivos "copiar" do manifesto remoto contra os
    arquivos soltos JÁ INSTALADOS (por hash, não por nome/data) e devolve
    a lista dos que mudaram: [(chave_relativa, nome_local, sha256_novo)].

    "chave_relativa" é o caminho como está no manifesto (ex.:
    "python/acessos.py") — usado pra montar a URL de download.
    "nome_local" é só o nome do arquivo (ex.: "acessos.py") — o bundle é
    uma pasta FLAT (_internal\\), não replica python\\/icones\\.

    PROPOSITALMENTE não olha a seção "compilar" do manifesto (o
    `vncshim.dll`) — esse arquivo não pode ser regerado por este módulo,
    só por uma reinstalação de verdade (ver docstring do módulo)."""
    base = _pasta_base()
    diferencas = []
    for chave, info in (manifesto_remoto.get("copiar") or {}).items():
        sha_novo = info.get("sha256")
        if not sha_novo:
            continue
        nome_local = os.path.basename(chave.replace("/", os.sep))
        caminho_local = os.path.join(base, nome_local)
        sha_atual = None
        if os.path.isfile(caminho_local):
            try:
                with open(caminho_local, "rb") as f:
                    sha_atual = _sha256(f.read())
            except Exception:
                sha_atual = None  # arquivo ilegivel conta como "diferente"
        if sha_atual != sha_novo:
            diferencas.append((chave, nome_local, sha_novo))
    return diferencas


def _gravar_manifesto_local(manifesto_remoto):
    """Sobrescreve o manifesto.json instalado pelo remoto recém-aplicado —
    SÓ chamado depois de uma aplicação sem nenhuma falha (ver
    aplicar_atualizacao()). Sem isso, versao_local() continuaria lendo a
    versão antiga pra sempre, e o chip "atualização disponível" nunca
    sumiria mesmo com tudo já atualizado (achado no teste de ponta a
    ponta de 2026-09-08, ver BACKLOG-exe.md, Item 5). Best-effort: se
    falhar em gravar, só loga silenciosamente pro chamador (via retorno
    None) — os arquivos já foram trocados com sucesso, isso aqui é
    cosmético (o chip), não deve virar "falha ao atualizar"."""
    try:
        with open(_caminho_manifesto_local(), "w", encoding="utf-8") as f:
            json.dump(manifesto_remoto, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False


def aplicar_atualizacao(manifesto_remoto, tag):
    """Baixa e sobrescreve, um por um, os arquivos soltos que mudaram.
    Roda de forma SÍNCRONA (bloqueante) — chamar via aplicar_async() de
    dentro da UI. Devolve um dict:
        {"aplicados": [nome, ...], "falhas": [(nome, motivo), ...]}

    Cada arquivo baixado é conferido pelo PRÓPRIO hash (o que o manifesto
    diz que deveria ser) ANTES de sobrescrever o que já está instalado —
    uma resposta truncada ou corrompida na rede não pode virar um arquivo
    quebrado no bundle. O arquivo antigo vai para `_NOME_BACKUP` antes de
    ser substituído, um nível só (não é histórico, é rede de segurança
    pro patch mais recente — mesma filosofia do `.backup_anterior` que
    `atualizar.ps1` já usa).

    Sem NENHUMA falha (mesmo que não houvesse nada pra aplicar — versão
    nova sem mudança nos arquivos "copiar", só no "compilar" por
    exemplo), o manifesto.json local é sobrescrito pelo remoto — é o que
    faz versao_local() acompanhar a versão de verdade e o chip de
    atualização sumir depois de aplicado."""
    base = _pasta_base()
    diferencas = listar_diferencas(manifesto_remoto)
    aplicados, falhas = [], []

    if diferencas:
        pasta_backup = os.path.join(base, _NOME_BACKUP)
        try:
            os.makedirs(pasta_backup, exist_ok=True)
        except Exception:
            pasta_backup = None

    for chave, nome_local, sha_esperado in diferencas:
        url = ("https://raw.githubusercontent.com/%s/%s/%s/%s"
               % (DONO_REPO, NOME_REPO, tag, chave))
        try:
            dados = _baixar_bytes(url)
        except Exception as e:
            falhas.append((nome_local, "falha ao baixar: %s" % e))
            continue

        if _sha256(dados) != sha_esperado:
            falhas.append((nome_local, "hash não confere após o download"
                                       " (rede instável? tente de novo)"))
            continue

        caminho_local = os.path.join(base, nome_local)
        try:
            if pasta_backup and os.path.isfile(caminho_local):
                shutil.copy2(caminho_local,
                            os.path.join(pasta_backup, nome_local))
            with open(caminho_local, "wb") as f:
                f.write(dados)
            aplicados.append(nome_local)
        except Exception as e:
            falhas.append((nome_local, "falha ao gravar: %s" % e))

    if not falhas:
        _gravar_manifesto_local(manifesto_remoto)

    return {"aplicados": aplicados, "falhas": falhas}


def aplicar_async(manifesto_remoto, tag, callback):
    """Mesma ideia de verificar_async(): baixar N arquivos é rede, roda
    numa THREAD separada, nunca na thread principal do GTK.
    `callback(resultado_dict)` chamado de volta via GLib.idle_add — só ali
    é seguro mexer em widgets (ex.: mostrar o diálogo de "reiniciar
    agora")."""
    from gi.repository import GLib

    def trabalhar():
        resultado = aplicar_atualizacao(manifesto_remoto, tag)
        GLib.idle_add(callback, resultado)

    threading.Thread(target=trabalhar, daemon=True).start()
