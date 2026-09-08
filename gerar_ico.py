#!/usr/bin/env python3
"""Ferramenta de RELEASE — gera icones/acessos.ico a partir de acessos.svg.

Não faz parte do runtime do Acessos (não é copiado pelo instalar.ps1 nem
importado por acessos.py) — roda uma vez, ou de novo sempre que o SVG
mudar, pra produzir o .ico usado por instalar.ps1 (ícone do atalho) e
compilar_exe.ps1 (--icon do .exe). Precisa do Python do MSYS2 (PyGObject +
Pillow — `pacman -S mingw-w64-x86_64-python-pillow`), não do CPython
oficial.

Uso:
    /c/msys64/mingw64/bin/python3.exe gerar_ico.py

Rasteriza cada tamanho DIRETO do SVG via GdkPixbuf — nítido em cada
resolução, sem o borrão de fazer downscale de uma única imagem grande — e
monta o container .ico com Pillow.
"""
import io
import os
import sys

import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(AQUI, "icones", "acessos.svg")
ICO = os.path.join(AQUI, "icones", "acessos.ico")
TAMANHOS = (16, 24, 32, 48, 64, 128, 256)


def rasterizar(tamanho):
    pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(SVG, tamanho, tamanho, False)
    if not pix.get_has_alpha():
        pix = pix.add_alpha(False, 0, 0, 0)
    ok, buf = pix.save_to_bufferv("png", [], [])
    if not ok:
        raise RuntimeError("GdkPixbuf falhou ao exportar PNG (%dpx)" % tamanho)
    return Image.open(io.BytesIO(bytes(buf))).convert("RGBA")


def main():
    imagens = [rasterizar(t) for t in TAMANHOS]
    base = imagens[-1]       # a maior primeiro no arquivo, convenção comum
    outras = imagens[:-1]
    base.save(
        ICO, format="ICO",
        sizes=[(im.width, im.height) for im in imagens],
        append_images=outras,
    )
    print("gerado: %s (%d bytes)" % (ICO, os.path.getsize(ICO)))


if __name__ == "__main__":
    sys.exit(main())
