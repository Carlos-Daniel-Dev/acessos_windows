# Backlog — empacotar o Acessos num `.exe` único

Objetivo final: alguém recebe **um arquivo** (ou um instalador único), roda,
e tem o Acessos funcionando — sem precisar saber que existe MSYS2, GTK3,
PyGObject ou um `.cmd` por trás. Duas frentes separadas: **instalação** (hoje
é `instalar.ps1`) e **execução** (hoje é `acessos.cmd` chamando o Python do
MSYS2). Este documento é backlog — nada aqui foi implementado ainda.

## Por que isso não é trivial

O maior obstáculo é o mesmo que já apareceu no LEIAME: **GTK3 + PyGObject no
Windows só existe pronto via MSYS2** (ABI MinGW). PyInstaller/Nuitka/cx_Freeze
partem do princípio de empacotar um interpretador CPython "oficial" (ABI
MSVC) + suas dependências — nenhum deles sabe empacotar sozinho um ambiente
MSYS2 inteiro (GTK3, Pango, Cairo, GLib, GdkPixbuf, os `.dll` da toolchain
MinGW). Isso não inviabiliza o objetivo, só significa que o passo "gerar o
.exe" precisa reunir manualmente as `.dll` do MSYS2 no bundle, não só o
código Python.

## Item 1 — Escolher a ferramenta de empacotamento

- [ ] **Avaliar Nuitka** (modo `--standalone`/`--onefile`): compila para C,
      tende a lidar melhor com extensões nativas (PyGObject faz muita
      chamada C/GObject introspection via `libgirepository`) do que
      PyInstaller, que às vezes tropeça em bibliotecas carregadas via
      `dlopen`/GI typelib. Ponto de atenção: GObject Introspection carrega
      `.typelib` em tempo de execução por caminho — precisa mapear
      `GI_TYPELIB_PATH` para dentro do bundle.
  - [ ] **Avaliar PyInstaller** como alternativa mais madura/documentada
      para casos GTK (há relatos de builds funcionais no ecossistema
      GIMP/Inkscape-like, mas nenhum é exatamente este caso).
  - [ ] Descartar `briefcase`/`cx_Freeze` a menos que a avaliação acima falhe
      — menos tração da comunidade com GTK3+MSYS2 especificamente.
  - **Critério de decisão**: gerar um "hello world" GTK3 (uma janela com um
      botão) standalone com cada ferramenta antes de investir na aplicação
      inteira. Se nenhuma funcionar de primeira, o fallback é o Item 1b.

- [ ] **Item 1b (fallback)**: em vez de compilar o interpretador, empacotar o
      MSYS2 runtime inteiro (só as `.dll`/pacotes necessários, não o MSYS2
      completo) ao lado de um `.exe` lançador nativo pequeno (C ou Rust) que
      seta `PATH`/`PYTHONPATH` e invoca `python.exe` do bundle — é
      essencialmente automatizar o que `instalar.ps1` já faz manualmente,
      só que rodando de um pacote pré-baixado em vez de instalar pacotes do
      zero via `pacman`. Mais controle, mais trabalho de manutenção (dll
      hell manual).

## Item 2 — Executável de instalação (substituir `instalar.ps1`)

- [ ] Decidir o formato: instalador tradicional (Inno Setup/NSIS) baixando/
      extraindo o MSYS2 + pacotes necessários, ou instalador "gordo" que já
      embute tudo (maior, mas funciona offline/sem depender de espelhos
      `pacman` no momento da instalação — hoje `instalar.ps1` depende de
      internet e dos repositórios do MSYS2 estarem no ar).
- [ ] Portar a lógica hoje em `instalar.ps1` (`Garantir-Msys2`,
      `Instalar-PacotesMsys2`, `Instalar-PacotesPython`, `Compilar-Vncshim`,
      `Instalar-Aplicacao`) para dentro do instalador, ou para um script que
      o instalador chama silenciosamente.
- [ ] `vncshim.dll`: hoje compilado NO MOMENTO DA INSTALAÇÃO (`gcc` do
      MSYS2, contra `libvncclient` do sistema alvo). Empacotado, isso vira
      **pré-compilar e distribuir o `.dll` pronto** — implica fixar a versão
      do LibVNCClient contra a qual compilar e testar compatibilidade ABI
      nas máquinas de destino (hoje esse risco não existe porque cada
      instalação compila local).
- [ ] `argon2-cffi` opcional: se o pacote final for "gordo" (embute tudo),
      decidir se argon2 entra sempre — resolveria de vez o aviso do LEIAME
      sobre padronizar a equipe (todas as máquinas com/sem argon2).
- [ ] Ícone e metadata do instalador/exe (`icones/acessos.svg` precisa virar
      `.ico` — ver Item 4).
- [ ] Assinatura de código (code signing): sem isso o SmartScreen do Windows
      vai marcar o instalador e o app como "editor desconhecido" — não
      bloqueia, mas assusta quem instala pela primeira vez. Decidir se vale
      o custo/processo de um certificado antes do rollout pra equipe.

## Item 3 — Executável de execução (substituir `acessos.cmd`)

- [ ] Depois do Item 1 escolhido, `acessos.py` + módulos viram um único
      `Acessos.exe` (ou uma pasta standalone com um `.exe` de entrada).
- [ ] **Subsistema do executável**: compilar como app **GUI** (`windows`
      subsystem), não console — isso elimina de vez o problema que
      `bandeja_windows.py` contorna hoje (não existe janela de console para
      esconder, porque o processo nunca abre uma). **Consequência**: perde-
      se o stdout/stderr "de graça" — decidir para onde vai o log
      (`--debug` hoje escreve em stderr): arquivo de log em
      `%LOCALAPPDATA%\acessos\log.txt`, com rotação, é o candidato óbvio.
  - [ ] Quando isso acontecer, `bandeja_windows.py` deixa de ser necessário
      no formato atual — mas o ÍCONE DE BANDEJA em si (pra minimizar o app
      inteiro, não só o console) pode continuar valendo como funcionalidade
      própria do app. Reavaliar o escopo do módulo nesse momento: vira
      "bandeja do Acessos" (o app inteiro minimiza pra lá) em vez de
      "bandeja do console".
- [ ] Revalidar o ConPTY (`conpty.py`) e o `win_embed.py` dentro do processo
      compilado — ambos usam `ctypes.WinDLL`, que deve continuar funcionando
      igual num binário compilado, mas precisa de teste real (nenhum dos
      dois foi testado assim até agora).
- [ ] Revalidar `vncwidget.py` carregando `libvncshim.dll` a partir do
      caminho do bundle (`_carregar_shim()` já procura ao lado do próprio
      arquivo — conferir que esse caminho existe/funciona dentro da
      estrutura de pastas que o empacotador gerar, que pode diferir de
      "tudo numa pasta só").
- [ ] `--conf`, `conexoes.ini`, `snippets.ini`: confirmar que os caminhos de
      configuração (`%LOCALAPPDATA%\acessos\...`, hoje resolvidos por
      `caminho_conf()`) continuam corretos rodando de um exe empacotado
      (evitar regressão tipo "salvando dentro da pasta do Program Files").

## Item 4 — Identidade visual do executável

- [ ] `icones/acessos.svg` → gerar um `.ico` multi-resolução (16/32/48/256px)
      para usar como ícone do `.exe`, do atalho do Menu Iniciar e da barra
      de tarefas — hoje o atalho cai no genérico do PowerShell (comentário
      em `instalar.ps1`, função de criação do atalho).
- [ ] O mesmo `.ico` serve para o ícone de bandeja (`bandeja_windows.py` usa
      hoje `IDI_APPLICATION`, o ícone genérico do Windows, por não ter um
      `.ico` próprio disponível em tempo de execução).

## Item 5 — Distribuição e atualização

- [ ] Versionamento: decidir esquema (semver?) e onde ele fica visível
      (rodapé da janela principal? `--version`?).
- [ ] Atualização: já existe `atualizar.ps1` + `manifesto.json`
      (manifesto de hashes SHA-256, patch incremental sem reinstalar) — ver
      seção "Atualizar sem reinstalar" no LEIAME. Decidir se o `.exe`
      empacotado mantém esse MESMO mecanismo (adaptado: o manifesto passa a
      descrever os arquivos DENTRO do bundle compilado, não `.py` soltos) ou
      se vira auto-update de verdade (checagem de versão + download
      embutido no próprio app). A lógica de "comparar hash, copiar só o que
      mudou, backup de 1 nível" do `atualizar.ps1` serve de base pros dois
      caminhos — não é trabalho perdido de qualquer forma.
- [ ] Canal de distribuição interno (rede da equipe, já que `.ini` de
      conexões fica em pasta sincronizada — mesma lógica de distribuição
      pode servir pro instalador).

## Ordem sugerida de ataque

1. Item 1 (prova de conceito GTK3 standalone) — decide se o caminho é
   "compilar de verdade" ou o fallback de empacotar o MSYS2 runtime.
2. Item 3 sobre a aplicação real (`acessos.py` compilado), com o console
   ainda presente por enquanto (não bloquear em cima do Item 4/5).
3. Item 4 (ícone) — barato, e destrava a UX do instalador/bandeja ficarem
   com cara de produto acabado.
4. Item 2 (instalador) por cima do executável já funcionando.
5. Item 5 por último — só faz sentido depois que existe algo versionado pra
   distribuir e atualizar.
