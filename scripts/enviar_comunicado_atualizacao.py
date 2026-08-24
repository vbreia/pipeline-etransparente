#!/usr/bin/env python3
"""
Envia o comunicado institucional de atualização da plataforma para todas as
OSCs cadastradas com e-mail. Reaproveita o template padrão de e-mail do IDC
(assets/email_template_idc_v3.html) e a função enviar_email() já existente em
send_reports.py — não duplica lógica de SMTP nem de layout.

Diferente do send_reports.py (relatório mensal, um por OSC com PDF anexado),
este script manda o MESMO conteúdo para todas as OSCs, sem anexo — só muda a
saudação personalizada, igual ao padrão já usado no relatório mensal.

Proteções (mesmo padrão de send_reports.py):
  - COMUNICADO_ENABLED=true é obrigatório para enviar de verdade.
  - COMUNICADO_TEST_MODE=true redireciona todos os envios para
    COMUNICADO_TEST_EMAIL (default: comunicacao@direitocoletivo.org.br),
    prefixando o assunto com [TESTE].

Uso:
    # teste (não sai nada de verdade, vai só para o e-mail de teste)
    docker exec -e COMUNICADO_ENABLED=true -e COMUNICADO_TEST_MODE=true \\
        airflow-scheduler bash -c "cd /home/airflow && python3 scripts/enviar_comunicado_atualizacao.py"

    # envio real, para todas as OSCs
    docker exec -e COMUNICADO_ENABLED=true \\
        airflow-scheduler bash -c "cd /home/airflow && python3 scripts/enviar_comunicado_atualizacao.py"
"""
import glob
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reaproveita a função de envio e a constante de descadastro já validadas em
# send_reports.py — não duplica lógica de SMTP nem de layout.
from send_reports import enviar_email, REMOVIDO, BANNER_IMG_RE  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(BASE_DIR, 'assets', 'email_template_idc_v3.html')

ASSUNTO = "Atualização da plataforma etransparente.org"

# Conteúdo aprovado pela presidência do IDC em 24/08/2026, condensado nos 4
# parágrafos que o template padrão suporta (sem reescrever nenhuma frase — só
# agrupando blocos aprovados dentro do mesmo <p> onde necessário).
PARAGRAFO_1 = (
    "O Instituto de Direito Coletivo (IDC) atualizou a plataforma etransparente.org "
    "com novos recursos de transparência e controle de qualidade dos dados. Cada "
    "relatório mensal agora exibe a versão da metodologia que o gerou. Se por algum "
    "motivo precisarmos mudar a forma de calcular a pontuação no futuro por mudança "
    "normativa, por exemplo, a alteração fica registrada e visível em cada relatório."
)
PARAGRAFO_2 = (
    "Adicionamos um canal direto para reportar qualquer divergência percebida nos "
    'dados. O botão "Notou algo errado? Reporte aqui" aparece no PDF do relatório, '
    "no e-mail mensal e no painel de acompanhamento, já preenchido com os dados do "
    "relatório específico para agilizar nossa resposta."
)
PARAGRAFO_3 = (
    "Passamos também a aceitar documentos nos formatos JPG e PNG, além de PDF, DOC "
    "e DOCX. Muitas organizações só têm foto ou digitalização do documento "
    "disponível, não um PDF."
)
PARAGRAFO_4 = (
    'Presando sempre pela transparência, mantemos um '
    '<a href="https://medium.com/@fastencoding/o-que-%C3%A9-um-changelog-5e20973324cd" '
    'style="color:#1a3a5c;text-decoration:underline;">changelog</a> público das '
    'mudanças na plataforma, disponível '
    '<a href="https://github.com/vbreia/pipeline-etransparente/blob/main/CHANGELOG.md" '
    'style="color:#1a3a5c;text-decoration:underline;">nesse link</a>. Publicamos ali '
    "cada correção e cada novo recurso, com data e descrição. Essas mudanças fazem "
    "parte do nosso compromisso contínuo com a precisão e a transparência dos dados "
    "que a plataforma apresenta. Qualquer dúvida, escreva para "
    '<a href="mailto:comunicacao@direitocoletivo.org.br" '
    'style="color:#1a3a5c;text-decoration:underline;">comunicacao@direitocoletivo.org.br</a>.'
)


def render_comunicado(template_html: str, nome_ong: str, url_ong: str) -> str:
    """Monta o e-mail de comunicado usando o mesmo template/estilo do relatório
    mensal, com banner de título próprio e saudação personalizada por OSC."""
    banner_html = (
        '<table role="presentation" border="0" cellpadding="0" cellspacing="0" '
        'width="100%"><tr><td align="center" '
        'style="background-color:#1a3a5c;padding:32px 24px;">'
        '<h1 style="color:#ffffff;font-size:20px;margin:0;font-weight:700;'
        'font-family:\'Montserrat\',Arial,sans-serif;letter-spacing:1px;">'
        'ATUALIZAÇÃO DA PLATAFORMA</h1>'
        '</td></tr></table>'
    )
    saudacao = (
        f'pessoa responsável pela instituição '
        f'<a href="{url_ong}" style="color:#1a3a5c;font-weight:700;text-decoration:none;">'
        f'{nome_ong.title()}</a> '
        f'na plataforma etransparente.org'
    )
    html = template_html
    html = BANNER_IMG_RE.sub(banner_html, html)
    html = html.replace('{{name}}', saudacao)
    html = html.replace('{{paragrafo_1}}', PARAGRAFO_1)
    html = html.replace('{{paragrafo_2}}', PARAGRAFO_2)
    html = html.replace('{{paragrafo_3}}', PARAGRAFO_3)
    html = html.replace('{{paragrafo_4}}', PARAGRAFO_4)
    html = html.replace('{{link_cta}}', 'https://etransparente.org')
    html = html.replace('{{texto_cta}}', 'Conheça a plataforma etransparente.org')
    html = html.replace('{{titulo_post}}', ASSUNTO)
    html = html.replace('{{pagina alternativa}}', '')
    html = html.replace('{{descadastro}}', REMOVIDO)
    html = html.replace('{{link_report_erro}}', '')
    return html


def find_latest(pattern: str) -> str | None:
    files = sorted(glob.glob(os.path.join(BASE_DIR, 'output', pattern)))
    return files[-1] if files else None


def carregar_ongs(path: str) -> list:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get('resultados', data.get('ongs', []))
    return data


def main():
    if os.environ.get('COMUNICADO_ENABLED', '').lower() != 'true':
        logger.warning(
            'COMUNICADO_ENABLED não está definido como "true" — nenhum e-mail será enviado. '
            'Isso é uma proteção contra disparo acidental.'
        )
        return

    test_mode = os.environ.get('COMUNICADO_TEST_MODE', '').lower() == 'true'
    test_email = os.environ.get('COMUNICADO_TEST_EMAIL', 'comunicacao@direitocoletivo.org.br')

    smtp_config = {
        'host': os.environ.get('AIRFLOW__SMTP__SMTP_HOST', 'smtp.gmail.com'),
        'port': int(os.environ.get('AIRFLOW__SMTP__SMTP_PORT', '587')),
        'from': os.environ.get('AIRFLOW__SMTP__SMTP_MAIL_FROM', ''),
        'user': os.environ.get('AIRFLOW__SMTP__SMTP_USER', ''),
        'password': os.environ.get('AIRFLOW__SMTP__SMTP_PASSWORD', ''),
        'starttls': os.environ.get('AIRFLOW__SMTP__SMTP_STARTTLS', 'True').lower() == 'true',
    }

    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template_html = f.read()

    ong_path = find_latest('oscs_etransparente_*.json')
    if not ong_path:
        logger.error('Nenhum arquivo oscs_etransparente_*.json encontrado em output/.')
        return

    ongs = carregar_ongs(ong_path)

    if test_mode:
        amostra = ongs[0] if ongs else {'nome': 'OSC de teste', 'url': 'https://etransparente.org'}
        html_body = render_comunicado(template_html, amostra.get('nome', ''), amostra.get('url', ''))
        logger.warning(
            'COMUNICADO_TEST_MODE ativo: enviando 1 e-mail de amostra (%s) para %s, '
            'em vez de %d e-mails reais.',
            amostra.get('nome', ''), test_email, len(ongs),
        )
        enviar_email(smtp_config, test_email, f'[TESTE] {ASSUNTO}', html_body)
        logger.info('E-mail de teste enviado para %s', test_email)
        return

    enviados = 0
    sem_email = 0
    falhas = 0

    for ong in ongs:
        nome = ong.get('nome', '').strip()
        email = ong.get('email', '').strip()
        url_ong = ong.get('url', 'https://etransparente.org')
        if not email:
            sem_email += 1
            logger.warning('Sem e-mail cadastrado: %s', nome)
            continue
        try:
            html_body = render_comunicado(template_html, nome, url_ong)
            enviar_email(smtp_config, email, ASSUNTO, html_body)
            enviados += 1
            logger.info('Comunicado enviado: %s (%s)', nome, email)
        except Exception as exc:
            falhas += 1
            logger.error('Falha ao enviar para %s (%s): %s', nome, email, exc)

    logger.info(
        'Resumo: %d total, %d enviados, %d sem e-mail, %d falhas',
        len(ongs), enviados, sem_email, falhas,
    )


if __name__ == '__main__':
    main()