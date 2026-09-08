; instalador.iss — instalador único do Acessos, via Inno Setup.
;
; Empacota a pasta dist_exe\Acessos\ JÁ PRONTA (produzida numa máquina de
; build por compilar_exe.ps1) — este script não compila nada, não sabe que
; MSYS2 existe, só extrai arquivos e cria atalhos. Ver BACKLOG-exe.md,
; Item 2 — decisão de 2026-09-08 (build uma vez, instalador distribui o
; binário pronto; Inno Setup escolhido no lugar de NSIS pela legibilidade).
;
; PRÉ-REQUISITO: rodar .\compilar_exe.ps1 antes, pra existir
; dist_exe\Acessos\Acessos.exe pra este script empacotar.
;
; COMPILAR:
;     & "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" instalador.iss
;
; VERSÃO: passada de fora via /DAppVersion=X.Y.Z (pensado pra publicar.ps1
; ler do manifesto.json e repassar); sem isso, cai num valor de
; desenvolvimento óbvio, pra nunca compilar "sem querer" com uma versão
; que pareça de produção.
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

[Setup]
; AppId FIXO: é o que permite ao Inno Setup reconhecer "isto já está
; instalado, isto é uma atualização" em vez de tratar cada instalação como
; um programa novo e diferente. NUNCA gerar de novo depois que a primeira
; versão real for distribuída. O "{{" (chave dobrada) é a forma do Inno
; escapar uma chave literal — sem isso ele tenta interpretar o GUID como
; uma constante interna (tipo {app}, {group}) e a compilação falha.
AppId={{ed9d32b6-0a74-44b1-9fbe-32becd35bdba}
AppName=Acessos
AppVersion={#AppVersion}
AppPublisher=Machadão
DefaultDirName={localappdata}\Acessos
; SEM ADMIN — mesma filosofia do instalar.ps1 de hoje ("instala no perfil
; do usuário, sem precisar de admin"). Ver decisão no BACKLOG-exe.md.
PrivilegesRequired=lowest
DefaultGroupName=Acessos
DisableProgramGroupPage=yes
OutputDir=dist_instalador
OutputBaseFilename=AcessosSetup-{#AppVersion}
SetupIconFile=icones\acessos.ico
UninstallDisplayIcon={app}\Acessos.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; a pasta dist_exe\Acessos\ já vem com tudo (~120-206 MB) — nada aqui pede
; conexão de internet nem baixa nada, então SetupLogging so ajuda a
; diagnosticar problema de instalação, não de rede
SetupLogging=yes

[Languages]
Name: "brportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
; recursesubdirs: leva a pasta _internal\ inteira (DLLs, typelibs, o
; libvncshim.dll, o FreeRDP embutido se compilar_exe.ps1 tiver incluído).
; ignoreversion: os arquivos do bundle não têm version resource própria
; pra maioria (typelibs, .dll de terceiros do MSYS2) — comparar por data
; e sobrescrever sempre é mais previsível que o Inno tentar decidir sozinho
; qual é "mais nova" por versão de arquivo.
Source: "dist_exe\Acessos\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
; os DOIS: Menu Iniciar (instalar.ps1 já fazia isso) e Área de Trabalho
; (pedido explícito — não existia em lugar nenhum até este instalador).
; O ícone vem do próprio .exe — compilar_exe.ps1 já embute icones\acessos.ico
; nele (--icon), então não precisa apontar pra um arquivo .ico separado.
Name: "{group}\Acessos"; Filename: "{app}\Acessos.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Acessos"; Filename: "{app}\Acessos.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
; desmarcável: quem não quiser poluir a área de trabalho pode desligar na
; tela do instalador — mas vem marcado por padrão, já que foi pedido
; explicitamente como parte da experiência de instalação.
Name: "desktopicon"; Description: "Criar um atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"

[Run]
Filename: "{app}\Acessos.exe"; Description: "Abrir o Acessos agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; TESTADO NA PRÁTICA (duas rodadas): sem isto, o desinstalador (que só
; remove o que ELE mesmo instalou) deixava pra trás o log.txt/
; log.anterior.txt que o app escreve em {app} em tempo de execução
; (_preparar_saida_sem_console em acessos.py) — a pasta não ficava vazia.
; A primeira tentativa foi "Type: filesandordirs; Name: {app}" (apagar a
; pasta toda) — não funcionou: nesse ponto do desinstalador o unins000.exe/
; .dat AINDA estão rodando de dentro de {app} (o Inno só os move pra um
; temp e apaga depois, no fim de tudo), então a pasta não conseguia ser
; removida por inteiro. A receita que funcionou é mirar só os arquivos
; especificos que o APP (não o instalador) cria em tempo de execução — o
; resto do {app} some sozinho pelo mecanismo padrão do Inno, que tenta
; remover a pasta no final se ela ficar vazia.
Type: files; Name: "{app}\log.txt"
Type: files; Name: "{app}\log.anterior.txt"
