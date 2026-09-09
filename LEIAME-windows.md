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
| `python/sftp.py` | **inalterado** — já é portável (paramiko puro) |
| `python/cofre.py`, `tema.py` | **acompanham o Linux** — copiados direto na atualização de 2026-09-09 (ver seção abaixo); sem patch Windows-específico |
| `python/dialogo_ui.py` | **novo (portado do Linux em 2026-09-09)** — formatos de diálogo compartilhados (`avisar`/`confirmar`/`perguntar`/`editor`); GTK puro, sem adaptação |
| `python/massa.py` | **novo (portado do Linux em 2026-09-09)** — motor de execução em lote via SSH; Python puro com `paramiko`, sem GTK, sem adaptação |
| `python/massa_ui.py` | **novo (portado do Linux em 2026-09-09)** — aba de UI da execução em lote; GTK puro, sem adaptação |
| `src/vncshim.c` | **inalterado** — compilado para `.dll` pelo `instalar.ps1`, mesmo código C |
| `icones/acessos.svg` | inalterado |
| `icones/acessos.ico` | **novo** — gerado por `gerar_ico.py`, usado como ícone do `.exe` e do atalho |

`massa.py`/`massa_ui.py` **portados em 2026-09-09** — decisão revisitada ao
trazer as atualizações do Linux (ver seção "Atualização de 2026-09-09"
abaixo). O motor (`massa.py`) é Python puro com `paramiko`, sem GTK nem
nada específico de Linux; funcionou sem nenhuma adaptação.

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

**Auto-atualização via GitHub, construída e testada** (2026-09-08):
`python/atualizador.py` compara a versão local (lida do `manifesto.json`
embutido no bundle) contra a última GitHub Release do repositório
(`Carlos-Daniel-Dev/acessos_windows`, ainda **privado** hoje — precisa
virar público antes da checagem funcionar de verdade). Avisa com um chip
+ botão "Atualizar agora" no rodapé; com confirmação do operador, baixa
os `.py` que mudaram (por hash, nunca por nome/data), confere o SHA-256
de cada download ANTES de sobrescrever, faz backup do arquivo antigo, e
oferece reiniciar o app pra usar a versão nova — **sem baixar/reinstalar
o `.exe` inteiro**. Não cobre o `vncshim.dll` (não pode ser recompilado
sem um compilador C embutido) — uma mudança nele continua exigindo
reinstalar via `.exe` novo. Testado com rede simulada (o repositório real
ainda não tem release publicada); falta testar contra o GitHub de
verdade assim que o repositório virar público.

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

## Atualização de 2026-09-09 — trazendo as atualizações do Linux

O projeto Linux original avançou bastante desde o porte inicial. Recebemos
um `.tar` com o estado atual de lá e trouxemos pro Windows tudo que fazia
sentido, preservando cada patch Windows-específico (RDP/SSH embutidos,
bandeja, saída sem console, `_MEIPASS`, `atualizador.py`, o seletor de
tema segmentado `.seg-topo`). Nada disso foi perdido — foi reaplicado por
cima da base nova do Linux, um ponto de cada vez.

**O que veio:**

- **`dialogo_ui.py` (novo módulo)** — os três formatos de diálogo do app
  (`avisar`/`confirmar`, `perguntar`, `editor`) viraram um módulo
  compartilhado. Antes o `cofre.py` duplicava esses helpers por conta
  própria e usava `Gtk.MessageDialog` pros avisos — que traz o estilo do
  SISTEMA e ignora boa parte do CSS do app; era por isso que os diálogos
  do cofre pareciam de outro programa. Agora tudo usa o mesmo estilo.
- **Histórico/backup versionado do `.ini`** — toda gravação passa por
  `escrever_ini()` (ponto único, atômico, com `fsync`+`os.replace` e uma
  guarda que aborta a escrita se a seção `[cofre]` seria perdida), e
  guarda até 20 cópias anteriores em `historico/`.
- **Reset do cofre ("esqueci a senha mestra")** — digitar `REINICIALIZAR`
  no campo de senha mestra oferece recomeçar o cofre do zero (com
  confirmação de 5 segundos), apagando os campos cifrados das conexões
  (ficariam lixo indecifrável com a chave antiga) e preservando o arquivo
  anterior em `historico/`.
- **`[geral] caminho=`** — permite relocar `conexoes.ini`/`snippets.ini`/
  `historico/` pra outra pasta (ex.: uma pasta sincronizada), com uma tela
  nova em Ajustes (`_abrir_ajustes`) que usa `Gtk.FileChooserDialog`.
- **Conexão instantânea/efêmera** — digitar algo como `10.1.1.99:22` ou
  `rdp serv-ad-2025` na busca e apertar Enter conecta na hora, sem gravar
  nada no `.ini` (`interpretar_alvo`/`conexao_efemera`).
- **Indicador de vida (ping) nos cards** — bolinha ao lado de cada máquina
  visível. **Adaptado pro Windows**: a sintaxe do `ping` diverge entre
  plataformas (Linux usa `-c`/`-W` em segundos, o `ping.exe` do Windows usa
  `-n`/`-w` em milissegundos) — sem a adaptação, o indicador ficaria sempre
  cinza. Também ganhou `CREATE_NO_WINDOW` pra não piscar um console preto a
  cada sondagem.
- **`massa.py`/`massa_ui.py` (execução em lote) — portados e habilitados.**
  Revisitando a decisão original de não portar: o motor é Python puro com
  `paramiko`, sem GTK nem nada específico de Linux — funcionou sem
  nenhuma adaptação. A barra de seleção/execução em lote, antes sempre
  escondida no Windows, agora aparece igual ao Linux.
- **Redesign completo do `tema.py`** — efeito "vidro"/gradiente na janela,
  ícones simbólicos (`Gtk.IconTheme`) no lugar de texto/emoji cru nas
  abas e nos cards (com fallback pro texto/emoji quando o tema de ícones
  não tem o nome pedido), headerbar de diálogo redesenhada. **Preservado
  do Windows**: o bloco `.seg-topo`/`.seg-topo-ini`/`.seg-topo-fim`/
  `.seg-topo-meio` (paleta própria pro seletor de tema, que mora na
  titlebar escura) e — crítico — o **fallback de fonte pra glifo**
  (`SIMBOLOS`: Segoe UI Symbol/Emoji/Fluent Icons/MDL2) anexado no fim da
  nova pilha de fontes (`IBM Plex Sans`/`Inter`/`Cantarell`). Sem esse
  fallback os glifos (⚙👁📁🚫⚡⌨⧉⟳＋) voltariam a aparecer como
  retângulo vazio no Windows — nem a fonte nova nem o Calibri antigo
  trazem esses pontos de código.
- **Removido, alinhado com o Linux**: a escala de fonte "grande" (botão
  "A+", `ESCALA_FONTE`) — decisão de produto do redesign novo, não bug.

**Testado**: rodando de fonte (MSYS2 python direto) e compilado
(`compilar_exe.ps1` + `Acessos.spec`, confirmando que `dialogo_ui.py`/
`massa.py`/`massa_ui.py` ficam soltos em `_internal\` como os demais
módulos do projeto, não compactados no `PYZ`) — os dois sobem sem erro,
com o seletor de tema, a barra de execução em lote e os glifos
aparecendo corretamente.

**Não testado ainda de ponta a ponta** (fica para a próxima rodada, antes
de qualquer release "1.0.0 stable" — decisão explícita de lançar mais
versões `0.x` primeiro): reset do cofre contra um cofre de verdade,
relocação de pasta de dados, indicador de vida contra máquinas reais
ligadas/desligadas, execução em lote contra um parque de verdade.

## Ajustes de 2026-09-09 (mesmo dia) — fonte grande e tema Rosé

Depois do redesign do `tema.py`, duas coisas visíveis foram revisadas:

- **Botão "A+" de volta** — a escala de fonte (`ESCALA_FONTE`/
  `ESCALA_FONTE_GRANDE`/`ESCALA_GLIFO`/`_escalar_fontes()`) tinha sido
  removida ao adotar o redesign do Linux (decisão de produto de lá, não
  bug). Reimplementada em cima da folha NOVA: continua sendo um multiplicador
  aplicado em cima do CSS já pronto (regex em cima de todo `font-size:
  Npx`), então não depende da estrutura exata das regras — funciona
  igual não importa quanto o `tema.py` mude depois. `ESCALA_FONTE` virou
  `1.0` (a folha nova já veio com os tamanhos calibrados; não faz sentido
  inflar 15% por cima de novo) e `ESCALA_GLIFO` ajustado pra `1.15`
  (a escala de glifo antiga, 1.30, ficava exagerada nos ícones do
  redesign novo).
- **Seletor de tema virou 3 opções, com um tema novo** — `tema.py` ganhou
  `NOMES_TEMA` (lista ordenada `[(chave, rótulo), ...]`) e um terceiro
  tema, `"rose"` (❀ Rosé): paleta rosa/branco, mesma estrutura de
  `"claro"` (vidro branco, titlebar clara). **Deliberadamente idênticos
  a `"claro"`**: os tokens de protocolo (`azul`/`verde`/`roxo` e as
  variantes `_fraco` — VNC/SSH/RDP), os status (`ok_*`/`erro_*`/
  `atencao_*`) e a tela remota/terminal (`palco`/`term_bg`/`term_fg`) —
  só o cromo (fundo, cartão, titlebar, vidro, botão de ação, banner)
  mudou pra rosa. `acessos.py` usa `segmentado(NOMES_TEMA, ...)` no
  lugar da lista fixa de 2 itens — um tema novo em `tema.py` aparece no
  seletor sem tocar em `acessos.py` de novo.

Testado rodando de fonte: os dois toggles (tema Rosé + A+) renderizam
corretamente, com os glifos legíveis nos dois tamanhos.

## Importador de CSV do RDM (mesmo dia, 2026-09-09)

Novo módulo `python/importar_rdm.py` — traz máquinas de um export
**"Export vault (.csv)"** do Devolutions Remote Desktop Manager pro
`conexoes.ini`, acessível em **Ajustes → IMPORTAR**.

Só o CSV é suportado (não `.rdm`/`.json`/`.html`/`.xml` — decisão
deliberada: `.rdm` é formato proprietário que pode trazer um blob de
credenciais cifrado com a chave do cofre deles, impossível de decifrar
aqui; `.json`/`.xml` têm schema aninhado desconhecido sem um exemplo
real pra confirmar contra; `.html` normalmente nem traz os campos
técnicos). Testado com um export real de ~225 máquinas antes de integrar
à UI.

**Mapeamento**: `Host` → host · `Port` → decide o protocolo (5900 VNC,
3389 RDP, 22 SSH, mesma tabela `PORTA_PROTO` de `acessos.py`) · `Display
Name` → título do card (deduplicado com sufixo numerado se repetir) ·
`Folder` → grupo, convertendo `\` em `;` (subgrupo do Acessos). Usuário e
senha nunca vêm no export — ficam em branco, como uma conexão cadastrada
à mão sem preencher o campo.

**Dois bugs achados testando contra o export real, corrigidos antes de
integrar**:
- **Mojibake de codificação** — o export trazia "ç"/"ã" como "Ã§"/"Ã£"
  (bytes UTF-8 decodificados como Windows-1252). `_corrigir_mojibake()`
  desfaz isso quando detecta o padrão, sem mexer em arquivos que já
  estão certos.
- **`/` não é separador de subpasta** — só `\` é. Uma pasta do RDM
  chamada "AD / ARQUIVOS / IMPRESSORAS / NAS" é UM nome só (usa "/" como
  pontuação decorativa); dividir por "/" também quebraria isso em quatro
  grupos errados. Confirmado contra o export: essa pasta hospeda AD,
  impressoras e NAS juntos, de propósito.

**Reimportar não duplica** — hosts já cadastrados no `conexoes.ini` são
pulados (comparação por host, não por nome), então rodar a importação
duas vezes com o mesmo arquivo é seguro.

Testado de ponta a ponta pela UI de verdade (Ajustes → Importar CSV do
RDM…, escolhendo o arquivo pelo `Gtk.FileChooserDialog`) contra o export
real do parque: **224 máquinas importadas**, grupos e subgrupos
aninhados corretamente na lateral (`01_Controle - Caixas` com 198
máquinas em 7 subgrupos, batendo exatamente com a soma), acentuação
correta ("Balanças"), e a reimportação do mesmo arquivo confirmada como
no-op (0 novas, todas puladas por já existirem).

### Achado testando com a equipe (mesmo dia): estrutura do bloco importado

A equipe testou contra o `conexoes.ini` de produção
(`C:\Users\<usuário>\.config\acessos\`) e reportou que o CSV "não estava
alimentando o arquivo com as definições padrão" — a importação **estava**
gravando (confirmado pelo `historico/`: backup antes do import, arquivo
crescendo de ~3,8 KB pra ~25 KB, 224 seções novas), só que cada bloco
importado só trazia `host`+`grupo` e mais o que fugia do default (ex.:
`vnc = 0` / `rdp = 1` pra uma máquina RDP) — o resto (`porta`, `modo`,
`ronly`, `auto`, `ssh`, `rdp` quando é 0, `rdp_tela`...) ficava de fora do
arquivo, contando só com o default do `Conexao.__init__` (`acessos.py`)
aplicado EM MEMÓRIA na hora de ler. Funcionava (a máquina aparecia e
conectava certo), mas o bloco no arquivo ficava com uma "forma" mais
enxuta do que uma conexão cadastrada à mão pelo editor (`Janela._editor()`
grava sempre o conjunto completo de campos do protocolo, mesmo quando
valem só o default) — abrir o `.ini` direto pra conferir ou editar uma
máquina importada mostrava menos linhas do que o esperado.

Corrigido em `_linhas_ini_da_maquina()`: agora escreve o MESMO conjunto
de campos que o editor grava — `vnc`/`ssh`/`rdp` sempre explícitos (`0`
ou `1`), e pro protocolo ativo os campos padrão dele também explícitos
(`porta`/`modo`/`ronly`/`auto` pra VNC; `ssh_porta`/`ssh_auto` pra SSH;
`rdp_porta`/`rdp_tela`/`rdp_auto` pra RDP). Reconfirmado contra o mesmo
export real: os 224 blocos agora saem no formato completo, idêntico ao
que o editor produziria pra cada uma dessas máquinas cadastradas à mão.
