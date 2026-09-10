# Acessos — Windows

Tela (VNC), shell (SSH) e RDP da mesma máquina, em abas, mais execução de
comandos em lote no parque inteiro — numa única janela, sem depender de
mais nada instalado além do próprio Acessos.

Este repositório é o **porte para Windows** do Acessos original (Linux),
feito em GTK3 + PyGObject via MSYS2, empacotado como um `.exe` standalone
(PyInstaller) com instalador próprio (Inno Setup) e auto-atualização via
GitHub Releases.

## Instalação

Duas formas, dependendo de quem você é:

- **Uso normal (equipe)**: baixe o instalador da [última release](../../releases/latest)
  (`AcessosSetup-X.Y.Z.exe`) e rode — sem admin, sem MSYS2, sem nada para
  instalar à parte. Cria atalho no Menu Iniciar e na Área de Trabalho.
- **De fonte / desenvolvimento**: `.\instalar.ps1` na raiz deste repositório
  (Windows 10 1809+ ou 11). Ele mesmo garante o MSYS2 e os pacotes
  necessários (GTK3, PyGObject, FreeRDP...). Veja `instalar.ps1 -?` para as
  opções (`-Verificar`, `-Remover`, `-Remover -LimparConfig`...).

## Funcionalidades

- Tela (VNC), shell (SSH) e RDP embutidos na mesma janela, em abas
- Cofre de senhas (cifrado, senha mestra separada do restante do arquivo)
- Execução de comandos em lote via SSH num grupo de máquinas (desligada por
  padrão — veja `massa_ativa` no `conexoes.ini`)
- Importador de exports CSV do Devolutions Remote Desktop Manager
- Temas Claro/Escuro/Rosé, com opção de fonte maior
- Histórico/backup automático do `conexoes.ini`, pasta de dados relocável
- Auto-atualizador: avisa quando há uma versão nova no GitHub e aplica sob
  confirmação, sem precisar reinstalar o `.exe` inteiro

## Documentação

- [`LEIAME-windows.md`](LEIAME-windows.md) — o que mudou em relação ao
  projeto original, decisões técnicas e changelog detalhado do porte
- [`BACKLOG-exe.md`](BACKLOG-exe.md) — histórico do empacotamento
  (PyInstaller, instalador, auto-atualização) e o que falta

## Licença

[GNU GPLv3](LICENSE) — mesma licença do projeto original. Este porte não é
um projeto independente: é uma adaptação do Acessos original para Windows,
e segue coberto pelos mesmos termos.

Copyright (C) 2026 Jurandir Moratelli.
