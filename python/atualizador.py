#!/usr/bin/env python3
"""atualizador — verifica se há uma versão mais nova do Acessos no GitHub.

SÓ VERIFICA E AVISA — não baixa nem aplica nada sozinho (decisão de
2026-09-08, ver BACKLOG-exe.md, Item 5: notificar e pedir confirmação, não
auto-aplicar, pra um push ruim na `main` não derrubar todo mundo
instantaneamente sem ninguém perceber).

FONTE DA VERDADE: a última GitHub Release publicada, não o HEAD cru da
`main` — um push no meio do dia, ainda incompleto, não deve virar "a
versão mais nova" pro app. Publicar uma release é o momento explícito de
"isto está pronto pra todo mundo".

REPOSITÓRIO PÚBLICO (decidido em 2026-09-08): sem repositório privado, não
há token/credencial nenhum pra gerenciar — a checagem e o download do
manifesto usam `raw.githubusercontent.com`/API pública do GitHub, sem
autenticação.

Este módulo faz a parte que já dava pra construir hoje (a checagem em si).
Baixar e aplicar os arquivos que mudaram depende do pré-requisito
arquitetural que JÁ EXISTE (ver launcher.py/Acessos.spec — os .py do
projeto ficam soltos em _internal\\) mas cujo lado "buscar do GitHub e
sobrescrever" ainda não foi construído — fica para a próxima etapa.
"""
import json
import os
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


def _repo_configurado():
    return not DONO_REPO.startswith("PREENCHER")


def _caminho_manifesto_local():
    """Onde o manifesto.json DESTA instalação está — dentro do bundle
    compilado (sys._MEIPASS) ou, rodando de fonte, ao lado deste arquivo
    (mesma convenção de caminho_icone()/_carregar_shim() já usam)."""
    aqui = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, "frozen", False):
        aqui = getattr(sys, "_MEIPASS", aqui)
    else:
        # rodando de fonte: manifesto.json fica na raiz do pacote, um
        # nivel acima de python\
        aqui = os.path.dirname(aqui)
    return os.path.join(aqui, "manifesto.json")


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


def versao_remota():
    """Devolve (versao, manifesto_dict) da última Release publicada no
    GitHub, ou None em QUALQUER falha — sem repositório configurado, sem
    rede, API fora do ar, release inexistente, o que for. Uma checagem de
    atualização que falha não pode nunca travar ou atrasar o arranque do
    app; por isso nenhuma exceção escapa desta função."""
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
        return versao, manifesto
    except Exception:
        # sem rede, DNS, repo/release inexistente, JSON malformado, o que
        # for — checagem de atualizacao e sempre best-effort, nunca
        # motivo pra propagar erro pro chamador
        return None


def verificar_async(callback):
    """Roda a checagem numa THREAD separada — chamadas de rede nunca devem
    rodar na thread principal do GTK, travariam a interface enquanto
    esperam resposta (mesmo cuidado que vncwidget.py já tem com a rede do
    VNC). `callback(tem_atualizacao, versao_local, versao_remota)` é
    chamado de volta na thread principal via GLib.idle_add — é lá, e não
    aqui, que fica seguro mexer em qualquer widget."""
    from gi.repository import GLib

    def trabalhar():
        local = versao_local()
        resultado_remoto = versao_remota()
        versao_nova = resultado_remoto[0] if resultado_remoto else None
        tem_atualizacao = bool(versao_nova and local and versao_nova != local)
        GLib.idle_add(callback, tem_atualizacao, local, versao_nova)

    threading.Thread(target=trabalhar, daemon=True).start()
