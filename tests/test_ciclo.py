"""Regras de data do ciclo (scripts/ciclo.py)."""
from datetime import datetime, timezone

import pytest

from ciclo import (
    CicloInvalido, ciclo_anterior, ciclo_do_intervalo, ciclo_esperado, ciclo_seguinte,
    dias_do_ciclo, limites_ciclo, parse_ciclo, rotulo_ciclo, validar_data,
)


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


# ── formato ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('valor', ['2026-13', '2026-00', '26-10', '2026/10', '2026-1', '', 'outubro'])
def test_formato_invalido(valor):
    with pytest.raises(CicloInvalido):
        parse_ciclo(valor)


def test_vizinhos_e_virada_de_ano():
    assert ciclo_anterior('2026-10') == '2026-09'
    assert ciclo_anterior('2027-01') == '2026-12'
    assert ciclo_seguinte('2026-12') == '2027-01'


def test_dias_do_ciclo():
    assert len(dias_do_ciclo('2026-09')) == 30
    assert len(dias_do_ciclo('2026-10')) == 31
    assert len(dias_do_ciclo('2028-02')) == 29   # bissexto
    assert len(dias_do_ciclo('2027-02')) == 28
    assert dias_do_ciclo('2026-09')[0] == '20260901'
    assert dias_do_ciclo('2026-09')[-1] == '20260930'


def test_limites_no_fuso_de_brasilia():
    inicio, fim = limites_ciclo('2026-09')
    assert inicio.isoformat().startswith('2026-09-01T00:00:00')
    assert fim.isoformat().startswith('2026-10-01T00:00:00')
    assert fim.utcoffset().total_seconds() == -3 * 3600


def test_rotulo():
    assert rotulo_ciclo('2026-10') == 'outubro/2026'


# ── ciclo vindo do Airflow ──────────────────────────────────────────────────

def test_ciclo_do_intervalo_execucao_agendada():
    # Execução de 03/11 às 11:30 UTC → intervalo começa em 03/10 → ciclo de outubro
    assert ciclo_do_intervalo(utc(2026, 10, 3, 11, 30)) == '2026-10'


def test_ciclo_do_intervalo_janeiro():
    assert ciclo_do_intervalo(utc(2026, 12, 3, 11, 30)) == '2026-12'


# ── validar_data: os incidentes reais ───────────────────────────────────────

def test_incidente_01_10_2026_mes_corrente_bloqueado():
    """Em 01/10 o pipeline processou OUTUBRO (mês que mal começou)."""
    with pytest.raises(CicloInvalido, match='ainda não terminou'):
        validar_data('2026-10', utc(2026, 10, 1, 11, 30))


def test_dia_1_mes_anterior_bloqueado_por_latencia_do_ga4():
    """Mesmo com o mês certo, no dia 1 o GA4 ainda não consolidou o dia 30."""
    with pytest.raises(CicloInvalido, match='48h'):
        validar_data('2026-09', utc(2026, 10, 1, 11, 30))


def test_dia_3_fluxo_normal_liberado():
    info = validar_data('2026-10', utc(2026, 11, 3, 11, 30))
    assert info['ciclo'] == '2026-10' and not info['reprocessamento']


def test_virada_de_ano_dezembro_processado_em_janeiro():
    info = validar_data('2026-12', utc(2027, 1, 3, 11, 30))
    assert info['ciclo_esperado'] == '2026-12'


def test_ciclo_antigo_exige_reprocessamento_explicito():
    with pytest.raises(CicloInvalido, match='não é o ciclo esperado'):
        validar_data('2026-09', utc(2026, 11, 3, 11, 30))
    info = validar_data('2026-09', utc(2026, 11, 3, 11, 30), permitir_reprocessamento=True)
    assert info['reprocessamento']


def test_futuro_bloqueado_mesmo_com_reprocessamento():
    with pytest.raises(CicloInvalido):
        validar_data('2026-12', utc(2026, 11, 3, 11, 30), permitir_reprocessamento=True)


def test_limite_exato_das_48h():
    # Setembro fecha em 01/10 00:00 BRT = 03:00 UTC; +48h = 03/10 03:00 UTC
    with pytest.raises(CicloInvalido):
        validar_data('2026-09', utc(2026, 10, 3, 2, 59))
    validar_data('2026-09', utc(2026, 10, 3, 3, 0))


def test_meia_noite_utc_ainda_e_dia_anterior_em_brasilia():
    # 01/11 01:00 UTC = 31/10 22:00 BRT → outubro ainda não terminou
    with pytest.raises(CicloInvalido, match='ainda não terminou'):
        validar_data('2026-10', utc(2026, 11, 1, 1, 0))
    assert ciclo_esperado(utc(2026, 11, 1, 1, 0)) == '2026-09'


def test_exige_datetime_com_fuso():
    with pytest.raises(ValueError):
        validar_data('2026-10', datetime(2026, 11, 3, 11, 30))
