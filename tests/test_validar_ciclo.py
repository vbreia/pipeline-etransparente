"""
Validação do ciclo: o caminho feliz aprova, e cada tipo de erro já visto em
produção BLOQUEIA. Dados falsos, sem rede.
"""
import copy
from datetime import datetime, timezone

import pytest

from ciclo import dias_do_ciclo
from validar_ciclo import ALERTA, BLOQUEANTE, Entradas, avaliar

CICLO = '2026-10'
DIAS = len(dias_do_ciclo(CICLO))  # 31


def _views(n):
    v = [0] * DIAS
    for i in range(n):
        v[i % DIAS] += 1
    return v


OSCS = [
    {'nome': 'INSTITUTO DE DIREITO COLETIVO - IDC', 'slug': 'instituto-de-direito-coletivo-idc',
     'email': 'idc@exemplo.org', 'views': 12},
    {'nome': 'LAR DE DANIEL CRISTOVÃO', 'slug': 'lar-de-daniel-cristovao', 'email': 'lar@exemplo.org', 'views': 29},
    {'nome': 'ASSOCIAÇÃO PESTALOZZI DE MAGÉ', 'slug': 'associacao-pestalozzi-de-mage',
     'email': 'pest@exemplo.org', 'views': 33},
]


def _url(slug):
    return f'https://etransparente.org/oscs/{slug}/'


@pytest.fixture
def entradas():
    views_oscs = [{'nome': o['nome'], 'url': _url(o['slug']), 'views': _views(o['views'])} for o in OSCS]
    relatorios = {
        'ciclo': CICLO, 'pasta': '20261103113500',
        'sha256_views': 'sha-views', 'sha256_extracao': 'sha-extracao',
        'relatorios': [{
            'nome': o['nome'], 'slug': o['slug'], 'url': _url(o['slug']), 'email': o['email'],
            'pdf': f'Relatório-{o["slug"]}.pdf', 'pdf_gerado': True, 'pdf_sha256': f'sha-{o["slug"]}',
            'views_disponiveis': True, 'views_total': o['views'],
            'nota_final': 30.0, 'max_nota': 30, 'classificacao': 'Ótimo',
        } for o in OSCS],
    }
    return Entradas(
        ciclo=CICLO,
        agora=datetime(2026, 11, 3, 11, 40, tzinfo=timezone.utc),
        extracao=[{'nome': o['nome'], 'url': _url(o['slug']), 'email': o['email']} for o in OSCS],
        scores=[{'nome': o['nome']} for o in OSCS],
        views_meta={
            'ciclo': CICLO, 'periodo_consultado': {'inicio': '2026-10-01', 'fim': '2026-10-31'},
            'gerado_em': '2026-11-03T11:35:00+00:00',
        },
        views_oscs=views_oscs,
        relatorios=relatorios,
        hashes_atuais={'views': 'sha-views', 'extracao': 'sha-extracao', 'relatorios': 'sha-rel'},
        pdfs_locais={f'Relatório-{o["slug"]}.pdf': f'sha-{o["slug"]}' for o in OSCS},
        pdfs_azure={f'Relatório-{o["slug"]}.pdf' for o in OSCS},
        historico_views=[
            {'mes': '2026-07', 'oscs': [{'url': _url('x'), 'views': [70]}]},
            {'mes': '2026-08', 'oscs': [{'url': _url('x'), 'views': [80]}]},
            {'mes': '2026-09', 'oscs': [{'url': _url('x'), 'views': [75]}]},
            {'mes': CICLO, 'oscs': copy.deepcopy(views_oscs)},
        ],
        historico_scores=[{'ciclo': '2026-09', 'nome': o['nome']} for o in OSCS],
        api_total=len(OSCS),
        ga4_cruzado={f'/oscs/{o["slug"]}/': o['views'] for o in OSCS},
    )


def _falhas(res):
    return {v['id'] for v in res['verificacoes'] if not v['ok']}


def test_caminho_feliz_aprova(entradas):
    res = avaliar(entradas)
    assert res['status'] == 'aprovado', [v for v in res['verificacoes'] if not v['ok']]
    assert _falhas(res) == set()
    assert res['resumo']['total_views'] == 74


# ── incidentes reais ────────────────────────────────────────────────────────

def test_incidente_out_2026_arquivo_gerado_antes_do_fim_do_ciclo(entradas):
    entradas.views_meta['gerado_em'] = '2026-10-01T11:35:00+00:00'
    res = avaliar(entradas)
    assert res['status'] == 'bloqueado' and 'views_formato' in _falhas(res)


def test_incidente_out_2026_arquivo_de_outro_ciclo(entradas):
    entradas.views_meta['ciclo'] = '2026-09'
    assert 'views_formato' in _falhas(avaliar(entradas))


def test_incidente_set_2026_mes_corrente(entradas):
    entradas.ciclo = '2026-11'
    assert 'data' in _falhas(avaliar(entradas))


def test_incidente_views_zeradas(entradas):
    for o in entradas.views_oscs:
        o['views'] = [0] * DIAS
    assert 'views_formato' in _falhas(avaliar(entradas))


def test_incidente_ago_2026_subcontagem_por_path(entradas):
    # GA4 registrou acessos em '/oscs/Lar-de-Daniel-Cristovao' que a consulta exata não pegou
    entradas.ga4_cruzado['/oscs/lar-de-daniel-cristovao/'] += 4
    res = avaliar(entradas)
    assert res['status'] == 'bloqueado' and 'cruzada_ga4' in _falhas(res)


def test_incidente_jul_2026_pdf_com_numero_diferente_do_dado(entradas):
    entradas.relatorios['relatorios'][1]['views_total'] = 517  # o antigo random.randint
    assert 'pdf_vs_views' in _falhas(avaliar(entradas))


def test_pdf_com_views_indisponiveis(entradas):
    entradas.relatorios['relatorios'][0]['views_disponiveis'] = False
    assert 'pdf_vs_views' in _falhas(avaliar(entradas))


def test_dashboard_diferente_do_pdf(entradas):
    entradas.historico_views[-1]['oscs'][0]['views'] = [0] * DIAS
    assert 'historico_dashboard' in _falhas(avaliar(entradas))


def test_ciclo_ausente_do_dashboard(entradas):
    entradas.historico_views = entradas.historico_views[:-1]
    assert 'historico_dashboard' in _falhas(avaliar(entradas))


def test_pdf_alterado_depois_de_gerado(entradas):
    entradas.pdfs_locais['Relatório-lar-de-daniel-cristovao.pdf'] = 'outro-hash'
    assert 'integridade' in _falhas(avaliar(entradas))


def test_views_alteradas_depois_dos_pdfs(entradas):
    entradas.hashes_atuais['views'] = 'mudou'
    assert 'integridade' in _falhas(avaliar(entradas))


def test_osc_perdida_entre_etapas(entradas):
    entradas.api_total = 4  # site tem uma OSC que a extração não pegou
    assert 'contagem' in _falhas(avaliar(entradas))


def test_email_sem_anexo(entradas):
    entradas.pdfs_azure.discard('Relatório-associacao-pestalozzi-de-mage.pdf')
    falhas = _falhas(avaliar(entradas))
    assert {'pdf_por_email', 'contagem'} <= falhas


def test_nomes_duplicados(entradas):
    entradas.extracao[2]['nome'] = entradas.extracao[1]['nome']
    assert 'nomes_unicos' in _falhas(avaliar(entradas))


def test_formato_antigo_sem_cabecalho(entradas):
    entradas.views_meta = None
    assert 'views_formato' in _falhas(avaliar(entradas))


# ── nunca aprovar o que não foi possível verificar ──────────────────────────

def test_ga4_indisponivel_bloqueia(entradas):
    entradas.ga4_cruzado = None
    entradas.erros_carga['ga4_cruzado'] = 'timeout'
    assert avaliar(entradas)['status'] == 'bloqueado'


def test_azure_indisponivel_bloqueia(entradas):
    entradas.pdfs_azure = None
    entradas.historico_views = None
    assert avaliar(entradas)['status'] == 'bloqueado'


def test_erro_inesperado_em_checagem_bloqueia(entradas):
    entradas.views_oscs.append({'nome': 'quebrada', 'url': None, 'views': None})
    assert avaliar(entradas)['status'] == 'bloqueado'


# ── alertas não bloqueiam, mas aparecem com nome ────────────────────────────

def test_osc_que_saiu_vira_alerta_com_nome(entradas):
    entradas.historico_scores.append({'ciclo': '2026-09', 'nome': 'APAE DE MIRACEMA'})
    res = avaliar(entradas)
    v = next(x for x in res['verificacoes'] if x['id'] == 'entradas_saidas')
    assert res['status'] == 'aprovado' and v['nivel'] == ALERTA and not v['ok']
    assert 'Saiu: APAE DE MIRACEMA' in v['itens']


def test_sem_email_vira_alerta(entradas):
    entradas.extracao[1]['email'] = ''
    entradas.relatorios['relatorios'][1]['email'] = ''
    res = avaliar(entradas)
    assert res['status'] == 'aprovado' and 'sem_email' in res['resumo']['alertas']


def test_tendencia_anormal_vira_alerta(entradas):
    for h in entradas.historico_views[:3]:
        h['oscs'][0]['views'] = [1000]
    res = avaliar(entradas)
    assert res['status'] == 'aprovado' and 'tendencia' in res['resumo']['alertas']


def test_niveis_declarados():
    from validar_ciclo import CHECAGENS
    assert len(CHECAGENS) == 12
    assert BLOQUEANTE != ALERTA
