#!/usr/bin/env bash
# resolver_dlls.sh — usado por compilar_exe.ps1, não roda sozinho no dia a
# dia.
#
# Resolve, recursivamente, TODAS as DLLs do MSYS2 (mingw64/bin) das quais
# um binário nativo depende. Existe porque --add-binary do PyInstaller só
# copia o arquivo que você pede — ele NÃO analisa as dependências de um
# executável externo (só faz isso para o próprio interpretador Python e
# suas extensões .pyd). Sem isto, wfreerdp.exe entraria no bundle sozinho,
# sem libfreerdp3.dll/libwinpr3.dll/ffmpeg/libx264 etc., e falharia ao
# carregar na hora de abrir uma conexão RDP.
#
# Uso: resolver_dlls.sh <binario-inicial.exe> <arquivo-de-saida.txt>
set -e
export PATH=/mingw64/bin:$PATH

binario_inicial="$1"
saida="$2"

declare -A visto
fila=("$binario_inicial")

while [ ${#fila[@]} -gt 0 ]; do
    atual="${fila[0]}"
    fila=("${fila[@]:1}")
    [ -n "${visto[$atual]:-}" ] && continue
    visto[$atual]=1

    caminho="/mingw64/bin/$atual"
    [ -f "$caminho" ] || continue

    # objdump -p lista o import table do PE; "DLL Name:" e a linha que
    # nomeia cada dependencia direta. So seguimos as que o proprio mingw64
    # fornece (existem em /mingw64/bin) — DLLs do Windows (KERNEL32.dll,
    # msvcrt.dll...) ja estao em toda maquina e nao precisam ser copiadas.
    for dll in $(objdump -p "$caminho" 2>/dev/null | grep "DLL Name:" | awk '{print $3}'); do
        if [ -f "/mingw64/bin/$dll" ] && [ -z "${visto[$dll]:-}" ]; then
            fila+=("$dll")
        fi
    done
done

printf '%s\n' "${!visto[@]}" | sort > "$saida"
