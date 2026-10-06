#!/usr/bin/env python3
"""
Desbloqueio TÉCNICO de um envio bloqueado por erro reportado — só para FALSO ALARME.

Se o erro era real: corrija e rode a DAG de novo (ou preparar_envios.py). A nova
preparação gera novo código, nova amostra e exige nova conferência — e arquiva o
bloqueio automaticamente. Este script NÃO é o caminho para erros reais.

Efeito: arquiva bloqueio.json em historico/ com quem liberou, quando e por quê,
e avisa presidência, transparência e comunicação. A presidência ainda precisa
conferir e confirmar o envio normalmente.

Uso (na VM):
  docker exec -w /home/airflow airflow-scheduler python scripts/desbloquear_envio.py \\
      --ciclo 2026-10 --responsavel "Victor Breia" --motivo "Views conferidas no GA4: 12 está correto"
"""
import argparse
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ciclo import adicionar_argumento_ciclo, rotulo_ciclo  # noqa: E402

CONTAINER = 'etransparente'


def main():
    p = argparse.ArgumentParser(description='Desbloqueio técnico (falso alarme) de envio bloqueado')
    adicionar_argumento_ciclo(p)
    p.add_argument('--responsavel', required=True, help='Nome de quem está liberando')
    p.add_argument('--motivo', required=True, help='Por que o reporte era falso alarme (fica registrado)')
    a = p.parse_args()
    if len(a.motivo.strip()) < 15:
        raise SystemExit('Descreva o motivo com pelo menos 15 caracteres — ele vai para o registro e para a gestão.')

    from azure.storage.blob import BlobServiceClient
    cont = BlobServiceClient.from_connection_string(
        os.environ['AZURE_STORAGE_CONNECTION_STRING']).get_container_client(CONTAINER)
    prefixo = f'envios/{a.ciclo}/'
    blob = cont.get_blob_client(prefixo + 'bloqueio.json')
    if not blob.exists():
        raise SystemExit(f'O ciclo {a.ciclo} não está bloqueado.')

    bloqueio = json.loads(blob.download_blob().readall())
    agora = datetime.now(timezone.utc)
    ts = agora.strftime('%Y%m%dT%H%M%SZ')

    # Se o bloqueio chegou depois da confirmação, os e-mails pendentes foram
    # marcados como "suspensos". Sem nenhum e-mail enviado, a confirmação
    # anterior é arquivada e a presidência confirma de novo. Com envio parcial,
    # a retomada é manual (raro) — não arriscamos duplicar e-mails.
    status = [(b.name, json.loads(cont.get_blob_client(b.name).download_blob().readall()))
              for b in cont.list_blobs(name_starts_with=prefixo + 'status/')]
    if any(st.get('estado') in ('enviado', 'enviando') for _, st in status):
        raise SystemExit('Há e-mails já enviados neste ciclo: a retomada parcial é manual. '
                         'Nada foi alterado. Ver doc/CICLO_E_VALIDACAO.md.')
    arquivados = []
    for nome_blob, st in status:
        cont.get_blob_client(f'{prefixo}historico/{ts}_status_{st["slug"]}.json').upload_blob(
            json.dumps(st, ensure_ascii=False).encode('utf-8'))
        cont.delete_blob(nome_blob)
    for nome in ('aprovacao.json', 'resultado.json'):
        b = cont.get_blob_client(prefixo + nome)
        if b.exists():
            cont.get_blob_client(f'{prefixo}historico/{ts}_{nome}').upload_blob(b.download_blob().readall())
            b.delete_blob()
            arquivados.append(nome)
    bloqueio['desbloqueio'] = {'responsavel': a.responsavel, 'motivo': a.motivo.strip(),
                               'tipo': 'falso_alarme', 'em': agora.isoformat(timespec='seconds')}
    cont.get_blob_client(f'{prefixo}historico/{ts}_bloqueio.json').upload_blob(
        json.dumps(bloqueio, ensure_ascii=False, indent=2).encode('utf-8'))
    blob.delete_blob()

    reportes = ''.join(f'<li>{escape(r["osc"])} — {escape(r["campo"])}: {escape(r["descricao"])} '
                       f'({escape(r["conta"])})</li>' for r in bloqueio.get('reportes', []))
    hora = agora.astimezone(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M (Brasília)')
    corpo = (
        '<div style="font-family:Arial,sans-serif;max-width:640px">'
        f'<h2 style="color:#1e3a8a">Envio do ciclo {rotulo_ciclo(a.ciclo)} desbloqueado</h2>'
        f'<p><b>Responsável:</b> {escape(a.responsavel)}<br><b>Data/hora:</b> {hora}<br>'
        f'<b>Motivo (falso alarme):</b> {escape(a.motivo)}</p>'
        f'<p><b>Reportes analisados:</b></p><ul>{reportes}</ul>'
        + ('<p>A confirmação anterior foi arquivada. ' if 'aprovacao.json' in arquivados else '<p>') +
        'O envio <b>não</b> foi retomado automaticamente: a presidência precisa conferir e confirmar '
        'em <a href="https://dashboard.etransparente.org/envio">dashboard.etransparente.org/envio</a>.</p></div>')
    destinatarios = [e.strip() for e in os.environ.get(
        'NOTIFICAR_GESTAO', 'presidencia@direitocoletivo.org.br,transparencia@direitocoletivo.org.br,'
        'comunicacao@direitocoletivo.org.br').split(',') if e.strip()]
    msg = MIMEText(corpo, 'html', 'utf-8')
    msg['Subject'] = f'[etransparente] Envio do ciclo {rotulo_ciclo(a.ciclo)} desbloqueado (falso alarme)'
    msg['From'] = 'transparencia@direitocoletivo.org.br'
    msg['To'] = ', '.join(destinatarios)
    with smtplib.SMTP(os.environ['AIRFLOW__SMTP__SMTP_HOST'],
                      int(os.environ.get('AIRFLOW__SMTP__SMTP_PORT', '587')), timeout=30) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(os.environ['AIRFLOW__SMTP__SMTP_USER'], os.environ['AIRFLOW__SMTP__SMTP_PASSWORD'])
        s.send_message(msg, to_addrs=destinatarios)
    print(f'Ciclo {a.ciclo} desbloqueado e gestão avisada. A presidência precisa confirmar o envio em /envio.')


if __name__ == '__main__':
    main()
