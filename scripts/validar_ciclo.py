#!/usr/bin/env python3
"""
Validação do ciclo — a barreira entre "gerou" e "pode ser enviado".

Roda depois de PDFs, upload e silver, e responde com evidência: os relatórios
deste ciclo estão corretos e consistentes entre si? Grava
`output/validacao_{ciclo}.json` e `gold/validacao/{ciclo}.json` (lido pela página
de aprovação). Sai com código 1 se qualquer verificação BLOQUEANTE falhar — aí a
DAG para e `preparar_envios` não roda.

Cada verificação existe por causa de um problema real:

| id                   | protege contra                                                     |
|----------------------|--------------------------------------------------------------------|
| data                 | mês errado / ciclo incompleto (set e out/2026)                     |
| views_formato        | arquivo de views velho, parcial ou de outro ciclo (out/2026)       |
| integridade          | PDF gerado com arquivo diferente do validado                       |
| pdf_vs_views         | PDF mostrando número diferente do dado (bug do random, jul/2026)   |
| historico_dashboard  | dashboard e PDF mostrando números diferentes                       |
| cruzada_ga4          | consulta ao GA4 subcontando (bug de path, ago/2026)                |
| contagem             | OSC perdida entre etapas                                           |
| nomes_unicos         | nota/PDF trocados entre OSCs com o mesmo nome                      |
| pdf_por_email        | e-mail saindo sem anexo (comportamento antigo do send_reports)     |
| entradas_saidas      | OSC sumindo da plataforma sem ninguém notar (APAE Miracema)        |
| sem_email            | OSC que não vai receber nada                                       |
| tendencia            | variação anormal do total de visualizações                         |

Uso: python scripts/validar_ciclo.py --ciclo 2026-10 [--reprocessar]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ciclo import (  # noqa: E402
    LATENCIA_GA4_HORAS, CicloInvalido, adicionar_argumento_ciclo, ciclo_anterior,
    dias_do_ciclo, limites_ciclo, validar_data,
)
from artefatos import (  # noqa: E402
    carregar_views, gravar_json, ler_json, localizar_dashboards_do_ciclo, sha256_arquivo,
)

BLOQUEANTE = 'bloqueante'
ALERTA = 'alerta'
VERSAO_VALIDADOR = 1
CONTAINER = 'etransparente'
API_WP = 'https://etransparente.org/wp-json/wp/v2/job_listing'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/115.0 Safari/537.36')
# Diferença máxima aceita, por OSC, entre o arquivo e a consulta independente ao GA4.
TOLERANCIA_CRUZADA = int(os.environ.get('VALIDACAO_TOLERANCIA_GA4', '0'))
# Faixa aceitável do total do ciclo em relação à mediana dos 3 anteriores.
FAIXA_TENDENCIA = (0.30, 3.00)


# ─────────────────────────────────────────────────────────────────────────────
# Entradas — tudo que a validação precisa, já carregado. As funções de checagem
# são puras (sem rede, sem disco) para poderem ser testadas no GitHub Actions.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Entradas:
    ciclo: str
    agora: datetime
    reprocessar: bool = False
    modo_teste: bool = False
    extracao: list[dict] = field(default_factory=list)
    scores: list[dict] = field(default_factory=list)
    views_meta: dict | None = None
    views_oscs: list[dict] = field(default_factory=list)
    relatorios: dict = field(default_factory=dict)          # relatorios.json do dash.py
    hashes_atuais: dict = field(default_factory=dict)       # sha256 recalculados agora
    pdfs_locais: dict = field(default_factory=dict)         # nome do pdf -> sha256 ('' se ausente)
    pdfs_azure: set | None = None                           # nomes em gold/{ciclo}/pdf/
    historico_views: list[dict] | None = None               # gold/oscs_views_historico.json
    historico_scores: list[dict] | None = None              # gold/oscs_historico.json
    api_total: int | None = None                            # X-WP-Total
    ga4_cruzado: dict | None = None                         # path normalizado -> views do ciclo
    erros_carga: dict = field(default_factory=dict)         # fonte -> mensagem de erro


def _r(id_: str, titulo: str, nivel: str, ok: bool, detalhe: str, itens: list | None = None) -> dict:
    return {'id': id_, 'titulo': titulo, 'nivel': nivel, 'ok': bool(ok),
            'detalhe': detalhe, 'itens': itens or []}


def _norm_path(url_ou_path: str) -> str:
    from urllib.parse import unquote, urlparse
    p = urlparse(url_ou_path).path if '://' in (url_ou_path or '') else (url_ou_path or '')
    p = unquote(p).lower()
    if not p.startswith('/'):
        p = '/' + p
    if not p.endswith('/'):
        p += '/'
    return p


def _nome(o: dict) -> str:
    return (o.get('nome') or o.get('title') or '').strip()


# ─────────────────────────────────────────────────────────────────────────────
# Checagens
# ─────────────────────────────────────────────────────────────────────────────

def checar_data(e: Entradas) -> dict:
    try:
        info = validar_data(e.ciclo, e.agora, e.reprocessar)
        modo = 'reprocessamento autorizado' if info['reprocessamento'] else 'fluxo normal'
        return _r('data', 'Data do ciclo', BLOQUEANTE, True,
                  f'Ciclo {e.ciclo} fechado e com dados do GA4 consolidados ({modo}).')
    except CicloInvalido as ex:
        return _r('data', 'Data do ciclo', BLOQUEANTE, False, str(ex))


def checar_views_formato(e: Entradas) -> dict:
    t = 'Arquivo de visualizações do ciclo'
    m = e.views_meta
    if not m:
        return _r('views_formato', t, BLOQUEANTE, False,
                  'Arquivo sem cabeçalho (formato antigo) — não há como provar ciclo e data de geração. '
                  'Regere com oscs_monthly_views.py --ciclo.')
    problemas = []
    inicio, fim = limites_ciclo(e.ciclo)
    if m.get('ciclo') != e.ciclo:
        problemas.append(f'cabeçalho declara ciclo {m.get("ciclo")}, esperado {e.ciclo}')
    periodo = m.get('periodo_consultado') or {}
    esperado_ini = inicio.strftime('%Y-%m-%d')
    esperado_fim = (fim - timedelta(days=1)).strftime('%Y-%m-%d')
    if periodo.get('inicio') != esperado_ini or periodo.get('fim') != esperado_fim:
        problemas.append(f'período consultado {periodo} difere de {esperado_ini}..{esperado_fim}')
    try:
        gerado = datetime.fromisoformat(m.get('gerado_em', ''))
        if gerado < fim + timedelta(hours=LATENCIA_GA4_HORAS):
            problemas.append(f'consulta feita em {gerado:%d/%m %H:%M}, antes de o GA4 consolidar o ciclo '
                             f'({LATENCIA_GA4_HORAS}h após {fim:%d/%m})')
    except ValueError:
        problemas.append('data de geração ausente ou inválida')
    n_dias = len(dias_do_ciclo(e.ciclo))
    errados = [_nome(o) for o in e.views_oscs if len(o.get('views') or []) != n_dias]
    if errados:
        problemas.append(f'{len(errados)} OSC(s) sem os {n_dias} dias do mês')
    total = sum(sum(o.get('views') or []) for o in e.views_oscs)
    if total <= 0:
        problemas.append('total de visualizações do ciclo é 0')
    if problemas:
        return _r('views_formato', t, BLOQUEANTE, False, '; '.join(problemas), errados)
    return _r('views_formato', t, BLOQUEANTE, True,
              f'{len(e.views_oscs)} OSCs × {n_dias} dias, {total} visualizações, '
              f'consultado em {m.get("gerado_em")}.')


def checar_integridade(e: Entradas) -> dict:
    t = 'Integridade dos arquivos (PDFs gerados a partir dos dados validados)'
    rel = e.relatorios
    problemas, itens = [], []
    if rel.get('sha256_views') != e.hashes_atuais.get('views'):
        problemas.append('o arquivo de views mudou depois que os PDFs foram gerados')
    if rel.get('sha256_extracao') != e.hashes_atuais.get('extracao'):
        problemas.append('o arquivo de extração mudou depois que os PDFs foram gerados')
    for r in rel.get('relatorios', []):
        atual = e.pdfs_locais.get(r['pdf'], '')
        if not r.get('pdf_gerado') or not atual:
            itens.append(f'{r["nome"]}: PDF não gerado')
        elif atual != r.get('pdf_sha256'):
            itens.append(f'{r["nome"]}: PDF alterado depois da geração')
    if itens:
        problemas.append(f'{len(itens)} PDF(s) ausentes ou alterados')
    if problemas:
        return _r('integridade', t, BLOQUEANTE, False, '; '.join(problemas), itens)
    return _r('integridade', t, BLOQUEANTE, True,
              f'{len(rel.get("relatorios", []))} PDFs conferidos por hash; views e extração inalteradas.')


def checar_pdf_vs_views(e: Entradas) -> dict:
    t = 'Número impresso em cada PDF = dado de visualizações'
    por_url = {_norm_path(o.get('url', '')): sum(o.get('views') or []) for o in e.views_oscs}
    itens = []
    for r in e.relatorios.get('relatorios', []):
        esperado = por_url.get(_norm_path(r.get('url', '')))
        if not r.get('views_disponiveis'):
            itens.append(f'{r["nome"]}: PDF sem visualizações ("indisponível")')
        elif esperado is None:
            itens.append(f'{r["nome"]}: OSC sem entrada no arquivo de views')
        elif r.get('views_total') != esperado:
            itens.append(f'{r["nome"]}: PDF mostra {r.get("views_total")}, dado = {esperado}')
    if itens:
        return _r('pdf_vs_views', t, BLOQUEANTE, False, f'{len(itens)} divergência(s)', itens)
    return _r('pdf_vs_views', t, BLOQUEANTE, True,
              f'Total por OSC idêntico em {len(e.relatorios.get("relatorios", []))} relatórios.')


def checar_historico_dashboard(e: Entradas) -> dict:
    t = 'Dashboard = PDF (histórico de visualizações do ciclo)'
    if e.historico_views is None:
        return _r('historico_dashboard', t, BLOQUEANTE, False,
                  f'Não foi possível ler gold/oscs_views_historico.json: {e.erros_carga.get("historico_views")}')
    entrada = next((h for h in e.historico_views if h.get('mes') == e.ciclo), None)
    if not entrada:
        return _r('historico_dashboard', t, BLOQUEANTE, False,
                  f'Ciclo {e.ciclo} ausente do histórico usado pelo dashboard.')
    dash = {_norm_path(o.get('url', '')): list(o.get('views') or []) for o in entrada.get('oscs', [])}
    itens = []
    for o in e.views_oscs:
        k = _norm_path(o.get('url', ''))
        if dash.get(k) != list(o.get('views') or []):
            itens.append(f'{_nome(o)}: dashboard {sum(dash.get(k) or [])} × arquivo {sum(o.get("views") or [])}')
    if itens:
        return _r('historico_dashboard', t, BLOQUEANTE, False, f'{len(itens)} OSC(s) divergentes', itens)
    return _r('historico_dashboard', t, BLOQUEANTE, True,
              f'Histórico do dashboard idêntico ao arquivo do ciclo ({len(e.views_oscs)} OSCs, dia a dia).')


def checar_cruzada_ga4(e: Entradas) -> dict:
    t = 'Conferência cruzada com o GA4 (consulta independente)'
    if e.ga4_cruzado is None:
        return _r('cruzada_ga4', t, BLOQUEANTE, False,
                  f'Consulta independente ao GA4 falhou: {e.erros_carga.get("ga4_cruzado")}')
    itens = []
    for o in e.views_oscs:
        k = _norm_path(o.get('url', ''))
        arquivo = sum(o.get('views') or [])
        independente = e.ga4_cruzado.get(k, 0)
        if abs(arquivo - independente) > TOLERANCIA_CRUZADA:
            itens.append(f'{_nome(o)} ({k}): pipeline {arquivo} × GA4 {independente}')
    if itens:
        return _r('cruzada_ga4', t, BLOQUEANTE, False,
                  f'{len(itens)} OSC(s) com número diferente do GA4 (tolerância {TOLERANCIA_CRUZADA})', itens)
    return _r('cruzada_ga4', t, BLOQUEANTE, True,
              f'{len(e.views_oscs)} OSCs batem com a consulta independente ao GA4.')


def checar_contagem(e: Entradas) -> dict:
    t = 'Mesma quantidade de OSCs em todas as etapas'
    rel = e.relatorios.get('relatorios', [])
    nomes_pdf = {r['pdf'] for r in rel}
    contagens = {
        'site (API)': e.api_total,
        'extração': len(e.extracao),
        'notas': len(e.scores),
        'visualizações': len(e.views_oscs),
        'relatórios': len(rel),
        'PDFs gerados': sum(1 for r in rel if r.get('pdf_gerado')),
        'PDFs no Azure': None if e.pdfs_azure is None else len(nomes_pdf & e.pdfs_azure),
    }
    resumo = ', '.join(f'{k}: {"?" if v is None else v}' for k, v in contagens.items())
    valores = [v for v in contagens.values() if v is not None]
    faltando = [k for k, v in contagens.items() if v is None]
    ok = not faltando and len(set(valores)) == 1
    nivel = ALERTA if e.modo_teste else BLOQUEANTE
    if faltando:
        return _r('contagem', t, nivel, False, f'Não foi possível contar em: {", ".join(faltando)}. {resumo}')
    return _r('contagem', t, nivel, ok, resumo if ok else f'Contagens diferentes — {resumo}')


def checar_nomes_unicos(e: Entradas) -> dict:
    t = 'Nomes de OSC únicos'
    vistos, dup = set(), set()
    for o in e.extracao:
        n = _nome(o).lower()
        (dup if n in vistos else vistos).add(n)
    if dup:
        return _r('nomes_unicos', t, BLOQUEANTE, False,
                  'Notas e PDFs são associados pelo nome — nomes repetidos podem trocar dados entre OSCs.',
                  sorted(dup))
    return _r('nomes_unicos', t, BLOQUEANTE, True, f'{len(vistos)} nomes distintos.')


def checar_pdf_por_email(e: Entradas) -> dict:
    t = 'Toda OSC com e-mail tem PDF do ciclo publicado'
    if e.pdfs_azure is None:
        return _r('pdf_por_email', t, BLOQUEANTE, False,
                  f'Não foi possível listar gold/{e.ciclo}/pdf/: {e.erros_carga.get("pdfs_azure")}')
    itens = [r['nome'] for r in e.relatorios.get('relatorios', [])
             if r.get('email') and (not r.get('pdf_gerado') or r['pdf'] not in e.pdfs_azure)]
    if itens:
        return _r('pdf_por_email', t, BLOQUEANTE, False, f'{len(itens)} OSC(s) receberiam e-mail sem anexo', itens)
    return _r('pdf_por_email', t, BLOQUEANTE, True, 'Todos os destinatários têm PDF publicado.')


def checar_entradas_saidas(e: Entradas) -> dict:
    t = 'OSCs que entraram ou saíram desde o ciclo anterior'
    anterior = ciclo_anterior(e.ciclo)
    if e.historico_scores is None:
        return _r('entradas_saidas', t, ALERTA, False,
                  f'Não foi possível ler gold/oscs_historico.json: {e.erros_carga.get("historico_scores")}')
    antes = {(h.get('nome') or '').strip() for h in e.historico_scores if h.get('ciclo') == anterior}
    agora = {_nome(o) for o in e.extracao}
    if not antes:
        return _r('entradas_saidas', t, ALERTA, True, f'Sem dados do ciclo {anterior} para comparar.')
    entraram, sairam = sorted(agora - antes), sorted(antes - agora)
    itens = [f'Entrou: {n}' for n in entraram] + [f'Saiu: {n}' for n in sairam]
    if itens:
        return _r('entradas_saidas', t, ALERTA, False,
                  f'{len(entraram)} entrada(s), {len(sairam)} saída(s) em relação a {anterior}', itens)
    return _r('entradas_saidas', t, ALERTA, True, f'Mesmas {len(agora)} OSCs de {anterior}.')


def checar_sem_email(e: Entradas) -> dict:
    t = 'OSCs sem e-mail cadastrado (não receberão o relatório)'
    itens = sorted(_nome(o) for o in e.extracao if not (o.get('email') or '').strip())
    if itens:
        return _r('sem_email', t, ALERTA, False, f'{len(itens)} OSC(s) sem e-mail', itens)
    return _r('sem_email', t, ALERTA, True, 'Todas as OSCs têm e-mail.')


def checar_tendencia(e: Entradas) -> dict:
    t = 'Total de visualizações dentro do padrão dos últimos meses'
    total = sum(sum(o.get('views') or []) for o in e.views_oscs)
    if not e.historico_views:
        return _r('tendencia', t, ALERTA, True, 'Sem histórico para comparar.')
    anteriores, c = [], e.ciclo
    for _ in range(3):
        c = ciclo_anterior(c)
        h = next((x for x in e.historico_views if x.get('mes') == c), None)
        if h:
            anteriores.append(sum(sum(o.get('views') or []) for o in h.get('oscs', [])))
    anteriores = [a for a in anteriores if a > 0]
    if len(anteriores) < 2:
        return _r('tendencia', t, ALERTA, True, 'Histórico insuficiente (menos de 2 meses).')
    mediana = statistics.median(anteriores)
    razao = total / mediana if mediana else 0
    ok = FAIXA_TENDENCIA[0] <= razao <= FAIXA_TENDENCIA[1]
    return _r('tendencia', t, ALERTA, ok,
              f'Ciclo: {total}; mediana dos meses anteriores: {mediana:.0f} ({razao:.0%}).')


CHECAGENS: list[Callable[[Entradas], dict]] = [
    checar_data, checar_views_formato, checar_integridade, checar_pdf_vs_views,
    checar_historico_dashboard, checar_cruzada_ga4, checar_contagem, checar_nomes_unicos,
    checar_pdf_por_email, checar_entradas_saidas, checar_sem_email, checar_tendencia,
]


def avaliar(e: Entradas) -> dict:
    """Roda todas as checagens. Uma checagem que quebra conta como falha (nunca como aprovação)."""
    resultados = []
    for f in CHECAGENS:
        try:
            resultados.append(f(e))
        except Exception as ex:  # defensivo: erro inesperado bloqueia
            resultados.append(_r(f.__name__.replace('checar_', ''), f.__name__, BLOQUEANTE, False,
                                 f'Erro inesperado na verificação: {ex!r}'))
    bloqueado = any(r['nivel'] == BLOQUEANTE and not r['ok'] for r in resultados)
    rel = e.relatorios.get('relatorios', [])
    return {
        'ciclo': e.ciclo,
        'versao_validador': VERSAO_VALIDADOR,
        'validado_em': e.agora.astimezone(timezone.utc).isoformat(timespec='seconds'),
        'status': 'bloqueado' if bloqueado else 'aprovado',
        'reprocessamento': e.reprocessar,
        'modo_teste': e.modo_teste,
        'resumo': {
            'oscs': len(e.extracao),
            'com_email': sum(1 for r in rel if r.get('email')),
            'sem_email': sum(1 for o in e.extracao if not (o.get('email') or '').strip()),
            'total_views': sum(sum(o.get('views') or []) for o in e.views_oscs),
            'bloqueantes_com_falha': [r['id'] for r in resultados if r['nivel'] == BLOQUEANTE and not r['ok']],
            'alertas': [r['id'] for r in resultados if r['nivel'] == ALERTA and not r['ok']],
        },
        'artefatos': {
            'pasta_relatorios': e.relatorios.get('pasta'),
            'sha256_relatorios': e.hashes_atuais.get('relatorios'),
            'sha256_views': e.hashes_atuais.get('views'),
            'sha256_extracao': e.hashes_atuais.get('extracao'),
        },
        'verificacoes': resultados,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Carga (rede + disco) — só roda na VM
# ─────────────────────────────────────────────────────────────────────────────

def _tentar(e: Entradas, chave: str, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except Exception as ex:
        e.erros_carga[chave] = repr(ex)
        return None


def consulta_cruzada_ga4(property_id: str, ciclo: str) -> dict:
    """Consulta INDEPENDENTE da usada no pipeline: um único total mensal por
    página que começa com /oscs/ (sem filtro por OSC, sem quebra por dia),
    normalizado do mesmo jeito. Se o pipeline subcontar por causa de variação
    de path (bug de ago/2026), os números divergem e o ciclo é bloqueado."""
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Filter, FilterExpression, Metric, RunReportRequest,
    )
    inicio, fim = limites_ciclo(ciclo)
    client = BetaAnalyticsDataClient()
    totais: dict[str, int] = {}
    offset = 0
    while True:
        resp = client.run_report(RunReportRequest(
            property=f'properties/{property_id}',
            dimensions=[Dimension(name='pagePath')],
            metrics=[Metric(name='screenPageViews')],
            date_ranges=[DateRange(start_date=inicio.strftime('%Y-%m-%d'),
                                   end_date=(fim - timedelta(days=1)).strftime('%Y-%m-%d'))],
            dimension_filter=FilterExpression(filter=Filter(
                field_name='pagePath',
                string_filter=Filter.StringFilter(
                    value='/oscs/', match_type=Filter.StringFilter.MatchType.BEGINS_WITH,
                    case_sensitive=False),
            )),
            limit=10000, offset=offset,
        ))
        for row in resp.rows:
            k = _norm_path(row.dimension_values[0].value)
            totais[k] = totais.get(k, 0) + int(row.metric_values[0].value or 0)
        offset += len(resp.rows)
        if not resp.rows or offset >= resp.row_count:
            break
    return totais


def carregar_entradas(ciclo: str, reprocessar: bool) -> Entradas:
    base = '/home/airflow' if os.path.exists('/home/airflow/output') else os.getcwd()
    out = os.path.join(base, 'output')
    e = Entradas(ciclo=ciclo, agora=datetime.now(timezone.utc), reprocessar=reprocessar,
                 modo_teste=os.environ.get('PIPELINE_TEST_MODE', '').lower() == 'true')

    pasta, manifesto = localizar_dashboards_do_ciclo(out, ciclo)
    if not pasta:
        raise SystemExit(f'Nenhum relatorios.json do ciclo {ciclo} em output/dashboards/ — rode dash.py antes.')
    e.relatorios = ler_json(manifesto)
    e.hashes_atuais['relatorios'] = sha256_arquivo(manifesto)

    extracao_path = os.path.join(out, e.relatorios.get('arquivo_extracao', ''))
    e.extracao = ler_json(extracao_path)
    e.hashes_atuais['extracao'] = sha256_arquivo(extracao_path)
    if e.modo_teste:
        e.extracao = [o for o in e.extracao if 'direito coletivo' in _nome(o).lower()]

    scores_path = os.path.join(out, 'scores', e.relatorios.get('arquivo_scores', ''))
    if os.path.isfile(scores_path):
        e.scores = ler_json(scores_path).get('resultados', [])

    views_path = os.path.join(out, f'oscs_views_{ciclo}.json')
    if os.path.isfile(views_path):
        e.views_meta, e.views_oscs = carregar_views(views_path)
        e.hashes_atuais['views'] = sha256_arquivo(views_path)

    for r in e.relatorios.get('relatorios', []):
        p = os.path.join(pasta, 'pdf', r['pdf'])
        e.pdfs_locais[r['pdf']] = sha256_arquivo(p) if os.path.isfile(p) and os.path.getsize(p) > 0 else ''

    def _azure():
        from azure.storage.blob import BlobServiceClient
        return BlobServiceClient.from_connection_string(os.environ['AZURE_STORAGE_CONNECTION_STRING'])

    cliente = _tentar(e, 'azure', _azure)
    if cliente:
        cont = cliente.get_container_client(CONTAINER)
        e.pdfs_azure = _tentar(e, 'pdfs_azure', lambda: {
            b.name.rsplit('/', 1)[-1] for b in cont.list_blobs(name_starts_with=f'gold/{ciclo}/pdf/')})
        e.historico_views = _tentar(e, 'historico_views', lambda: json.loads(
            cont.get_blob_client('gold/oscs_views_historico.json').download_blob().readall()))
        e.historico_scores = _tentar(e, 'historico_scores', lambda: json.loads(
            cont.get_blob_client('gold/oscs_historico.json').download_blob().readall()))
    else:
        for k in ('pdfs_azure', 'historico_views', 'historico_scores'):
            e.erros_carga[k] = e.erros_carga.get('azure')

    def _api_total():
        import requests
        r = requests.get(API_WP, params={'per_page': 1}, headers={'User-Agent': UA}, timeout=30)
        r.raise_for_status()
        return int(r.headers['X-WP-Total'])
    e.api_total = None if e.modo_teste else _tentar(e, 'api_total', _api_total)
    if e.modo_teste:
        e.api_total = len(e.extracao)

    prop = os.environ.get('GA4_PROPERTY_ID')
    e.ga4_cruzado = _tentar(e, 'ga4_cruzado', lambda: consulta_cruzada_ga4(prop, ciclo)) if prop else None
    if not prop:
        e.erros_carga['ga4_cruzado'] = 'GA4_PROPERTY_ID não definida'
    return e


def publicar(resultado: dict, ciclo: str) -> str:
    base = '/home/airflow' if os.path.exists('/home/airflow/output') else os.getcwd()
    local = os.path.join(base, 'output', f'validacao_{ciclo}.json')
    gravar_json(local, resultado)
    try:
        from azure.storage.blob import BlobServiceClient
        c = BlobServiceClient.from_connection_string(os.environ['AZURE_STORAGE_CONNECTION_STRING'])
        with open(local, 'rb') as f:
            c.get_blob_client(CONTAINER, f'gold/validacao/{ciclo}.json').upload_blob(f, overwrite=True)
        print(f'Publicado: gold/validacao/{ciclo}.json')
    except Exception as ex:
        print(f'AVISO: não foi possível publicar a validação no Azure: {ex!r}')
    return local


def imprimir(resultado: dict) -> None:
    print('=' * 70)
    print(f'VALIDAÇÃO DO CICLO {resultado["ciclo"]}: {resultado["status"].upper()}')
    print('=' * 70)
    for v in resultado['verificacoes']:
        marca = '✅' if v['ok'] else ('❌' if v['nivel'] == BLOQUEANTE else '⚠️ ')
        print(f'{marca} {v["titulo"]}\n   {v["detalhe"]}')
        for item in v['itens'][:20]:
            print(f'     - {item}')
        if len(v['itens']) > 20:
            print(f'     ... e mais {len(v["itens"]) - 20}')


def main():
    parser = argparse.ArgumentParser(description='Valida o ciclo antes de preparar o envio')
    adicionar_argumento_ciclo(parser)
    parser.add_argument('--reprocessar', action='store_true',
                        help='Ciclo antigo reprocessado de propósito (passado pela DAG via conf)')
    args = parser.parse_args()

    entradas = carregar_entradas(args.ciclo, args.reprocessar)
    resultado = avaliar(entradas)
    imprimir(resultado)
    publicar(resultado, args.ciclo)
    if resultado['status'] != 'aprovado':
        print('\nCiclo BLOQUEADO — preparar_envios não vai rodar. Corrija e rode a DAG de novo.')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
