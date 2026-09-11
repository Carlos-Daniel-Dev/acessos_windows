#
#  compilar_exe.ps1 — empacota o Acessos num executável standalone, via
#  PyInstaller do MSYS2 (ver BACKLOG-exe.md, Item 1 — resolvido em
#  2026-09-04: o MSYS2 empacota PyInstaller já compilado contra o ABI
#  certo, com hooks prontos para gi.repository/GTK3).
#
#  NÃO substitui instalar.ps1/atualizar.ps1 ainda — é o primeiro passo pra
#  isso (ver Item 3 do backlog). O resultado é uma pasta standalone que
#  roda em QUALQUER Windows 10/11 sem MSYS2 instalado — foi testado assim
#  num "hello world" antes de apontar pra aplicação real.
#
#  USO:
#     .\compilar_exe.ps1                empacota (--onedir, sem console)
#     .\compilar_exe.ps1 -Console       mantém o console (mais fácil de
#                                       depurar um build novo)
#     .\compilar_exe.ps1 -PularVncshim  reusa um libvncshim.dll já
#                                       compilado antes (mais rápido para
#                                       iterar quando só o .py mudou)
#     .\compilar_exe.ps1 -PularRdpshim  idem, para o librdpshim.dll
#
#  RDP: linkado direto (rdpshim.c/librdpshim.dll — ver RDPSHIM-interno.md,
#  não publicado), sem processo externo. Não é mais opcional/pulável
#  como o wfreerdp.exe embutido era antes (-SemRdp saiu) — RDP faz parte
#  do bundle sempre, igual VNC.

[CmdletBinding()]
param(
    [switch]$Console,
    [switch]$PularVncshim,
    [switch]$PularRdpshim
)

$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

function Azul($t) { Write-Host $t -ForegroundColor Cyan }
function Ok($t)   { Write-Host $t -ForegroundColor Green }
function Nota($t) { Write-Host "       $t" -ForegroundColor Gray }
function Erro($t) { Write-Host "ERRO: $t" -ForegroundColor Red }

$Aqui = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Aqui)) { $Aqui = (Get-Location).Path }

$Msys2Raiz = "C:\msys64"
$Msys2Bin  = Join-Path $Msys2Raiz "usr\bin\bash.exe"
$Mingw64   = Join-Path $Msys2Raiz "mingw64"
if (-not (Test-Path $Msys2Bin)) {
    Erro "MSYS2 não encontrado em $Msys2Raiz — rode .\instalar.ps1 primeiro"
    exit 1
}

$PastaBuild = Join-Path $Aqui "build_exe"
$PastaDist  = Join-Path $Aqui "dist_exe"
New-Item -ItemType Directory -Force -Path $PastaBuild | Out-Null

function Msys2Exec($comando) {
    # mesma receita do instalar.ps1/atualizar.ps1: MSYSTEM=MINGW64 obrigatorio
    # (senao /mingw64/bin nao entra no PATH do bash) e HOME/USERPROFILE
    # precisam estar setados — sem eles, ferramentas Python que usam
    # pathlib.Path.home() (o proprio PyInstaller, entre outras) abortam
    # com "Could not determine home directory" mesmo com tudo instalado.
    $guardaAnterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $env:MSYSTEM = "MINGW64"
        $env:CHERE_INVOKING = "1"
        if (-not $env:HOME) {
            $env:HOME = ($env:USERPROFILE -replace '\\', '/') -replace '^([A-Za-z]):', '/$1'
        }
        & $Msys2Bin -lc $comando 2>&1 | ForEach-Object { Write-Host "       $_" }
        $codigo = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $guardaAnterior
    }
    return $codigo
}

# --------------------------------------------------- 1. garantir PyInstaller
Azul "[1/4] conferindo PyInstaller (MSYS2)"
$temPyinstaller = Msys2Exec "export PATH=/mingw64/bin:`$PATH; python3 -c 'import PyInstaller' 2>/dev/null"
if ($temPyinstaller -ne 0) {
    Nota "instalando mingw-w64-x86_64-pyinstaller..."
    $codigo = Msys2Exec "pacman -S --needed --noconfirm mingw-w64-x86_64-pyinstaller"
    if ($codigo -ne 0) {
        Erro "não consegui instalar o PyInstaller via pacman"
        exit 1
    }
}
Ok "  PyInstaller ok"

# --------------------------------------------------- 2. vncshim.dll fresco
$DllOrigem = Join-Path $PastaBuild "libvncshim.dll"
if ($PularVncshim -and (Test-Path $DllOrigem)) {
    Azul "[2/5] libvncshim.dll (reaproveitado, -PularVncshim)"
} else {
    Azul "[2/5] compilando libvncshim.dll"
    $origemC = (Join-Path $Aqui "src\vncshim.c") -replace '\\', '/'
    $destinoDll = ($DllOrigem) -replace '\\', '/'
    $comando = @"
export PATH=/mingw64/bin:`$PATH
gcc -shared -O2 -Wall -o '$destinoDll' '$origemC' \
    `$(pkg-config --cflags --libs libvncclient)
"@
    $codigo = Msys2Exec $comando
    if ($codigo -ne 0 -or -not (Test-Path $DllOrigem)) {
        Erro "falha ao compilar libvncshim.dll (código $codigo)"
        exit 1
    }
}
Ok "  libvncshim.dll — $((Get-Item $DllOrigem).Length) bytes"

# -------------------------------------------------- 2b. rdpshim.dll fresco
#
# Mesma receita do vncshim: linka libfreerdp/libwinpr direto (ver
# src/rdpshim.c e RDPSHIM-interno.md, não publicado). __STDC_NO_THREADS__
# contorna um <threads.h> ausente neste MSYS2 (achado testando — ver doc
# interna); WIN32_LEAN_AND_MEAN já está no próprio rdpshim.c.
$RdpshimDllOrigem = Join-Path $PastaBuild "librdpshim.dll"
if ($PularRdpshim -and (Test-Path $RdpshimDllOrigem)) {
    Azul "[2b/5] librdpshim.dll (reaproveitado, -PularRdpshim)"
} else {
    Azul "[2b/5] compilando librdpshim.dll"
    $origemC = (Join-Path $Aqui "src\rdpshim.c") -replace '\\', '/'
    $destinoDll = ($RdpshimDllOrigem) -replace '\\', '/'
    $comando = @"
export PATH=/mingw64/bin:`$PATH
gcc -shared -O2 -Wall -D__STDC_NO_THREADS__ -o '$destinoDll' '$origemC' \
    `$(pkg-config --cflags --libs freerdp-client3 freerdp3 winpr3) -lws2_32
"@
    $codigo = Msys2Exec $comando
    if ($codigo -ne 0 -or -not (Test-Path $RdpshimDllOrigem)) {
        Erro "falha ao compilar librdpshim.dll (código $codigo)"
        exit 1
    }
}
Ok "  librdpshim.dll — $((Get-Item $RdpshimDllOrigem).Length) bytes"

# ---------------------------------------- 2c. dependências do rdpshim.dll
#
# --add-binary do PyInstaller so copia o arquivo pedido — ele NAO analisa
# as dependencias de um binario nosso (isso so acontece para o proprio
# interpretador Python e as extensoes .pyd). librdpshim.dll sozinho no
# bundle falharia ao carregar, sem libfreerdp3.dll/libwinpr3.dll e toda a
# pilha de codecs de video (ffmpeg, x264, x265, vpx...) que elas linkam.
# O resolver_dlls.sh percorre esse grafo de dependencias recursivamente,
# a partir do PROPRIO librdpshim.dll (fora de mingw64/bin — ver o
# suporte a caminho completo adicionado no script).
Azul "[2c/5] resolvendo dependências do librdpshim.dll"
$ListaDeps = Join-Path $PastaBuild "rdpshim_deps.txt"
$resolverPosix = (Join-Path $Aqui "resolver_dlls.sh") -replace '\\', '/'
$rdpshimPosix = ($RdpshimDllOrigem -replace '\\', '/')
$listaPosix = ($ListaDeps -replace '\\', '/')
$codigo = Msys2Exec "bash '$resolverPosix' '$rdpshimPosix' '$listaPosix'"
if ($codigo -ne 0 -or -not (Test-Path $ListaDeps)) {
    Erro "falha ao resolver dependências do librdpshim.dll (código $codigo)"
    exit 1
}
$AddBinariesRdp = @()
$nomes = Get-Content $ListaDeps | Where-Object { $_ -ne "" }
foreach ($nome in $nomes) {
    $caminho = Join-Path $Mingw64 "bin\$nome"
    if (Test-Path $caminho) {
        $AddBinariesRdp += (($caminho -replace '\\', '/') + ";.")
    }
}
Ok "  $($AddBinariesRdp.Count) DLL(s) de dependência do RDP (libfreerdp/libwinpr + codecs)"

# --------------------------------------------------- 3. empacotar
Azul "[3/5] empacotando com PyInstaller (Acessos.spec, --onedir)"
if (Test-Path $PastaDist) { Remove-Item -Recurse -Force $PastaDist }

# A partir daqui, quem decide COMO empacotar é Acessos.spec (mantido a
# mao, nao gerado) — ele e quem tira os modulos do projeto de dentro do
# PYZ e os deixa soltos (ver o proprio arquivo pro porque). Este script so
# repassa os parametros que MUDAM de build pra build, via variavel de
# ambiente — um .spec nao aceita os mesmos --flags de linha de comando que
# uma chamada direta ao pyinstaller aceitaria.
$SpecFile = Join-Path $Aqui "Acessos.spec"
if (-not (Test-Path $SpecFile)) {
    Erro "Acessos.spec não encontrado em $Aqui"
    exit 1
}

$env:ACESSOS_RAIZ = $Aqui
$env:ACESSOS_JANELA = if ($Console) { "0" } else { "1" }
$env:ACESSOS_ICONE = Join-Path $Aqui "icones\acessos.ico"
if (-not (Test-Path $env:ACESSOS_ICONE)) {
    Nota "icones\acessos.ico não encontrado — .exe sai com o ícone genérico do PyInstaller"
    Nota "(rode gerar_ico.py pra criar um a partir do acessos.svg)"
    $env:ACESSOS_ICONE = ""
}
$env:ACESSOS_VNCSHIM_DLL = $DllOrigem
$env:ACESSOS_RDPSHIM_DLL = $RdpshimDllOrigem
$env:ACESSOS_MINGW64_BIN = Join-Path $Mingw64 "bin"
# a mesma lista de nomes de arquivo que resolver_dlls.sh gravou no passo
# 2c — Acessos.spec resolve o caminho completo sozinho, a partir de
# ACESSOS_MINGW64_BIN acima (evita duplicar a lista aqui)
$env:ACESSOS_RDPSHIM_DEPS_TXT = $ListaDeps

$specPosix = ($SpecFile -replace '\\', '/')
$distPosix = ($PastaDist -replace '\\', '/')
$buildPosix = ($PastaBuild -replace '\\', '/')

$codigo = Msys2Exec @"
export PATH=/mingw64/bin:`$PATH
pyinstaller --noconfirm --distpath '$distPosix' --workpath '$buildPosix/work' '$specPosix'
"@
if ($codigo -ne 0) {
    Erro "PyInstaller falhou (código $codigo) — veja o log acima"
    exit 1
}

$ExeFinal = Join-Path $PastaDist "Acessos\Acessos.exe"
if (-not (Test-Path $ExeFinal)) {
    Erro "build terminou mas $ExeFinal não existe"
    exit 1
}

# --------------------------------------------------- 4. relatorio
Azul "[5/5] pronto"
$tamanho = "{0:N0}" -f ((Get-ChildItem -Recurse (Split-Path $ExeFinal) |
                         Measure-Object -Property Length -Sum).Sum / 1MB)
Ok "  $ExeFinal"
Nota "  tamanho total da pasta: ~$tamanho MB"
Nota "  modo: $(if ($Console) { 'console visível' } else { 'janela (sem console) — log em %LOCALAPPDATA%\acessos\log.txt' })"
Nota "  RDP: embutido via librdpshim.dll (linkado direto, sem processo externo) — $($AddBinariesRdp.Count) DLL(s) de dependência"
Write-Host ""
Nota "testar: $ExeFinal"
Nota "para simular uma máquina sem MSYS2, rode numa sessão com PATH mínimo"
Nota "(o hello-world de prova já foi validado assim — ver BACKLOG-exe.md)"
