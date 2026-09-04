#
#  gerar_manifesto.ps1 — ferramenta de RELEASE, não de instalação.
#
#  Quem prepara uma atualização do Acessos roda este script depois de editar
#  os arquivos em python\, src\ ou icones\. Ele recalcula o SHA-256 de cada
#  arquivo rastreado e regrava manifesto.json — é esse arquivo que o
#  atualizar.ps1 (rodado pela equipe) usa para saber o que mudou.
#
#  USO:
#     .\gerar_manifesto.ps1                usa a data de hoje como versão
#     .\gerar_manifesto.ps1 -Versao 2026.09.10.1
#
#  MANTER EM SINCRONIA com $modulos em instalar.ps1 (função
#  Instalar-Aplicacao) — um arquivo esquecido aqui nunca chega a quem
#  rodar atualizar.ps1, mesmo depois de editado.

[CmdletBinding()]
param(
    [string]$Versao
)

$ErrorActionPreference = "Stop"
$Aqui = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Aqui)) { $Aqui = (Get-Location).Path }

if (-not $Versao) {
    $Versao = Get-Date -Format "yyyy.MM.dd.HHmm"
}

# arquivos copiados como estao (sem compilar) — caminho relativo a $Aqui,
# sempre com barra normal (portavel, e assim que o atualizar.ps1 espera)
$ArquivosCopiar = @(
    "python\acessos.py",
    "python\vncwidget.py",
    "python\sftp.py",
    "python\cofre.py",
    "python\tema.py",
    "python\rdp_windows.py",
    "python\ssh_windows.py",
    "python\win_embed.py",
    "python\conpty.py",
    "python\bandeja_windows.py",
    "icones\acessos.svg"
)

# arquivos que precisam de um passo extra (compilação) em vez de so copiar
$ArquivosCompilar = @(
    @{ origem = "src\vncshim.c"; saida = "libvncshim.dll" }
)

function Sha256($caminho) {
    (Get-FileHash -Algorithm SHA256 -Path $caminho).Hash.ToLower()
}

$copiar = [ordered]@{}
foreach ($rel in $ArquivosCopiar) {
    $caminho = Join-Path $Aqui $rel
    if (-not (Test-Path $caminho)) {
        Write-Host "AVISO: $rel não encontrado — pulado no manifesto" -ForegroundColor Yellow
        continue
    }
    $item = Get-Item $caminho
    $copiar[$rel -replace '\\', '/'] = [ordered]@{
        sha256 = Sha256 $caminho
        bytes  = $item.Length
    }
}

$compilar = [ordered]@{}
foreach ($entrada in $ArquivosCompilar) {
    $caminho = Join-Path $Aqui $entrada.origem
    if (-not (Test-Path $caminho)) {
        Write-Host "AVISO: $($entrada.origem) não encontrado — pulado no manifesto" -ForegroundColor Yellow
        continue
    }
    $item = Get-Item $caminho
    $compilar[$entrada.origem -replace '\\', '/'] = [ordered]@{
        sha256 = Sha256 $caminho
        bytes  = $item.Length
        saida  = $entrada.saida
    }
}

$manifesto = [ordered]@{
    versao    = $Versao
    gerado_em = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    copiar    = $copiar
    compilar  = $compilar
}

$destino = Join-Path $Aqui "manifesto.json"
$manifesto | ConvertTo-Json -Depth 6 | Set-Content -Path $destino -Encoding UTF8

Write-Host "manifesto.json gerado — versão $Versao" -ForegroundColor Green
Write-Host "  $($copiar.Count) arquivo(s) de cópia, $($compilar.Count) de compilação" -ForegroundColor DarkGray
