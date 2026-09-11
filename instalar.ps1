#
#  instalar.ps1 — monta o Acessos por inteiro no Windows (10 1809+ / 11).
#
#  Espelha o instalar.sh do Linux, na mesma ordem de passos, trocando
#  pacman/dnf por MSYS2 (unico jeito pratico de ter, num so lugar: GTK3 +
#  PyGObject + gcc + libvncclient + FreeRDP, todos ja compilados p/ Windows).
#
#  Faz tudo numa passada:
#     1. garante o MSYS2 (instala via winget se faltar)
#     2. instala os pacotes MSYS2 (GTK3, PyGObject, gcc, libvncclient, FreeRDP)
#     3. instala os pacotes Python extras (paramiko, cryptography, argon2,
#        pyte) dentro do Python do MSYS2 — sem pywin32/pywinpty, que
#        não existem para o Python MinGW (ver conpty.py)
#     4. compila o vncshim.dll e o librdpshim.dll
#     5. instala em %LOCALAPPDATA%\Acessos e cria o atalho do menu iniciar
#
#  RDP: embutido via librdpshim.dll (linka libfreerdp/libwinpr direto —
#  ver RDPSHIM-interno.md, não publicado). FreeRDP dev (mingw-w64-x86_64-
#  freerdp) é essencial agora, igual libvncclient — sem ele o script para
#  (não há mais "-SemRdp" pra degradar com a aba desabilitada).
#
#  USO:
#     .\instalar.ps1                instala ou atualiza
#     .\instalar.ps1 -Verificar     so testa o que ja esta instalado
#     .\instalar.ps1 -Remover       desinstala (preserva a configuracao)
#     .\instalar.ps1 -Remover -LimparConfig
#                                   desinstala E apaga conexoes.ini, cofre,
#                                   historico/ e snippets — pede confirmacao
#                                   explicita antes (perda de dados real e
#                                   irreversivel, nao ha "historico/" que
#                                   salve depois disto)
#
#  Sem WSL, sem container, sem Store. Instala no perfil do usuario, sem
#  precisar de admin — a UNICA parte que pode pedir elevacao e o instalador
#  do MSYS2 em si, na primeira vez.

[CmdletBinding()]
param(
    [switch]$Verificar,
    [switch]$Remover,
    [switch]$LimparConfig
)

$ErrorActionPreference = "Stop"

# O bash do MSYS2 emite texto em UTF-8. Sem isto o console le com a
# codepage ANSI do sistema e os acentos saem corrompidos ("atenÃ§Ã£o").
# Envolvido em try porque nem todo host aceita a troca (o ISE, por
# exemplo, ignora em algumas versoes) — e nao vale abortar por isso.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

$Aqui = $PSScriptRoot

# ATENCAO: nao passar valor possivelmente nulo para Split-Path.
# A validacao de parametro acontece ANTES do cmdlet executar, entao
# -ErrorAction SilentlyContinue NAO captura esse caso — o erro
# "Não é possível associar o argumento ao parâmetro 'Path'" escapa e
# aborta o script. Por isso cada origem e testada antes de ser usada.
if ([string]::IsNullOrWhiteSpace($Aqui)) {
    $caminhoInvocado = $MyInvocation.MyCommand.Path
    if (-not [string]::IsNullOrWhiteSpace($caminhoInvocado)) {
        $Aqui = Split-Path -Parent $caminhoInvocado
    }
}

# PowerShell ISE: $PSScriptRoot fica vazio ao rodar por F8 (seleção) ou
# com arquivo nunca salvo. O ISE expoe o arquivo atual por outro caminho.
if ([string]::IsNullOrWhiteSpace($Aqui) -and $psISE) {
    $arquivoIse = $psISE.CurrentFile.FullPath
    if (-not [string]::IsNullOrWhiteSpace($arquivoIse)) {
        $Aqui = Split-Path -Parent $arquivoIse
    }
}

# Ultimo recurso: o local onde o pacote costuma ser extraido. Vale so se a
# arvore esperada (python\ e src\) estiver realmente la.
if ([string]::IsNullOrWhiteSpace($Aqui)) {
    foreach ($tentativa in @("C:\acessos_windows", (Get-Location).Path)) {
        if (-not [string]::IsNullOrWhiteSpace($tentativa) -and
            (Test-Path (Join-Path $tentativa "src\vncshim.c"))) {
            $Aqui = $tentativa
            Write-Host "       usando $Aqui (detectado por fallback)" -ForegroundColor Gray
            break
        }
    }
}

if ([string]::IsNullOrWhiteSpace($Aqui)) {
    Write-Host "ERRO: não consegui descobrir a pasta deste script." -ForegroundColor Red
    Write-Host "       No PowerShell ISE, salve o arquivo e rode com F5 (não F8)." -ForegroundColor Gray
    Write-Host "       Ou defina o caminho na mão antes de rodar:" -ForegroundColor Gray
    Write-Host '         $Aqui = "C:\acessos_windows"' -ForegroundColor Gray
    exit 1
}

# Confere logo que a arvore esperada esta ali — erra cedo e com mensagem
# clara, em vez de falhar la no meio da compilacao do vncshim.
if (-not (Test-Path (Join-Path $Aqui "src\vncshim.c"))) {
    Write-Host "ERRO: não encontrei src\vncshim.c em $Aqui" -ForegroundColor Red
    Write-Host "       O instalar.ps1 precisa estar na RAIZ do pacote, junto" -ForegroundColor Gray
    Write-Host "       das pastas python\, src\ e icones\." -ForegroundColor Gray
    exit 1
}
$Msys2Raiz = "C:\msys64"
$Msys2Bin  = Join-Path $Msys2Raiz "usr\bin\bash.exe"
$Mingw64   = Join-Path $Msys2Raiz "mingw64"
$PyMsys    = Join-Path $Mingw64 "bin\python3.exe"

# LOCALAPPDATA e a pasta do Menu Iniciar podem vir VAZIAS quando o perfil
# esta redirecionado, quando o script roda numa sessao sem perfil carregado
# (tarefa agendada, PsExec, alguns terminais embutidos) ou sob politica de
# grupo restritiva. Join-Path com $null aborta com
# "Não é possível associar o argumento ao parâmetro 'Path'", entao cada uma
# ganha um fallback antes de ser usada.
$RaizLocal = $env:LOCALAPPDATA
if ([string]::IsNullOrWhiteSpace($RaizLocal)) {
    $RaizLocal = [Environment]::GetFolderPath("LocalApplicationData")
}
if ([string]::IsNullOrWhiteSpace($RaizLocal) -and
    -not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
    $RaizLocal = Join-Path $env:USERPROFILE "AppData\Local"
}
if ([string]::IsNullOrWhiteSpace($RaizLocal)) {
    Write-Host "ERRO: não consegui determinar a pasta de instalação." -ForegroundColor Red
    Write-Host "       LOCALAPPDATA e USERPROFILE estão ambos vazios — isso" -ForegroundColor Gray
    Write-Host "       acontece em sessões sem perfil de usuário carregado." -ForegroundColor Gray
    Write-Host "       Rode numa janela normal do PowerShell, como o seu usuário." -ForegroundColor Gray
    exit 1
}
$Destino = Join-Path $RaizLocal "Acessos"

$RaizMenu = [Environment]::GetFolderPath("StartMenu")
if ([string]::IsNullOrWhiteSpace($RaizMenu) -and
    -not [string]::IsNullOrWhiteSpace($env:APPDATA)) {
    $RaizMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu"
}
# sem Menu Iniciar acessivel o atalho e simplesmente pulado: e conveniencia,
# nao requisito — o acessos.cmd continua funcionando
$MenuAtalho = $null
if (-not [string]::IsNullOrWhiteSpace($RaizMenu)) {
    $MenuAtalho = Join-Path $RaizMenu "Programs\Acessos.lnk"
}

if ($PSBoundParameters.ContainsKey("Verbose") -or $VerbosePreference -ne "SilentlyContinue") {
    Write-Host "  script em ..... $Aqui" -ForegroundColor DarkGray
    Write-Host "  instalar em ... $Destino" -ForegroundColor DarkGray
    Write-Host "  atalho ........ $(if ($MenuAtalho) { $MenuAtalho } else { '(pulado)' })" -ForegroundColor DarkGray
}

function Azul($t) { Write-Host $t -ForegroundColor Cyan }
function Ok($t)   { Write-Host $t -ForegroundColor Green }
function Nota($t) { Write-Host "       $t" -ForegroundColor Gray }
function Erro($t) { Write-Host "ERRO: $t" -ForegroundColor Red }

# --------------------------------------------------------------- remover
#
# A pasta de configuracao (conexoes.ini, cofre, historico/, snippets.ini)
# fica FORA de $Destino de proposito — e' dado do usuario, nao parte do
# programa, e o padrao de -Remover sempre foi preserva-la. -LimparConfig
# e' o oposto explicito disso: so apaga com confirmacao digitada, porque
# nao ha como desfazer (nem o historico/, que existe justamente pra
# recuperar erros de edicao, sobrevive a isto).
#
# Mesma conta que _dir_padrao()/_ler_caminho_geral() fazem em acessos.py:
# XDG_CONFIG_HOME (ou ~/.config) + "acessos" e' o lugar padrao, que pode
# conter uma chave [geral] caminho= apontando a pasta de dados de verdade
# (recurso de "pasta de dados relocavel") — se houver, as DUAS pastas
# precisam ser apagadas, senao "limpar" deixa a metade dos dados para tras.
function Obter-PastaConfigPadrao {
    $base = $env:XDG_CONFIG_HOME
    if ([string]::IsNullOrWhiteSpace($base)) {
        $base = Join-Path $env:USERPROFILE ".config"
    }
    return Join-Path $base "acessos"
}

function Obter-PastaRelocada([string]$iniPadrao) {
    # leitura crua do "[geral]\ncaminho = ..." — mesmo dado que
    # _ler_caminho_geral() le em acessos.py, sem depender de nenhum parser
    if (-not (Test-Path $iniPadrao)) { return $null }
    $dentroDeGeral = $false
    foreach ($linha in Get-Content -Path $iniPadrao -Encoding UTF8) {
        $l = $linha.Trim()
        if ($l -match '^\[(.+)\]$') {
            $dentroDeGeral = ($Matches[1].Trim().ToLower() -eq "geral")
            continue
        }
        if ($dentroDeGeral -and $l -match '^caminho\s*=\s*(.+)$') {
            $valor = $Matches[1].Trim()
            if ($valor) { return [System.Environment]::ExpandEnvironmentVariables($valor) }
        }
    }
    return $null
}

function Remover-Tudo {
    Azul "Removendo"
    if (Test-Path $Destino) { Remove-Item -Recurse -Force $Destino }
    if ($MenuAtalho -and (Test-Path $MenuAtalho)) { Remove-Item -Force $MenuAtalho }

    $pastaConfig = Obter-PastaConfigPadrao
    if (-not $LimparConfig) {
        Ok "removido. A configuração em $pastaConfig foi preservada."
        Nota "Use -Remover -LimparConfig para apagar também conexões, cofre e histórico."
        return
    }

    $iniPadrao = Join-Path $pastaConfig "conexoes.ini"
    $pastaRelocada = Obter-PastaRelocada $iniPadrao
    $alvos = [System.Collections.Generic.List[string]]::new()
    $alvos.Add($pastaConfig)
    if ($pastaRelocada -and (Test-Path $pastaRelocada) -and
        ((Resolve-Path $pastaRelocada).Path -ne (Resolve-Path $pastaConfig -ErrorAction SilentlyContinue).Path)) {
        $alvos.Add($pastaRelocada)
    }
    $existentes = @($alvos | Where-Object { Test-Path $_ })

    if (-not $existentes) {
        Ok "removido. Nenhuma pasta de configuração encontrada para apagar."
        return
    }

    Write-Host ""
    Write-Host "ATENÇÃO — isto apaga PERMANENTEMENTE, sem volta:" -ForegroundColor Yellow
    foreach ($p in $existentes) {
        Write-Host "  $p" -ForegroundColor Yellow
    }
    Write-Host "  - conexoes.ini: TODAS as máquinas cadastradas e seus ajustes" -ForegroundColor Yellow
    Write-Host "  - cofre: a senha mestra e qualquer credencial guardada nele" -ForegroundColor Yellow
    Write-Host "  - historico/: os backups automáticos (não salva desta vez)" -ForegroundColor Yellow
    Write-Host "  - snippets.ini: os comandos salvos da execução em lote" -ForegroundColor Yellow
    Write-Host ""
    $resposta = Read-Host "Digite APAGAR (tudo maiúsculo) para confirmar, ou qualquer outra coisa para cancelar"
    if ($resposta -ne "APAGAR") {
        Nota "Cancelado — a configuração NÃO foi apagada."
        return
    }

    foreach ($p in $existentes) {
        Remove-Item -Recurse -Force $p -Confirm:$false
    }
    Ok "removido, incluindo a configuração ($($existentes.Count) pasta(s))."
}

# ------------------------------------------------------------ verificar
function Verificar-Tudo {
    Azul "Verificação"
    $falhas = 0

    if (Test-Path (Join-Path $Destino "libvncshim.dll")) {
        Ok "  vncshim ....... instalado"
    } else {
        Erro "  vncshim não encontrado em $Destino"
        $falhas++
    }

    if (Test-Path (Join-Path $Destino "librdpshim.dll")) {
        Ok "  rdpshim ........ instalado"
    } else {
        Erro "  rdpshim não encontrado em $Destino"
        $falhas++
    }

    $sshExe = Get-Command "ssh.exe" -ErrorAction SilentlyContinue
    if ($sshExe) {
        Ok "  Cliente OpenSSH  instalado ($($sshExe.Source))"
    } else {
        Erro "  ssh.exe não encontrado — ative em Configurações > Aplicativos > Recursos opcionais > Cliente OpenSSH"
        $falhas++
    }

    if (-not (Test-Path $PyMsys)) {
        Erro "  Python do MSYS2 não encontrado em $PyMsys"
        $falhas++
    } else {
        $script = @"
import sys
sys.path.insert(0, r'$Destino')
falhou = []
try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    print('  GTK3 ........... ok')
except Exception as e:
    falhou.append('GTK3: %s' % e)

for mod in ('paramiko', 'cryptography', 'pyte'):
    try:
        __import__(mod)
    except Exception as e:
        falhou.append('%s: %s' % (mod, e))

# os dois modulos em ctypes que substituem pywin32 e pywinpty
try:
    import rdpwidget
    print('  rdpwidget ...... ok')
except Exception as e:
    falhou.append('rdpwidget: %s' % e)
try:
    import conpty
    if conpty.TEM_CONPTY:
        print('  ConPTY ......... ok')
    else:
        falhou.append('ConPTY: %s' % conpty.ERRO_CONPTY)
except Exception as e:
    falhou.append('conpty: %s' % e)

# esconde o console/mostra o icone de bandeja depois do login — cosmetico,
# nao interrompe a verificacao se faltar (mensagem some no relatorio, so)
try:
    import bandeja_windows
    print('  bandeja ........ %s' % ('ok' if bandeja_windows.disponivel()
                                     else 'indisponível'))
except Exception as e:
    falhou.append('bandeja_windows: %s' % e)

if falhou:
    print('\n  problemas:')
    for f in falhou:
        print('   - %s' % f)
    sys.exit(1)
print('  Python deps .... ok')
"@
        $script | & $PyMsys - 2>&1 | ForEach-Object { Write-Host $_ }
        if ($LASTEXITCODE -ne 0) { $falhas++ }
    }
    return $falhas -eq 0
}

# --------------------------------------------------------- passo 1: msys2
function Garantir-Msys2 {
    Azul "[1/5] MSYS2 (GTK3 + toolchain)"
    if (Test-Path $Msys2Bin) {
        Nota "já instalado em $Msys2Raiz"
        return
    }
    Nota "instalando via winget (pode pedir elevação uma vez)"
    # mesmo cuidado do Msys2-Exec: o winget escreve progresso/avisos no
    # stderr, que com ErrorActionPreference=Stop viraria erro terminante
    $guardaAnterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        winget install --id MSYS2.MSYS2 -e --accept-source-agreements --accept-package-agreements 2>&1 |
            ForEach-Object { Write-Host "       $_" }
    } finally {
        $ErrorActionPreference = $guardaAnterior
    }
    if (-not (Test-Path $Msys2Bin)) {
        Erro "instalação do MSYS2 não apareceu em $Msys2Raiz — instale manualmente em https://www.msys2.org e rode de novo."
        exit 1
    }
    Atualizar-BaseMsys2
}

function Atualizar-BaseMsys2 {
    # O pacman -Syu do MSYS2 precisa rodar DUAS vezes, e isso e
    # documentado: a primeira passada atualiza o proprio runtime (msys2
    # -runtime, pacman) e encerra o shell pedindo para fechar os
    # programas MSYS2 — e daquele aviso no stderr que vem o
    # "terminate other MSYS2 programs before proceeding". Somente a
    # segunda passada, num shell novo, termina de atualizar o resto.
    Nota "atualizando a base do MSYS2 (passo 1 de 2)"
    Msys2-Exec "pacman -Syu --noconfirm"
    Nota "atualizando a base do MSYS2 (passo 2 de 2)"
    Msys2-Exec "pacman -Syu --noconfirm"
}

function Msys2-Exec($comando) {
    # O bash escreve AVISOS no stderr (ex.: "terminate other MSYS2
    # programs before proceeding"). Com $ErrorActionPreference = "Stop"
    # o PowerShell converte qualquer stderr de programa nativo em erro
    # TERMINANTE (NativeCommandError) — abortando o script por um aviso
    # inofensivo. Quem decide se deu certo e o CODIGO DE SAIDA, entao
    # baixamos a guarda so em volta da chamada nativa.
    $guardaAnterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # MSYSTEM=MINGW64 e OBRIGATORIO: sem ele o "bash -lc" entra no
        # shell MSYS puro, onde /mingw64/bin NAO esta no PATH — e ai
        # python3, gcc e pkg-config simplesmente "nao existem"
        # ("python3: command not found"), mesmo instalados.
        $env:MSYSTEM = "MINGW64"
        $env:CHERE_INVOKING = "1"
        & $Msys2Bin -lc $comando 2>&1 | ForEach-Object { Write-Host "       $_" }
        $codigo = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $guardaAnterior
    }
    if ($codigo -ne 0) {
        throw "comando MSYS2 falhou (código $codigo): $comando"
    }
}

# --------------------------------------------------- passo 2: pacotes msys2
function Instalar-PacotesMsys2 {
    Azul "[2/5] pacotes do MSYS2 (GTK3, PyGObject, gcc, libvncclient, FreeRDP)"
    # Um a um, e nao numa lista unica: o pacman aborta a transacao inteira
    # quando UM alvo nao existe (foi o que aconteceu com o argon2-cffi), e
    # ai nem os pacotes disponiveis entram.
    $essenciais = @(
        "mingw-w64-x86_64-gcc",
        "mingw-w64-x86_64-pkgconf",
        "mingw-w64-x86_64-gtk3",
        "mingw-w64-x86_64-python",
        "mingw-w64-x86_64-python-gobject",
        "mingw-w64-x86_64-python-cairo",
        "mingw-w64-x86_64-python-pip",
        "mingw-w64-x86_64-libvncserver",
        # ESSENCIAL agora, nao mais opcional: o RDP embutido linka
        # libfreerdp/libwinpr direto via librdpshim.dll (ver
        # RDPSHIM-interno.md, nao publicado) — sem os headers/libs de
        # dev do FreeRDP, rdpshim.c nem compila, igual libvncclient
        # pro VNC.
        "mingw-w64-x86_64-freerdp"
    )
    foreach ($p in $essenciais) {
        if (-not (Msys2-Tentar "pacman -S --needed --noconfirm $p")) {
            throw "não consegui instalar $p — é essencial (GTK3/compilador/libvncclient/FreeRDP)"
        }
    }
}

# Roda um comando MSYS2 sem abortar o script: devolve $true/$false.
# Usado onde a ausencia de um pacote NAO e fatal.
function Msys2-Tentar($comando) {
    $guardaAnterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # MSYSTEM=MINGW64 e OBRIGATORIO: sem ele o "bash -lc" entra no
        # shell MSYS puro, onde /mingw64/bin NAO esta no PATH — e ai
        # python3, gcc e pkg-config simplesmente "nao existem"
        # ("python3: command not found"), mesmo instalados.
        $env:MSYSTEM = "MINGW64"
        $env:CHERE_INVOKING = "1"
        & $Msys2Bin -lc $comando 2>&1 | ForEach-Object { Write-Host "       $_" }
        $codigo = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $guardaAnterior
    }
    return ($codigo -eq 0)
}

# Instala um pacote Python tentando, em ordem: pacote do pacman, pip
# normal, pip --break-system-packages e pip --user.
#
# POR QUE A CADEIA: desde a PEP 668 o Python do MSYS2 vem marcado como
# "externally managed", e o pip RECUSA instalar nele sem uma dessas
# saidas ("error: externally-managed-environment"). O instalar.sh do
# Linux passa pelo mesmo aperto e resolve com --user; aqui tentamos
# primeiro o pacote nativo (melhor de todos) e vamos descendo.
#
# --break-system-packages vem antes de --user de proposito: instalar em
# --user coloca o modulo em ~/.local, que o lancador precisaria enxergar
# por PYTHONPATH. Funciona, mas e mais uma peca para dar errado, entao
# fica como ultimo recurso.
function Instalar-Pip($nomePacote, $nomeModulo, $pacotePacman) {
    $pyMsysPosix = $PyMsys -replace '\\', '/'

    if ($pacotePacman) {
        if (Msys2-Tentar "pacman -S --needed --noconfirm $pacotePacman") {
            if (Msys2-Tentar "$pyMsysPosix -c 'import $nomeModulo'") {
                Nota "$nomeModulo — instalado pelo pacman"
                return $true
            }
        }
    }

    $tentativas = @(
        "-m pip install --upgrade $nomePacote",
        "-m pip install --upgrade --break-system-packages $nomePacote",
        "-m pip install --upgrade --user --break-system-packages $nomePacote",
        "-m pip install --upgrade --user $nomePacote"
    )
    foreach ($t in $tentativas) {
        if (Msys2-Tentar "$pyMsysPosix $t") {
            if (Msys2-Tentar "$pyMsysPosix -c 'import $nomeModulo'") {
                Nota "$nomeModulo — instalado por pip"
                return $true
            }
        }
    }
    return $false
}

# --------------------------------------------------- passo 3: pip extras
function Instalar-PacotesPython {
    Azul "[3/5] pacotes Python"

    # POR QUE VIA PACMAN, E NAO PIP:
    # paramiko e cryptography contem codigo nativo. Instalar pelo pip
    # obrigaria a compilar do fonte dentro do MSYS2 (cryptography ainda
    # puxa Rust), o que e lento e quebra facil. O MSYS2 ja publica os dois
    # compilados para o MinGW.
    #
    # NAO esta aqui, de proposito: pywinpty. O wheel dele e para o CPython
    # oficial (ABI MSVC) e NAO instala neste Python (MinGW) — era a causa
    # do "pip falhou (código 1)". A funcao de que precisavamos dele esta
    # reimplementada em ctypes puro: python\conpty.py (CreatePseudoConsole).
    # pywin32 nunca foi necessario aqui — nem win_embed.py (removido, RDP
    # nao reparenta janela mais) nem rdpshim.c (C, nao Python) precisam dele.
    #
    # Instalados UM A UM, e nao numa lista: o pacman aborta a transacao
    # inteira quando UM alvo nao existe, entao um pacote ausente levaria
    # embora os que estavam disponiveis.
    $obrigatorios = @(
        "mingw-w64-x86_64-python-paramiko",
        "mingw-w64-x86_64-python-cryptography"
    )
    foreach ($p in $obrigatorios) {
        if (-not (Msys2-Tentar "pacman -S --needed --noconfirm $p")) {
            throw "não consegui instalar $p — sem ele o Acessos não conecta (paramiko: SFTP; cryptography: cofre de senhas)"
        }
    }

    # pyte e Python puro e NAO existe no MSYS2 (verificado: "pacman -Ss
    # python-pyte" so devolve pytest, que e outro pacote). Portanto so o
    # caminho do pip resta — e e por isso que a cadeia com
    # --break-system-packages importa: desde a PEP 668 o Python do MSYS2
    # vem marcado como "externally managed" e o pip recusa sem ela.
    if (-not (Instalar-Pip "pyte" "pyte" $null)) {
        throw "não consegui instalar o pyte — sem ele a aba de SSH não desenha o terminal"
    }

    # ARGON2 E OPCIONAL, igual no instalar.sh do Linux: sem ele o
    # cofre.py cai em PBKDF2 e segue funcionando. O MSYS2 nao empacota
    # argon2-cffi, entao so o caminho do pip resta — e ele precisa do
    # cffi, que vem do pacman.
    Nota "argon2 (opcional — reforça a derivação da senha mestra do cofre)"
    Msys2-Tentar "pacman -S --needed --noconfirm mingw-w64-x86_64-python-cffi" | Out-Null
    if (Instalar-Pip "argon2-cffi" "argon2" $null) {
        Nota "argon2 instalado"
    } else {
        Nota "argon2 indisponível — o cofre usará PBKDF2 e segue funcionando"
        Nota "ATENÇÃO: um cofre criado com Argon2id em outra máquina NÃO abrirá aqui"
    }
}

# ---------------------------------------------------- passo 4: vncshim
function Compilar-Vncshim {
    Azul "[4/5] compilando o vncshim.dll"
    New-Item -ItemType Directory -Force -Path $Destino | Out-Null
    # caminhos convertidos pra barra normal: dentro do bash do MSYS2, uma
    # barra invertida solta e escape de caractere e comeria pedacos do
    # caminho (ex.: "\A" vira so "A"). Sem implib de proposito: o carregamento
    # e via ctypes.WinDLL (dlopen), nao link-time, entao nao precisa de .dll.a
    $origemC = (Join-Path $Aqui "src\vncshim.c") -replace '\\', '/'
    $destinoDll = (Join-Path $Destino "libvncshim.dll") -replace '\\', '/'
    Msys2-Exec @"
export PATH=/mingw64/bin:`$PATH
gcc -shared -O2 -Wall -o '$destinoDll' '$origemC' \
    `$(pkg-config --cflags --libs libvncclient)
"@
    if (Test-Path (Join-Path $Destino "libvncshim.dll")) {
        $tam = (Get-Item (Join-Path $Destino "libvncshim.dll")).Length
        Nota "libvncshim.dll — $tam bytes"
    } else {
        throw "compilação do vncshim.dll não gerou o arquivo esperado"
    }
}

# mesma receita, pro RDP embutido (ver RDPSHIM-interno.md, não publicado).
# __STDC_NO_THREADS__ contorna um <threads.h> ausente neste MSYS2 (achado
# testando — sem isto a compilação falha com "threads.h: No such file").
function Compilar-Rdpshim {
    Azul "[4b/5] compilando o librdpshim.dll"
    New-Item -ItemType Directory -Force -Path $Destino | Out-Null
    $origemC = (Join-Path $Aqui "src\rdpshim.c") -replace '\\', '/'
    $destinoDll = (Join-Path $Destino "librdpshim.dll") -replace '\\', '/'
    Msys2-Exec @"
export PATH=/mingw64/bin:`$PATH
gcc -shared -O2 -Wall -D__STDC_NO_THREADS__ -o '$destinoDll' '$origemC' \
    `$(pkg-config --cflags --libs freerdp-client3 freerdp3 winpr3) -lws2_32
"@
    if (Test-Path (Join-Path $Destino "librdpshim.dll")) {
        $tam = (Get-Item (Join-Path $Destino "librdpshim.dll")).Length
        Nota "librdpshim.dll — $tam bytes"
    } else {
        throw "compilação do librdpshim.dll não gerou o arquivo esperado"
    }
}

# ---------------------------------------------------- passo 5: aplicacao
function Instalar-Aplicacao {
    Azul "[5/5] instalando o Acessos em $Destino"
    New-Item -ItemType Directory -Force -Path $Destino | Out-Null

    $modulos = @("acessos.py", "vncwidget.py", "sftp.py", "cofre.py", "tema.py",
                 "rdp_shim.py", "rdpwidget.py", "ssh_windows.py",
                 "conpty.py", "bandeja_windows.py", "atualizador.py",
                 "dialogo_ui.py", "massa.py", "massa_ui.py",
                 "importar_rdm.py")
    foreach ($m in $modulos) {
        $origem = Join-Path $Aqui "python\$m"
        if (Test-Path $origem) {
            Copy-Item $origem (Join-Path $Destino $m) -Force
        } else {
            Nota "aviso: $m não encontrado em python\ — pulado"
        }
    }
    # massa.py / massa_ui.py: propositalmente NÃO portados (ver LEIAME)

    Copy-Item (Join-Path $Aqui "icones\acessos.svg") $Destino -Force -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $Aqui "icones\acessos.ico") $Destino -Force -ErrorAction SilentlyContinue

    # LANCADOR: junta o interpretador do MSYS2 (unico que enxerga GTK3 e
    # PyGObject) com os modulos do Acessos. Equivalente ao script em
    # ~/.local/bin/acessos do Linux.
    $lancador = @"
@echo off
set PYTHONPATH=$Destino;%PYTHONPATH%
set PATH=$Mingw64\bin;%PATH%
"$PyMsys" "$Destino\acessos.py" %*
"@
    Set-Content -Path (Join-Path $Destino "acessos.cmd") -Value $lancador -Encoding ASCII

    # atalho do menu iniciar — conveniencia, nao requisito: se a pasta do
    # Menu Iniciar nao estiver acessivel, apenas avisa e segue
    if (-not $MenuAtalho) {
        Nota "pasta do Menu Iniciar indisponível — atalho pulado"
    } else {
        try {
            $pastaMenu = Split-Path -Parent $MenuAtalho
            if (-not (Test-Path $pastaMenu)) {
                New-Item -ItemType Directory -Force -Path $pastaMenu | Out-Null
            }
            $wsh = New-Object -ComObject WScript.Shell
            $atalho = $wsh.CreateShortcut($MenuAtalho)
            $atalho.TargetPath = Join-Path $Destino "acessos.cmd"
            $atalho.WorkingDirectory = $Destino
            $icone = Join-Path $Destino "acessos.ico"
            if (Test-Path $icone) {
                # ",0" seleciona o primeiro icone do arquivo — .ico so tem
                # um, mas o formato IconLocation e sempre "caminho,indice"
                $atalho.IconLocation = "$icone,0"
            }
            # sem acessos.ico (build antigo, ou gerar_ico.py nao rodou):
            # cai no icone padrao do .cmd — nao bloqueia o uso
            $atalho.Save()
        } catch {
            Nota "não consegui criar o atalho ($($_.Exception.Message))"
            Nota "rode direto por $Destino\acessos.cmd"
        }
    }
}

# --------------------------------------------------------------- main
if ($Remover) { Remover-Tudo; exit 0 }
if ($Verificar) {
    if (Verificar-Tudo) { Ok "`ntudo certo"; exit 0 } else { exit 1 }
}

Azul "Acessos — instalação (Windows)"
Write-Host ""

Garantir-Msys2
Instalar-PacotesMsys2
Instalar-PacotesPython
Compilar-Vncshim
Compilar-Rdpshim
Instalar-Aplicacao

# BASELINE PARA O ATUALIZAR.PS1: sem isto, a primeira vez que alguem rodar
# atualizar.ps1 nesta maquina nao teria como saber se o vncshim.dll que
# acabou de ser compilado aqui corresponde ao src\vncshim.c atual — e
# recompilaria a toa, so para descobrir que nao havia mudanca nenhuma.
# Gravar aqui deixa esse primeiro patch mais rapido. Cosmetico: falha aqui
# nao compromete a instalacao, so faz o atualizar.ps1 recompilar 1x a mais.
try {
    $manifestoLocal = Join-Path $Aqui "manifesto.json"
    $versaoManifesto = "desconhecida"
    if (Test-Path $manifestoLocal) {
        $versaoManifesto = (Get-Content -Path $manifestoLocal -Raw -Encoding UTF8 |
                            ConvertFrom-Json).versao
    }
    $hashVncshimC = (Get-FileHash -Algorithm SHA256 `
                     -Path (Join-Path $Aqui "src\vncshim.c")).Hash.ToLower()
    [ordered]@{
        versao           = $versaoManifesto
        aplicado_em      = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        vncshim_c_sha256 = $hashVncshimC
    } | ConvertTo-Json | Set-Content -Path (Join-Path $Destino ".estado_patch.json") -Encoding UTF8
} catch {
    Nota "não consegui gravar .estado_patch.json (cosmético, sem impacto na instalação)"
}

Write-Host ""
Verificar-Tudo | Out-Null
Write-Host ""
Ok "pronto."
Write-Host ""
Nota "Rodar: pelo menu Iniciar > Acessos, ou $Destino\acessos.cmd"
Write-Host ""
Nota "RDP embutido via librdpshim.dll (linka libfreerdp/libwinpr direto,"
Nota "sem processo externo — ver RDPSHIM-interno.md, não publicado)."
Nota "SSH usa o ssh.exe nativo do Windows, hospedado via ConPTY."
