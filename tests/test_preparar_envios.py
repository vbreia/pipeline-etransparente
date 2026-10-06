"""Preparação do envio: amostra, código de validação e trava de validação."""
import random

import pytest

from preparar_envios import (
    calcular_codigo, conferir_validacao, e_idc, elegivel, escolher_amostra, media_diaria,
)


def rel(slug, email='x@exemplo.org', pdf=True, nome=None):
    return {'slug': slug, 'nome': nome or slug.upper(), 'email': email, 'pdf_gerado': pdf}


IDC = rel('instituto-de-direito-coletivo-idc', nome='INSTITUTO DE DIREITO COLETIVO - IDC')
OUTRAS = [rel(f'osc-{i}') for i in range(10)]


def test_idc_sempre_primeira_e_fixa():
    for semente in range(50):
        amostra = escolher_amostra([*OUTRAS, IDC], set(), random.Random(semente))
        assert amostra[0] == {'slug': IDC['slug'], 'fixa': True}
        assert len(amostra) == 3
        assert all(not a['fixa'] for a in amostra[1:])
        assert len({a['slug'] for a in amostra}) == 3


def test_evita_repetir_sorteadas_do_ciclo_anterior():
    anterior = {f'osc-{i}' for i in range(8)}  # só osc-8 e osc-9 são "novas"
    for semente in range(50):
        sorteadas = {a['slug'] for a in escolher_amostra([IDC, *OUTRAS], anterior, random.Random(semente))[1:]}
        assert sorteadas == {'osc-8', 'osc-9'}


def test_completa_com_repetidas_quando_faltam_novas():
    anterior = {f'osc-{i}' for i in range(10)}
    amostra = escolher_amostra([IDC, *OUTRAS], anterior, random.Random(1))
    assert len(amostra) == 3


def test_so_sorteia_quem_pode_receber():
    lista = [IDC, rel('sem-email', email=''), rel('sem-pdf', pdf=False), rel('ok-1'), rel('ok-2')]
    for semente in range(30):
        slugs = {a['slug'] for a in escolher_amostra(lista, set(), random.Random(semente))}
        assert 'sem-email' not in slugs and 'sem-pdf' not in slugs


def test_sorteio_varia():
    vistos = {tuple(a['slug'] for a in escolher_amostra([IDC, *OUTRAS], set(), random.Random(s)))
              for s in range(30)}
    assert len(vistos) > 5


def test_idc_identificado_por_slug_ou_nome():
    assert e_idc(IDC)
    assert e_idc({'slug': '', 'nome': 'Instituto de Direito Coletivo'})
    assert not e_idc(rel('lar-de-daniel'))


def test_elegivel():
    assert elegivel(rel('a'))
    assert not elegivel(rel('a', email='  '))
    assert not elegivel(rel('a', pdf=False))


@pytest.mark.parametrize('total,dias,esperado', [(12, 30, '0,4'), (23, 30, '0,8'), (0, 31, '0,0'), (None, 30, '—')])
def test_media_diaria_igual_ao_pdf(total, dias, esperado):
    assert media_diaria(total, dias) == esperado


# ── código de validação ─────────────────────────────────────────────────────

def _emails():
    return [{'slug': s, 'destinatario': f'{s}@x.org', 'assunto': f'Assunto {s}',
             'pdf_blob': f'gold/2026-10/pdf/{s}.pdf', 'pdf_sha256': f'p-{s}', 'email_sha256': f'e-{s}'}
            for s in ('a', 'b', 'c')]


AMOSTRA = [{'slug': 'a', 'fixa': True}, {'slug': 'b', 'fixa': False}]


def test_codigo_estavel_independente_da_ordem():
    e = _emails()
    assert calcular_codigo('2026-10', 'v', 'r', e, AMOSTRA) == calcular_codigo('2026-10', 'v', 'r', e[::-1], AMOSTRA)


@pytest.mark.parametrize('campo', ['destinatario', 'assunto', 'pdf_sha256', 'email_sha256'])
def test_qualquer_mudanca_no_envio_muda_o_codigo(campo):
    base = calcular_codigo('2026-10', 'v', 'r', _emails(), AMOSTRA)
    e = _emails()
    e[1][campo] += '-alterado'
    assert calcular_codigo('2026-10', 'v', 'r', e, AMOSTRA) != base


def test_mudanca_na_validacao_ou_na_amostra_muda_o_codigo():
    base = calcular_codigo('2026-10', 'v', 'r', _emails(), AMOSTRA)
    assert calcular_codigo('2026-10', 'v2', 'r', _emails(), AMOSTRA) != base
    assert calcular_codigo('2026-10', 'v', 'r', _emails(), [{'slug': 'c', 'fixa': False}]) != base
    assert calcular_codigo('2026-10', 'v', 'r', _emails()[:2], AMOSTRA) != base  # OSC a menos


# ── só prepara o que foi validado ───────────────────────────────────────────

VALIDACAO_OK = {
    'ciclo': '2026-10', 'status': 'aprovado',
    'artefatos': {'sha256_relatorios': 'rel', 'sha256_views': 'views'},
    'resumo': {'bloqueantes_com_falha': []},
}


def test_validacao_aprovada_e_inalterada_libera():
    assert conferir_validacao(VALIDACAO_OK, '2026-10', 'rel', 'views') == []


def test_validacao_bloqueada_recusa():
    v = {**VALIDACAO_OK, 'status': 'bloqueado', 'resumo': {'bloqueantes_com_falha': ['cruzada_ga4']}}
    motivos = conferir_validacao(v, '2026-10', 'rel', 'views')
    assert motivos and 'cruzada_ga4' in motivos[0]


def test_arquivos_alterados_depois_da_validacao_recusa():
    assert conferir_validacao(VALIDACAO_OK, '2026-10', 'rel-novo', 'views')
    assert conferir_validacao(VALIDACAO_OK, '2026-10', 'rel', 'views-novo')


def test_validacao_de_outro_ciclo_recusa():
    assert conferir_validacao(VALIDACAO_OK, '2026-11', 'rel', 'views')
