#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
importar_rdm — traz máquinas de um export CSV do Devolutions Remote
Desktop Manager (RDM) pro conexoes.ini do Acessos.

FORMATO SUPORTADO: "Export vault (.csv)" do RDM, cabeçalho
    Host,Port,Description,Display Name,Folder
Os outros formatos que o RDM oferece (`.rdm`, `.json`, `.html`, `.xml`)
NÃO são lidos por este módulo — decisão de 2026-09-09 (ver
LEIAME-windows.md): `.rdm` é formato proprietário e pode trazer um blob
de credenciais cifrado com a chave do cofre deles (impossível decifrar
aqui); `.json`/`.xml` têm schema aninhado desconhecido sem um exemplo
real; `.html` normalmente nem traz os campos técnicos. CSV é tabular,
documentado e testado contra um export real.

MAPEAMENTO
    Host          -> host
    Port          -> decide o protocolo (5900 VNC, 3389 RDP, 22 SSH —
                     mesma tabela PORTA_PROTO de acessos.py) e a porta
                     não-padrão, quando difere do valor usual do protocolo
    Display Name  -> nome da seção (o título do card) — deduplicado com
                     um sufixo " (2)", " (3)"... se o CSV repetir o nome
    Folder        -> grupo, convertendo "\\" (subpasta do RDM) em ";"
                     (subgrupo do Acessos, ver SEP_GRUPO em acessos.py)
    Description   -> ignorado (vazio em todo export que vimos até agora;
                     e não há campo equivalente no Acessos pra guardar)

NÃO IMPORTA usuário nem senha — o CSV do RDM não traz isso (ficam no
cofre proprietário deles, que este módulo não tenta decifrar). Toda
máquina chega sem senha, exatamente como uma conexão cadastrada à mão
sem preencher o campo — o Acessos pergunta na hora de conectar.

JÁ EXISTE NO INI: uma linha cujo host já aparece em alguma seção do
conexoes.ini atual é pulada (comparação por host, sem diferenciar
maiúsculas) — reimportar o mesmo CSV duas vezes não duplica cards.

CODIFICAÇÃO: exports do RDM feitos no Windows às vezes saem com um erro
clássico de dupla-codificação (um "ç" vira "Ã§", símbolo de bytes UTF-8
decodificados como Windows-1252) — _corrigir_mojibake() desfaz isso
quando detecta o padrão, sem mexer em arquivos que já estão certos.
"""
import csv
import io

# mesma tabela de acessos.py (interpretar_alvo) — mantida separada de
# propósito: este módulo não importa acessos.py (evita import circular,
# mesmo motivo de dialogo_ui.py/massa_ui.py serem injetados por fora)
PORTA_PROTO = {"22": "ssh", "3389": "rdp", "5900": "vnc"}
SEP_GRUPO = ";"

CAMPOS_ESPERADOS = {"Host", "Port", "Display Name", "Folder"}


def _corrigir_mojibake(texto):
    """Desfaz um Windows-1252 decodificado por cima de bytes UTF-8 — o
    sintoma é "ç"/"ã"/"õ" virando "Ã§"/"Ã£"/"Ãµ". Só reencoda se a volta
    for possível; devolve o texto original se não (mais seguro que
    arriscar embaralhar algo que já estava certo)."""
    if "Ã" not in texto and "Â" not in texto:
        return texto
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def _ler_texto(caminho):
    """O RDM exporta ora em UTF-8 (com ou sem BOM), ora em Windows-1252
    puro — tenta nessa ordem e fica com a primeira que não falhar."""
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(caminho, encoding=codificacao, newline="") as f:
                return f.read()
        except (UnicodeDecodeError, OSError):
            continue
    raise OSError("não consegui ler o arquivo com nenhuma codificação conhecida")


def _grupo_de_folder(folder):
    """"01_Controle - Caixas\\01_ Loja 02" -> "01_Controle - Caixas;01_ Loja 02"

    SÓ "\\" (barra invertida) é separador de subpasta no RDM — "/" é
    pontuação comum DENTRO de um nome de pasta (ex.: "AD / ARQUIVOS /
    IMPRESSORAS / NAS" é UMA pasta só, não quatro subpastas; achado
    testando contra um export real, 2026-09-09). Dividir por "/" também
    quebraria esse nome em quatro grupos errados."""
    folder = (folder or "").strip().strip("\\")
    if not folder:
        return ""
    partes = [p.strip() for p in folder.split("\\") if p.strip()]
    return SEP_GRUPO.join(partes)


def _nome_unico(nome, usados):
    """Cabeçalho de seção do INI precisa ser único e não pode conter
    colchetes. Um Display Name repetido no CSV ganha um sufixo numerado
    — nunca sobrescreve uma entrada já vista NESTA importação."""
    nome = (nome or "").strip().replace("]", ")").replace("[", "(") or "sem nome"
    base, candidato, n = nome, nome, 2
    while candidato.lower() in usados:
        candidato = "%s (%d)" % (base, n)
        n += 1
    usados.add(candidato.lower())
    return candidato


def ler_csv_rdm(caminho):
    """Lê o CSV e devolve uma lista de dicts:
        {"nome", "host", "porta", "protocolo", "grupo", "linha_origem"}

    "linha_origem" é só pra mensagem de erro/relatório (2 = primeira
    linha após o cabeçalho), não vai pro INI. "protocolo" vem None
    quando a porta não bate com nenhum protocolo conhecido — a entrada
    ainda é devolvida (quem chama decide o que fazer)."""
    texto = _corrigir_mojibake(_ler_texto(caminho))
    leitor = csv.DictReader(io.StringIO(texto))
    campos = set(leitor.fieldnames or [])
    if not CAMPOS_ESPERADOS.issubset(campos):
        faltando = CAMPOS_ESPERADOS - campos
        raise ValueError(
            "cabeçalho inesperado — faltam as colunas %s (achei: %s). "
            "Confirme que é um \"Export vault (.csv)\" do RDM."
            % (", ".join(sorted(faltando)), ", ".join(leitor.fieldnames or [])))

    saida = []
    usados = set()
    for i, linha in enumerate(leitor, start=2):
        host = (linha.get("Host") or "").strip()
        if not host:
            continue
        porta = (linha.get("Port") or "").strip()
        nome_bruto = (linha.get("Display Name") or "").strip() or host
        saida.append({
            "nome": _nome_unico(nome_bruto, usados),
            "host": host,
            "porta": porta,
            "protocolo": PORTA_PROTO.get(porta),
            "grupo": _grupo_de_folder(linha.get("Folder")),
            "linha_origem": i,
        })
    return saida


def _hosts_existentes(caminho_ini):
    """Hosts já cadastrados no conexoes.ini atual, em minúsculas — leitura
    crua (configparser), não precisa do cofre aberto pra isto."""
    import configparser
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read(caminho_ini, encoding="utf-8")
    except (OSError, configparser.Error):
        return set()
    vistos = set()
    for secao in cp.sections():
        if secao == "geral":
            continue
        host = cp[secao].get("host", "").strip().lower()
        if host:
            vistos.add(host)
    return vistos


def _linhas_ini_da_maquina(entrada):
    """Monta o bloco [seção] pra uma entrada — só os campos que ela
    realmente precisa; Conexao.__init__ (acessos.py) já tem os defaults
    certos pra tudo que ficar de fora (porta 5900, VNC ligado, RDP/SSH
    desligados)."""
    linhas = ["\n[%s]\n" % entrada["nome"], "host  = %s\n" % entrada["host"]]
    if entrada["grupo"]:
        linhas.append("grupo = %s\n" % entrada["grupo"])

    protocolo = entrada["protocolo"]
    if protocolo == "rdp":
        linhas.append("vnc   = 0\n")
        linhas.append("rdp   = 1\n")
        if entrada["porta"] and entrada["porta"] != "3389":
            linhas.append("rdp_porta = %s\n" % entrada["porta"])
    elif protocolo == "ssh":
        linhas.append("vnc   = 0\n")
        linhas.append("ssh   = 1\n")
        if entrada["porta"] and entrada["porta"] != "22":
            linhas.append("ssh_porta = %s\n" % entrada["porta"])
    else:
        # "vnc" ou porta desconhecida: VNC fica ligado por padrão (mesmo
        # comportamento de uma conexão cadastrada à mão) — melhor
        # aparecer com a tela na porta informada do que sumir da lista.
        if entrada["porta"] and entrada["porta"] != "5900":
            linhas.append("porta = %s\n" % entrada["porta"])
    return linhas


def importar(caminho_csv, caminho_ini, escrever_ini_fn):
    """Lê o CSV e ANEXA as máquinas novas ao conexoes.ini (nunca
    sobrescreve o que já está lá; hosts já cadastrados são pulados).

    `escrever_ini_fn` é injetado pra não criar dependência circular com
    acessos.py — é o `escrever_ini` de lá, o ponto único de escrita do
    INI (atômico, com backup em `historico/`; mesmo padrão de
    massa_ui.construir()/dialogo_ui pra evitar import circular).

    Devolve um dict:
        {"importadas": int, "puladas_existentes": int,
         "puladas_sem_host": int, "avisos": [str, ...]}
    """
    todas = ler_csv_rdm(caminho_csv)
    existentes = _hosts_existentes(caminho_ini)

    try:
        with open(caminho_ini, encoding="utf-8") as f:
            linhas = f.readlines()
    except OSError:
        linhas = []

    avisos = []
    importadas = 0
    puladas_existentes = 0
    for entrada in todas:
        if entrada["host"].lower() in existentes:
            puladas_existentes += 1
            continue
        if entrada["protocolo"] is None and entrada["porta"]:
            avisos.append(
                "linha %d (%s): porta %s não é VNC/SSH/RDP conhecida — "
                "importada como tela (VNC) nessa porta, confira"
                % (entrada["linha_origem"], entrada["nome"], entrada["porta"]))
        linhas.extend(_linhas_ini_da_maquina(entrada))
        existentes.add(entrada["host"].lower())  # o próprio CSV pode repetir host
        importadas += 1

    if importadas == 0:
        return {"importadas": 0, "puladas_existentes": puladas_existentes,
               "puladas_sem_host": 0, "avisos": avisos}

    if not linhas or linhas[-1].strip():
        linhas.append("\n")

    if not escrever_ini_fn(caminho_ini, linhas,
                           "importar RDM (%d máquinas)" % importadas):
        raise OSError("falha ao gravar o conexoes.ini")

    return {"importadas": importadas, "puladas_existentes": puladas_existentes,
           "puladas_sem_host": 0, "avisos": avisos}
