/* rdpshim.c — ponte estavel entre Python (ctypes) e libfreerdp/libwinpr.
 *
 * POR QUE ESTE ARQUIVO EXISTE
 * ---------------------------
 * Mesma razao do vncshim.c: rdpContext/rdpSettings tem forma que muda por
 * build/versao — e por isso o proprio FreeRDP 3.x ja NAO deixa ler/escrever
 * a struct rdpSettings direto, so via freerdp_settings_set_*(id) com um ID
 * nomeado (FreeRDP_ServerHostname, FreeRDP_Username...). O unico "chute" de
 * layout que ainda fazemos e o de MeuContexto, e esse e seguro: o proprio
 * FreeRDP garante isso por contrato — rdpContext PRECISA ser o primeiro
 * campo (e o unico requisito), o resto do tamanho e informado por nos via
 * instance->ContextSize antes de freerdp_context_new() alocar.
 *
 * O QUE ISTO SUBSTITUI
 * ---------------------
 * Antes: rdp_windows.py abria wfreerdp.exe como PROCESSO EXTERNO e
 * reparentava a janela dele (SetParent, ver win_embed.py) dentro da nossa.
 * Aqui: linkamos libfreerdp/libwinpr direto, igual o vncshim.c ja faz com
 * libvncclient — o RDP passa a desenhar num framebuffer nosso (gdi->
 * primary_buffer), sem processo externo, sem janela pra reparentar.
 *
 * ESCOPO DESTA PRIMEIRA VERSAO: tela + teclado + mouse. Sem clipboard, sem
 * redirecionamento de unidade/impressora, sem audio — esses sao canais
 * dinamicos (drdynvc) que podem entrar depois se fizerem falta.
 *
 * COMPILAR:
 *   gcc -shared -O2 -Wall -o librdpshim.dll rdpshim.c \
 *       $(pkg-config --cflags --libs freerdp-client3 freerdp3 winpr3)
 */

/* WIN32_LEAN_AND_MEAN antes de winsock2.h: sem isto, o windows.h que
 * vem atras traz shellapi.h, cujas macros NIIF_* colidem com os enums
 * de mesmo nome que freerdp/rail.h declara (erro real visto compilando:
 * "expected identifier before numeric constant" em NIIF_NONE). */
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>

#include <freerdp/freerdp.h>
#include <freerdp/gdi/gdi.h>
#include <freerdp/input.h>
#include <freerdp/settings.h>
#include <freerdp/version.h>
#include <winpr/synch.h>
#include <winpr/wtypes.h>

#include <stdlib.h>
#include <string.h>
#include <stdint.h>

/* WSAStartup — o Winsock NAO se inicializa sozinho no Windows. Todo
 * cliente FreeRDP "de verdade" (wfreerdp.exe incluso) chama isto no
 * proprio main() antes de qualquer coisa de rede; como o shim nao TEM
 * um main() (e uma DLL chamada pelo Python), precisa chamar aqui.
 * Achado testando: sem isto, getaddrinfo() falha pra QUALQUER host,
 * ate um IP literal como "127.0.0.1" — sintoma enganoso, parece erro
 * de DNS mas e so Winsock nunca inicializado. */
static int WSA_INICIADO = 0;

static void garantir_winsock(void) {
    if (WSA_INICIADO) return;
    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);
    WSA_INICIADO = 1;
}

/* Callbacks para o lado Python — deliberadamente simples, sem struct
 * nenhuma cruzando a fronteira (mesma disciplina do vncshim.c). */
typedef void (*cb_atualizou)(void *ctx, int x, int y, int w, int h);
typedef void (*cb_redimensionou)(void *ctx, int w, int h);
typedef void (*cb_desconectou)(void *ctx, uint32_t codigo, const char *motivo);

/* Contexto customizado do FreeRDP: rdpContext TEM que ser o primeiro
 * campo — e o unico contrato de layout que o FreeRDP exige de quem
 * estende o contexto. instance->ContextSize (ver rs_criar) informa o
 * tamanho total; freerdp_context_new() aloca e devolve isto via
 * instance->context, ja com o campo rdpContext preenchido. */
typedef struct {
    rdpContext context;    /* PRECISA ser o primeiro campo */

    void *ctx_py;
    cb_atualizou ao_atualizar;
    cb_redimensionou ao_redimensionar;
    cb_desconectou ao_desconectar;

    char *usuario;
    char *senha;
    char *dominio;

    int largura_pedida;
    int altura_pedida;
    int ignorar_certificado;   /* equivalente ao /cert:ignore de hoje */

    int morto;
} MeuContexto;

/* ---- callbacks de bootstrap (chamados pelo FreeRDP, nao pelo Python) ---- */

static BOOL cb_context_new(freerdp *instance, rdpContext *context) {
    (void)instance;
    (void)context;
    return TRUE;   /* nada extra a inicializar alem do que rs_criar faz */
}

static void cb_context_free(freerdp *instance, rdpContext *context) {
    (void)instance;
    (void)context;
}

/* Roda ANTES do handshake de rede. E aqui que se pede os codecs — de
 * proposito pedimos os SIMPLES (bitmap cru/RLE, NSCodec desligado,
 * RemoteFX desligado): sao eles que o gdi_init() decodifica em software
 * sem depender da pilha de video pesada (ffmpeg/x264/x265/av1...) que
 * hoje faz o bundle do wfreerdp.exe pesar ~84MB. Trocar por codecs mais
 * eficientes fica pra depois, se a banda/CPU de alguma ligacao exigir. */
static BOOL cb_pre_connect(freerdp *instance) {
    rdpSettings *settings = instance->context->settings;
    MeuContexto *mc = (MeuContexto *)instance->context;

    /* host/porta ja foram gravados em rs_conectar, ANTES de
     * freerdp_connect() chamar este callback — nada a fazer aqui com
     * eles. (Achado ao testar: uma linha residual que lia e regravava
     * FreeRDP_ServerHostname aqui corrompia o valor — set_string libera
     * o ponteiro antigo antes de copiar, e o "antigo" e o mesmo que
     * acabara de ser lido — classico bug de auto-atribuicao.) */
    if (mc->largura_pedida > 0)
        freerdp_settings_set_uint32(settings, FreeRDP_DesktopWidth, (UINT32)mc->largura_pedida);
    if (mc->altura_pedida > 0)
        freerdp_settings_set_uint32(settings, FreeRDP_DesktopHeight, (UINT32)mc->altura_pedida);
    freerdp_settings_set_uint32(settings, FreeRDP_ColorDepth, 32);

    freerdp_settings_set_bool(settings, FreeRDP_RemoteFxCodec, FALSE);
    freerdp_settings_set_bool(settings, FreeRDP_NSCodec, FALSE);
    freerdp_settings_set_bool(settings, FreeRDP_SoftwareGdi, TRUE);
    freerdp_settings_set_bool(settings, FreeRDP_IgnoreCertificate,
                              mc->ignorar_certificado ? TRUE : FALSE);

    /* +clipboard/-clipboard etc. (canais dinamicos) ficam de fora nesta
     * primeira versao — soh tela, teclado e mouse. */
    return TRUE;
}

static BOOL cb_end_paint(rdpContext *context) {
    MeuContexto *mc = (MeuContexto *)context;
    rdpGdi *gdi = context->gdi;
    if (!gdi || mc->morto) return TRUE;

    /* v1: repinta a regiao suja acumulada pelo proprio gdi (gdi->
     * primary->hdc->hwnd->invalid) se disponivel; sem ela, repinta tudo.
     * Repintar tudo a cada EndPaint e simples e correto — otimizar para
     * so a regiao suja e um ajuste de desempenho, nao de corretude, e
     * fica para quando houver uma ligacao lenta de verdade para medir
     * contra (mesmo cuidado do vncshim.c: nao calibrar no escuro). */
    if (mc->ao_atualizar)
        mc->ao_atualizar(mc->ctx_py, 0, 0, gdi->width, gdi->height);
    return TRUE;
}

/* Roda DEPOIS do handshake — e aqui que o framebuffer de software
 * (gdi->primary_buffer) fica disponivel. Equivalente ao hook_malloc_fb
 * do vncshim.c, so que o FreeRDP ja cuida de alocar/realocar sozinho;
 * so precisamos pendurar o EndPaint pra saber quando repintar. */
static BOOL cb_post_connect(freerdp *instance) {
    MeuContexto *mc = (MeuContexto *)instance->context;

    if (!gdi_init(instance, PIXEL_FORMAT_BGRX32))
        return FALSE;

    instance->context->update->EndPaint = cb_end_paint;

    if (mc->ao_redimensionar) {
        rdpGdi *gdi = instance->context->gdi;
        mc->ao_redimensionar(mc->ctx_py, gdi->width, gdi->height);
    }
    return TRUE;
}

static void cb_post_disconnect(freerdp *instance) {
    MeuContexto *mc = (MeuContexto *)instance->context;
    if (instance->context->gdi) {
        gdi_free(instance);
    }
    if (mc->ao_desconectar) {
        UINT32 codigo = freerdp_get_last_error(instance->context);
        const char *motivo = freerdp_get_last_error_string(codigo);
        mc->ao_desconectar(mc->ctx_py, codigo, motivo ? motivo : "");
    }
}

/* Credenciais: a copia (strdup) e obrigatoria — o FreeRDP libera o que
 * devolvemos aqui, mesma regra do hook_senha/hook_credencial no vncshim.c. */
static BOOL cb_authenticate_ex(freerdp *instance, char **username, char **password,
                               char **domain, rdp_auth_reason reason) {
    (void)reason;
    MeuContexto *mc = (MeuContexto *)instance->context;
    free(*username); free(*password); free(*domain);
    *username = strdup(mc->usuario ? mc->usuario : "");
    *password = strdup(mc->senha ? mc->senha : "");
    *domain = strdup(mc->dominio ? mc->dominio : "");
    return TRUE;
}

/* Aceita qualquer certificado — equivalente ao /cert:ignore que o
 * rdp_windows.py ja passa hoje pro wfreerdp.exe. Devolve 1 (aceitar
 * desta vez) sempre que ignorar_certificado estiver ligado; senao,
 * recusa (0) — nao ha dialogo interativo nesta v1. */
static DWORD cb_verify_certificate_ex(freerdp *instance, const char *host, UINT16 port,
                                      const char *common_name, const char *subject,
                                      const char *issuer, const char *fingerprint,
                                      DWORD flags) {
    (void)instance; (void)host; (void)port; (void)common_name;
    (void)subject; (void)issuer; (void)fingerprint; (void)flags;
    MeuContexto *mc = (MeuContexto *)instance->context;
    return mc->ignorar_certificado ? 1 : 0;
}

/* ---- API exposta ao Python ---- */

MeuContexto *rs_criar(void *ctx_py, cb_atualizou ao_atualizar,
                      cb_redimensionou ao_redimensionar,
                      cb_desconectou ao_desconectar) {
    garantir_winsock();
    freerdp *instance = freerdp_new();
    if (!instance) return NULL;

    instance->ContextSize = sizeof(MeuContexto);
    instance->ContextNew = cb_context_new;
    instance->ContextFree = cb_context_free;
    instance->PreConnect = cb_pre_connect;
    instance->PostConnect = cb_post_connect;
    instance->PostDisconnect = cb_post_disconnect;
    instance->AuthenticateEx = cb_authenticate_ex;
    instance->VerifyCertificateEx = cb_verify_certificate_ex;

    if (!freerdp_context_new(instance)) {
        freerdp_free(instance);
        return NULL;
    }

    MeuContexto *mc = (MeuContexto *)instance->context;
    mc->ctx_py = ctx_py;
    mc->ao_atualizar = ao_atualizar;
    mc->ao_redimensionar = ao_redimensionar;
    mc->ao_desconectar = ao_desconectar;
    mc->ignorar_certificado = 1;   /* mesmo padrao de hoje (/cert:ignore) */
    return mc;
}

void rs_definir_credenciais(MeuContexto *mc, const char *usuario,
                            const char *senha, const char *dominio) {
    if (!mc) return;
    free(mc->usuario); mc->usuario = usuario ? strdup(usuario) : NULL;
    free(mc->senha);   mc->senha   = senha   ? strdup(senha)   : NULL;
    free(mc->dominio); mc->dominio = dominio ? strdup(dominio) : NULL;
}

void rs_definir_tela(MeuContexto *mc, int largura, int altura) {
    if (!mc) return;
    mc->largura_pedida = largura;
    mc->altura_pedida = altura;
}

void rs_definir_ignorar_certificado(MeuContexto *mc, int ignorar) {
    if (mc) mc->ignorar_certificado = ignorar;
}

/* Conecta. Devolve 1 em sucesso. BLOQUEIA — chame de uma thread (mesma
 * regra do vs_conectar no vncshim.c). */
int rs_conectar(MeuContexto *mc, const char *host, int porta) {
    if (!mc) return 0;
    freerdp *instance = mc->context.instance;
    rdpSettings *settings = mc->context.settings;

    freerdp_settings_set_string(settings, FreeRDP_ServerHostname, host);
    freerdp_settings_set_uint32(settings, FreeRDP_ServerPort, (UINT32)porta);

    if (!freerdp_connect(instance)) {
        mc->morto = 1;
        return 0;
    }
    return 1;
}

/* Espera ate `ms` milissegundos por dados/timeout do FreeRDP. Devolve 1
 * se ha algo pra processar, 0 em timeout, -1 em erro — mesma convencao
 * do vs_esperar. Usa freerdp_get_event_handles/WaitForMultipleObjects
 * (Win32) em vez do WaitForMessage do vncshim.c, que e API da
 * libvncclient — aqui e API nativa do Windows, ja usada sem pywin32 em
 * conpty.py/win_embed.py. */
int rs_esperar(MeuContexto *mc, int ms) {
    if (!mc || mc->morto) return -1;
    HANDLE handles[64];
    DWORD n = freerdp_get_event_handles(&mc->context, handles, 64);
    if (n == 0) return -1;
    DWORD r = WaitForMultipleObjects(n, handles, FALSE, (DWORD)ms);
    if (r == WAIT_TIMEOUT) return 0;
    if (r == WAIT_FAILED) return -1;
    return 1;
}

/* Processa mensagens pendentes. Devolve 1 se ok, 0 se a conexao caiu. */
int rs_processar(MeuContexto *mc) {
    if (!mc || mc->morto) return 0;
    if (!freerdp_check_event_handles(&mc->context)) {
        mc->morto = 1;
        return 0;
    }
    return 1;
}

uint8_t *rs_framebuffer(MeuContexto *mc) {
    if (!mc || !mc->context.gdi) return NULL;
    return mc->context.gdi->primary_buffer;
}

int rs_largura(MeuContexto *mc) {
    return (mc && mc->context.gdi) ? mc->context.gdi->width : 0;
}

int rs_altura(MeuContexto *mc) {
    return (mc && mc->context.gdi) ? mc->context.gdi->height : 0;
}

int rs_morto(MeuContexto *mc) {
    return (!mc || mc->morto) ? 1 : 0;
}

/* Teclado: `scancode` e o scancode PS/2 Set 1 cru — o mesmo vocabulario
 * que freerdp_input_send_keyboard_event espera. event.hardware_keycode
 * do GDK, no backend Win32, JA E esse valor (GDK copia direto do
 * WM_KEYDOWN/WM_KEYUP), sem precisar de tabela VK->scancode nenhuma do
 * lado Python. O bit de tecla ESTENDIDA (setas, Insert/Delete/Home/End/
 * PageUp/PageDown, Ctrl/Alt direitos...) o GDK nao expoe separado —
 * fica por conta de uma lista estatica do lado Python (ver
 * RDPSHIM-interno.md). KBD_FLAGS_RELEASE/KBD_FLAGS_EXTENDED (winpr/
 * input.h) sao aplicados aqui a partir dos dois inteiros que o Python
 * decidiu. */
void rs_tecla(MeuContexto *mc, int scancode, int estendida, int pressionada) {
    if (!mc || mc->morto || !mc->context.input) return;
    UINT16 flags = 0;
    if (estendida) flags |= KBD_FLAGS_EXTENDED;
    if (!pressionada) flags |= KBD_FLAGS_RELEASE;
    freerdp_input_send_keyboard_event(mc->context.input, flags, (UINT8)scancode);
}

/* Mouse: botoes em bits (PTR_FLAGS_*, winpr/input.h) — o lado Python
 * decide qual flag mandar (botao esquerdo/direito/meio, roda), igual o
 * vs_ponteiro do vncshim.c faz com o bitmask do RFB. */
void rs_ponteiro(MeuContexto *mc, int x, int y, int flags) {
    if (!mc || mc->morto || !mc->context.input) return;
    freerdp_input_send_mouse_event(mc->context.input, (UINT16)flags,
                                   (UINT16)x, (UINT16)y);
}

void rs_destruir(MeuContexto *mc) {
    if (!mc) return;
    freerdp *instance = mc->context.instance;
    if (!mc->morto)
        freerdp_disconnect(instance);
    free(mc->usuario);
    free(mc->senha);
    free(mc->dominio);
    freerdp_context_free(instance);
    freerdp_free(instance);
}
