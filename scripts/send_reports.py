#!/usr/bin/env python3
"""
Envio mensal de relatórios de transparência por e-mail.

Para cada ONG com e-mail cadastrado:
  - E-mail HTML com template IDC + PDF anexado

Para o IDC (comunicacao@direitocoletivo.org.br):
  - Relatório consolidado da execução
"""
import glob
import html as _html
import json
import logging
import os
import re
import smtplib
import unicodedata
import ssl
from datetime import date, datetime, timezone, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from azure.storage.blob import generate_blob_sas, BlobSasPermissions, BlobServiceClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MESES = [
    '', 'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
]

REMOVIDO = 'Para cancelar o recebimento, responda a este e-mail'

BASE_DIR = '/home/airflow' if os.path.exists('/home/airflow/output') else os.getcwd()
TEMPLATE_PATH = os.path.join(BASE_DIR, 'assets', 'email_template_idc_v3.html')

def get_env_or_raise(key):
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f'{key} não definida')
    return val

def find_latest(pattern):
    files = sorted(glob.glob(os.path.join(BASE_DIR, 'output', pattern)))
    return files[-1] if files else None

def find_latest_dir(base):
    dirs = sorted(glob.glob(os.path.join(base, '*')))
    return dirs[-1] if dirs else None

def carregar_ongs(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get('resultados', data.get('ongs', []))
    return data

def carregar_scores(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('resultados', [])

def normalizar_para_arquivo(texto: str) -> str:
    """Remove acentos, converte para minúsculas e substitui caracteres especiais por hífen."""
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode()
    texto = texto.lower()
    texto = re.sub(r'[^a-z0-9]+', '-', texto)
    texto = texto.strip('-')
    return texto

def encontrar_pdf(pdf_dir: str, nome_ong: str) -> str | None:
    nome_normalizado = normalizar_para_arquivo(nome_ong)
    for f in os.listdir(pdf_dir):
        nome_arquivo = normalizar_para_arquivo(f)
        if nome_normalizado in nome_arquivo:
            return os.path.join(pdf_dir, f)
    return None

def normalizar(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode().lower()

def encontrar_pdf_idc(pasta_pdf):
    for f in os.listdir(pasta_pdf):
        nome = normalizar(f)
        if 'instituto' in nome and 'direito' in nome and 'coletivo' in nome:
            return os.path.join(pasta_pdf, f)
    return None

def gerar_sas_url(connection_string, container, blob_path, dias=30):
    client = BlobServiceClient.from_connection_string(connection_string)
    account_name = client.account_name
    account_key = client.credential.account_key
    expiry = datetime.now(timezone.utc) + timedelta(days=dias)
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container,
        blob_name=blob_path,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=expiry,
    )
    return f'https://{account_name}.blob.core.windows.net/{container}/{blob_path}?{sas_token}'

def mes_ano():
    hoje = date.today()
    return hoje.month, hoje.year, MESES[hoje.month], hoje.strftime('%Y-%m')

def build_paragraphs(entry, mes, ano, mes_extenso):
    classificacao = entry.get('classificacao', 'Regular')
    nota = entry.get('nota_final', 0)
    max_nota = entry.get('max_nota', 30)
    nota_str = f'{nota:.1f}' if isinstance(nota, float) else str(nota)

    paragrafo_1 = (
        f'Encaminhamos em anexo o Relatório Mensal do Índice de Transparência '
        f'referente ao período de {mes_extenso}/{ano}, elaborado pelo Instituto de Direito '
        f'Coletivo com base nas informações públicas disponíveis na plataforma '
        f'etransparente.org.'
    )

    if classificacao in ('Bom', 'Ótimo'):
        paragrafo_2 = (
            f'Sua organização obteve a classificação {classificacao} com nota '
            f'{nota_str}/{max_nota}, demonstrando um elevado compromisso com a '
            f'transparência e a prestação de contas. Esse resultado fortalece a '
            f'confiança de parceiros, financiadores e órgãos públicos na atuação '
            f'da sua organização.'
        )
        paragrafo_3 = (
            'O documento pode ser apresentado em processos de captação de recursos, '
            'prestação de contas a financiadores, renovação de parcerias com o poder '
            'público e em relatórios institucionais.'
        )
        paragrafo_4 = (
            'Para acessar e atualizar as informações da sua organização na '
            'plataforma, acesse etransparente.org.'
        )
    else:
        paragrafo_2 = (
            f'Sua organização obteve a classificação Regular com nota '
            f'{nota_str}/{max_nota}. Identificamos que há informações e documentos '
            f'que ainda podem ser preenchidos ou atualizados no cadastro, o que '
            f'contribuiria para elevar o índice de transparência da sua organização.'
        )
        paragrafo_3 = (
            'Organizações com maior índice de transparência têm mais credibilidade '
            'perante financiadores, parceiros e órgãos públicos, além de ampliar '
            'as possibilidades de captação de recursos e celebração de parcerias.'
        )
        paragrafo_4 = (
            'Para atualizar as informações da sua organização e melhorar sua '
            'classificação, acesse etransparente.org.'
        )

    return paragrafo_1, paragrafo_2, paragrafo_3, paragrafo_4

BANNER_IMG_RE = re.compile(
    r'<img\s+src="{{url_banner}}"[^>]*>'
)

def render_template(template_html, nome_ong, cta_url, assunto, p1, p2, p3, p4):
    banner_html = (
        '<table role="presentation" border="0" cellpadding="0" cellspacing="0" '
        'width="100%"><tr><td align="center" '
        'style="background-color:#1a3a5c;padding:32px 24px;">'
        '<h1 style="color:#ffffff;font-size:20px;margin:0;font-weight:700;'
        'font-family:\'Montserrat\',Arial,sans-serif;letter-spacing:1px;">'
        'RELATÓRIO MENSAL DE TRANSPARÊNCIA</h1>'
        '</td></tr></table>'
    )
    saudacao = 'pessoa responsável pela instituição na plataforma etransparente.org'
    html = template_html
    html = BANNER_IMG_RE.sub(banner_html, html)
    html = html.replace('{{name}}', saudacao)
    html = html.replace('{{paragrafo_1}}', p1)
    html = html.replace('{{paragrafo_2}}', p2)
    html = html.replace('{{paragrafo_3}}', p3)
    html = html.replace('{{paragrafo_4}}', p4)
    html = html.replace('{{link_cta}}', cta_url)
    html = html.replace('{{texto_cta}}', 'Confira agora seu Relatório Mensal de Transparência')
    html = html.replace('{{titulo_post}}', assunto)
    html = html.replace('{{pagina alternativa}}', '')
    html = html.replace('{{descadastro}}', REMOVIDO)
    return html

def enviar_email(smtp_config, to_addr, subject, html_body, pdf_path=None):
    msg = MIMEMultipart('mixed')
    msg['From'] = smtp_config['from']
    msg['To'] = to_addr
    msg['Subject'] = subject

    msg_related = MIMEMultipart('related')
    msg_related.attach(MIMEText(html_body, 'html', 'utf-8'))
    msg.attach(msg_related)

    if pdf_path and os.path.isfile(pdf_path):
        with open(pdf_path, 'rb') as f:
            part = MIMEApplication(f.read(), _subtype='pdf')
            part.add_header('Content-Disposition', 'attachment',
                            filename=os.path.basename(pdf_path))
            msg.attach(part)

    with smtplib.SMTP(smtp_config['host'], smtp_config['port']) as server:
        if smtp_config.get('starttls', True):
            context = ssl.create_default_context()
            server.starttls(context=context)
        if smtp_config.get('user') and smtp_config.get('password'):
            server.login(smtp_config['user'], smtp_config['password'])
        server.send_message(msg)

def carregar_template():
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        return f.read()

def build_relatorio_execucao_html(template_html, stats, ongs_detalhes, mes_extenso, ano):
    now = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    titulo = f'Relatório de Execução — Pipeline etransparente — {mes_extenso}/{ano}'

    banner_admin = (
        '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">'
        '<tr><td align="center" style="background-color:#1a3a5c;padding:32px 24px;">'
        '<h1 style="color:#ffffff;font-size:20px;margin:0;font-weight:700;'
        'font-family:\'Montserrat\',Arial,sans-serif;letter-spacing:1px;">'
        'RELATÓRIO DE EXECUÇÃO — PIPELINE ETRANSPARENTE</h1>'
        '</td></tr></table>'
    )

    # ── Seção 1: Alertas ──
    alertas = ''

    if stats['falhas']:
        falhas_rows = ''.join(
            f'<li>{nome} — {email} — Motivo: {motivo}</li>'
            for nome, email, motivo in stats['falhas']
        )
        alertas += (
            '<div style="background:#fef2f2;border-left:4px solid #dc2626;'
            'padding:16px;margin-bottom:12px;border-radius:4px;">'
            f'<strong style="color:#dc2626;">❌ FALHAS DE ENVIO ({len(stats["falhas"])})</strong>'
            f'<ul>{falhas_rows}</ul></div>'
        )

    zeradas = [d for d in ongs_detalhes if d['nota_final'] == 0]
    if zeradas:
        zeradas_rows = ''.join(
            f'<li>{d["nome"]} — <a href="{d["url_etransparente"]}" style="color:#ea580c;">ver página</a></li>'
            for d in zeradas
        )
        alertas += (
            '<div style="background:#fff7ed;border-left:4px solid #ea580c;'
            'padding:16px;margin-bottom:12px;border-radius:4px;">'
            f'<strong style="color:#ea580c;">⚠️ ONGs COM NOTA ZERADA ({len(zeradas)})</strong>'
            f'<ul>{zeradas_rows}</ul></div>'
        )

    p1 = alertas if alertas else '<p style="color:#888;font-size:13px;">Nenhum alerta nesta execução.</p>'

    # ── Seção 2: Resumo geral ──
    p2 = f'''<table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
  <tr>
    <td style="padding:12px;background:#f8fafc;border:1px solid #e2e8f0;font-size:13px;">Total de ONGs processadas</td>
    <td style="padding:12px;background:#f8fafc;border:1px solid #e2e8f0;font-size:13px;font-weight:700;">{stats['total']}</td>
  </tr>
  <tr>
    <td style="padding:12px;border:1px solid #e2e8f0;font-size:13px;">Emails enviados com sucesso</td>
    <td style="padding:12px;border:1px solid #e2e8f0;font-size:13px;font-weight:700;color:#16a34a;">{stats['enviados']}</td>
  </tr>
  <tr>
    <td style="padding:12px;background:#f8fafc;border:1px solid #e2e8f0;font-size:13px;">Sem email cadastrado</td>
    <td style="padding:12px;background:#f8fafc;border:1px solid #e2e8f0;font-size:13px;font-weight:700;color:#ea580c;">{len(stats['sem_email'])}</td>
  </tr>
  <tr>
    <td style="padding:12px;border:1px solid #e2e8f0;font-size:13px;">Falhas de envio</td>
    <td style="padding:12px;border:1px solid #e2e8f0;font-size:13px;font-weight:700;color:#dc2626;">{len(stats['falhas'])}</td>
  </tr>
  <tr>
    <td style="padding:12px;background:#f8fafc;border:1px solid #e2e8f0;font-size:13px;">Data/hora da execução</td>
    <td style="padding:12px;background:#f8fafc;border:1px solid #e2e8f0;font-size:13px;">{now}</td>
  </tr>
</table>'''

    # ── Seção 3: Tabela de ONGs por nota (pior primeiro) ──
    sorted_ongs = sorted(ongs_detalhes, key=lambda d: (d['nota_final'], d['nome']))
    CORES_CLASS = {'Regular': '#fef2f2', 'Bom': '#fefce8', 'Ótimo': '#f0fdf4'}

    table_rows = ''
    for i, d in enumerate(sorted_ongs, 1):
        bg = CORES_CLASS.get(d['classificacao'], '#ffffff')
        email_col = d['email'] if d['email'] else '—  sem email'
        pdf_link = (
            f'<a href="{d["pdf_sas_url"]}" style="color:#1a3a5c;">📄 Ver PDF</a>'
            if d['pdf_sas_url'] else '—'
        )
        table_rows += f'''<tr style="background:{bg};">
      <td style="padding:8px;border:1px solid #e2e8f0;">{i}</td>
      <td style="padding:8px;border:1px solid #e2e8f0;font-weight:600;">{d['nome']}</td>
      <td style="padding:8px;border:1px solid #e2e8f0;text-align:center;">{d['nota_final']}/{d['max_nota']}</td>
      <td style="padding:8px;border:1px solid #e2e8f0;text-align:center;">{d['classificacao']}</td>
      <td style="padding:8px;border:1px solid #e2e8f0;">{_html.escape(email_col)}</td>
      <td style="padding:8px;border:1px solid #e2e8f0;text-align:center;">{pdf_link}</td>
      <td style="padding:8px;border:1px solid #e2e8f0;text-align:center;"><a href="{d['url_etransparente']}" style="color:#1a3a5c;">🔗 Ver página</a></td>
    </tr>'''

    p3 = f'''<h3 style="font-family:'Montserrat',Arial,sans-serif;color:#1a3a5c;font-size:15px;margin:24px 0 12px;">ONGs por nota (pior primeiro)</h3>
<table style="width:100%;border-collapse:collapse;font-size:12px;">
  <thead>
    <tr style="background:#1a3a5c;color:#ffffff;">
      <th style="padding:10px;text-align:left;">#</th>
      <th style="padding:10px;text-align:left;">ONG</th>
      <th style="padding:10px;text-align:center;">Nota</th>
      <th style="padding:10px;text-align:center;">Classificação</th>
      <th style="padding:10px;text-align:left;">Email enviado para</th>
      <th style="padding:10px;text-align:center;">PDF</th>
      <th style="padding:10px;text-align:center;">Página</th>
    </tr>
  </thead>
  <tbody>
    {table_rows}
  </tbody>
</table>'''

    # ── Seção 4: ONGs sem email ──
    sem_email_nomes = stats.get('sem_email', [])
    if sem_email_nomes:
        sem_email_list = ''.join(f'<li>{_html.escape(n)}</li>' for n in sem_email_nomes)
    else:
        sem_email_list = '<li style="color:#888;">Nenhuma ONG sem email cadastrado.</li>'

    p4 = f'''<h3 style="font-family:'Montserrat',Arial,sans-serif;color:#1a3a5c;font-size:15px;margin:24px 0 12px;">ONGs sem email cadastrado</h3>
<ul>{sem_email_list}</ul>'''

    # ── Render no template ──
    html = template_html
    html = BANNER_IMG_RE.sub(banner_admin, html)
    html = html.replace('{{name}}', 'administrador do sistema')
    html = html.replace('{{titulo_post}}', titulo)
    html = html.replace('{{paragrafo_1}}', p1)
    html = html.replace('{{paragrafo_2}}', p2)
    html = html.replace('{{paragrafo_3}}', p3)
    html = html.replace('{{paragrafo_4}}', p4)
    html = html.replace('{{link_cta}}', '')
    html = html.replace('{{texto_cta}}', '')
    html = html.replace('{{pagina alternativa}}', '')
    html = html.replace('{{descadastro}}', REMOVIDO)
    return html

def main():
    # Proteção contra disparo acidental
    if os.environ.get('SEND_REPORTS_ENABLED', '').lower() != 'true':
        logger.warning(
            'SEND_REPORTS_ENABLED não está definida como true. '
            'Nenhum email enviado. Configure no .env para habilitar.'
        )
        return

    test_mode = os.environ.get('SEND_REPORTS_TEST_MODE', '').lower() == 'true'
    test_email = os.environ.get('SEND_REPORTS_TEST_EMAIL', 'comunicacao@direitocoletivo.org.br')

    smtp_config = {
        'host': get_env_or_raise('AIRFLOW__SMTP__SMTP_HOST'),
        'port': int(os.environ.get('AIRFLOW__SMTP__SMTP_PORT', '587')),
        'user': get_env_or_raise('AIRFLOW__SMTP__SMTP_USER'),
        'password': get_env_or_raise('AIRFLOW__SMTP__SMTP_PASSWORD'),
        'from': 'transparencia@direitocoletivo.org.br',
        'starttls': os.environ.get('AIRFLOW__SMTP__SMTP_STARTTLS', 'True').lower() == 'true',
    }

    mes, ano, mes_extenso, mes_ano_str = mes_ano()

    # Carregar dados
    ong_path = find_latest('oscs_etransparente_*.json')
    scores_path = find_latest(os.path.join('scores', 'transparency_scores_*.json'))
    template_html = carregar_template()

    if not ong_path:
        raise RuntimeError('Nenhum arquivo oscs_etransparente_*.json encontrado')
    if not scores_path:
        raise RuntimeError('Nenhum arquivo transparency_scores_*.json encontrado')

    ongs = carregar_ongs(ong_path)
    scores_list = carregar_scores(scores_path)

    # Mapa de scores por nome
    scores_map = {s['nome']: s for s in scores_list}

    # Última pasta de dashboards
    dash_base = os.path.join(BASE_DIR, 'output', 'dashboards')
    pasta_pdf = None
    latest_dash = find_latest_dir(dash_base)
    if latest_dash:
        pasta_pdf = os.path.join(latest_dash, 'pdf')

    if not pasta_pdf or not os.path.isdir(pasta_pdf):
        logger.warning('Pasta de PDFs não encontrada em %s', pasta_pdf)
        pasta_pdf = None

    # Build detalhes de todas as ONGs para o relatório de execução
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    ongs_detalhes = []
    for ong in ongs:
        nome = ong.get('nome', '').strip()
        if not nome:
            continue
        score = scores_map.get(nome, {})
        email = ong.get('email', '').strip()
        url_ong = ong.get('url', 'https://etransparente.org/')
        pdf_path = encontrar_pdf(pasta_pdf, nome) if pasta_pdf else None
        sas_url = ''
        if pdf_path and conn_str:
            blob_path = f'gold/{mes_ano_str}/pdf/{os.path.basename(pdf_path)}'
            try:
                sas_url = gerar_sas_url(conn_str, 'etransparente', blob_path)
            except Exception:
                pass
        ongs_detalhes.append({
            'nome': nome,
            'nota_final': score.get('nota_final', 0),
            'max_nota': score.get('max_nota', 30),
            'classificacao': score.get('classificacao', 'Regular'),
            'email': email,
            'pdf_sas_url': sas_url,
            'url_etransparente': url_ong,
        })

    # Em modo teste, enviar apenas 2 emails: 1 Bom/Ótimo + 1 Regular
    if test_mode:
        idc_pdf = encontrar_pdf_idc(pasta_pdf) if pasta_pdf else None
        bom_ong = regular_ong = None
        for ong in ongs:
            n = ong.get('nome', '').strip()
            e = ong.get('email', '').strip()
            if not n or not e:
                continue
            cls = scores_map.get(n, {}).get('classificacao', 'Regular')
            if cls in ('Bom', 'Ótimo') and bom_ong is None:
                bom_ong = ong
            if cls == 'Regular' and regular_ong is None:
                regular_ong = ong
            if bom_ong and regular_ong:
                break
        ongs_a_processar = [o for o in (bom_ong, regular_ong) if o is not None]
        logger.info(
            'Modo teste: %d ONG(s) selecionada(s) (1 Bom/Ótimo, 1 Regular)',
            len(ongs_a_processar),
        )
    else:
        ongs_a_processar = ongs
        idc_pdf = None

    stats = {
        'total': len(ongs),
        'enviados': 0,
        'sem_email': [],
        'falhas': [],
    }

    for ong in ongs_a_processar:
        nome = ong.get('nome', '').strip()
        email = ong.get('email', '').strip()
        url_ong = ong.get('url', 'https://etransparente.org')

        if not nome:
            continue

        score_entry = scores_map.get(nome, {})
        classificacao = score_entry.get('classificacao', 'Regular')

        p1, p2, p3, p4 = build_paragraphs(score_entry, mes, ano, mes_extenso)

        if not email:
            logger.info('ONG sem e-mail: %s', nome)
            stats['sem_email'].append(nome)
            continue

        assunto = f'{nome} — Relatório Mensal de Transparência — {mes_extenso}/{ano}'

        pdf_path = encontrar_pdf(pasta_pdf, nome) if pasta_pdf else None
        if not pdf_path and pasta_pdf:
            logger.warning('PDF não encontrado para: %s', nome)

        destino = email
        if test_mode:
            destino = test_email
            assunto = f'[TESTE] {assunto}'
            if idc_pdf:
                pdf_path = idc_pdf

        if pdf_path:
            conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
            if conn_str:
                blob_path = f'gold/{mes_ano_str}/pdf/{os.path.basename(pdf_path)}'
                cta_url = gerar_sas_url(conn_str, 'etransparente', blob_path)
            else:
                cta_url = url_ong
        else:
            cta_url = url_ong

        html_body = render_template(template_html, nome, cta_url, assunto, p1, p2, p3, p4)

        if test_mode:
            aviso = (
                f'<p style="background:#fff3cd;padding:12px;font-size:12px;">'
                f'<strong>⚠️ MODO DE TESTE</strong> — Em produção este email seria '
                f'enviado para: {email}</p>'
            )
            html_body = html_body.replace(
                '</head>',
                f'</head>{aviso}',
            )

        try:
            enviar_email(smtp_config, destino, assunto, html_body, pdf_path)
            logger.info('E-mail enviado: %s (%s)', nome, destino)
            stats['enviados'] += 1
        except Exception as e:
            logger.error('Falha ao enviar para %s (%s): %s', nome, destino, e)
            stats['falhas'].append((nome, destino, str(e)))

    # Relatório de execução
    relatorio_html = build_relatorio_execucao_html(
        template_html, stats, ongs_detalhes, mes_extenso, ano
    )
    consolidado_subject = (
        f'[Pipeline etransparente] Relatório de Execução — {mes_extenso}/{ano} — '
        f'{stats["enviados"]}/{stats["total"]} enviados'
    )
    try:
        enviar_email(
            smtp_config,
            'comunicacao@direitocoletivo.org.br',
            consolidado_subject,
            relatorio_html,
        )
        logger.info('Relatório de execução enviado para comunicacao@direitocoletivo.org.br')
    except Exception as e:
        logger.error('Falha ao enviar relatório de execução: %s', e)

    logger.info(
        'Resumo: %d total, %d enviados, %d sem e-mail, %d falhas',
        stats['total'], stats['enviados'],
        len(stats['sem_email']), len(stats['falhas']),
    )

if __name__ == '__main__':
    main()
