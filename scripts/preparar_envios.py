#!/usr/bin/env python3
"""
Prepara o envio do ciclo — monta os e-mails PRONTOS, sorteia a amostra de
conferência e calcula o código de validação. NÃO envia nada.

Só roda se `validar_ciclo.py` aprovou o ciclo E se os arquivos validados não
mudaram desde a validação (conferido por hash).

Saída (local em output/envios/{ciclo}/ e no Azure em envios/{ciclo}/ — FORA de gold/,
que é legível pelo token do dashboard; aqui há e-mails de OSCs):
  emails/{slug}.json   e-mail final de cada OSC (destinatário, assunto, HTML, PDF)
  amostra.json         IDC (fixa) + 2 OSCs sorteadas para a conferência humana
  manifesto.json       lista do que será enviado + código de validação

O código de validação é o hash de tudo que será enviado. A aprovação na página
/envio vale para ESTE código: se algo for regerado, o código muda e a
aprovação anterior deixa de valer.

Uso:
  python scripts/preparar_envios.py --ciclo 2026-10
  python scripts/preparar_envios.py --ciclo 2026-10 --destino-teste comunicacao@direitocoletivo.org.br
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import unicodedata
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ciclo import adicionar_argumento_ciclo, ciclo_anterior, dias_do_ciclo, rotulo_ciclo  # noqa: E402
from artefatos import (  # noqa: E402
    gravar_json, ler_json, localizar_dashboards_do_ciclo, sha256_arquivo, sha256_json,
)

CONTAINER = 'etransparente'
VALIDADE_LINK_PDF_DIAS = 60
TAMANHO_AMOSTRA_SORTEADA = 2
SLUG_IDC = 'instituto-de-direito-coletivo'


# ─────────────────────────────────────────────────────────────────────────────
# Lógica pura (testada no GitHub Actions)
# ─────────────────────────────────────────────────────────────────────────────

def _sem_acento(t: str) -> str:
    return unicodedata.normalize('NFKD', t or '').encode('ASCII', 'ignore').decode().lower()


def e_idc(r: dict) -> bool:
    return SLUG_IDC in (r.get('slug') or '') or 'instituto de direito coletivo' in _sem_acento(r.get('nome', ''))


def elegivel(r: dict) -> bool:
    """Pode receber e-mail: tem destinatário e PDF gerado."""
    return bool((r.get('email') or '').strip()) and bool(r.get('pdf_gerado'))


def media_diaria(total: int | None, dias: int) -> str:
    """Mesmo formato do PDF (dash.py): uma casa decimal, vírgula."""
    if total is None or not dias:
        return '—'
    return f'{total / dias:.1f}'.replace('.', ',')


def escolher_amostra(relatorios: list[dict], amostra_anterior: set[str],
                     rng: random.Random, n_sorteadas: int = TAMANHO_AMOSTRA_SORTEADA) -> list[dict]:
    """IDC fixa + n OSCs sorteadas entre as elegíveis.

    Evita repetir as sorteadas do ciclo anterior quando há opção. O sorteio usa
    gerador do sistema (não reprodutível) e é feito aqui, no servidor — a página
    só exibe o resultado, então recarregar não troca as OSCs.
    """
    elegiveis = [r for r in relatorios if elegivel(r)]
    idc = next((r for r in elegiveis if e_idc(r)), None)
    outras = [r for r in elegiveis if not e_idc(r)]
    novas = [r for r in outras if r['slug'] not in amostra_anterior]
    repetidas = [r for r in outras if r['slug'] in amostra_anterior]
    rng.shuffle(novas)
    rng.shuffle(repetidas)
    sorteadas = (novas + repetidas)[:n_sorteadas]
    escolhidas = ([idc] if idc else []) + sorteadas
    return [{'slug': r['slug'], 'fixa': r is idc} for r in escolhidas]


def calcular_codigo(ciclo: str, sha_validacao: str, sha_relatorios: str,
                    emails: list[dict], amostra: list[dict]) -> str:
    """Hash de tudo que será enviado + da validação que autorizou."""
    return sha256_json({
        'ciclo': ciclo,
        'sha256_validacao': sha_validacao,
        'sha256_relatorios': sha_relatorios,
        'emails': [{k: e[k] for k in ('slug', 'destinatario', 'assunto', 'pdf_blob', 'pdf_sha256', 'email_sha256')}
                   for e in sorted(emails, key=lambda x: x['slug'])],
        'amostra': [a['slug'] for a in amostra],
    })


def conferir_validacao(validacao: dict, ciclo: str, sha_relatorios: str, sha_views: str) -> list[str]:
    """Motivos para NÃO preparar (lista vazia = pode preparar)."""
    motivos = []
    if validacao.get('ciclo') != ciclo:
        motivos.append(f'validação é do ciclo {validacao.get("ciclo")}, não de {ciclo}')
    if validacao.get('status') != 'aprovado':
        motivos.append(f'validação do ciclo está "{validacao.get("status")}" '
                       f'(falhas: {", ".join(validacao.get("resumo", {}).get("bloqueantes_com_falha", []))})')
    art = validacao.get('artefatos', {})
    if art.get('sha256_relatorios') != sha_relatorios:
        motivos.append('os relatórios mudaram depois da validação — valide de novo')
    if art.get('sha256_views') != sha_views:
        motivos.append('o arquivo de visualizações mudou depois da validação — valide de novo')
    return motivos


def avisar_ciclo_pronto(manifesto: dict, amostra: list[dict], validacao: dict) -> None:
    """E-mail interno para presidência, transparência e comunicação (usa o SMTP da VM)."""
    import html as _h
    import smtplib
    import ssl
    from email.mime.text import MIMEText

    destinatarios = [e.strip() for e in os.environ.get(
        'NOTIFICAR_GESTAO',
        'presidencia@direitocoletivo.org.br,transparencia@direitocoletivo.org.br,'
        'comunicacao@direitocoletivo.org.br').split(',') if e.strip()]
    resumo = validacao.get('resumo', {})
    alertas = [v for v in validacao.get('verificacoes', []) if not v['ok']]
    itens = ''.join(f'<li>⚠️ {_h.escape(v["titulo"])}: {_h.escape(v["detalhe"])}'
                    + ''.join(f'<br>&nbsp;&nbsp;– {_h.escape(str(i))}' for i in v['itens'][:15]) + '</li>'
                    for v in alertas)
    amostra_html = ''.join(f'<li>{_h.escape(a["nome"])}{" (fixa)" if a["fixa"] else ""}</li>' for a in amostra)
    teste = ' [ENSAIO]' if manifesto.get('modo_teste') else ''
    corpo = (
        '<div style="font-family:Arial,sans-serif;max-width:640px;color:#0f172a">'
        f'<h2 style="color:#1e3a8a">Ciclo {_h.escape(manifesto["rotulo"])} pronto para conferência{teste}</h2>'
        f'<p>A validação automática aprovou o ciclo ({len(validacao.get("verificacoes", []))} verificações). '
        f'<b>{manifesto["total_emails"]}</b> e-mails estão preparados e <b>nada foi enviado</b>.</p>'
        f'<p>Total de visualizações no ciclo: <b>{resumo.get("total_views", "?")}</b> · '
        f'OSCs: <b>{manifesto["total_oscs"]}</b> · Sem e-mail: <b>{len(manifesto["sem_email"])}</b> · '
        f'Código de validação: <b>{manifesto["codigo_curto"]}</b></p>'
        + (f'<p><b>Pontos de atenção:</b></p><ul>{itens}</ul>' if itens else '')
        + f'<p><b>Amostra para conferência:</b></p><ul>{amostra_html}</ul>'
        '<p>Para conferir e autorizar o envio: '
        '<a href="https://dashboard.etransparente.org/envio">dashboard.etransparente.org/envio</a> '
        '(acesso da presidência).</p>'
        '<p style="font-size:12px;color:#64748b">Mensagem automática do pipeline etransparente.</p></div>'
    )
    msg = MIMEText(corpo, 'html', 'utf-8')
    msg['Subject'] = f'[etransparente]{teste} Ciclo {manifesto["rotulo"]} pronto para conferência e envio'
    msg['From'] = 'transparencia@direitocoletivo.org.br'
    msg['To'] = ', '.join(destinatarios)
    with smtplib.SMTP(os.environ['AIRFLOW__SMTP__SMTP_HOST'],
                      int(os.environ.get('AIRFLOW__SMTP__SMTP_PORT', '587')), timeout=30) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(os.environ['AIRFLOW__SMTP__SMTP_USER'], os.environ['AIRFLOW__SMTP__SMTP_PASSWORD'])
        s.send_message(msg, to_addrs=destinatarios)
    print(f'Aviso "ciclo pronto" enviado para: {", ".join(destinatarios)}')


# ─────────────────────────────────────────────────────────────────────────────
# Execução (VM)
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Prepara (sem enviar) os e-mails do ciclo')
    adicionar_argumento_ciclo(parser)
    parser.add_argument('--destino-teste', default='',
                        help='Envia TODOS os e-mails para este endereço (ensaio). Marca o manifesto como teste.')
    args = parser.parse_args()
    ciclo = args.ciclo

    from azure.storage.blob import BlobServiceClient
    import send_reports as sr  # reaproveita o template e os textos já aprovados

    base = '/home/airflow' if os.path.exists('/home/airflow/output') else os.getcwd()
    out = os.path.join(base, 'output')

    # 1. Só prepara o que foi validado — e se nada mudou desde a validação
    pasta, manifesto_rel = localizar_dashboards_do_ciclo(out, ciclo)
    validacao_path = os.path.join(out, f'validacao_{ciclo}.json')
    if not pasta or not os.path.isfile(validacao_path):
        raise SystemExit(f'Faltam relatórios ou validação do ciclo {ciclo}. Rode dash.py e validar_ciclo.py antes.')
    relatorios = ler_json(manifesto_rel)
    validacao = ler_json(validacao_path)
    sha_rel = sha256_arquivo(manifesto_rel)
    views_path = os.path.join(out, f'oscs_views_{ciclo}.json')
    sha_views = sha256_arquivo(views_path) if os.path.isfile(views_path) else ''
    motivos = conferir_validacao(validacao, ciclo, sha_rel, sha_views)
    if motivos:
        print('PREPARAÇÃO RECUSADA:\n  - ' + '\n  - '.join(motivos))
        raise SystemExit(1)
    sha_validacao = sha256_arquivo(validacao_path)

    cliente = BlobServiceClient.from_connection_string(os.environ['AZURE_STORAGE_CONNECTION_STRING'])
    cont = cliente.get_container_client(CONTAINER)
    prefixo = f'envios/{ciclo}/'

    # 2. Nunca preparar de novo um ciclo em que algum e-mail JÁ SAIU (evita duplicidade).
    #    Se o envio foi interrompido por bloqueio sem nenhum e-mail enviado, a
    #    nova preparação arquiva os status antigos e recomeça.
    status_antigos = list(cont.list_blobs(name_starts_with=prefixo + 'status/'))
    for b in status_antigos:
        if json.loads(cont.get_blob_client(b.name).download_blob().readall()).get('estado') in ('enviado', 'enviando'):
            raise SystemExit(f'O ciclo {ciclo} já teve e-mails enviados — preparação recusada para evitar '
                             f'duplicidade. Tratamento manual necessário (ver doc/CICLO_E_VALIDACAO.md).')

    # 3. Montar os e-mails
    ano, mes = (int(x) for x in ciclo.split('-'))
    mes_extenso = sr.MESES[mes]
    template = sr.carregar_template()
    verificacoes = sr.carregar_verificacoes(ciclo)
    n_dias = len(dias_do_ciclo(ciclo))
    conn = os.environ['AZURE_STORAGE_CONNECTION_STRING']
    modo_teste = bool(args.destino_teste)

    dir_envio = os.path.join(out, 'envios', ciclo)
    dir_emails = os.path.join(dir_envio, 'emails')
    for antigo in (os.listdir(dir_emails) if os.path.isdir(dir_emails) else []):
        os.remove(os.path.join(dir_emails, antigo))

    emails, sem_email, sem_pdf = [], [], []
    for r in relatorios['relatorios']:
        if not (r.get('email') or '').strip():
            sem_email.append(r['nome'])
            continue
        if not r.get('pdf_gerado'):
            sem_pdf.append(r['nome'])  # a validação já bloqueia isso; defesa extra
            continue
        pdf_blob = f'gold/{ciclo}/pdf/{r["pdf"]}'
        assunto = f'{r["nome"]} — Relatório Mensal de Transparência — {mes_extenso}/{ano}'
        p1, p2, p3, p4 = sr.build_paragraphs(r, mes, ano, mes_extenso)
        verif = verificacoes.get(r['nome'], {})
        mailto = sr._build_mailto_report(r['nome'], mes_extenso, ano,
                                         hash_hex=verif.get('hash', ''),
                                         url_verificacao=verif.get('url_verificacao', ''))
        cta = sr.gerar_sas_url(conn, CONTAINER, pdf_blob, dias=VALIDADE_LINK_PDF_DIAS)
        html = sr.render_template(template, r['nome'], r.get('url', 'https://etransparente.org'),
                                  cta, assunto, p1, p2, p3, p4, mailto)
        destinatario = r['email'].strip()
        if modo_teste:
            html = html.replace('</head>', (
                '</head><p style="background:#fff3cd;padding:12px;font-size:12px;">'
                f'<strong>⚠️ ENSAIO</strong> — em produção este e-mail iria para: {destinatario}</p>'), 1)
            assunto, destinatario = f'[ENSAIO] {assunto}', args.destino_teste

        email = {
            'ciclo': ciclo, 'slug': r['slug'], 'nome': r['nome'],
            'destinatario': destinatario, 'destinatario_original': r['email'].strip(),
            'assunto': assunto, 'html': html,
            'pdf_blob': pdf_blob, 'pdf_nome': r['pdf'], 'pdf_sha256': r['pdf_sha256'],
        }
        email['email_sha256'] = sha256_json(email)
        gravar_json(os.path.join(dir_emails, f'{r["slug"]}.json'), email)
        emails.append(email)

    if sem_pdf:
        raise SystemExit(f'OSCs com e-mail mas sem PDF: {sem_pdf} — preparação recusada.')

    # 4. Amostra de conferência (IDC + 2 sorteadas, sem repetir o ciclo anterior)
    anterior = set()
    blob_amostra_ant = cont.get_blob_client(f'envios/{ciclo_anterior(ciclo)}/amostra.json')
    if blob_amostra_ant.exists():
        anterior = {a['slug'] for a in json.loads(blob_amostra_ant.download_blob().readall()).get('oscs', [])
                    if not a.get('fixa')}
    por_slug = {r['slug']: r for r in relatorios['relatorios']}
    escolha = escolher_amostra(relatorios['relatorios'], anterior, random.SystemRandom())
    amostra = []
    for a in escolha:
        r = por_slug[a['slug']]
        amostra.append({
            **a, 'nome': r['nome'],
            'views_total': r.get('views_total'), 'media_diaria': media_diaria(r.get('views_total'), n_dias),
            'nota_final': r.get('nota_final'), 'max_nota': r.get('max_nota'),
            # exatamente como o PDF imprime ({nota_final}/{max_nota} em dash.py), para a conferência
            'nota_exibida': f"{r.get('nota_final')}/{r.get('max_nota')}",
            'classificacao': r.get('classificacao'),
            'pdf_blob': f'gold/{ciclo}/pdf/{r["pdf"]}',
        })

    # 5. Manifesto + código de validação
    codigo = calcular_codigo(ciclo, sha_validacao, sha_rel, emails, amostra)
    preparado_em = datetime.now(timezone.utc).isoformat(timespec='seconds')
    manifesto = {
        'ciclo': ciclo, 'rotulo': rotulo_ciclo(ciclo), 'preparado_em': preparado_em,
        'modo_teste': modo_teste, 'destino_teste': args.destino_teste or None,
        'codigo_validacao': codigo, 'codigo_curto': codigo[:8].upper(),
        'sha256_validacao': sha_validacao, 'sha256_relatorios': sha_rel,
        'total_oscs': len(relatorios['relatorios']), 'total_emails': len(emails),
        'sem_email': sorted(sem_email),
        'emails': [{k: e[k] for k in ('slug', 'nome', 'destinatario', 'assunto', 'pdf_blob',
                                       'pdf_sha256', 'email_sha256')} for e in emails],
        'amostra': [a['slug'] for a in amostra],
    }
    gravar_json(os.path.join(dir_envio, 'amostra.json'),
                {'ciclo': ciclo, 'codigo_validacao': codigo, 'oscs': amostra})
    gravar_json(os.path.join(dir_envio, 'manifesto.json'), manifesto)

    # 6. Publicar. Uma nova preparação invalida aprovação/bloqueio anteriores:
    #    eles são arquivados em historico/ (nada é apagado sem registro).
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for b in status_antigos:
        conteudo = cont.get_blob_client(b.name).download_blob().readall()
        cont.get_blob_client(f'{prefixo}historico/{ts}_{b.name.rsplit("/", 1)[-1]}').upload_blob(conteudo)
        cont.delete_blob(b.name)
    for nome in ('aprovacao.json', 'bloqueio.json', 'resultado.json'):
        b = cont.get_blob_client(prefixo + nome)
        if b.exists():
            conteudo = b.download_blob().readall()
            cont.get_blob_client(f'{prefixo}historico/{ts}_{nome}').upload_blob(conteudo, overwrite=False)
            b.delete_blob()
            print(f'Arquivado: {nome} (preparação anterior invalidada)')
    for b in list(cont.list_blobs(name_starts_with=prefixo + 'emails/')):
        cont.delete_blob(b.name)
    for nome_arq in sorted(os.listdir(dir_emails)):
        with open(os.path.join(dir_emails, nome_arq), 'rb') as f:
            cont.get_blob_client(prefixo + 'emails/' + nome_arq).upload_blob(f, overwrite=True)
    for nome_arq in ('amostra.json', 'manifesto.json'):  # manifesto por último
        with open(os.path.join(dir_envio, nome_arq), 'rb') as f:
            cont.get_blob_client(prefixo + nome_arq).upload_blob(f, overwrite=True)

    # 7. Avisar a gestão que o ciclo está pronto para conferência
    avisar_ciclo_pronto(manifesto, amostra, validacao)

    print('=' * 70)
    print(f'ENVIO DO CICLO {ciclo} PREPARADO{" (ENSAIO → " + args.destino_teste + ")" if modo_teste else ""}')
    print(f'  E-mails prontos: {len(emails)} | Sem e-mail: {len(sem_email)}')
    print(f'  Amostra: {", ".join(a["nome"] for a in amostra)}')
    print(f'  Código de validação: {manifesto["codigo_curto"]} ({codigo})')
    print('  Nada foi enviado. O envio depende da conferência e confirmação em /envio.')


if __name__ == '__main__':
    main()
