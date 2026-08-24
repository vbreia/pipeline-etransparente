#!/usr/bin/env python3
"""
Envia o comunicado institucional de atualização da plataforma para todas as
OSCs cadastradas com e-mail. Reaproveita a função enviar_email() já existente
em send_reports.py — não duplica lógica de SMTP.

Diferente do send_reports.py (relatório mensal, um por OSC com PDF anexado),
este script manda o MESMO texto para todas as OSCs, sem anexo.

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
import html as _html
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reaproveita a função de envio já validada em send_reports.py — não duplica lógica de SMTP.
from send_reports import enviar_email  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ASSUNTO = "Atualização da plataforma etransparente.org"

# Conteúdo aprovado pela presidência do IDC em 24/08/2026.
CORPO_TEXTO = """Prezados(as),

O Instituto de Direito Coletivo (IDC) atualizou a plataforma etransparente.org com novos
recursos de transparência e controle de qualidade dos dados.

Cada relatório mensal agora exibe a versão da metodologia que o gerou. Se mudarmos a forma de
calcular a pontuação no futuro, essa mudança fica registrada e visível em cada relatório.
Notas de ciclos com versões diferentes deixam de ser diretamente comparáveis entre si, e o
relatório vai sinalizar isso quando acontecer.

Adicionamos um canal direto para reportar qualquer divergência percebida nos dados. O botão
"Notou algo errado? Reporte aqui" aparece no PDF do relatório, no e-mail mensal e no painel de
acompanhamento, já preenchido com os dados do relatório específico para agilizar nossa
resposta.

Passamos também a aceitar documentos nos formatos JPG e PNG, além de PDF, DOC e DOCX. Muitas
organizações só têm foto ou digitalização do documento disponível, não um PDF.

Essas mudanças fazem parte do nosso compromisso contínuo com a precisão e a transparência dos
dados que a plataforma apresenta.

Qualquer dúvida, escreva para comunicacao@direitocoletivo.org.br.

Atenciosamente,
Equipe etransparente.org
Instituto de Direito Coletivo"""


def montar_html(corpo_texto: str) -> str:
    """Converte o texto plano em HTML simples, um <p> por parágrafo."""
    paragrafos = corpo_texto.strip().split('\n\n')
    corpo_html = ''.join(
        f'<p style="margin:0 0 16px;font-family:Arial,sans-serif;font-size:14px;'
        f'line-height:1.6;color:#1e2a3a;">{_html.escape(p).replace(chr(10), "<br>")}</p>'
        for p in paragrafos
    )
    return f'<div style="max-width:600px;margin:0 auto;padding:24px;">{corpo_html}</div>'


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

    ong_path = find_latest('oscs_etransparente_*.json')
    if not ong_path:
        logger.error('Nenhum arquivo oscs_etransparente_*.json encontrado em output/.')
        return

    ongs = carregar_ongs(ong_path)
    html_body = montar_html(CORPO_TEXTO)

    if test_mode:
        logger.warning(
            'COMUNICADO_TEST_MODE ativo: enviando 1 e-mail de amostra para %s, '
            'em vez de %d e-mails reais.',
            test_email, len(ongs),
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
        if not email:
            sem_email += 1
            logger.warning('Sem e-mail cadastrado: %s', nome)
            continue
        try:
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