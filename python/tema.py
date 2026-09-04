#!/usr/bin/env python3
"""Tema, paleta e folha de estilo do Acessos.

Aqui mora tudo o que é aparência: as cores de cada tema, as famílias de
fonte e o CSS. Separado do acessos.py porque são 500+ linhas de folha de
estilo — conteúdo que não é lógica de programa e que só se mexe quando o
assunto é interface.

Quem usa:
    tema.gerar_css("escuro")     -> bytes, para o CssProvider
    tema.TEMAS["escuro"]["fundo"]
    tema.rgba("#112233")         -> Gdk.RGBA
    tema.fonte_mono(11)          -> Pango.FontDescription
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango  # noqa: E402


# ---------------------------------------------------------------- temas

ACENTOS = ["#d2d6e6", "#0ca678", "#e8590c", "#ae3ec9", "#1098ad", "#d6336c"]

TEMAS = {
    "claro": dict(
        fundo="#f4f6f8", cartao="#ffffff", borda="#e3e8ec", borda2="#cfd6dd",
        texto="#11161a", sec="#5d6b78", fraco="#93a1ad",
        topo1="#171c22", topo2="#242c35",
        topo_txt="#ffffff", topo_sec="#aab6c2",
        vidro="rgba(255,255,255,0.08)", vidro_h="rgba(255,255,255,0.16)",
        vidro_b="rgba(255,255,255,0.14)",
        palco="#0b0f14", term_bg="#0d1117", term_fg="#d7dee6",
        sel="#11161a", sel_txt="#ffffff",
        hover="#eef2f5", campo="#ffffff",
        ok_bg="#dcf5ec", ok_fg="#0b7a63",
        erro_bg="#fde4e4", erro_fg="#b02a37", erro_h="#8d1f2a",
        neutro_bg="#eaeef1", neutro_fg="#5d6b78",
        atencao_bg="#fdf1d8", atencao_fg="#8a5a00",
        acao="#11161a", acao_txt="#ffffff", acao_hover="#2b333c",
        azul="#4c6ef5", azul_h="#3b5bdb", verde="#0ca678",
        hero1="#171c22", hero2="#2b3a4a", hero_txt="#ffffff",
    ),
    "escuro": dict(
        fundo="#0f1216", cartao="#171b21", borda="#242a32", borda2="#333b45",
        texto="#e8edf2", sec="#9aa6b2", fraco="#6d7a86",
        topo1="#080a0d", topo2="#12171d",
        topo_txt="#ffffff", topo_sec="#9aa6b2",
        vidro="rgba(255,255,255,0.06)", vidro_h="rgba(255,255,255,0.13)",
        vidro_b="rgba(255,255,255,0.10)",
        palco="#06080a", term_bg="#0d1117", term_fg="#d7dee6",
        sel="#e8edf2", sel_txt="#0f1216",
        hover="#1e242b", campo="#171b21",
        ok_bg="#0d2f28", ok_fg="#4fd1b0",
        erro_bg="#341a1e", erro_fg="#c9414d", erro_h="#e05561",
        neutro_bg="#1e242b", neutro_fg="#9aa6b2",
        atencao_bg="#332810", atencao_fg="#e0b458",
        acao="#e8edf2", acao_txt="#0f1216", acao_hover="#ffffff",
        azul="#748ffc", azul_h="#91a7ff", verde="#38d9a9",
        hero1="#0b0e12", hero2="#1c2733", hero_txt="#ffffff",
    ),
}

# ---------------------------------------------------------------------
# FONTES DE SIMBOLO — por que esta lista existe
#
# Os icones do Acessos NAO sao imagens: sao CARACTERES (⚙ U+2699,
# 👁 U+1F441, 📁, 🚫, ⚡, ⌨, ⧉, ⟳, ＋). Se nenhuma familia da pilha
# tiver o glifo, o Pango desenha o retangulo vazio — foi o que aconteceu
# com a engrenagem e o olho no Windows: nem Calibri nem IBM Plex
# (que nao esta instalada la) trazem esses pontos de codigo.
#
# O Pango faz fallback POR GLIFO percorrendo a pilha, entao basta anexar
# as fontes de simbolo do sistema no FIM: o texto normal continua saindo
# na fonte escolhida e so os glifos ausentes caem nelas.
#   Segoe UI Symbol  -> simbolos monocromaticos (⚙ ⌨ ⧉ ⟳ ▾)
#   Segoe UI Emoji   -> os emoji coloridos (👁 📁 🚫 ⚡)
#   Segoe Fluent Icons / Segoe MDL2 Assets -> reserva no Windows 10/11
# As duas ultimas do Linux (DejaVu/Noto) ficam para o mesmo arquivo
# servir nas duas plataformas.
# ---------------------------------------------------------------------
SIMBOLOS = ('"Segoe UI Symbol", "Segoe UI Emoji", "Segoe Fluent Icons", '
            '"Segoe MDL2 Assets", "Noto Color Emoji", '
            '"Noto Sans Symbols 2", "DejaVu Sans"')

MONO = ('"IBM Plex Mono", "Consolas", "DejaVu Sans Mono", monospace, '
        + SIMBOLOS)
SANS = '"Calibri", Times, serif, ' + SIMBOLOS
COND = '"Calibri", Times, serif, ' + SIMBOLOS

# ---------------------------------------------------------------------
# APARENCIA — os tres botoes de ajuste ficam aqui, juntos, de proposito.
#
# ESCALA_FONTE e ESCALA_GLIFO nao sao aplicadas regra por regra: o
# gerar_css() multiplica TODO "font-size: Npx" da folha no fim. Assim
# nao ha risco de esquecer uma regra e ficar com dois tamanhos brigando
# — foi por isso que virou fator, e nao 45 numeros editados a mao.
#
# ESCALA_FONTE  1.0 = tamanhos originais; 1.15 = 15% maior. Este e o
#               tamanho PADRAO do programa (o "atual" da opcao de fonte
#               grande, ver ESCALA_FONTE_GRANDE logo abaixo).
# ESCALA_FONTE_GRANDE  multiplicador extra sobre ESCALA_FONTE quando o
#               usuario liga a opcao "fonte grande" (bt_fonte, em
#               acessos.py). 1.5 = mais 50% em cima do tamanho padrao,
#               nao em cima do tamanho original do CSS.
# ESCALA_GLIFO  vale para os icones-glifo (⌨ ⧉ 📁 ＋ ...), que sao TEXTO
#               e portanto tambem crescem por font-size. Multiplica em
#               cima da escala de fonte efetiva (padrao ou grande).
# TAMANHO_ICONE_IMAGEM  para os poucos icones que sao Gtk.Image de
#               verdade (o ⌂ da barra), medidos em Gtk.IconSize.
# ---------------------------------------------------------------------
ESCALA_FONTE = 1.15
ESCALA_FONTE_GRANDE = 1.5
ESCALA_GLIFO = 1.30

# MONO NAO recebe Times de proposito: o terminal SSH e o painel de log
# alinham em COLUNAS. Uma fonte proporcional ali desalinharia tabelas,
# barras de progresso e qualquer saida de programa de tela cheia (htop,
# nano) — e o pyte, que desenha o terminal no Windows, assume celula de
# largura fixa. Times entra em tudo o que e texto de interface (titulos,
# nomes, botoes, rotulos); o que e saida de maquina segue monoespacado.

CSS_MOLDE = """
window, .fundo { background-color: %(fundo)s; color: %(texto)s; }

/* ---------------- titlebar de vidro ----------------
   O GTK3 nao tem backdrop-filter. O efeito vem de camadas translucidas
   sobre um gradiente escuro: sem sombra, sem relevo, so luz. */
headerbar.integrada {
    background-image: linear-gradient(180deg, %(topo1)s 0%%, %(topo2)s 100%%);
    background-color: %(topo1)s;
    border: none;
    box-shadow: none;
    min-height: 34px;
    padding: 0px 6px;
}
headerbar.integrada > * { box-shadow: none; text-shadow: none; }

.marca-topo { color: %(topo_txt)s; font-family: """ + COND + """; font-size: 13px; font-weight: 600; }
.marca-sub  { color: %(topo_sec)s; font-family: """ + MONO + """; font-size: 10px; }

.btn-topo {
    background-image: none;
    background-color: %(vidro)s;
    color: %(topo_sec)s;
    border: 1px solid %(vidro_b)s;
    border-radius: 6px;
    padding: 2px 8px;
    min-height: 0px; min-width: 0px;
    box-shadow: none; text-shadow: none;
    font-family: """ + MONO + """; font-size: 10px;
    transition: background-color 140ms ease, color 140ms ease;
}
.btn-topo:hover   { background-color: %(vidro_h)s; color: %(topo_txt)s; }
.btn-topo:active,
.btn-topo:checked { background-color: %(vidro_h)s; color: %(topo_txt)s; border-color: %(topo_txt)s; }

.btn-janela {
    background-image: none; background-color: transparent;
    color: %(topo_sec)s; border: none; border-radius: 6px;
    padding: 2px 9px; min-height: 0px; min-width: 0px;
    box-shadow: none; text-shadow: none;
    font-family: """ + MONO + """; font-size: 12px;
    transition: background-color 140ms ease;
}
.btn-janela:hover { background-color: %(vidro_h)s; color: %(topo_txt)s; }
.btn-fechar:hover { background-color: #d13438; color: #ffffff; }

/* ---------------- texto ---------------- */
.rotulo     { color: %(sec)s;   font-family: """ + MONO + """; font-size: 10px; }
.secundario { color: %(sec)s;   font-family: """ + MONO + """; font-size: 11px; }
.fraco      { color: %(fraco)s; font-family: """ + MONO + """; font-size: 10px; }
.mono       { color: %(texto)s; font-family: """ + MONO + """; font-size: 12px; }
.titulo-secao {
    color: %(fraco)s; font-family: """ + MONO + """;
    font-size: 10px; font-weight: 600;
}

.cartao { background-color: %(cartao)s; border: 1px solid %(borda)s; border-radius: 6px; }

/* dialogos: sem isto o corpo fica com a cor crua do tema do sistema e o
   conjunto vira uma colcha de retalhos */
/* GTK3: GtkDialog tem no CSS chamado "window" com classe ".dialog" — nao
   existe elemento de tipo "dialog". Selecionar por "dialog X" nunca casava
   com nada; o fallback era sempre o tema do sistema. Por isso a classe
   propria .acessos-dialogo, aplicada a mao em cada Gtk.Dialog criado. */
/* corpo, blocos e campos na MESMA cor: a separacao vem das bordas, nao de
   tres tons diferentes competindo entre si */
dialog, .acessos-dialogo box, .acessos-dialogo .fundo, .acessos-dialogo scrolledwindow, .acessos-dialogo viewport {
    background-color: %(cartao)s; color: %(texto)s;
}
.acessos-dialogo label { color: %(texto)s; }
.acessos-dialogo entry {
    min-height: 28px;
    background-color: %(cartao)s;
    color: %(texto)s;
    border: 1px solid %(borda2)s;
}
.acessos-dialogo entry:focus { border-color: %(azul)s; }

/* cabecalho do dialogo: liso, mesma cor do corpo. Um gradiente proprio aqui
   destoava de tudo e parecia um enxerto de outro programa. */
.acessos-dialogo headerbar {
    background-image: none;
    background-color: %(cartao)s;
    border: none; border-bottom: 1px solid %(borda)s;
    box-shadow: none; min-height: 40px; padding: 0px 8px;
}
.acessos-dialogo headerbar .title, .acessos-dialogo headerbar > box > label {
    color: %(texto)s;
    font-family: """ + COND + """; font-size: 15px; font-weight: 600;
}

/* O GTK aplica seu proprio estilo a botoes dentro de headerbar e vence a
   classe .acao: o fundo ficava escuro com a letra tambem escura. Estas
   regras sao mais especificas e reescrevem cor de fundo E de texto,
   inclusive a do label interno. */
.acessos-dialogo headerbar button {
    background-image: none;
    box-shadow: none; text-shadow: none;
}
.acessos-dialogo headerbar button.acao,
.acessos-dialogo button.acao {
    background-color: %(azul)s;
    border: 1px solid %(azul)s;
}
.acessos-dialogo headerbar button.acao label,
.acessos-dialogo button.acao label {
    color: #ffffff;
    background-color: transparent;
}
.acessos-dialogo headerbar button.acao:hover,
.acessos-dialogo button.acao:hover { background-color: %(azul_h)s; border-color: %(azul_h)s; }

.acessos-dialogo headerbar button:not(.acao),
.acessos-dialogo .area-acao button:not(.acao) {
    background-color: %(cartao)s;
    border: 1px solid %(borda2)s;
}
.acessos-dialogo .area-acao { background-color: %(cartao)s; border-top: 1px solid %(borda)s; }
.acessos-dialogo headerbar button:not(.acao) label,
.acessos-dialogo .area-acao button:not(.acao) label { color: %(texto)s; }
.acessos-dialogo headerbar button:not(.acao):hover,
.acessos-dialogo .area-acao button:not(.acao):hover { background-color: %(hover)s; }

/* botoes na area de acao (dialogos sem headerbar, como o de confirmacao) */
.acessos-dialogo .area-acao button {
    background-image: none; box-shadow: none;
}

/* combo e switch dentro do dialogo */
.acessos-dialogo combobox, .acessos-dialogo combobox box, .acessos-dialogo combobox entry {
    background-color: %(cartao)s; color: %(texto)s;
}
.acessos-dialogo combobox button {
    background-image: none; background-color: %(cartao)s;
    color: %(texto)s; border: 1px solid %(borda2)s; border-radius: 6px;
    box-shadow: none; min-height: 28px;
}
.acessos-dialogo combobox button label { color: %(texto)s; }
.acessos-dialogo combobox entry { border-right-width: 0px; }
/* O container nao precisa de moldura: com corpo e blocos na mesma cor, a
   borda externa so criava um retangulo solto. Quem delimita e o campo. */
.bloco {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
}
.bloco entry {
    background-color: %(cartao)s;
    border: 1px solid %(borda2)s;
    border-radius: 6px;
}
.bloco-cab {
    color: %(sec)s; font-family: """ + MONO + """;
    font-size: 10px; font-weight: 600;
}
.bloco-off { opacity: 0.45; }
.dica { color: %(fraco)s; font-family: """ + MONO + """; font-size: 9px; }
.regua  { min-height: 2px; }

/* ---------------- chips ---------------- */
.chip {
    font-family: """ + MONO + """; font-size: 10px; font-weight: 600;
    border-radius: 4px; padding: 2px 7px;
}
.chip-ok      { background-color: %(ok_bg)s;      color: %(ok_fg)s; }
.chip-erro    { background-color: %(erro_bg)s;    color: %(erro_fg)s; }
.chip-neutro  { background-color: %(neutro_bg)s;  color: %(neutro_fg)s; }
.chip-atencao { background-color: %(atencao_bg)s; color: %(atencao_fg)s; }

/* ---------------- botoes ---------------- */
/* Em qualquer botao com filho Label o GTK pinta o LABEL, e a cor da classe
   no botao e ignorada — foi o que produziu preto sobre preto. Toda regra de
   cor aqui vale para o botao E para o label interno. */
.acao {
    background-image: none; background-color: %(acao)s; color: %(acao_txt)s;
    border: 1px solid %(acao)s; border-radius: 6px;
    padding: 5px 12px; min-height: 0px; box-shadow: none;
    font-family: """ + SANS + """; font-size: 12px; font-weight: 600;
    transition: background-color 140ms ease;
}
.acao label            { color: %(acao_txt)s; background-color: transparent; }
/* O anel de foco do GTK3 e um outline TRACEJADO desenhado sobre o rotulo.
   "outline: none" nao basta em todos os temas: quem desliga de fato e
   outline-style, e ele precisa valer tambem para o label interno e para o
   estado de foco. */
button, button label,
button:focus, button:focus label,
button:hover, button:active, button:checked,
.acessos-dialogo button, .acessos-dialogo button label,
.acessos-dialogo button:focus, .acessos-dialogo button:focus label {
    outline-style: none;
    outline-width: 0px;
    outline-color: transparent;
    outline-offset: 0px;
    -gtk-outline-radius: 0px;
    /* O tema (Adwaita) desenha um text-shadow sutil no texto de botoes com
       fundo solido — e o "borrao"/sombra suave no "Tela"/"RDP" dos cards.
       So tinha sido zerado para botoes DE DIALOGO ("ULTIMA PALAVRA" mais
       abaixo); faltava aqui, no bloco que vale para o app inteiro. */
    text-shadow: none;
}
/* Alem do outline, o tema desenha um box-shadow inset no botao com foco —
   e ele que produz o retangulo escuro DENTRO do azul. */
button:focus, button:hover, button:active, button:checked,
.acessos-dialogo button, .acessos-dialogo button:focus, .acessos-dialogo button:hover,
.acessos-dialogo button:active, .acessos-dialogo headerbar button:focus {
    box-shadow: none;
}
/* O botao de resposta padrao ganha a moldura propria do tema — e ela que
   sobrava em volta de "Salvar" enquanto "Cancelar" ficava limpo.
   ATENCAO: no GTK3 isto e a CLASSE .default, nao a pseudo-classe :default,
   que nao existe e faz o CssProvider recusar a folha inteira. */
button.default, button.default label,
.acessos-dialogo button.default, .acessos-dialogo button.default label,
.acessos-dialogo headerbar button.default {
    box-shadow: none;
    outline-style: none;
    outline-width: 0px;
    outline-color: transparent;
}
.acessos-dialogo button.acao.default,
.acessos-dialogo headerbar button.acao.default {
    background-color: %(azul)s;
    border: 1px solid %(azul)s;
}
.acessos-dialogo button.acao:focus,
.acessos-dialogo button.acao.default:focus { border-color: %(azul)s; }

/* mesma geometria em todos os botoes de dialogo: sem isto o primario da
   headerbar usava padding diferente do .perigo e um parecia maior */
.acessos-dialogo headerbar button, .acessos-dialogo .area-acao button, .acessos-dialogo button {
    padding: 5px 12px;
    border-radius: 6px;
    min-height: 0px;
    font-family: """ + SANS + """; font-size: 12px; font-weight: 600;
}

/* negacao e desfazimento: vermelho com texto legivel */
.perigo {
    background-image: none;
    background-color: %(erro_fg)s;
    border: 1px solid %(erro_fg)s;
    border-radius: 6px;
    padding: 5px 12px; min-height: 0px; box-shadow: none;
    font-family: """ + SANS + """; font-size: 12px; font-weight: 600;
    transition: background-color 140ms ease;
}
.perigo.default, .perigo.default label { box-shadow: none; outline-style: none; }
.perigo label          { color: #ffffff; background-color: transparent; }
.perigo:hover          { background-color: %(erro_h)s; border-color: %(erro_h)s; }
.perigo:hover label    { color: #ffffff; }
.perigo:focus          { box-shadow: none; }   /* nao mexe em borda: mudaria o tamanho */
.acessos-dialogo button.perigo,
.acessos-dialogo .area-acao button.perigo,
.acessos-dialogo headerbar button.perigo {
    background-color: %(erro_fg)s;
    border: 1px solid %(erro_fg)s;
}
.acessos-dialogo button.perigo label,
.acessos-dialogo .area-acao button.perigo label,
.acessos-dialogo headerbar button.perigo label { color: #ffffff; }
.acessos-dialogo button.perigo:hover,
.acessos-dialogo .area-acao button.perigo:hover,
.acessos-dialogo headerbar button.perigo:hover {
    background-color: %(erro_h)s; border-color: %(erro_h)s;
}
.acao:hover            { background-color: %(acao_hover)s; }  /* so cor */
.acao:hover label      { color: %(acao_txt)s; }
.acao:disabled         { background-color: %(borda)s; border-color: %(borda)s; color: %(fraco)s; }
.acao:disabled label   { color: %(fraco)s; }

.secundaria label      { color: %(texto)s; background-color: transparent; }
.secundaria:disabled label { color: %(fraco)s; }
.tog label             { color: inherit; background-color: transparent; }
.seg label             { color: inherit; background-color: transparent; }
.btn-topo label        { color: inherit; background-color: transparent; }
.btn-janela label      { color: inherit; background-color: transparent; }

.secundaria {
    background-image: none; background-color: %(cartao)s; color: %(texto)s;
    border: 1px solid %(borda2)s; border-radius: 5px;
    padding: 1px 9px; min-height: 0px; box-shadow: none;
    font-family: """ + MONO + """; font-size: 11px;
    transition: background-color 140ms ease;
}
.secundaria:hover    { background-color: %(hover)s; }
.secundaria:disabled { color: %(fraco)s; }

/* toggles semanticos: apagado = inativo */
.tog {
    background-image: none; background-color: %(cartao)s;
    border: 1px solid %(borda2)s; border-radius: 5px;
    padding: 1px 8px; min-height: 0px; color: %(fraco)s; box-shadow: none;
    font-family: """ + MONO + """; font-size: 11px;
    font-weight: 600;   /* fixo: variar por estado mudava a metrica do texto
                           e podia disparar laco de realocacao */
    transition: background-color 140ms ease, color 140ms ease;
}
.tog:hover { background-color: %(hover)s; }
/* glifo isolado precisa de corpo maior que o texto, mas sem inflar a barra */
.tog-glifo { font-size: 14px; padding: 0px 8px; min-height: 0px; }
.tog-bloq:checked, .tog-bloq:checked:hover {
    background-color: %(erro_bg)s; border-color: %(erro_fg)s;
    color: %(erro_fg)s;
}
.tog-ok:checked, .tog-ok:checked:hover {
    background-color: %(ok_bg)s; border-color: %(ok_fg)s;
    color: %(ok_fg)s;
}

/* ---------------- segmentado (substitui o ComboBox) ---------------- */
.seg {
    background-image: none; background-color: %(cartao)s;
    color: %(sec)s; border: 1px solid %(borda2)s;
    border-radius: 0px; padding: 1px 9px; min-height: 0px;
    box-shadow: none; font-family: """ + MONO + """; font-size: 11px;
    font-weight: 600;   /* fixo: variar por estado mudava a metrica do texto
                           e disparava laco de realocacao dentro de dialogos */
    transition: background-color 140ms ease, color 140ms ease;
}
.seg:hover { background-color: %(hover)s; }
.seg:checked, .seg:checked:hover {
    background-color: %(acao)s; color: %(acao_txt)s; border-color: %(acao)s;
}
.seg-ini { border-top-left-radius: 6px; border-bottom-left-radius: 6px; }
.seg-fim { border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
.seg-meio { border-left-width: 0px; border-right-width: 0px; }

/* ---------------- areas ---------------- */
.palco { background-color: %(palco)s; }
.log, .log text {
    background-color: %(term_bg)s; color: %(term_fg)s;
    font-family: """ + MONO + """; font-size: 11px;
    /* caret-color NAO herda de `color` no GTK3: sem declarar, o cursor
       fica na cor do tema (escura) sobre o fundo escuro do terminal e
       some. Aparecia como "campo sem cursor" ao editar o comando. */
    caret-color: %(term_fg)s;
    -gtk-secondary-caret-color: %(term_fg)s;
}
.lista { background-color: %(cartao)s; color: %(texto)s; }
.lista:selected { background-color: %(sel)s; color: %(sel_txt)s; }
entry {
    background-image: none; background-color: %(campo)s; color: %(texto)s;
    border: 1px solid %(borda2)s; border-radius: 6px; box-shadow: none;
}
notebook > header { background-color: %(fundo)s; border-color: %(borda)s; }
notebook > header > tabs > tab {
    background-color: transparent; color: %(sec)s;
    border-color: %(borda)s; padding: 3px 8px; min-height: 0px;
}
notebook > header > tabs > tab:checked { background-color: %(cartao)s; color: %(texto)s; }


/* fechar-aba e um EventBox, nao um Gtk.Button: a classe ".flat" que o tema
   aplica em botoes com relief NONE carregava padding/min-size proprios que
   competiam com este CSS. Sem fundo nem borda — o hover e so a cor e o
   peso do "×", trocados na mao via enter/leave (a pseudo-classe :hover do
   CSS nao e garantida em EventBox como e em Button). */
.fechar-aba {
    background-image: none;
    background-color: transparent;
    border: 1px solid transparent;
    padding: 0px;
    min-height: 16px;
    min-width: 16px;
    box-shadow: none;
}
.fechar-aba-x {
    font-family: """ + SANS + """;
    font-size: 11px;
    /* peso 700 FIXO nos dois estados. Eu tinha posto 600 normal e 800 no
       hover: pesos diferentes mudam a metrica do glifo, o "×" fica mais
       largo, e a aba inteira muda de tamanho ao passar o mouse. Mesma
       regra dos botoes — estado so pode mexer em COR. */
    font-weight: 700;
    color: %(fraco)s;
}
.fechar-aba-x-hover {
    color: %(erro_fg)s;
}

scrolledwindow, viewport, flowbox { background-color: transparent; }

.aba-nome { font-family: """ + MONO + """; font-size: 11px; color: %(texto)s; }
.aba-tipo {
    font-family: """ + MONO + """; font-size: 9px; font-weight: 600;
    color: #ffffff; border-radius: 3px; padding: 0px 4px;
}
.aba-vnc { background-color: %(azul)s; }
.aba-ssh { background-color: %(verde)s; }
.aba-rdp { background-color: %(atencao_fg)s; }

.rodape-info { color: %(fraco)s; font-family: """ + MONO + """; font-size: 11px; }

/* ---------------- dashboard ---------------- */
/* Faixa de topo: sem raio e sem margem, encosta nas bordas da area de
   conteudo. Um cartao flutuante ali deixava a pagina sem ancora. */
.hero {
    background-image: linear-gradient(115deg, %(hero1)s 0%%, %(hero2)s 100%%);
    background-color: %(hero1)s;
    border-radius: 0px;
    border-bottom: 1px solid %(hero1)s;
}
.hero-eyebrow {
    color: %(topo_sec)s;
    font-family: """ + MONO + """; font-size: 10px; font-weight: 600;
}
.hero-titulo { color: %(hero_txt)s; font-family: """ + COND + """; font-size: 32px; font-weight: 600; }
.hero-sub    { color: %(topo_sec)s; font-family: """ + MONO + """; font-size: 10px; }
/* credito: mesma altura de linha do caminho do INI, mais apagado ainda —
   presente sem disputar atencao com a informacao util */
.hero-credito {
    color: %(topo_sec)s;
    font-family: """ + MONO + """;
    font-size: 10px;
    opacity: 0.55;
}
.hero-num    { color: %(hero_txt)s; font-family: """ + COND + """; font-size: 27px; font-weight: 600; }
.hero-cap    { color: %(topo_sec)s; font-family: """ + MONO + """; font-size: 9px; }
.hero-risco  { opacity: 0.14; }

/* EventBox com janela propria precisa de fundo explicito, senao pinta a cor
   crua do tema por baixo dos cards */
.evt { background-color: transparent; }

.card {
    background-color: %(cartao)s;
    border: 1px solid %(borda)s;
    border-radius: 10px;
}
.card:hover { border-color: %(borda2)s; background-color: %(hover)s; }
.card-nome  { color: %(texto)s; font-family: """ + COND + """; font-size: 17px; font-weight: 600; }
.card-host  { color: %(sec)s;   font-family: """ + MONO + """; font-size: 12px; }
.card-meta  { color: %(fraco)s; font-family: """ + MONO + """; font-size: 10px; }

/* caixa de selecao do lote: discreta, some no fundo do card ate ser
   marcada — nao deve competir com o nome da maquina */
.marca-lote check {
    min-height: 13px; min-width: 13px;
    border-radius: 3px;
    border: 1px solid %(borda2)s;
    background-image: none;
    background-color: %(cartao)s;
    box-shadow: none;
}
.marca-lote check:checked {
    background-color: %(azul)s;
    border-color: %(azul)s;
    color: #ffffff;
}
.trilho     { border-radius: 3px; min-width: 4px; }
.grupo-titulo    { color: %(texto)s; font-family: """ + COND + """; font-size: 18px; font-weight: 600; }
.subgrupo-titulo { color: %(sec)s;   font-family: """ + COND + """; font-size: 15px; font-weight: 600; }
.grupo-cont   { color: %(fraco)s; font-family: """ + MONO + """; font-size: 10px; }

/* ---------------------------------------------------------------------
   ULTIMA PALAVRA SOBRE OS BOTOES DE DIALOGO

   Regra de ouro daqui para baixo: GEOMETRIA e declarada UMA vez, num
   seletor SEM pseudo-classe. Estados (:hover, :focus, :active, :backdrop)
   so podem mexer em COR.

   Foi a mistura dos dois que fez a janela inteira "dar zoom" ao passar o
   mouse: um estado trazia padding ou borda diferente, o botao mudava de
   tamanho, e o dialogo inteiro era realocado em cascata.
   --------------------------------------------------------------------- */

/* --- geometria (sem estado) --- */
.acessos-dialogo button,
.acessos-dialogo headerbar button,
.acessos-dialogo .area-acao button {
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 12px;
    min-height: 0px;
    min-width: 0px;
    margin: 0px;
    background-image: none;
    box-shadow: none;
    text-shadow: none;
    outline-style: none;
    outline-width: 0px;
    outline-offset: 0px;
    -gtk-outline-radius: 0px;
    font-family: """ + SANS + """;
    font-size: 12px;
    font-weight: 600;
}
.acessos-dialogo button label,
.acessos-dialogo headerbar button label,
.acessos-dialogo .area-acao button label {
    border: 0px solid transparent;
    background-color: transparent;
    background-image: none;
    box-shadow: none;
    outline-style: none;
    font-size: 12px;
    font-weight: 600;
}

/* --- so cor daqui para baixo --- */
.acessos-dialogo button.acao,
.acessos-dialogo headerbar button.acao,
.acessos-dialogo .area-acao button.acao            { background-color: %(azul)s; }
.acessos-dialogo button.acao:hover,
.acessos-dialogo headerbar button.acao:hover,
.acessos-dialogo .area-acao button.acao:hover      { background-color: %(azul_h)s; }
.acessos-dialogo button.acao:active,
.acessos-dialogo headerbar button.acao:active,
.acessos-dialogo .area-acao button.acao:active     { background-color: %(azul_h)s; }
.acessos-dialogo button.acao:backdrop,
.acessos-dialogo headerbar button.acao:backdrop,
.acessos-dialogo .area-acao button.acao:backdrop   { background-color: %(azul)s; }
.acessos-dialogo button.acao label,
.acessos-dialogo headerbar button.acao label,
.acessos-dialogo .area-acao button.acao label      { color: #ffffff; }

.acessos-dialogo button.perigo,
.acessos-dialogo headerbar button.perigo,
.acessos-dialogo .area-acao button.perigo          { background-color: %(erro_fg)s; }
.acessos-dialogo button.perigo:hover,
.acessos-dialogo headerbar button.perigo:hover,
.acessos-dialogo .area-acao button.perigo:hover    { background-color: %(erro_h)s; }
.acessos-dialogo button.perigo:active,
.acessos-dialogo headerbar button.perigo:active,
.acessos-dialogo .area-acao button.perigo:active   { background-color: %(erro_h)s; }
.acessos-dialogo button.perigo:backdrop,
.acessos-dialogo headerbar button.perigo:backdrop,
.acessos-dialogo .area-acao button.perigo:backdrop { background-color: %(erro_fg)s; }
.acessos-dialogo button.perigo label,
.acessos-dialogo headerbar button.perigo label,
.acessos-dialogo .area-acao button.perigo label    { color: #ffffff; }

.acessos-dialogo button:not(.acao):not(.perigo)          { background-color: %(cartao)s; }
.acessos-dialogo button:not(.acao):not(.perigo):hover    { background-color: %(hover)s; }
.acessos-dialogo button:not(.acao):not(.perigo):backdrop { background-color: %(cartao)s; }
.acessos-dialogo button:not(.acao):not(.perigo) label    { color: %(texto)s; }
"""

def _escalar_fontes(css, escala_fonte=ESCALA_FONTE):
    """Multiplica todo 'font-size: Npx' da folha pelas escalas.

    Feito no texto final, e nao em cada regra, para que nenhuma passe
    batida. As regras de glifo (.tog-glifo, .btn-janela) levam o fator
    extra, porque nelas o "icone" e um caractere de texto — crescer a
    fonte E crescer o icone.

    `escala_fonte` e a escala de fonte JA EFETIVA (ESCALA_FONTE sozinha,
    ou multiplicada por ESCALA_FONTE_GRANDE quando o usuario pede fonte
    maior) — quem decide isso e gerar_css(), este aqui so aplica.
    """
    import re

    # min-height/padding dos botoes de glifo tambem precisam acompanhar,
    # senao o caractere maior fica cortado pela caixa antiga.
    classes_glifo = (".tog-glifo", ".btn-janela")

    def escala_da_linha(trecho_antes):
        # olha o ultimo seletor aberto antes desta propriedade
        corte = trecho_antes.rfind("}")
        seletor = trecho_antes[corte + 1:]
        if any(c in seletor for c in classes_glifo):
            return escala_fonte * ESCALA_GLIFO
        return escala_fonte

    saida = []
    pos = 0
    for m in re.finditer(r"font-size:\s*(\d+(?:\.\d+)?)px", css):
        fator = escala_da_linha(css[:m.start()])
        novo = max(1, int(round(float(m.group(1)) * fator)))
        saida.append(css[pos:m.start()])
        saida.append("font-size: %dpx" % novo)
        pos = m.end()
    saida.append(css[pos:])
    css = "".join(saida)

    # A caixa dos botoes de glifo cresce junto com o caractere. Editamos o
    # padding QUE JA EXISTE na regra: inserir um segundo "padding:" antes
    # do original nao funcionaria — na cascata do CSS a ultima declaracao
    # da mesma propriedade vence, e a antiga anularia a nova.
    if ESCALA_GLIFO != 1.0:
        css = re.sub(
            r"(\.tog-glifo\s*\{[^}]*?padding:\s*)0px\s+8px",
            lambda m: "%s0px %dpx" % (
                m.group(1), max(8, int(round(8 * ESCALA_GLIFO)))),
            css, count=1)
        css = re.sub(
            r"(\.btn-janela\s*\{[^}]*?padding:\s*)2px\s+9px",
            lambda m: "%s%dpx %dpx" % (
                m.group(1), max(2, int(round(2 * ESCALA_GLIFO))),
                max(9, int(round(9 * ESCALA_GLIFO)))),
            css, count=1)
    return css


def gerar_css(tema, fonte_grande=False):
    """Folha pronta para o CssProvider, já com as cores do tema.

    `fonte_grande=True` aplica ESCALA_FONTE_GRANDE (1.5x) em cima do
    tamanho padrão (ESCALA_FONTE) — é a opção que o botão "A+" da
    titlebar liga/desliga em acessos.py.
    """
    escala = ESCALA_FONTE * (ESCALA_FONTE_GRANDE if fonte_grande else 1.0)
    return _escalar_fontes(CSS_MOLDE % TEMAS[tema], escala).encode()


def rgba(h):
    """'#rrggbb' -> Gdk.RGBA."""
    c = Gdk.RGBA()
    c.parse(h)
    return c


def fonte_mono(tamanho=11):
    """Nunca peça uma família que pode não existir.

    O Pango cai num fallback proporcional, e o VTE — que dimensiona a célula
    pela largura do caractere — estica o terminal inteiro. Por isso
    perguntamos ao Pango o que existe antes de escolher.
    """
    ctx = Gtk.Label().get_pango_context()
    fams = {f.get_name(): f for f in ctx.list_families()}
    for familia in ("IBM Plex Mono", "DejaVu Sans Mono"):
        f = fams.get(familia)
        if f is not None and f.is_monospace():
            return Pango.FontDescription("%s %d" % (familia, tamanho))
    return Pango.FontDescription("monospace %d" % tamanho)
