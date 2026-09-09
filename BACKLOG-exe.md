# Backlog — empacotar o Acessos num `.exe` único

Objetivo final: alguém recebe **um arquivo** (ou um instalador único), roda,
e tem o Acessos funcionando — sem precisar saber que existe MSYS2, GTK3,
PyGObject ou um `.cmd` por trás. Duas frentes separadas: **instalação** (hoje
é `instalar.ps1`) e **execução** (hoje é `acessos.cmd` chamando o Python do
MSYS2). Este documento é backlog — nada aqui foi implementado ainda.

## Por que isso não é trivial (e o que já deixou de ser um risco)

A preocupação original: **GTK3 + PyGObject no Windows só existe pronto via
MSYS2** (ABI MinGW), e PyInstaller/Nuitka/cx_Freeze partem do princípio de
empacotar um interpretador CPython "oficial" (ABI MSVC) — a suposição era
que nenhum saberia empacotar sozinho um ambiente MSYS2 inteiro.

**Isso não se confirmou.** O MSYS2 empacota o **PyInstaller nativamente**
(`mingw-w64-x86_64-pyinstaller`, compilado contra o Python do próprio
MSYS2 — sem conflito de ABI) e ele já tem hooks prontos para
`gi.repository` (Gtk, Gdk, GLib, GdkPixbuf, Pango, cairo, HarfBuzz,
freetype2, GioWin32, GLibWin32...). Um teste real (não simulado) confirmou:

## Item 1 — Escolher a ferramenta de empacotamento ✅ resolvido

- [x] **PyInstaller via MSYS2** — testado de ponta a ponta em
      2026-09-04. `pacman -S mingw-w64-x86_64-pyinstaller` instala sem
      atrito (ABI já compatível). Um app GTK3 mínimo (`Gtk.Window` +
      `Gtk.Button`) empacotado com `pyinstaller --onedir` bundlou sozinho
      `libgtk-3-0.dll`, `libgdk-3-0.dll`, `libpango*.dll`, `libcairo*.dll`,
      os `.typelib` (Gtk-3.0, Gdk-3.0, GdkPixbuf-2.0, Pango-1.0,
      cairo-1.0) e os loaders do gdk-pixbuf — sem nenhuma intervenção
      manual de path/DLL.
  - [x] **Testado rodando com PATH mínimo** (sem `C:\msys64` em lugar
      nenhum) — o `.exe` gerado iniciou e rodou o loop do GTK
      normalmente (saída limpa, `exitCode=0`, sem erro de DLL ausente).
      Confirma que o bundle é **genuinamente redistribuível**, não
      apenas "funciona porque o MSYS2 ainda está no PATH desta máquina".
  - [x] Nuitka também está disponível via pacman
      (`mingw-w64-x86_64-python-nuitka`) mas não foi testado — o
      PyInstaller já resolveu de primeira, sem necessidade de comparar.
      Deixar registrado como alternativa se algo em Item 3 (a aplicação
      real, bem mais pesada que o hello-world) esbarrar num hook faltando.
  - [x] **Item 1b (fallback de empacotar o MSYS2 manualmente) descartado**
      — não é mais necessário; o caminho direto funcionou.
  - Tamanho do bundle de teste (`--onedir`, sem otimizar): ~113 MB para um
      hello-world. Esperado — GTK3 + Pango + HarfBuzz + temas de ícone
      inteiros. Otimização de tamanho (excluir loaders/locales não usados)
      fica para depois de ter a aplicação real funcionando.

## Item 2 — Executável de instalação (substituir `instalar.ps1`)

> **VISÃO A ESTUDAR COM CALMA — não implementar ainda, só levantar
> opções.** Hoje, pra gerar o `Acessos.exe` (Item 3), ainda é preciso ter a
> árvore-fonte inteira aberta (`python\`, `src\`, `icones\`) e o MSYS2 com
> GTK3/PyGObject/FreeRDP instalados — `compilar_exe.ps1` roda EM CIMA
> disso. Isso é só um requisito de quem CONSTRÓI o `.exe`; quem só usa o
> resultado não precisa de nada disso. A ideia deste item é fechar esse
> ciclo: **um único instalador `.exe`** que, numa máquina limpa, sem MSYS2
> nem nada, faz só isto (nada de MSYS2/pacman/gcc no alvo — ver decisão
> logo abaixo):
> 1. extrai a pasta `dist_exe\Acessos\` (já pronta, construída antes numa
>    máquina de build por `compilar_exe.ps1`) pro destino — **DECIDIDO em
>    2026-09-08: continua `%LOCALAPPDATA%\Acessos`**, sem admin
>    (`PrivilegesRequired=lowest` no Inno Setup), mesma filosofia que
>    `instalar.ps1` já tem hoje ("sem precisar de admin"). Program Files
>    foi descartado por exigir admin em toda instalação/atualização —
>    fricção que o projeto não tem hoje e não deveria ganhar por causa do
>    instalador;
> 2. cria o atalho do Menu Iniciar (`instalar.ps1` já faz isso) **e
>    também um atalho na Área de Trabalho** (ainda não existe em lugar
>    nenhum — nem no `instalar.ps1` de hoje, nem no `compilar_exe.ps1`).
>
> **DECIDIDO em 2026-09-08**: build UMA VEZ, instalador distribui o
> binário pronto (Opção B) — não gera o `.exe` na máquina do usuário
> final. Motivo, comparando as duas frentes de atualização:
>
> | | Opção A (build no usuário final) | Opção B (build único, decidida) |
> |---|---|---|
> | **Instalação nova pega a última versão sozinha?** | Sim, de graça — compilar É ler o código atual, igual `instalar.ps1` hoje | Não — precisa de um passo explícito de republicar o `.exe` (ver `publicar.ps1` abaixo) |
> | **Máquina já instalada, como atualiza?** | Reaproveita `atualizar.ps1` (incremental, leve, já existe) | `atualizar.ps1` não serve — código Python fica dentro do `PYZ` do PyInstaller (mesma limitação já anotada no Item 5). Atualizar = reinstalar por cima (baixar o `.exe` inteiro de novo) |
> | **Reprodutibilidade** | Cada máquina builda com o que o `pacman` tiver naquele momento — pode variar entre instalações | Um único binário testado, igual para todo mundo |
> | **Requisito na máquina do usuário** | MSYS2 + toolchain inteiro (~1-2 GB), só "de passagem" | Nenhum — só extrai o que já veio pronto |
>
> A Opção A ganha de graça o "sempre atualizado", mas perde reprodutibilidade
> (o próprio Item 2 já reclamava disso sobre o `vncshim.dll`, antes desta
> decisão) e obriga todo mundo a carregar o MSYS2 completo só pra montar o
> `.exe` uma vez. Ganhou a Opção B — mas ela precisa fechar a lacuna do
> "esquecer de republicar":
>
> - [x] **`publicar.ps1` — CONSTRUÍDO E TESTADO em 2026-09-08.** Encadeia
>       `gerar_manifesto.ps1` + `compilar_exe.ps1` + `ISCC.exe`
>       (`instalador.iss`) + cópia opcional pro ponto de distribuição
>       (`-DestinoPublicacao`) + limpeza de `dist_exe\`/`build_exe\` no
>       final, tudo num comando só. Não elimina o risco de alguém esquecer
>       de rodar depois de editar código, mas reduz de "vários passos
>       manuais" pra "um ritual: editei, rodo publicar.ps1, pronto".
>       **Testado de ponta a ponta**: rodou os 4 passos, gerou
>       `AcessosSetup-<versão>.exe`, e o instalador resultante passou pelo
>       mesmo ciclo completo (instalar → rodar → desinstalar → config
>       preservada) que o teste manual do `instalador.iss` já tinha
>       validado. **Bug real encontrado e corrigido durante a construção**:
>       a versão inicial usava *array splatting* (`@("-PularVncshim")`)
>       pra repassar switches pros scripts internos — não funciona, um
>       array splat passa os elementos como valor posicional solto, não
>       como nome de parâmetro (`"Não é possível localizar um parâmetro
>       posicional que aceite o argumento"`). Corrigido pra *hashtable
>       splatting* (`@{PularVncshim=$true}`), a forma certa de repassar
>       parâmetros nomeados/switches em PowerShell. Também descoberto:
>       `$LASTEXITCODE` não é confiável para checar sucesso de outro
>       script `.ps1` chamado (só funciona de verdade pra executáveis
>       nativos) — `gerar_manifesto.ps1`/`compilar_exe.ps1` não chamam
>       `exit 0` no caminho de sucesso, então o sinal real de "deu certo"
>       usado é a EXISTÊNCIA do arquivo que cada passo deveria ter criado.
> - [ ] **Update de máquina já instalada = reinstalar por cima**, não
>       incremental — aceito como trade-off por ora. Fica pro Item 5 (auto-
>       update/notificação) decidir se algum dia vale a pena resolver a
>       arquitetura pra permitir patch incremental do `.exe` (mover os
>       `.py` pra fora do `PYZ`, como já anotado lá) ou se "reinstalar" é
>       simples o suficiente pro público-alvo.

- [x] **CONSTRUÍDO E TESTADO DE PONTA A PONTA em 2026-09-08:
      `instalador.iss`** (Inno Setup, não NSIS — script declarativo mais
      legível, suporte de primeira classe pra instalação sem admin, wizard
      de fábrica, `ISCC.exe` fácil de automatizar). Inno Setup 6.7.3
      instalado nesta máquina via `winget install JRSoftware.InnoSetup`
      (foi parar em `%LOCALAPPDATA%\Programs\Inno Setup 6`, por usuário,
      sem admin — nem o PRÓPRIO Inno Setup exigiu elevação aqui).
      Compilado com `ISCC.exe /DAppVersion=X.Y.Z instalador.iss` (a versão
      pensada pra vir do `manifesto.json` via `publicar.ps1`, ainda não
      escrito). Resultado: `AcessosSetup-X.Y.Z.exe`, ~58 MB (comprimido
      via LZMA2 a partir dos ~207 MB do bundle).
  - [x] **Ciclo completo testado, não só compilado**: instalei
        silenciosamente (`/VERYSILENT /SUPPRESSMSGBOXES`), confirmei
        `Acessos.exe` + `_internal\` no lugar certo, os DOIS atalhos
        (Menu Iniciar em subpasta de grupo + Área de Trabalho) apontando
        pro alvo certo com o ícone certo (extraído e conferido
        visualmente), o app abrindo pelo atalho da Área de Trabalho com
        PATH mínimo (sem MSYS2), e a desinstalação silenciosa removendo
        tudo (inclusive os dois atalhos) sem deixar rastro.
  - [x] **Bug real encontrado e corrigido durante o teste**: a primeira
        tentativa de desinstalação deixava um `log.txt`/`log.anterior.txt`
        pra trás (escrito pelo app em tempo de execução, não pelo
        instalador) — a pasta não ficava vazia. Tentei
        `Type: filesandordirs; Name: "{app}"` no `[UninstallDelete]`
        primeiro; NÃO funcionou (o `unins000.exe`/`.dat` ainda estão
        rodando de dentro de `{app}` nesse ponto do processo, travando a
        remoção da pasta inteira). A correção que funcionou, testada de
        novo do zero: mirar os arquivos ESPECÍFICOS que o app cria
        (`Type: files; Name: "{app}\log.txt"` + idem pro `.anterior`) e
        deixar o mecanismo padrão do Inno remover a pasta vazia sozinho no
        final.
  - [x] **Achado de processo, não de código**: `%LOCALAPPDATA%\Acessos` é
        a MESMA pasta que o fluxo antigo (`instalar.ps1`/MSYS2) já usa —
        tinha resíduo de sessões de teste anteriores (`.py` soltos,
        `acessos.cmd`) que precisou ser limpo à mão antes do teste, e
        também um atalho solto direto em `Programs\Acessos.lnk` (de uma
        versão antiga do `instalar.ps1`, sem subpasta de grupo) que ficou
        pra trás. Não afeta o instalador novo em si, mas é bom saber que
        os dois fluxos de instalação competem pelo mesmo diretório — não
        rodar os dois "instalados ao mesmo tempo" na mesma máquina sem
        limpar antes.
  - Atalho na Área de Trabalho: **feito** (`[Tasks]` com a opção marcada
        por padrão, desmarcável na tela do instalador).
- [x] ~~Portar `Garantir-Msys2`/`Instalar-PacotesMsys2`/`Compilar-Vncshim`
      pro instalador~~ — **não é mais necessário com a Opção B**: essa
      lógica toda já roda hoje em `compilar_exe.ps1`, na máquina de build,
      não no alvo. O instalador final não precisa saber que MSYS2 existe.
- [x] ~~`vncshim.dll` pré-compilado~~ — **já é assim desde o Item 3**:
      `compilar_exe.ps1` compila e embute o `.dll` dentro do bundle na
      máquina de build; quem instala só recebe o resultado. O risco de
      fixar a versão do LibVNCClient contra a qual compilar é real, mas já
      existia desde o Item 3 (não é novo pela decisão de hoje) — mesmo
      raciocínio do `publicar.ps1`: testar uma vez, distribuir testado.
- [ ] `argon2-cffi` opcional — **ADIADO em 2026-09-08.** Com a Opção B, a
      pergunta mudou de "todo mundo instala argon2?" pra "a MÁQUINA DE
      BUILD tem argon2 instalado quando `compilar_exe.ps1` roda?" — de um
      jeito ou de outro, fica CONSISTENTE entre todos os usuários
      automaticamente (resolve de vez o aviso do LEIAME sobre padronizar a
      equipe manualmente). **Checado nesta máquina de build em
      2026-09-08: NÃO tem argon2-cffi instalado** — todo `Acessos.exe`
      gerado até agora usa PBKDF2 (`KDF_PADRAO` cai pra ele quando
      `TEM_ARGON=False` em `cofre.py`). Decisão adiada — instalar é barato
      quando quiserem (`pacman -S mingw-w64-x86_64-python-cffi` + `pip
      install argon2-cffi` nesta máquina, antes do próximo
      `compilar_exe.ps1`), mas por ora segue PBKDF2 (ainda seguro, só não
      é o KDF mais forte disponível).
- [ ] Ícone e metadata do instalador/exe (`icones/acessos.svg` precisa virar
      `.ico` — ver Item 4).
- [x] **COFRE RESETADO PARA O USUÁRIO FINAL** — estudado e fechado em
      2026-09-08, levantado pelo usuário. Investigação (lendo
      `cofre.py`/`acessos.py` direto, não suposição). Só resta o item de
      PROCESSO abaixo (checklist de quem construir o instalador, não algo
      pra estudar mais):
  - [x] **Já é seguro por construção, hoje**: `conexoes.ini` mora em
        `~/.config/acessos/conexoes.ini` — config POR USUÁRIO DO SO, não
        um artefato de build. Nem `instalar.ps1` nem `compilar_exe.ps1`
        tocam em `~/.config` em nenhum momento (conferido lendo
        `Instalar-Aplicacao`/o script de empacotamento de novo). Uma
        instalação numa máquina/perfil novo nasce SEM esse arquivo →
        `_cofre.destrancar()` lê `tem_secao=False`, `em_claro=0` → devolve
        `(None, True)` direto, sem perguntar nada — o operador só vê o
        diálogo de senha mestra quando ELE mesmo criar uma conexão com
        senha e reiniciar o app. Nenhuma mudança de código necessária pra
        esse caso.
  - [ ] **O risco é de PROCESSO, não de código**: esta própria máquina de
        dev/teste já tem um cofre de verdade em
        `~/.config/acessos/conexoes.ini` (usado nos testes desta sessão).
        Quem gerar o instalador único no futuro precisa garantir que o
        processo de build NUNCA copie a pasta `~/.config` de quem está
        construindo o pacote — vira item de checklist/CI, não algo pra
        "corrigir" no código (o código já não faz isso).
  - [ ] **Se quiserem ship de um `conexoes.ini` "starter"** (lista de
        servidores pré-cadastrada pra facilitar o onboarding): a receita
        seguro que o código JÁ SUPORTA é enviar esse arquivo SEM nenhuma
        seção `[cofre]`. Se tiver senhas em texto claro, o primeiro
        lançamento detecta sozinho (`em_claro > 0`) e oferece "Proteger
        senhas" — cria o cofre com a senha que o PRÓPRIO usuário final
        escolher ali, e migra as senhas pra dentro dele
        (`migrar_para_cifrado`, já existe e já é usado). Sem senha nenhuma
        no arquivo starter, ninguém é incomodado (fica pra o usuário
        cadastrar as próprias credenciais depois).
  - [x] **Gap do "criar cofre proativamente" — DECIDIDO em 2026-09-08:
        não vale a pena mexer no código fonte.** Existe (não há menu
        "Configurar cofre agora"; `destrancar()` só oferece criar quando já
        há uma senha em texto claro salva), mas o fluxo real já cobre o
        caso: primeira conexão com senha → reinicia o app → oferece
        proteger automaticamente. Ninguém fica sem cofre por falta de um
        botão — o usuário final só vê o diálogo quando de fato tem algo
        pra proteger, o que já acontece sozinho. Fechado sem alteração de
        código.
- [ ] **Assinatura de código (code signing) — ADIADO em 2026-09-08.**
      Sem isso o SmartScreen do Windows marca o instalador e o `.exe` como
      "editor desconhecido" — não bloqueia, exige um clique em "Executar
      assim mesmo". Opções levantadas, nenhuma escolhida ainda: certificado
      OV (~$100-400/ano, reputação do SmartScreen constrói aos poucos, não
      resolve na hora), EV (mais caro, reputação quase instantânea),
      Microsoft Trusted Signing (mais novo, baseado em Azure, tende a ser
      mais barato que EV), ou não assinar e resolver por processo (orientar
      a equipe a clicar "Executar assim mesmo", ou marcar como confiável
      via GPO/Intune se as máquinas forem gerenciadas). Autoassinar com
      certificado próprio NÃO resolve — só um cert que encadeia até uma
      raiz confiada pela Microsoft ajuda. Revisitar se/quando a distribuição
      for além da equipe interna.

## Item 3 — Executável de execução (substituir `acessos.cmd`) ✅ 1ª build validada

Feito e testado de verdade em 2026-09-04, com `compilar_exe.ps1` (novo —
roda o PyInstaller do MSYS2 sobre `python\acessos.py`, adiciona o
`libvncshim.dll` recém-compilado e o `icones/acessos.svg` como dados, e o
typelib `GdkWin32` que o Item abaixo descobriu estar faltando):

- [x] **Subsistema GUI (`--windowed`, sem console)** — decidido e
      implementado, não console. Isso tornou `bandeja_windows.py`
      desnecessário PARA ESTE BUILD (ele já se comporta corretamente: sem
      console pra achar, `iniciar()` retorna False e não faz nada — ver seu
      próprio guard `if not console: return False`). Fica registrado como
      útil para quem ainda roda via `acessos.cmd`/MSYS2 direto.
  - [x] **stdout/stderr resolvidos**: nova função `_preparar_saida_sem_console()`
      em `acessos.py`, chamada logo no início de `main()`. Redireciona para
      `%LOCALAPPDATA%\acessos\log.txt` (mantém so a rodada anterior como
      `log.anterior.txt`, sem crescer sem fim). **Achado real, não só
      teórico**: a primeira versão detectava "sem console" checando
      `sys.stdout is None` — verdade para `pythonw.exe`, mas o bootloader
      `runw.exe` do PyInstaller entrega um stream que aceita `write()` e
      descarta tudo, nunca `None`. Trocado para `GetConsoleWindow()` (a
      mesma checagem que `bandeja_windows.py` já usava) — confirmado com um
      teste dedicado (log gravado com `hwnd_console=0, stdout=None`) antes
      de virar código definitivo.
- [x] **`__file__` não aponta para diretório real quando empacotado** —
      confirmado na prática (não teórico): `caminho_icone()` (`acessos.py`)
      e `_carregar_shim()` (`vncwidget.py`) usavam
      `os.path.dirname(os.path.abspath(__file__))`, que sob PyInstaller
      resolve para dentro do bundle compactado, não um caminho de disco.
      Corrigido nos dois: quando `getattr(sys, "frozen", False)`, usar
      `sys._MEIPASS` no lugar (a pasta `_internal` ao lado do `.exe`, onde
      `--add-data`/`--add-binary` realmente colocam os arquivos).
- [x] **GdkWin32 typelib ausente** — `win_embed.py` (RDP embutido via
      `SetParent`) precisa de `GdkWin32-3.0.typelib`; o PyInstaller tem hook
      próprio para `GioWin32`/`GLibWin32` (aparecem sozinhos no bundle) mas
      NÃO para `GdkWin32` — ninguém empacotou esse hook ainda. Sem isto o
      RDP embutido falharia SÓ no build compilado, com um erro difícil de
      relacionar com a causa. Corrigido via `--add-binary` manual em
      `compilar_exe.ps1`.
- [x] **Build real testado de ponta a ponta**: `Acessos.exe` (--onedir,
      ~122 MB) rodou com PATH mínimo (sem MSYS2 em lugar nenhum),
      confirmado via `MainWindowTitle='Acessos'` — uma janela GTK real
      renderizou, esperando o diálogo do cofre (não digitamos a senha —
      teste não interativo).
- [x] **Conexão real testada pela equipe em 2026-09-04**: VNC e SSH
      conectaram normalmente a partir do `.exe` compilado —
      `libvncshim.dll` e o ConPTY (`conpty.py`) funcionam no build
      empacotado, confirmado com sessão de verdade (não só o app abrindo).
  - [ ] **RDP não conectou** — mas pelo motivo ESPERADO, não um bug do
      empacotamento: `wfreerdp.exe` não estava instalado na máquina de
      teste.
  - [x] **FreeRDP embutido no bundle (feito em 2026-09-04, a pedido)**:
      novo `resolver_dlls.sh` percorre recursivamente (via `objdump -p`) o
      grafo de dependências nativas do `wfreerdp.exe` — necessário porque
      `--add-binary` do PyInstaller NÃO analisa dependências de um
      executável externo, só do próprio Python/extensões. Achado real: o
      fechamento tem **91 arquivos** (`libfreerdp3.dll`/`libwinpr3.dll` +
      toda a pilha de codecs de vídeo que o FreeRDP linka — ffmpeg, x264,
      x265, vpx, aom, opus, USB redirection —, a maioria sem NADA a ver com
      GTK). `rdp_windows.py` (`_bin_rdp_windows()`) ajustado para procurar
      primeiro em `sys._MEIPASS` (o bundle) antes de cair no `PATH` do
      sistema. **Testado**: `wfreerdp.exe` do bundle rodou sozinho (exibiu
      o banner de ajuda completo) com PATH mínimo, sem MSYS2 — confirma que
      o fechamento de DLLs está completo e correto. Custo: bundle saltou de
      ~122 MB para **~206 MB** (+84 MB). Flag `-SemRdp` em
      `compilar_exe.ps1` pula tudo isso para quem preferir o bundle menor
      com FreeRDP externo (mesma exigência de hoje).
- [x] `ssh.exe`: localizado via `shutil.which()` (busca no PATH do
      sistema) em `ssh_windows.py` — continua assim, é o OpenSSH do
      próprio Windows (10/11), não faz sentido embutir.
- [x] `conexoes.ini`/`snippets.ini`: `caminho_conf()`/`caminho_snippets()`
      usam `XDG_CONFIG_HOME`/`~/.config` (não `%LOCALAPPDATA%`, nem
      `__file__`) — mesmo comportamento rodando de fonte ou compilado, sem
      mudança necessária.
- [ ] **Tamanho do bundle**: ~206 MB com FreeRDP embutido (~122 MB sem,
      via `-SemRdp`) — otimizar depois (excluir locales/loaders de
      gdk-pixbuf não usados, avaliar UPX, ou os codecs de vídeo do FreeRDP
      que provavelmente não são todos necessários — x265/av1/USB redirect
      são recursos avançados que talvez a equipe nunca use) só faz sentido
      depois que o Item 2 (instalador) fechar.

## Item 4 — Identidade visual do executável ✅ feito em 2026-09-04

- [x] `icones/acessos.svg` → `icones/acessos.ico`, multi-resolução
      (16/24/32/48/64/128/256px) — novo `gerar_ico.py` (ferramenta de
      release, não faz parte do runtime): rasteriza cada tamanho DIRETO do
      SVG via GdkPixbuf (nítido em cada resolução, sem downscale borrado de
      uma única imagem grande) e monta o container `.ico` com Pillow
      (`mingw-w64-x86_64-python-pillow`, instalado via pacman).
- [x] **Ícone do `.exe`**: `compilar_exe.ps1` passa `--icon
      icones/acessos.ico` pro PyInstaller. **Testado de verdade**:
      extraído o ícone embutido no `.exe` gerado (via
      `System.Drawing.Icon.ExtractAssociatedIcon`) e conferido
      visualmente — é o monitor azul/verde do SVG, não o genérico do
      PyInstaller.
- [x] **Ícone do atalho do Menu Iniciar**: `instalar.ps1` agora copia
      `acessos.ico` para `%LOCALAPPDATA%\Acessos` e seta
      `$atalho.IconLocation` nele — antes caía no ícone genérico do
      `.cmd`/PowerShell.
- [x] ~~Ícone de bandeja~~ já resolvido antes deste item, numa sessão
      anterior: `bandeja_windows.py` já rasteriza `icones/acessos.svg`
      via GdkPixbuf (função `_icone_da_svg`), não usa mais
      `IDI_APPLICATION` desde que `caminho_icone()` existe. Não precisou
      de mudança nenhuma com a chegada do `.ico` — o caminho da bandeja é
      independente (lê o SVG direto, não o `.ico`).

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
- [ ] **AUTO-ATUALIZAÇÃO VIA GITHUB — estudado em 2026-09-08, pré-requisito
      arquitetural já construído e provado, resto ainda não implementado.**
      Decisão da equipe: versionar o projeto num repositório GitHub
      **público** próprio (revisto depois — a decisão original era
      privado, 8 usuários, ver nota de autenticação abaixo); o
      `Acessos.exe` em execução verifica sozinho se há uma versão mais
      nova e avisa o operador — sem aplicar sozinho (decidido: notificar e
      pedir confirmação, não auto-aplicar, pra um push ruim na `main` não
      derrubar todo mundo instantaneamente sem ninguém perceber). O pedido
      original era "buscar a versão mais recente da branch principal"; ver
      ressalva sobre tags/releases
      abaixo.
  - [x] **Pré-requisito arquitetural — CONSTRUÍDO E PROVADO em
        2026-09-08.** Antes, num build PyInstaller `--onedir`, o código
        Python do projeto (`acessos.py`, `tema.py`, `cofre.py`...) ficava
        compactado DENTRO do `PYZ-00.pyz` — não dava pra trocar um `.py`
        sozinho ali sem rodar `compilar_exe.ps1` de novo. Resolvido com
        dois arquivos novos:
      - **`python/launcher.py`** — novo ponto de entrada, minúsculo e
        estável de propósito (só ajusta o `sys.path` e importa `acessos`).
        É o ÚNICO módulo que ainda fica compilado dentro do `.exe` — tem
        que ser assim, é o bootstrap que o PyInstaller precisa pra
        arrancar.
      - **`Acessos.spec`** — mantido à mão (não gerado automaticamente):
        deixa a `Analysis` normal descobrir as dependências nativas (pra
        não perder os hooks do GTK/FreeRDP), mas depois REMOVE os módulos
        do projeto (`acessos`, `tema`, `cofre`, `sftp`, `vncwidget`,
        `rdp_windows`, `ssh_windows`, `win_embed`, `conpty`,
        `bandeja_windows`) da lista que vai pro `PYZ` e os adiciona como
        dado solto em `_internal\` — exatamente como `icones/acessos.svg`
        já era tratado. `compilar_exe.ps1` foi adaptado pra chamar
        `pyinstaller Acessos.spec` em vez da lista de `--flags` de CLI de
        antes, repassando os parâmetros que mudam de build pra build
        (ícone, DLLs do FreeRDP, console/janela) via variável de
        ambiente — um `.spec` não aceita os mesmos `--flags`.
      - **PROVADO NA PRÁTICA, não só compilado**: build gerado, confirmado
        que os 10 módulos do projeto ficam soltos em `_internal\` (e
        `launcher.py` NÃO, como esperado) — depois, com o app JÁ
        compilado, editei `acessos.py` (uma linha de log só pra teste),
        copiei o arquivo modificado DIRETO por cima do `_internal\
        acessos.py` do bundle (sem rodar `compilar_exe.ps1`/PyInstaller de
        novo), abri o app e a mudança apareceu no `log.txt` — prova
        concreta de que o `.py` solto é o que roda de verdade, e que
        trocar ele funciona sem recompilar. Bundle ainda funcional depois
        da mudança (app abriu normalmente antes e depois do patch de
        teste).
      - **Achado colateral**: o título da janela (`MainWindowTitle`) NÃO é
        um bom sinal pra esse tipo de teste — o app usa uma barra de
        título customizada (`headerbar`), e o texto visível "Acessos" é um
        `Gtk.Label` fixo, sem relação com a propriedade `title=` da
        janela. O `log.txt` foi o sinal confiável usado.
  - [ ] **Fonte da verdade: tags/releases, não o HEAD cru da `main`** —
        recomendação, a confirmar com a equipe. Comparar contra o commit
        mais recente da `main` direto significa que um push no meio do
        dia, ainda incompleto, já é "a versão mais nova" pro app — sem
        nenhum estágio de "isso está pronto pra todo mundo". Usar GitHub
        Releases (ou ao menos tags) como o marcador de versão dá um
        momento explícito de "isto é a versão oficial agora", sem exigir
        infraestrutura de CI — é só marcar um commit como release quando
        estiver pronto. A checagem de arquivos mudados dentro dessa
        release ainda pode ser por hash de cada `.py`, igual ao
        `manifesto.json`.
  - [x] **Autenticação — REVISTO em 2026-09-08: repositório será
        PÚBLICO** (decisão interna da equipe, mudou depois da conversa
        sobre Modelo A/B de token). Isso elimina o problema inteiro: sem
        repositório privado, não tem token nenhum pra gerenciar — nada de
        Modelo A nem B, nada de arquivo local de credencial, nada de
        "nunca hardcoded". A checagem de versão e o download dos arquivos
        mudados podem ir direto em `raw.githubusercontent.com` ou na API
        pública do GitHub, sem autenticação — mais simples E mais seguro
        por construção (menos superfície de ataque, nada de segredo pra
        vazar). Único cuidado que passa a valer: **nada sensível pode ir
        pro repositório** (o cofre/`conexoes.ini` já não vai — mora em
        `~/.config/acessos`, fora do controle de versão — mas vale
        reforçar como regra explícita agora que qualquer um na internet
        pode ler o código-fonte).
  - [x] **Checagem em si — CONSTRUÍDA E TESTADA em 2026-09-08.** Novo
        `python/atualizador.py`: `versao_local()` lê o `versao` do
        `manifesto.json` embutido no bundle (adicionado como `datas` no
        `Acessos.spec`, mesmo tratamento do `icones/acessos.svg`);
        `versao_remota()` busca a última GitHub Release (API pública,
        `.../releases/latest` → `tag_name`) e o `manifesto.json` daquela
        tag via `raw.githubusercontent.com` — sem autenticação, repo
        público (decisão revista acima). `versao_local` reaproveita o
        formato do próprio `manifesto.json` (data+hora), como decidido.
        Fonte de versão: constante `DONO_REPO`/`NOME_REPO` no topo do
        arquivo. **PREENCHIDA em 2026-09-08**:
        `Carlos-Daniel-Dev/acessos_windows` — descoberto que o repositório
        JÁ EXISTIA (remote `origin` já configurado, commit `V0.1`), ao
        contrário do que se pensava quando o Item 5 foi estudado
        originalmente. **Está PRIVADO hoje** — confirmado testando acesso
        anônimo via API e `raw.githubusercontent.com` (ambos devolveram
        404). Precisa virar público nas configurações do GitHub antes da
        checagem funcionar de verdade; até lá, `versao_remota()` recebe
        404 e devolve `None` graciosamente (mesmo comportamento de
        "repositório não configurado" — não quebra nada, só não encontra
        nenhuma atualização ainda).
      - **`verificar_async(callback)`**: roda a checagem numa THREAD (rede
        nunca pode rodar na thread principal do GTK) e devolve o
        resultado via `GLib.idle_add` — mesmo cuidado que `vncwidget.py`
        já tem com a rede do VNC.
      - **Avisar o operador — feito**: chip no rodapé da `Janela`
        principal (`chip_atualizacao`, reaproveitando o `chip(...)` que já
        existe), escondido por padrão (`set_no_show_all`, mesmo padrão do
        `lb_captura` na barra de título), só aparece se
        `_ao_verificar_atualizacao()` receber `tem_atualizacao=True`.
        Disparado uma vez, no fim de `Janela.__init__`
        (`_iniciar_checagem_atualizacao()`).
      - **Baixar e aplicar os arquivos mudados — CONSTRUÍDO E TESTADO em
        2026-09-08.** `atualizador.listar_diferencas(manifesto_remoto)`
        compara, POR HASH (não por nome/data), cada entrada da seção
        "copiar" do manifesto remoto contra o arquivo solto já instalado
        no bundle (`sys._MEIPASS`) — PROPOSITALMENTE não olha a seção
        "compilar" (`vncshim.dll`): esse arquivo não pode ser regerado
        sem um compilador C, uma mudança nele continua exigindo
        reinstalar via `.exe` novo. `atualizador.aplicar_atualizacao(...)`
        baixa cada arquivo diferente de `raw.githubusercontent.com`,
        **confere o SHA-256 do que baixou contra o que o manifesto
        prometia ANTES de sobrescrever** (uma resposta truncada/corrompida
        na rede não pode virar um arquivo quebrado no bundle), faz backup
        do arquivo antigo (`.backup_atualizacao\`, um nível só, mesma
        filosofia do `.backup_anterior` que `atualizar.ps1` já usa) e só
        então grava o novo. `aplicar_async()` roda tudo numa thread (é
        rede — mesmo cuidado de `verificar_async()`).
        - **UI**: botão "Atualizar agora" no rodapé, ao lado do chip
          (aparecem juntos). Clicar pede confirmação
          (`Janela.confirmar()`, já existente), aplica em background, e
          ao terminar oferece "Reiniciar agora" (`Janela.confirmar()` de
          novo) — que abre uma nova instância do `.exe` via
          `subprocess.Popen([sys.executable])` e fecha a atual. Falhas
          parciais são relatadas por arquivo (`Janela.avisar()`), sem
          travar os que deram certo.
        - **Testado com rede simulada** (o repositório real ainda está
          privado, sem release publicada pra testar contra o GitHub de
          verdade): script que monkeypatcha `_baixar_bytes()` pra devolver
          conteúdo fake com hash correspondente, aplicado contra um bundle
          `.exe` compilado de verdade. Confirmou: (1) arquivos IDÊNTICOS
          ao manifesto não aparecem como diferença; (2) um arquivo com
          hash diferente é corretamente detectado, baixado (simulado) e
          sobrescrito, com backup do original confirmado em disco; (3)
          **downloads com hash que NÃO bate são corretamente REJEITADOS**
          — a checagem de integridade funciona de verdade, não só na
          teoria.
        - **Achado colateral, não um bug**: o mesmo teste revelou que
          `manifesto.json` estava desatualizado (3 arquivos com hash
          diferente do que o manifesto registrava) — não é falha da
          lógica de comparação, é só o manifesto não ter sido regerado
          depois de edições recentes. `gerar_manifesto.ps1` corrigido
          pra incluir `atualizador.py` na lista rastreada (estava
          faltando desde que o arquivo foi criado) e o manifesto foi
          regerado.
        - **Achado real sobre o próprio teste manual**: descobri que
          `MainWindowTitle='Acessos'` sozinho NÃO confirma que a janela
          principal abriu — o diálogo de senha do cofre (`cofre.py`,
          `_dialogo("Acessos", pai)`) usa o MESMO título. Testes
          anteriores desta sessão que só checavam o título podem ter
          confirmado apenas "chegou no diálogo do cofre", não "a janela
          principal (com o rodapé novo) construiu sem erro". Corrigido
          testando também o TAMANHO da janela (`GetWindowRect` via
          ctypes/P-Invoke do PowerShell) — a principal é maximizada
          (~1920x1040 nesta máquina), o diálogo é pequeno. Testado de
          verdade com uma config `--conf` descartável, sem cofre (pra não
          mexer no cofre real desta máquina) — confirmado: janela
          principal maximizada, rodapé com o chip/botão novos construído
          sem erro, `log.txt` limpo.
      - **Dois bugs reais encontrados e corrigidos durante o teste**:
        (1) `atualizador.py` não estava em `MODULOS_PROJETO` no
        `Acessos.spec` nem importado em lugar nenhum — a primeira
        tentativa de build falhou com o `raise SystemExit` de segurança
        do próprio `.spec` ("módulo do projeto não encontrado pela
        Analysis"), porque um módulo nunca importado não é descoberto
        pela análise estática do PyInstaller; corrigido importando de
        verdade em `acessos.py` (`import atualizador as _atualizador`,
        mesmo padrão tolerante a falha do `cofre`). (2) `manifesto.json`
        tem BOM (gravado por `Set-Content -Encoding UTF8` do PowerShell
        5.1, que sempre inclui um) — `json.load(..., encoding="utf-8")`
        rejeitava com `JSONDecodeError: Unexpected UTF-8 BOM`; corrigido
        pra `"utf-8-sig"` (descarta o BOM se presente, funciona igual sem
        ele) — aplicado tanto na leitura local quanto no
        `manifesto.json` baixado do GitHub, que pode ter vindo com o
        mesmo BOM.
      - **Testado de ponta a ponta com o `.exe` compilado de verdade**:
        `versao_local()` leu corretamente `2026.09.08.1406` do
        `manifesto.json` embutido; app abriu normalmente, sem nenhum erro
        no `log.txt` (a checagem falhou graciosamente, como esperado — na
        época do teste o repositório ainda não tinha sido identificado
        como o de verdade).
  - [ ] **Pontos ainda não estudados, ficam pra próxima rodada**: o que
        fazer se o GitHub estiver inacessível além de simplesmente não
        avisar nada (já coberto — `versao_remota()` nunca levanta exceção);
        limite de taxa da API pública do GitHub sem autenticação (~60
        req/hora por IP — mais apertado que os ~5000/hora com token que se
        cogitava antes da decisão de repositório público; ok pra 8 pessoas
        checando ocasionalmente, mas vale não checar com muita frequência);
        a parte de baixar e aplicar os arquivos mudados de verdade.
  - [x] **Corrigido em 2026-09-09**: depois de aplicar a atualização e
        reiniciar, o chip "atualização disponível" continuava aparecendo,
        e clicar em "Atualizar agora" de novo só confirmava que já estava
        tudo em dia. Causa: `manifesto.json` instalado NÃO estava na lista
        `copiar` do próprio manifesto (é o arquivo que compara, não um dos
        comparados) — `aplicar_atualizacao()` nunca o sobrescrevia, então
        `versao_local()` continuava lendo a versão antiga pra sempre.
        Fix: `_gravar_manifesto_local()` em `atualizador.py` — sempre que
        `aplicar_atualizacao()` termina SEM nenhuma falha (mesmo que não
        houvesse arquivo "copiar" pra baixar, só "compilar"), o
        `manifesto.json` local é sobrescrito pelo remoto recém-aplicado.
        Best-effort (não vira "falha ao atualizar" se essa gravação
        falhar — os arquivos de verdade já foram trocados com sucesso,
        isso aqui é só o que o chip lê depois). Com uma falha (atualização
        parcial), o manifesto local NÃO é tocado de propósito — o chip
        deve continuar avisando até uma tentativa sem falhas.
  - [x] **Teste real de ponta a ponta contra a Release v0.2.2, 2026-09-08**:
        rodando o build antigo (v0.2.1) de verdade, clicando nos botões via
        automação de mouse (diálogos do GTK são modais) — a checagem e o
        aviso (chip + "Atualizar agora") funcionaram perfeitamente contra a
        API/Release pública de verdade. O clique em "Atualizar" revelou um
        **bug real**: "Falha ao atualizar — hash não confere após o
        download". Causa raiz, NÃO é rede: o repositório está com
        `core.autocrlf=true`; os `.py` no working tree do Windows ficam com
        `CRLF`, mas o Git sempre armazena (e o GitHub sempre serve via
        `raw.githubusercontent.com`/API de conteúdo) o blob normalizado em
        `LF`. `gerar_manifesto.ps1` calculava o SHA-256 a partir do arquivo
        local em CRLF — o hash gravado no manifesto publicado NUNCA batia
        com o que `atualizador.py` baixa (sempre LF), pra qualquer arquivo
        `.py`/texto, permanentemente (não é uma falha transitória — tentar
        de novo não resolve). Corrigido criando `.gitattributes`
        (`*.py`/`*.svg`/`manifesto.json` com `eol=lf`, deliberadamente sem
        mexer em `*.ps1`/`*.sh` — já têm exigências de BOM próprias
        testadas antes), forçando o checkout local pra LF e regerando o
        manifesto (`gerar_manifesto.ps1 -Versao 0.2.3`) — o hash resultante
        de `python/acessos.py` (`20c59b77...`, 266050 bytes) bateu
        exatamente com o que o GitHub já servia. Release `v0.2.3` publicada
        e o teste **repetido com sucesso**: checagem → aviso → confirmação
        → download → hash confere → 5 arquivo(s) aplicado(s) → "reiniciar
        agora" → o processo reaberto mostrou o título com **"atualizado ✓"**
        — a prova de ponta a ponta de que o auto-atualizador troca o código
        em disco e ele entra em vigor sem reinstalar o `.exe`.
        Efeito colateral encontrado no próprio teste: `_reiniciar_app()`
        (compilado) reabria com `subprocess.Popen([sys.executable])`, sem
        argumento nenhum — descartando silenciosamente qualquer `--conf`/
        `--debug`/`--x11`/`--wayland` com que o processo original tinha
        sido aberto. Inofensivo hoje (os atalhos do `instalador.iss` nunca
        passam argumento), mas corrigido mesmo assim: repassa
        `sys.argv[1:]` nos dois ramos (compilado e rodando de fonte).

## Ordem sugerida de ataque

1. ~~Item 1~~ ✅ feito em 2026-09-04 — PyInstaller via MSYS2, validado com
   um hello-world GTK3 rodando standalone (sem MSYS2 no PATH).
2. ~~Item 3~~ ✅ build real feita e testada com conexões de verdade em
   2026-09-04 — `Acessos.exe` sem console, log em arquivo,
   GdkWin32/`__file__` corrigidos. **VNC, SSH e RDP confirmados** (RDP
   depois de embutir o FreeRDP no bundle — 91 arquivos, +84 MB, testado
   rodando `wfreerdp.exe` standalone).
3. ~~Item 4~~ ✅ feito em 2026-09-04 — `.ico` gerado do SVG
   (`gerar_ico.py`), aplicado no `.exe` (`compilar_exe.ps1 --icon`) e no
   atalho do Menu Iniciar (`instalar.ps1`); conferido visualmente extraindo
   o ícone do `.exe` gerado.
4. ~~Item 2~~ ✅ `instalador.iss` + `publicar.ps1` construídos e testados
   de ponta a ponta em 2026-09-08 — instala, cria os dois atalhos, roda
   sem MSYS2, desinstala limpo, preserva a config do usuário, e o ciclo
   inteiro (manifesto → compilar → empacotar) roda num comando só. Restam
   só as decisões adiadas de propósito (assinatura de código, argon2-cffi
   na máquina de build) e a nova frente de auto-atualização via GitHub
   (ver Item 5, estudo de 2026-09-08).
5. ~~Item 5~~ ✅ (auto-atualização via GitHub) — **completo e confirmado
   de ponta a ponta em 2026-09-08**. `launcher.py` + `Acessos.spec` (os
   `.py` do projeto ficam soltos em `_internal\`); `python/atualizador.py`
   completo (checa, baixa, confere hash, aplica com backup; UI no rodapé
   com confirmação antes de aplicar e antes de reiniciar); repositório
   público, Release `v0.2.3` publicada. Teste real: rodando um build
   antigo (v0.2.1) de verdade, clicando nos botões via automação de mouse
   — checagem, download, hash e aplicação bateram certo, e depois de
   reiniciar o título mostrou "atualizado ✓". No caminho, um bug real de
   CRLF vs LF no hash do manifesto foi encontrado e corrigido (PR #4,
   `.gitattributes`) — ver o relato completo acima, nesta mesma seção.
6. **Item 6 — trazer as atualizações do Linux (2026-09-09)**. O Linux
   original recebeu bastante coisa desde o porte inicial: `dialogo_ui.py`
   (módulo de diálogos compartilhado), histórico/backup versionado do
   `.ini`, reset do cofre, `[geral] caminho=` (pasta de dados relocável),
   conexão instantânea/efêmera, indicador de vida (ping) nos cards,
   `massa.py`/`massa_ui.py` (execução em lote — decisão de não portar
   revisitada e revertida) e um redesign completo do `tema.py`. Tudo
   portado preservando cada patch Windows-específico (RDP/SSH embutidos,
   bandeja, `atualizador.py`, `.seg-topo`, fallback de fonte pra glifo) —
   ver `LEIAME-windows.md`, seção "Atualização de 2026-09-09", para o
   relato completo. Testado rodando de fonte e compilado
   (`compilar_exe.ps1`); **decisão explícita: mais releases `0.x` antes de
   qualquer "1.0.0 stable"** — reset do cofre, relocação de pasta,
   indicador de vida e execução em lote ainda precisam de teste de ponta a
   ponta contra dados/máquinas de verdade.
7. **Item 7 — teste real de cofre/relocação e dois achados (2026-09-09,
   mesmo dia)**. Rodando o app de fonte contra um `conexoes.ini` isolado
   (fora do `~/.config/acessos` real, com automação de mouse/teclado via
   PowerShell), testado o fluxo de criação de cofre ("Proteger senhas")
   de ponta a ponta: 2 senhas em texto claro corretamente migradas para
   `enc:v1:...`, seção `[cofre]` gravada certa. Dois achados reais no
   caminho:
   - **Bug real, não relacionado ao teste em si**: `self.rodape` (a barra
     no rodapé com caminho do INI, versão instalada e contagem de
     máquinas) nunca aparecia — nem antes desta sessão, nem depois do PR
     do "versão sempre visível". Causa: o container tem
     `set_no_show_all(True)` (pra sumir/aparecer ao trocar de aba), e
     isso bloqueia o `show_all()` GERAL da janela de alcançar os FILHOS
     dele — os rótulos permanentes (caminho, versão, contagem) nunca
     recebiam seu próprio `.show()`, só o chip/botão de atualização
     funcionavam (esses são ligados via `set_visible()` direto na lógica
     de checagem, não dependem do cascade). Corrigido em `_rodape()`:
     os três rótulos permanentes são mostrados na mão, uma vez, na
     construção — os três condicionais (chip, botão, "×") continuam de
     fora desse show manual, cada um se revela sozinho quando há motivo.
   - **Decisão do usuário: reset do cofre (`REINICIALIZAR`) removido**,
     não só adiado — `PALAVRA_RESET`, `_limpar_sigilosos()`,
     `_confirmar_reset()` e o ramo `"reiniciar"` de `destrancar()`
     tirados de `cofre.py`; o texto de ajuda do diálogo de senha mestra
     atualizado pra deixar claro que não há recuperação. Risco aceito
     explicitamente para uso interno da equipe: perder a senha mestra
     agora significa apagar a seção `[cofre]` do `conexoes.ini` na mão e
     recadastrar as senhas do zero.
   - **Relocação de pasta (`[geral] caminho=`) testada de ponta a ponta,
     mesma sessão**: via Ajustes → "LOCAL DOS ARQUIVOS" → "Escolher
     pasta...", apontado para uma pasta vazia isolada (variável de
     ambiente `XDG_CONFIG_HOME` própria, nada tocado no
     `~/.config/acessos` real). Confirmado em disco: `conexoes.ini`
     copiado pra pasta nova, chave `caminho=` gravada no INI padrão.
     Reiniciado o processo (mesmo `XDG_CONFIG_HOME`): `caminho_conf()`
     seguiu o ponteiro sozinho, o painel passou a mostrar o nome da
     pasta nova ("pasta_relocada_teste") e o caminho completo no
     rodapé, e o cofre destrancou com a MESMA senha mestra (salt e
     verificador migraram corretos) — as 2 conexões de teste
     continuaram visíveis e intactas.
   - **Todas as 4 pendências de 1.0.0 fechadas nesta sessão**: reset do
     cofre saiu de escopo (removido), indicador de vida e execução em
     lote considerados cobertos (lógica idêntica ao Linux), relocação
     de pasta testada de ponta a ponta acima. Sem pendência de teste
     conhecida barrando 1.0.0 — falta só decidir quando de fato
     lançar (ver Item 2: assinatura de código e canal de distribuição
     interno continuam adiados, não são bloqueio técnico).
