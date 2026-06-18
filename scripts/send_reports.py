#!/usr/bin/env python3
"""
Envio mensal de relatórios de transparência por e-mail.

Para cada ONG com e-mail cadastrado:
  - E-mail HTML com template IDC + PDF anexado

Para o IDC (comunicacao@direitocoletivo.org.br):
  - Relatório consolidado da execução
"""
import glob
import json
import logging
import os
import re
import smtplib
import ssl
from datetime import date, datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

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

def normalizar_nome(nome):
    s = nome.strip().lower()
    s = re.sub(r'[^a-z0-9áéíóúâêôãõçü]+', '_', s)
    s = s.strip('_')
    return s

def encontrar_pdf(pasta_pdf, nome_ong):
    norm = normalizar_nome(nome_ong)
    for f in os.listdir(pasta_pdf):
        if normalizar_nome(f).endswith(norm + '.pdf'):
            return os.path.join(pasta_pdf, f)
    return None

def encontrar_pdf_idc(pasta_pdf):
    for f in os.listdir(pasta_pdf):
        nome = normalizar_nome(f)
        if 'instituto_de_direito_coletivo' in nome or '_idc_' in nome or nome.startswith('idc_'):
            return os.path.join(pasta_pdf, f)
    return None

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
    saudacao = (
        f'pessoa responsável pela {nome_ong.title()} '
        f'na plataforma etransparente.org'
    )
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

def build_consolidado_html(stats):
    now = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    mes, ano, *_ = mes_ano()
    rows_sem_email = ''.join(
        f'<li>{nome}</li>' for nome in stats['sem_email']
    ) if stats['sem_email'] else '<li style="color:#888;">Nenhuma</li>'

    rows_falhas = ''.join(
        f'<li>{nome} — {email}: {motivo}</li>'
        for nome, email, motivo in stats['falhas']
    ) if stats['falhas'] else '<li style="color:#888;">Nenhuma</li>'

    return f'''<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;padding:20px;">
<h2>Relatório de Execução — {mes}/{ano}</h2>
<p><strong>Data/hora:</strong> {now}</p>
<p><strong>Total de ONGs processadas:</strong> {stats['total']}</p>
<p><strong>E-mails enviados com sucesso:</strong> {stats['enviados']}</p>

<h3>ONGs sem e-mail cadastrado</h3>
<ul>{rows_sem_email}</ul>

<h3>Falhas de envio</h3>
<ul>{rows_falhas}</ul>
</body>
</html>'''

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
            cta_url = (
                f'https://etransparentedata.blob.core.windows.net/etransparente'
                f'/gold/{mes_ano_str}/pdf/{os.path.basename(pdf_path)}'
            )
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

    # Relatório consolidado
    consolidado_html = build_consolidado_html(stats)
    consolidado_subject = (
        f'[Pipeline etransparente] Relatório de Execução — {mes_ano_str}'
    )
    try:
        enviar_email(
            smtp_config,
            'comunicacao@direitocoletivo.org.br',
            consolidado_subject,
            consolidado_html,
        )
        logger.info('Relatório consolidado enviado para comunicacao@direitocoletivo.org.br')
    except Exception as e:
        logger.error('Falha ao enviar relatório consolidado: %s', e)

    logger.info(
        'Resumo: %d total, %d enviados, %d sem e-mail, %d falhas',
        stats['total'], stats['enviados'],
        len(stats['sem_email']), len(stats['falhas']),
    )

if __name__ == '__main__':
    main()
