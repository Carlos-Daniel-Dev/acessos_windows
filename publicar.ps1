#
#  publicar.ps1 — encadeia gerar_manifesto.ps1 + compilar_exe.ps1 +
#  instalador.iss num comando só. Fecha a lacuna que a Opção B (build uma
#  vez, distribui pronto — ver BACKLOG-exe.md, Item 2) deixa em aberto: sem
#  isto, "esquecer de republicar" depois de editar código é fácil de
#  acontecer — vira um ritual de um comando só, em vez de quatro passos
#  manuais.
#
#  O QUE FAZ, NESSA ORDEM
#     1. gerar_manifesto.ps1  -> recalcula os hashes, decide a versão
#     2. compilar_exe.ps1     -> gera dist_exe\Acessos\ (o .exe standalone)
#     3. ISCC.exe             -> empacota isso num instalador único
#     4. copia o instalador (e o manifesto.json) pro ponto de distribuição,
#        se -DestinoPublicacao for informado
#     5. limpa os artefatos de build (dist_exe\, build_exe\) — são
#        regeneráveis, não precisam ficar ocupando espaço depois de prontos
#
#  USO:
#     .\publicar.ps1                          usa a data/hora como versão
#     .\publicar.ps1 -Versao 2026.09.10.1     versão explícita
#     .\publicar.ps1 -DestinoPublicacao "\\servidor\acessos"
#                                             copia o instalador pronto pra lá
#     .\publicar.ps1 -PularVncshim            repassado pro compilar_exe.ps1
#     .\publicar.ps1 -SemRdp                  repassado pro compilar_exe.ps1
#     .\publicar.ps1 -ManterBuild             não limpa dist_exe\/build_exe\
#                                             no final (útil pra depurar)

[CmdletBinding()]
param(
    [string]$Versao,
    [string]$DestinoPublicacao,
    [switch]$PularVncshim,
    [switch]$SemRdp,
    [switch]$ManterBuild
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

foreach ($arquivo in @("gerar_manifesto.ps1", "compilar_exe.ps1", "instalador.iss")) {
    if (-not (Test-Path (Join-Path $Aqui $arquivo))) {
        Erro "$arquivo não encontrado em $Aqui — publicar.ps1 precisa estar"
        Erro "na raiz do pacote, junto dos outros scripts"
        exit 1
    }
}

# ISCC.exe muda de lugar conforme como o Inno Setup foi instalado —
# winget (usado nesta máquina) põe em %LOCALAPPDATA%\Programs, o
# instalador clássico do site vai pra Program Files. Tenta os caminhos
# conhecidos antes de desistir.
function AcharIscc {
    $candidatos = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidatos) {
        if (Test-Path $c) { return $c }
    }
    $peloPath = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($peloPath) { return $peloPath.Source }
    return $null
}

$Iscc = AcharIscc
if (-not $Iscc) {
    Erro "ISCC.exe (compilador do Inno Setup) não encontrado"
    Nota "instale com: winget install JRSoftware.InnoSetup"
    exit 1
}

# --------------------------------------------------- 1. manifesto (+ versão)
#
# NOTA SOBRE $LASTEXITCODE: nem gerar_manifesto.ps1 nem compilar_exe.ps1
# chamam "exit 0" no caminho de sucesso — só "exit 1" quando falham. Sem um
# "exit 0" explícito, $LASTEXITCODE some ou fica com o valor de uma chamada
# nativa anterior (de dentro do próprio script chamado), NÃO confiável pra
# decidir "deu certo" aqui fora. Por isso o sinal de sucesso de verdade é
# sempre o ARQUIVO QUE DEVERIA TER SIDO CRIADO — mesmo padrão que
# compilar_exe.ps1 e o ISCC.exe já usam internamente pra se auto-checar.
$antes = if (Test-Path (Join-Path $Aqui "manifesto.json")) {
    (Get-Item (Join-Path $Aqui "manifesto.json")).LastWriteTimeUtc
} else { $null }

Azul "[1/4] gerando manifesto"
# splat de HASHTABLE, nao de array: um array so passa valores posicionais
# soltos — "-Versao"/"-PularVncshim" digitados dentro de um array NAO sao
# reconhecidos como nome de parametro pelo binder (testado na pratica:
# deu "Nao e possivel localizar um parametro posicional" na primeira
# versao deste script, que usava array).
$argsManifesto = @{}
if ($Versao) { $argsManifesto["Versao"] = $Versao }
& (Join-Path $Aqui "gerar_manifesto.ps1") @argsManifesto

$caminhoManifesto = Join-Path $Aqui "manifesto.json"
$depois = if (Test-Path $caminhoManifesto) { (Get-Item $caminhoManifesto).LastWriteTimeUtc } else { $null }
if (-not $depois -or $depois -eq $antes) {
    Erro "gerar_manifesto.ps1 terminou mas manifesto.json não foi atualizado"
    exit 1
}
# a versão de VERDADE é a que ficou gravada no manifesto — evita duplicar
# aqui a lógica de "sem -Versao, usa a data de hoje" que já existe lá
$manifesto = Get-Content -Path $caminhoManifesto -Raw -Encoding UTF8 | ConvertFrom-Json
$VersaoFinal = $manifesto.versao
Ok "  versão: $VersaoFinal"

# --------------------------------------------------- 2. compilar o .exe
Azul "[2/4] compilando o .exe (compilar_exe.ps1)"
$argsCompilar = @{}
if ($PularVncshim) { $argsCompilar["PularVncshim"] = $true }
if ($SemRdp)        { $argsCompilar["SemRdp"] = $true }
& (Join-Path $Aqui "compilar_exe.ps1") @argsCompilar
# ($LASTEXITCODE não é confiável aqui pelo mesmo motivo do passo 1 —
# compilar_exe.ps1 não chama "exit 0" no caminho de sucesso. O arquivo
# abaixo é quem decide.)
$ExeGerado = Join-Path $Aqui "dist_exe\Acessos\Acessos.exe"
if (-not (Test-Path $ExeGerado)) {
    Erro "compilar_exe.ps1 terminou mas $ExeGerado não existe"
    exit 1
}
Ok "  Acessos.exe pronto"

# --------------------------------------------------- 3. empacotar instalador
Azul "[3/4] empacotando o instalador (Inno Setup)"
& $Iscc "/DAppVersion=$VersaoFinal" (Join-Path $Aqui "instalador.iss")
if ($LASTEXITCODE -ne 0) {
    Erro "ISCC.exe falhou (código $LASTEXITCODE)"
    exit 1
}
$InstaladorGerado = Join-Path $Aqui "dist_instalador\AcessosSetup-$VersaoFinal.exe"
if (-not (Test-Path $InstaladorGerado)) {
    Erro "ISCC.exe terminou mas $InstaladorGerado não existe"
    exit 1
}
$tamanhoMB = "{0:N0}" -f ((Get-Item $InstaladorGerado).Length / 1MB)
Ok "  $InstaladorGerado ($tamanhoMB MB)"

# --------------------------------------------------- 4. publicar (opcional)
if ($DestinoPublicacao) {
    Azul "[4/4] copiando pro ponto de distribuição"
    if (-not (Test-Path $DestinoPublicacao)) {
        try {
            New-Item -ItemType Directory -Force -Path $DestinoPublicacao | Out-Null
        } catch {
            Erro "não consegui criar/acessar $DestinoPublicacao ($($_.Exception.Message))"
            Nota "o instalador ficou pronto em $InstaladorGerado — copie manualmente"
            exit 1
        }
    }
    Copy-Item $InstaladorGerado $DestinoPublicacao -Force
    # o manifesto.json tambem precisa chegar la: e o que atualizar.ps1 (pro
    # fluxo MSYS2/nao-compilado) e uma futura checagem de atualizacao leem
    Copy-Item (Join-Path $Aqui "manifesto.json") $DestinoPublicacao -Force
    Ok "  copiado pra $DestinoPublicacao"
} else {
    Azul "[4/4] sem -DestinoPublicacao — instalador fica só em dist_instalador\"
    Nota "copie manualmente pro ponto de distribuição da equipe, se for o caso"
}

# --------------------------------------------------- limpeza
if (-not $ManterBuild) {
    Remove-Item -Recurse -Force (Join-Path $Aqui "dist_exe") -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $Aqui "build_exe") -ErrorAction SilentlyContinue
    Nota "dist_exe\ e build_exe\ removidos (regeneráveis; use -ManterBuild pra manter)"
}

Write-Host ""
Ok "publicado: versão $VersaoFinal"
