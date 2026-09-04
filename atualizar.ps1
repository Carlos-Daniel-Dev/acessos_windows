#
#  atualizar.ps1 — aplica uma atualização do Acessos SEM reinstalar tudo.
#
#  Complementa o instalar.ps1 (que continua sendo o jeito de fazer a
#  instalação DE VERDADE, do zero — MSYS2, pacotes, primeira compilação do
#  vncshim). Este script assume que isso já rodou uma vez e só sincroniza
#  os arquivos que MUDARAM desde a última vez, usando manifesto.json como
#  fonte da verdade — sem MSYS2, sem pacman, sem recompilar nada que não
#  precise.
#
#  FLUXO
#     1. quem prepara a atualização edita python\, src\ ou icones\ e roda
#        .\gerar_manifesto.ps1 — isso regrava manifesto.json com o SHA-256
#        de cada arquivo rastreado.
#     2. a pasta inteira (com o manifesto.json novo) é distribuída pro
#        mesmo lugar de sempre (a mesma pasta sincronizada de onde o
#        instalar.ps1 já é rodado hoje).
#     3. cada máquina roda .\atualizar.ps1 — bem mais rápido que o
#        instalar.ps1 inteiro, porque só copia o que o hash acusa como
#        diferente, e só recompila o vncshim.dll se src\vncshim.c mudou.
#
#  USO:
#     .\atualizar.ps1                aplica as diferenças
#     .\atualizar.ps1 -SoDetectar    so mostra o que mudaria, nao aplica
#     .\atualizar.ps1 -Forcar        aplica mesmo com o Acessos rodando
#                                    (arquivos travados sao reportados,
#                                    nao derrubam o resto do patch)

[CmdletBinding()]
param(
    [switch]$SoDetectar,
    [switch]$Forcar
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
function Aviso($t) { Write-Host "AVISO: $t" -ForegroundColor Yellow }

# ---- mesma logica de descoberta do instalar.ps1, resumida: $Aqui e a
# pasta deste script (onde tambem estao python\, src\, icones\ e o
# manifesto.json novo); $Destino e onde o Acessos ja esta instalado.
$Aqui = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Aqui)) { $Aqui = (Get-Location).Path }

$ManifestoPath = Join-Path $Aqui "manifesto.json"
if (-not (Test-Path $ManifestoPath)) {
    Erro "manifesto.json não encontrado em $Aqui"
    Nota "rode .\gerar_manifesto.ps1 antes de distribuir a atualização"
    exit 1
}

$RaizLocal = $env:LOCALAPPDATA
if ([string]::IsNullOrWhiteSpace($RaizLocal)) {
    $RaizLocal = [Environment]::GetFolderPath("LocalApplicationData")
}
if ([string]::IsNullOrWhiteSpace($RaizLocal) -and
    -not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
    $RaizLocal = Join-Path $env:USERPROFILE "AppData\Local"
}
if ([string]::IsNullOrWhiteSpace($RaizLocal)) {
    Erro "não consegui determinar %LOCALAPPDATA% (mesmo problema do instalar.ps1)"
    exit 1
}
$Destino = Join-Path $RaizLocal "Acessos"

if (-not (Test-Path $Destino)) {
    Erro "$Destino não existe — o Acessos ainda não foi instalado aqui"
    Nota "rode .\instalar.ps1 primeiro (instalação completa, uma vez só)"
    exit 1
}

$Msys2Raiz = "C:\msys64"
$Msys2Bin  = Join-Path $Msys2Raiz "usr\bin\bash.exe"

$EstadoPath = Join-Path $Destino ".estado_patch.json"

Azul "Acessos — verificando atualizações"
Nota "pacote ........ $Aqui"
Nota "instalado em ... $Destino"
Write-Host ""

$manifesto = Get-Content -Path $ManifestoPath -Raw -Encoding UTF8 | ConvertFrom-Json
Nota "manifesto versão $($manifesto.versao) ($($manifesto.gerado_em))"

$estado = $null
if (Test-Path $EstadoPath) {
    try {
        $estado = Get-Content -Path $EstadoPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Aviso ".estado_patch.json corrompido — tratando como instalação sem histórico"
        $estado = $null
    }
}

function Sha256($caminho) {
    (Get-FileHash -Algorithm SHA256 -Path $caminho).Hash.ToLower()
}

# --------------------------------------------------- 1. detectar diferenças
$paraCopiar = @()
foreach ($prop in $manifesto.copiar.PSObject.Properties) {
    $relPosix = $prop.Name                      # ex.: "python/acessos.py"
    $info = $prop.Value
    $relWin = $relPosix -replace '/', '\'
    $origem = Join-Path $Aqui $relWin
    $nomeArquivo = Split-Path -Leaf $relWin
    $destinoArq = Join-Path $Destino $nomeArquivo

    if (-not (Test-Path $origem)) {
        Aviso "$relPosix está no manifesto mas não existe no pacote — pulado"
        continue
    }
    $hashOrigem = Sha256 $origem
    if ($hashOrigem -ne $info.sha256) {
        # o arquivo no pacote nao bate com o que o manifesto registrou —
        # o manifesto esta desatualizado (alguem editou depois de gerar
        # manifesto.json). Nao bloqueia: o hash de VERDADE do arquivo e
        # quem manda: comparamos o INSTALADO contra ele, nao contra o
        # manifesto.
        Aviso "$relPosix mudou depois do manifesto ser gerado — rode gerar_manifesto.ps1 de novo"
    }
    $hashInstalado = if (Test-Path $destinoArq) { Sha256 $destinoArq } else { $null }
    if ($hashInstalado -ne $hashOrigem) {
        $paraCopiar += [pscustomobject]@{
            relativo = $relPosix
            origem   = $origem
            destino  = $destinoArq
            novo     = [string]::IsNullOrEmpty($hashInstalado)
        }
    }
}

$precisaCompilar = $false
$vncshimInfo = $manifesto.compilar."src/vncshim.c"
if ($vncshimInfo) {
    $origemC = Join-Path $Aqui "src\vncshim.c"
    $dllDestino = Join-Path $Destino $vncshimInfo.saida
    if (-not (Test-Path $origemC)) {
        Aviso "src/vncshim.c está no manifesto mas não existe no pacote — pulado"
    } else {
        $hashCAtual = Sha256 $origemC
        $hashCInstalado = if ($estado) { $estado.vncshim_c_sha256 } else { $null }
        if (-not (Test-Path $dllDestino)) {
            $precisaCompilar = $true
            Nota "libvncshim.dll ausente em $Destino — será compilado"
        } elseif (-not $estado) {
            # primeira vez que o atualizar.ps1 roda nesta maquina: nao ha
            # historico de qual .c gerou o .dll instalado (so o instalar.ps1
            # rodou ate agora, e ele nao grava esse estado). Recompila uma
            # vez so para estabelecer a baseline; das proximas, so recompila
            # se src/vncshim.c realmente mudar.
            $precisaCompilar = $true
            Nota "primeira execução do atualizar.ps1 nesta máquina — recompilando o"
            Nota "vncshim.dll uma vez para estabelecer a referência (normal, só acontece agora)"
        } elseif ($hashCAtual -ne $hashCInstalado) {
            $precisaCompilar = $true
        }
    }
}

if ($paraCopiar.Count -eq 0 -and -not $precisaCompilar) {
    Ok "já está tudo atualizado — nenhuma diferença encontrada"
    exit 0
}

Write-Host ""
Azul "diferenças encontradas:"
foreach ($item in $paraCopiar) {
    $rotulo = if ($item.novo) { "novo" } else { "mudou" }
    Nota "  [$rotulo] $($item.relativo)"
}
if ($precisaCompilar) {
    Nota "  [compilar] src/vncshim.c -> $($vncshimInfo.saida)"
}
Write-Host ""

if ($SoDetectar) {
    Nota "-SoDetectar: nada foi aplicado"
    exit 0
}

# --------------------------------------------------- 2. checar Acessos aberto
# python.exe e generico demais pro nome do processo dizer alguma coisa —
# olhamos a LINHA DE COMANDO de cada processo python, procurando acessos.py.
$rodando = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'python3.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'acessos\.py' }

if ($rodando -and -not $Forcar) {
    Erro "o Acessos está rodando (PID $($rodando.ProcessId -join ', '))"
    Nota "feche pelo ícone da bandeja (botão direito > Sair do Acessos) e rode de novo"
    Nota "ou rode com -Forcar para tentar mesmo assim (arquivos travados falham"
    Nota "isoladamente; rode de novo depois de fechar para completar o patch)"
    exit 1
}
if ($rodando -and $Forcar) {
    Aviso "Acessos rodando (PID $($rodando.ProcessId -join ', ')) — continuando por causa de -Forcar"
    Aviso "os .py so valem depois de reiniciar o Acessos; o libvncshim.dll pode falhar"
    Aviso "por estar em uso (uma sessao VNC aberta trava o arquivo)"
}

# --------------------------------------------------- 3. backup (1 nivel, gira)
$PastaBackup = Join-Path $Destino ".backup_anterior"
if (($paraCopiar.Count -gt 0 -or $precisaCompilar) -and (Test-Path $PastaBackup)) {
    Remove-Item -Recurse -Force $PastaBackup -ErrorAction SilentlyContinue
}
if ($paraCopiar.Count -gt 0 -or $precisaCompilar) {
    New-Item -ItemType Directory -Force -Path $PastaBackup | Out-Null
}

# --------------------------------------------------- 4. aplicar copias
$falhas = @()
foreach ($item in $paraCopiar) {
    try {
        if (Test-Path $item.destino) {
            Copy-Item $item.destino (Join-Path $PastaBackup (Split-Path -Leaf $item.destino)) -Force
        }
        Copy-Item $item.origem $item.destino -Force
        Ok "  copiado: $($item.relativo)"
    } catch {
        $falhas += $item.relativo
        Aviso "  falhou (provavelmente em uso): $($item.relativo) — $($_.Exception.Message)"
    }
}

# --------------------------------------------------- 5. recompilar vncshim
$hashCUsado = if ($estado) { $estado.vncshim_c_sha256 } else { $null }
if ($precisaCompilar) {
    if (-not (Test-Path $Msys2Bin)) {
        Aviso "MSYS2 não encontrado em $Msys2Raiz — não dá para recompilar o vncshim.dll aqui"
        Aviso "rode .\instalar.ps1 nesta máquina para restaurar o toolchain"
    } else {
        Azul "compilando libvncshim.dll"
        $dllDestino = Join-Path $Destino $vncshimInfo.saida
        if (Test-Path $dllDestino) {
            Copy-Item $dllDestino (Join-Path $PastaBackup $vncshimInfo.saida) -Force -ErrorAction SilentlyContinue
        }
        $origemC = (Join-Path $Aqui "src\vncshim.c") -replace '\\', '/'
        $destinoDll = ($dllDestino) -replace '\\', '/'
        $comando = @"
export PATH=/mingw64/bin:`$PATH
gcc -shared -O2 -Wall -o '$destinoDll' '$origemC' \
    `$(pkg-config --cflags --libs libvncclient)
"@
        $guardaAnterior = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $env:MSYSTEM = "MINGW64"
            $env:CHERE_INVOKING = "1"
            & $Msys2Bin -lc $comando 2>&1 | ForEach-Object { Write-Host "       $_" }
            $codigo = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $guardaAnterior
        }
        if ($codigo -eq 0 -and (Test-Path $dllDestino)) {
            Ok "  libvncshim.dll recompilado"
            $hashCUsado = Sha256 (Join-Path $Aqui "src\vncshim.c")
        } else {
            $falhas += "src/vncshim.c (compilação)"
            Aviso "  falha ao compilar libvncshim.dll (código $codigo) — o .dll antigo continua no lugar"
        }
    }
}

# --------------------------------------------------- 6. gravar estado
$novoEstado = [ordered]@{
    versao             = $manifesto.versao
    aplicado_em        = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    vncshim_c_sha256   = $hashCUsado
}
$novoEstado | ConvertTo-Json | Set-Content -Path $EstadoPath -Encoding UTF8

Write-Host ""
if ($falhas.Count -gt 0) {
    Aviso "concluído com pendências (rode de novo depois de fechar o Acessos):"
    foreach ($f in $falhas) { Nota "  - $f" }
    exit 1
}

Ok "atualizado para a versão $($manifesto.versao)"
if ($rodando) {
    Nota "feche e abra o Acessos de novo para os arquivos novos valerem"
}
