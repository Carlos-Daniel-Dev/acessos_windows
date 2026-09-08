# Acessos — porte para Windows

Este pacote é um **complemento** ao repositório Linux original, não uma
reescrita. `instalar.ps1` espera encontrar, ao lado dele, a mesma árvore
`python/`, `src/`, `icones/` do projeto — os arquivos abaixo já estão
copiados aqui, os inalterados junto dos novos/patchados.

## O que tem aqui

| Arquivo | Situação |
|---|---|
| `instalar.ps1` | **novo** — equivalente ao `instalar.sh`, via MSYS2 |
| `gerar_manifesto.ps1` | **novo** — ferramenta de release: gera `manifesto.json` |
| `manifesto.json` | **novo** — hashes SHA-256 dos arquivos rastreados, para o patcher |
| `atualizar.ps1` | **novo** — aplica atualizações incrementais, sem reinstalar tudo |
| `compilar_exe.ps1` | **novo** — empacota `acessos.py` num `.exe` standalone (PyInstaller/MSYS2) |
| `instalador.iss` | **novo** — instalador único (Inno Setup): extrai o `.exe` pronto, cria atalhos no Menu Iniciar e na Área de Trabalho |
| `publicar.ps1` | **novo** — encadeia manifesto + `compilar_exe.ps1` + `instalador.iss` num comando só |
| `resolver_dlls.sh` | **novo** — resolve o fechamento de dependências nativas do FreeRDP (usado por `compilar_exe.ps1`) |
| `python/launcher.py` | **novo** — ponto de entrada do `.exe` compilado; único módulo que fica compilado dentro dele (ver `Acessos.spec`) |
| `Acessos.spec` | **novo** — spec do PyInstaller mantido à mão: tira os `.py` do projeto do `PYZ`, deixa soltos em `_internal\` |
| `python/atualizador.py` | **novo** — verifica se há versão nova no GitHub e avisa (não baixa/aplica sozinho) |
| `gerar_ico.py` | **novo** — gera `icones/acessos.ico` a partir do `.svg` (ferramenta de release) |
| `python/win_embed.py` | **novo** — reparenta HWND externa (`SetParent`), em **ctypes puro** (sem pywin32) |
| `python/conpty.py` | **novo** — ConPTY (`CreatePseudoConsole`) em **ctypes puro** (sem pywinpty) |
| `python/bandeja_windows.py` | **novo** — esconde o console do lançador depois do login e o representa por um ícone de bandeja (`Shell_NotifyIcon`), **ctypes puro** |
| `python/rdp_windows.py` | **novo** — `AbaRdpWindows`: FreeRDP para Windows + `win_embed` no lugar do `Gtk.Socket` |
| `python/ssh_windows.py` | **novo** — `AbaSshWindows`: `ssh.exe` nativo hospedado via ConPTY (`conpty.py`) + `pyte` |
| `python/vncwidget.py` | **patchado** — só o carregador do shim (`.dll` em vez de `.so`); resto idêntico ao original |
| `python/acessos.py` | **patchado** — importa os módulos Windows condicionalmente (`sys.platform == "win32"`) nos mesmos pontos onde já escolhia entre `AbaRdp`/`AbaRdpEmbutido` e montava `AbaSsh` |
| `python/sftp.py`, `cofre.py`, `tema.py` | **inalterados** — já são portáveis (paramiko/cryptography puros) |
| `src/vncshim.c` | **inalterado** — compilado para `.dll` pelo `instalar.ps1`, mesmo código C |
| `icones/acessos.svg` | inalterado |
| `icones/acessos.ico` | **novo** — gerado por `gerar_ico.py`, usado como ícone do `.exe` e do atalho |

`massa.py`/`massa_ui.py` **não foram portados**, por instrução explícita do
LEIAME original.

## Decisões tomadas (resumo da conversa)

- **RDP**: FreeRDP para Windows (`wfreerdp.exe`), não `mstsc.exe` — mantém o
  mesmo vocabulário de flags (`/cert:ignore`, `/d:`, `/u:`, `/p:`) que o
  resto do projeto já depende, e segue a preferência por ramos opensource
  do LEIAME original. Embutido via `SetParent` depois que a janela sobe —
  não existe `/parent-window:` equivalente no Windows, então a ordem é
  invertida em relação ao `xfreerdp` no X11.
- **SSH**: `ssh.exe` nativo (OpenSSH-for-Windows, já vem no Windows 10/11),
  hospedado via **ConPTY** (`pywinpty`), não `SetParent` de uma janela de
  console. Um console reparentado tira o controle programático que o login
  automático precisa — o mesmo problema que o `sshpass` resolve no Linux
  criando seu próprio pseudo-terminal por baixo.
- **Cortado, por decisão explícita**: menu de biblioteca de snippets no
  SSH. O mecanismo de injeção (escrever no pty) continua existindo — é o
  mesmo usado pelo login automático — só a UI da biblioteca não foi.
- **GTK3 mantido** como base da interface, via MSYS2 (GTK3 + PyGObject
  pré-compilados para Windows).
- **Console escondido após o login, com ícone de bandeja** (`bandeja_windows.py`):
  o `acessos.cmd` chama `python.exe` direto (sem `start`, sem `pythonw`), então
  o console ficava aberto a sessão inteira — poluição visual e um Ctrl+C sem
  querer ali matava o processo. Depois que o cofre aceita a senha, o console
  é escondido (`ShowWindow`/`SW_HIDE`) e vira um ícone na bandeja do sistema
  (`Shell_NotifyIcon`, com o próprio `icones/acessos.svg` rasterizado via
  GdkPixbuf — mesma biblioteca que já desenha o ícone da barra de título)
  com menu para reabri-lo (diagnóstico) ou sair. Console
  escondido não recebe foco de teclado, então o Ctrl+C acidental deixa de
  chegar nele. **Limitação conhecida:** sob Windows Terminal (padrão no
  Windows 11), o conhost por trás de cada aba já é oculto por design —
  escondê-lo não fecha a aba que aparece na tela; o ícone de bandeja continua
  funcionando, mas como extra, não substituto.
- **`pywin32` e `pywinpty` eliminados.** Os wheels dos dois são compilados
  contra o CPython oficial (ABI MSVC); o Python que traz o GTK3 no Windows
  é o do MSYS2 (ABI MinGW), então o pip tentava compilar do fonte e falhava.
  As duas funções de que precisávamos foram reimplementadas em `ctypes`,
  que já vem no Python: `win_embed.py` (user32: `SetParent`,
  `EnumWindows`) e `conpty.py` (kernel32: `CreatePseudoConsole`). Isso
  mantém o toolchain único que era o pedido original.
- **paramiko/cryptography vêm do pacman**, não do pip: têm código nativo,
  e o MSYS2 já os publica compilados. `pyte` (Python puro) vem por pip.
- **argon2-cffi é opcional**, como já era no `instalar.sh` do Linux: o
  MSYS2 não o empacota, então o instalador tenta via pip e, se falhar,
  segue com aviso — o `cofre.py` cai em PBKDF2 e funciona normalmente.
  **Atenção porém:** o `cofre.py` grava qual KDF foi usado, e um cofre
  criado com Argon2id **não abre** numa máquina sem argon2. Como o `.ini`
  de vocês fica em pasta sincronizada, padronize a equipe — todas as
  máquinas com argon2, ou nenhuma.

## O que ficou para depois (gaps conhecidos, não escondidos)

- **Captura total de teclado no RDP** (o botão ⌨ hoje desabilitado): no
  Linux é `XGrabKeyboard`; no Windows precisaria de `SetWindowsHookEx` de
  baixo nível. Não implementado.
- **Cores ANSI no terminal SSH**: o `pyte` já interpreta os códigos, mas o
  `Gtk.TextView` em `ssh_windows.py` ainda desenha tudo monocromático — os
  `Gtk.TextTag` por atributo (fg/bg/negrito) são o próximo passo natural,
  marcados como TODO no próprio arquivo.
- **Clique em URL** no terminal SSH: não portado.
- **`instalar.ps1` não foi testado num Windows real** — foi revisado à mão
  (sintaxe, escaping PowerShell↔MSYS2↔bash), mas o ambiente onde escrevi
  isso não tem Windows disponível para rodar de fato. Primeiro teste da
  equipe deveria ser `./instalar.ps1 -Verificar` logo após instalar, pra
  pegar qualquer problema de path/escaping cedo.

## Atualizar sem reinstalar (`atualizar.ps1`)

O `instalar.ps1` continua sendo a instalação completa (MSYS2, pacotes,
primeira compilação do `vncshim.dll`) — mas rodá-lo de novo só para levar
um `.py` editado até a equipe é lento e refaz trabalho que não mudou.

**Fluxo de atualização:**

1. Depois de editar `python\`, `src\` ou `icones\`, rode
   `.\gerar_manifesto.ps1` — recalcula o SHA-256 de cada arquivo rastreado
   e regrava `manifesto.json` (aceita `-Versao` para nomear a versão; sem
   isso usa a data/hora atual).
2. Distribua a pasta inteira (com o `manifesto.json` novo) do mesmo jeito
   que já é feito hoje para o `instalar.ps1`.
3. Cada máquina roda `.\atualizar.ps1` — compara o hash de cada arquivo
   rastreado contra o que está instalado em `%LOCALAPPDATA%\Acessos` e só
   copia o que realmente mudou. Só recompila `libvncshim.dll` se
   `src\vncshim.c` tiver mudado (comparação contra `.estado_patch.json`,
   gravado em `%LOCALAPPDATA%\Acessos` a cada aplicação — inclusive pelo
   próprio `instalar.ps1`, para a primeira execução do patcher já achar
   uma referência em vez de recompilar à toa).

Flags úteis: `-SoDetectar` (mostra o que mudaria, sem aplicar nada) e
`-Forcar` (aplica mesmo com o Acessos aberto — arquivos travados, como o
`.dll` em uso por uma sessão VNC ativa, falham isoladamente e são
reportados no fim, sem derrubar o resto do patch). Por padrão, o script
recusa aplicar com o Acessos rodando (detectado pela linha de comando do
processo `python.exe`, já que o console fica escondido — ver
`bandeja_windows.py`) e pede para fechar pelo menu da bandeja primeiro.

Cada patch faz backup de 1 nível (`.estado_patch.json` e
`.backup_anterior\` dentro da própria pasta instalada) dos arquivos que
serão sobrescritos — não é histórico de versões, só uma rede de segurança
para o patch mais recente.

## Compilar tudo num `.exe`

Em andamento — ver [BACKLOG-exe.md](BACKLOG-exe.md) para o roteiro
completo. **Primeira build real já funciona** (2026-09-04):
`.\compilar_exe.ps1` empacota `python\acessos.py` inteiro (via PyInstaller
do MSYS2 — `mingw-w64-x86_64-pyinstaller`, ABI já compatível, sem conflito)
num `Acessos.exe` standalone (`dist_exe\Acessos\`), testado rodando SEM o
MSYS2 no PATH.

Flags: `-Console` (mantém console visível, mais fácil de depurar um build
novo) e `-PularVncshim` (reaproveita um `libvncshim.dll` já compilado, pra
iterar mais rápido quando só o `.py` mudou).

Por padrão o build sai **sem console** (`--windowed`) — nesse modo,
`sys.stdout`/`sys.stderr` são redirecionados para
`%LOCALAPPDATA%\acessos\log.txt` (`_preparar_saida_sem_console()` em
`acessos.py`; mantém só a rodada anterior como `log.anterior.txt`). Sem
console, `bandeja_windows.py` não tem o que esconder e não faz nada — ele
continua útil só para quem roda via `acessos.cmd`/MSYS2 direto.

**Testado pela equipe com conexões de verdade**: VNC, SSH e RDP conectam
normalmente a partir do `.exe` compilado. O RDP inicialmente não conectou
(a máquina de teste não tinha `wfreerdp.exe` instalado — ele é achado via
PATH, uma ferramenta externa) — resolvido embutindo o FreeRDP inteiro
(binário + as 91 DLLs das quais ele depende, incluindo toda a pilha de
codecs de vídeo) dentro do bundle via `resolver_dlls.sh`. Isso engorda o
`.exe` de ~122 MB para ~206 MB; quem preferir o bundle menor com FreeRDP
instalado à parte (mesma exigência de sempre) usa
`.\compilar_exe.ps1 -SemRdp`.

**Instalador único, testado de ponta a ponta** (2026-09-08):
`instalador.iss` (Inno Setup — precisa dele instalado; `winget install
JRSoftware.InnoSetup` funciona sem admin) empacota a pasta `dist_exe\
Acessos\` já pronta. Compilar:

    & "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" `
        /DAppVersion=2026.09.08.1 instalador.iss

Gera `AcessosSetup-<versão>.exe` (~58 MB, comprimido) em
`dist_instalador\`. Instala em `%LOCALAPPDATA%\Acessos` sem pedir admin,
cria atalho no Menu Iniciar **e** na Área de Trabalho (desmarcável na tela
do instalador), e o desinstalador remove tudo de volta — inclusive
`log.txt`/`log.anterior.txt` que o app escreve em tempo de execução —
preservando a configuração do usuário (`~/.config/acessos`, fora da pasta
de instalação de propósito). Testado o ciclo completo: instalar → abrir
pelo atalho (com PATH mínimo, sem MSYS2) → desinstalar → conferir que a
config sobreviveu.

**Publicar tudo num comando só**: `.\publicar.ps1` encadeia
`gerar_manifesto.ps1` + `compilar_exe.ps1` + `ISCC.exe` + limpeza dos
artefatos de build, e opcionalmente copia o instalador pronto pro ponto de
distribuição (`-DestinoPublicacao <caminho>`). Testado de ponta a ponta —
o instalador resultante passa pelo mesmo ciclo (instalar → rodar →
desinstalar → config preservada) que o teste manual já validou.

**Arquitetura do bundle mudou (2026-09-08)**: os módulos do próprio
projeto (`acessos.py`, `tema.py`, `cofre.py`...) não ficam mais
compactados dentro do `PYZ` do PyInstaller — ficam soltos em `_internal\`,
igual às DLLs de terceiros já ficavam. `compilar_exe.ps1` agora chama
`pyinstaller Acessos.spec` (mantido à mão) em vez de passar uma lista de
`--flags`, e o ponto de entrada real do `.exe` virou `python/launcher.py`
(minúsculo, só ajusta o `sys.path` e importa `acessos`) — é o único módulo
que continua compilado dentro do binário. **Provado, não só implementado**:
com o `.exe` já compilado, editei um `.py`, copiei o arquivo modificado
direto por cima do `_internal\` do bundle (sem rodar `compilar_exe.ps1`/
PyInstaller de novo) e a mudança apareceu no `log.txt` na próxima abertura.
Isso é o pré-requisito pra uma futura auto-atualização via GitHub (ver
Item 5 do backlog) só sobrescrever o `.py` que mudou, sem reinstalar tudo.

**Checagem de atualização via GitHub, construída** (2026-09-08):
`python/atualizador.py` compara a versão local (lida do `manifesto.json`
embutido no bundle) contra a última GitHub Release do repositório —
público, sem autenticação nenhuma. Só avisa (um chip no rodapé da janela
principal); não baixa nem aplica nada sozinho. **Repositório ainda não
existe** — preencher `DONO_REPO`/`NOME_REPO` no topo do arquivo quando ele
for criado; até lá, a checagem simplesmente não encontra nada e não avisa
nada, sem quebrar o app.

## Ordem sugerida pra testar

1. `.\instalar.ps1` numa máquina limpa (ou VM) — confere se o MSYS2 sobe,
   os pacotes instalam e o `vncshim.dll` compila.
2. `.\instalar.ps1 -Verificar` — confirma que todos os módulos importam.
3. Abrir uma conexão só de **VNC** primeiro (é o caminho mais simples: sem
   embutimento de janela externa, só o shim + Cairo).
4. Depois **RDP** contra um servidor de teste, observando se o `SetParent`
   encaixa a janela do FreeRDP dentro da aba.
5. Por último **SSH**, testando login automático (senha no `.ini`) e o
   fluxo de troca de host key (apagar uma entrada de `known_hosts` e
   reconectar pra ver se o diálogo de "remover e reconectar" aparece).
6. **Bandeja**: depois do login no cofre, confira se o console some da
   barra de tarefas e se aparece o ícone na bandeja; clique com o botão
   direito nele para reabrir o console (deve reaparecer com foco) e para
   sair pelo menu (deve fechar a janela principal e o ícone deve sumir da
   bandeja, sem ficar "fantasma" até passar o mouse em cima).
