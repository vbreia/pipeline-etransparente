# ARQUIVO GERADO — NÃO EDITE AQUI. Edite envio/comum.py e rode envio/sincronizar_copias.py
"""
Código comum ao envio com aprovação — usado pela API do dashboard
(api/shared_code/comum.py) e pela Function de envio
(functions/comum.py).

ESTE é o arquivo canônico. As duas cópias são geradas a partir dele por
`envio/sincronizar_copias.py`, e o teste tests/test_envio_comum.py falha se
alguma cópia divergir — a API e a Function nunca podem interpretar o estado
de um ciclo de formas diferentes.

Layout no Azure (container `etransparente`, FORA de gold/ — gold/ é legível
pelo token de leitura do dashboard; aqui há e-mails de OSCs e dados de acesso):

  envios/{ciclo}/manifesto.json        o que será enviado + código de validação
  envios/{ciclo}/amostra.json          IDC + 2 sorteadas
  envios/{ciclo}/emails/{slug}.json    e-mail pronto de cada OSC
  envios/{ciclo}/conferencia/{uid}/{slug}.json   abertura de PDF pela aprovadora
  envios/{ciclo}/aprovacao.json        quem confirmou, quando, de onde
  envios/{ciclo}/bloqueio.json         erro reportado (impede qualquer envio)
  envios/{ciclo}/status/{slug}.json    resultado de cada e-mail
  envios/{ciclo}/resultado.json        fechamento do envio
  envios/_alertas/...                  tentativas negadas (controle de repetição)
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import smtplib
import ssl
import urllib.request
from datetime import datetime, timedelta, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

CONTAINER = 'etransparente'
PREFIXO = 'envios/'
PAPEL_APROVADOR = 'aprovador_envio'
FUSO_BRT = timezone(timedelta(hours=-3))

GESTAO_PADRAO = ('presidencia@direitocoletivo.org.br,transparencia@direitocoletivo.org.br,'
                 'comunicacao@direitocoletivo.org.br')
TECNICO_PADRAO = 'comunicacao@direitocoletivo.org.br'
URL_PAINEL = 'https://dashboard.etransparente.org/envio'

ESTADOS_FINAIS = {'enviado', 'falhou_definitivo', 'suspenso_por_bloqueio'}


# ── tempo ───────────────────────────────────────────────────────────────────

def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def formatar_brt(iso_ou_dt) -> str:
    dt = datetime.fromisoformat(iso_ou_dt) if isinstance(iso_ou_dt, str) else iso_ou_dt
    return dt.astimezone(FUSO_BRT).strftime('%d/%m/%Y %H:%M:%S (Brasília)')


# ── integridade ─────────────────────────────────────────────────────────────

def sha256_json(obj) -> str:
    """Idêntico a scripts/artefatos.py:sha256_json — usado para conferir o e-mail preparado."""
    canon = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


# ── Azure Blob / Queue ──────────────────────────────────────────────────────

def _conn() -> str:
    c = os.environ.get('DADOS_STORAGE')
    if not c:
        raise RuntimeError('Configuração DADOS_STORAGE ausente')
    return c


def container():
    from azure.storage.blob import BlobServiceClient
    return BlobServiceClient.from_connection_string(_conn()).get_container_client(CONTAINER)


def ler_json(cont, caminho: str):
    b = cont.get_blob_client(caminho)
    if not b.exists():
        return None
    return json.loads(b.download_blob().readall())


def gravar_json(cont, caminho: str, dados, sobrescrever: bool = True) -> bool:
    """Grava JSON. Com sobrescrever=False, só grava se não existir (retorna False se já existia)."""
    from azure.core.exceptions import ResourceExistsError
    try:
        cont.get_blob_client(caminho).upload_blob(
            json.dumps(dados, ensure_ascii=False, indent=2).encode('utf-8'), overwrite=sobrescrever)
        return True
    except ResourceExistsError:
        return False


def caminho(ciclo: str, *partes: str) -> str:
    return PREFIXO + ciclo + '/' + '/'.join(partes)


def ciclos_preparados(cont) -> list[str]:
    ciclos = set()
    for b in cont.list_blobs(name_starts_with=PREFIXO):
        partes = b.name.split('/')
        if len(partes) >= 3 and partes[2] == 'manifesto.json':
            ciclos.add(partes[1])
    return sorted(ciclos)


def estado_ciclo(cont, ciclo: str) -> dict:
    """Tudo que se sabe sobre o envio de um ciclo, lido do Azure."""
    status = {}
    for b in cont.list_blobs(name_starts_with=caminho(ciclo, 'status/')):
        s = json.loads(cont.get_blob_client(b.name).download_blob().readall())
        status[s['slug']] = s
    return {
        'manifesto': ler_json(cont, caminho(ciclo, 'manifesto.json')),
        'amostra': ler_json(cont, caminho(ciclo, 'amostra.json')),
        'validacao': ler_json(cont, f'gold/validacao/{ciclo}.json'),
        'aprovacao': ler_json(cont, caminho(ciclo, 'aprovacao.json')),
        'bloqueio': ler_json(cont, caminho(ciclo, 'bloqueio.json')),
        'resultado': ler_json(cont, caminho(ciclo, 'resultado.json')),
        'status': status,
    }


def fila(nome: str = 'envios'):
    from azure.storage.queue import QueueClient, TextBase64EncodePolicy
    return QueueClient.from_connection_string(_conn(), nome, message_encode_policy=TextBase64EncodePolicy())


def url_leitura_temporaria(blob_path: str, minutos: int = 15) -> str:
    """Link de leitura de UM arquivo, válido por poucos minutos."""
    from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas
    svc = BlobServiceClient.from_connection_string(_conn())
    sas = generate_blob_sas(
        account_name=svc.account_name, container_name=CONTAINER, blob_name=blob_path,
        account_key=svc.credential.account_key, permission=BlobSasPermissions(read=True),
        expiry=agora_utc() + timedelta(minutes=minutos),
    )
    return f'https://{svc.account_name}.blob.core.windows.net/{CONTAINER}/{blob_path}?{sas}'


# ── regras do ciclo ─────────────────────────────────────────────────────────

def motivos_para_nao_aprovar(estado: dict, codigo: str) -> list[str]:
    """Lista vazia = ciclo pode ser aprovado com este código."""
    m, v = estado.get('manifesto'), estado.get('validacao')
    motivos = []
    if not m:
        return ['Não há envio preparado para este ciclo.']
    if m.get('codigo_validacao') != codigo:
        motivos.append('O código exibido não é o código atual do ciclo — recarregue a página.')
    if not v or v.get('status') != 'aprovado':
        motivos.append('A validação automática do ciclo não está aprovada.')
    if estado.get('bloqueio'):
        motivos.append('O envio está bloqueado por um erro reportado.')
    if estado.get('aprovacao'):
        motivos.append('Este ciclo já foi confirmado.')
    if estado.get('status'):
        motivos.append('O envio deste ciclo já começou.')
    return motivos


def envio_concluido(estado: dict) -> bool:
    m = estado.get('manifesto') or {}
    slugs = {e['slug'] for e in m.get('emails', [])}
    finais = {s for s, st in estado.get('status', {}).items() if st.get('estado') in ESTADOS_FINAIS}
    return bool(slugs) and slugs <= finais


def resumir_resultado(estado: dict) -> dict:
    st = estado.get('status', {})
    por_estado: dict[str, list[str]] = {}
    for s in st.values():
        por_estado.setdefault(s.get('estado', '?'), []).append(s.get('nome', s.get('slug')))
    return {
        'total': len((estado.get('manifesto') or {}).get('emails', [])),
        'enviados': len(por_estado.get('enviado', [])),
        'falhas': sorted(por_estado.get('falhou_definitivo', [])),
        'suspensos': sorted(por_estado.get('suspenso_por_bloqueio', [])),
        'sem_email': (estado.get('manifesto') or {}).get('sem_email', []),
    }


# ── identidade e origem do acesso (SWA) ─────────────────────────────────────

def principal(headers) -> dict | None:
    """Usuário autenticado, a partir do cabeçalho que o Static Web App injeta.

    O cabeçalho é colocado pela plataforma depois do login no Entra ID —
    o navegador não consegue forjá-lo nas funções gerenciadas do SWA.
    """
    bruto = headers.get('x-ms-client-principal')
    if not bruto:
        return None
    p = json.loads(base64.b64decode(bruto).decode('utf-8'))
    claims = {c.get('typ'): c.get('val') for c in p.get('claims', []) or []}
    return {
        'id': p.get('userId', ''),
        'email': (p.get('userDetails') or '').lower(),
        'papeis': [r for r in p.get('userRoles', []) if r not in ('anonymous', 'authenticated')],
        'nome_conta': claims.get('name') or claims.get('http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name') or '',
    }


def ip_cliente(headers) -> str:
    for h in ('x-azure-clientip', 'x-client-ip', 'x-forwarded-for'):
        v = headers.get(h)
        if v:
            ip = v.split(',')[0].strip()
            if ip.count(':') == 1:  # IPv4:porta
                ip = ip.split(':')[0]
            return ip
    return ''


def geolocalizar(ip: str) -> dict:
    """Localização APROXIMADA pelo IP (indício, não prova — VPN e rede móvel distorcem)."""
    if not ip:
        return {}
    try:
        with urllib.request.urlopen(f'https://ipinfo.io/{ip}/json', timeout=3) as r:
            d = json.loads(r.read())
        return {k: d.get(k, '') for k in ('city', 'region', 'country', 'org')}
    except Exception:
        return {}


def dados_de_acesso(headers) -> dict:
    ip = ip_cliente(headers)
    geo = geolocalizar(ip)
    local = ', '.join(x for x in (geo.get('city'), geo.get('region'), geo.get('country')) if x)
    return {
        'ip': ip,
        'local_aproximado': local or 'indisponível',
        'provedor': geo.get('org') or 'indisponível',
        'navegador': headers.get('user-agent', ''),
        'registrado_em': agora_utc().isoformat(timespec='seconds'),
    }


def nomes_compativeis(declarado: str, titular: str) -> bool | None:
    """True/False se dá para comparar; None se a conta não informa o nome."""
    if not titular:
        return None
    def tokens(t):
        import unicodedata
        t = unicodedata.normalize('NFKD', t).encode('ASCII', 'ignore').decode().lower()
        return {p for p in t.replace('.', ' ').split() if len(p) > 2}
    a, b = tokens(declarado), tokens(titular)
    return bool(a & b)


# ── e-mail ──────────────────────────────────────────────────────────────────

def destinatarios_gestao() -> list[str]:
    return [e.strip() for e in os.environ.get('NOTIFICAR_GESTAO', GESTAO_PADRAO).split(',') if e.strip()]


def destinatario_tecnico() -> str:
    return os.environ.get('EMAIL_TECNICO', TECNICO_PADRAO)


def enviar_email(para: list[str] | str, assunto: str, corpo_html: str,
                 anexo: bytes | None = None, nome_anexo: str = '') -> None:
    if isinstance(para, str):
        para = [para]
    msg = MIMEMultipart('mixed')
    msg['From'] = os.environ.get('SMTP_FROM', 'transparencia@direitocoletivo.org.br')
    msg['To'] = ', '.join(para)
    msg['Subject'] = assunto
    msg.attach(MIMEText(corpo_html, 'html', 'utf-8'))
    if anexo is not None:
        parte = MIMEApplication(anexo, _subtype='pdf')
        parte.add_header('Content-Disposition', 'attachment', filename=nome_anexo or 'relatorio.pdf')
        msg.attach(parte)
    with smtplib.SMTP(os.environ.get('SMTP_HOST', 'smtp.gmail.com'),
                      int(os.environ.get('SMTP_PORT', '587')), timeout=30) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(os.environ['SMTP_USER'], os.environ['SMTP_PASSWORD'])
        s.send_message(msg, to_addrs=para)


class Html(str):
    """Marca um valor como HTML confiável (gerado pelo próprio sistema). Todo o resto é escapado."""


def html_notificacao(titulo: str, linhas: list[tuple[str, str]], rodape: str = '',
                     cor: str = '#1e3a8a', itens: list[str] | None = None) -> str:
    """E-mail interno simples: título, tabela chave/valor, lista opcional.

    Valores digitados por usuários (nome, descrição de erro) são SEMPRE escapados.
    """
    def esc(x):
        return x if isinstance(x, Html) else html.escape(str(x))
    tabela = ''.join(
        f'<tr><td style="padding:6px 12px;color:#64748b;white-space:nowrap;vertical-align:top">{esc(k)}</td>'
        f'<td style="padding:6px 12px;color:#0f172a">{esc(v)}</td></tr>' for k, v in linhas)
    lista = ''
    if itens:
        lista = '<ul style="margin:8px 0 0 18px;padding:0">' + ''.join(f'<li>{esc(i)}</li>' for i in itens) + '</ul>'
    return (
        '<div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;color:#0f172a">'
        f'<div style="background:{cor};color:#fff;padding:16px 20px;border-radius:8px 8px 0 0;font-size:17px;'
        f'font-weight:700">{esc(titulo)}</div>'
        '<div style="border:1px solid #e2e8f0;border-top:0;padding:12px 8px;border-radius:0 0 8px 8px">'
        f'<table style="border-collapse:collapse;font-size:14px;width:100%">{tabela}</table>{lista}'
        f'<p style="font-size:12px;color:#64748b;margin:14px 12px 4px">{esc(rodape)}</p>'
        '<p style="font-size:12px;color:#64748b;margin:4px 12px">Mensagem automática do sistema de envio '
        f'do etransparente.org — <a href="{URL_PAINEL}">{URL_PAINEL}</a></p></div></div>'
    )
