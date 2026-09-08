#!/usr/bin/env python3
"""launcher — ponto de entrada do executável compilado. NÃO é o programa.

POR QUE ESTE ARQUIVO EXISTE
-----------------------------
O PyInstaller SEMPRE compila o script de entrada (o que é passado direto
pra `Analysis([...])`) pra dentro do `.exe` — não tem como deixar ELE
solto, é o bootstrap que carrega tudo o resto. Se `acessos.py` fosse o
próprio ponto de entrada, ele ficaria preso lá pra sempre, e a ideia toda
de "trocar um `.py` sem recompilar" (ver BACKLOG-exe.md, Item 5 — pré-
requisito da auto-atualização via GitHub) não funcionaria pro arquivo mais
importante do projeto.

A solução: este arquivo é o único que fica de fato compilado dentro do
`.exe` — e ele não faz nada além de ajustar o `sys.path` e importar
`acessos` como um módulo normal, igual a `tema`/`cofre`/etc. já são. Isso
faz `acessos.py` (com toda a lógica de verdade) virar só mais um módulo
comum, elegível pro mesmo tratamento de "arquivo solto em `_internal\\`"
que o `Acessos.spec` já aplica aos outros — ver lá o porquê e o como.

Fica tão pequeno e tão estável de propósito: quanto menos código aqui,
menos motivo pra precisar recompilar o `.exe` de verdade no futuro.
"""
import sys

if getattr(sys, "frozen", False):
    # sys._MEIPASS: onde o PyInstaller extraiu/instalou os dados do bundle
    # (a pasta _internal\, no --onedir de hoje). Precisa entrar no INÍCIO
    # do sys.path, antes de qualquer import de acessos/tema/cofre/etc. —
    # são eles que vivem la soltos, e sem isto o Python nao os acha.
    sys.path.insert(0, sys._MEIPASS)

import acessos  # noqa: E402 (import depois do sys.path de proposito)

if __name__ == "__main__":
    sys.exit(acessos.main())
