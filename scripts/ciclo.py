#!/usr/bin/env python3
"""
Fonte ÚNICA de verdade sobre "qual ciclo é este" no pipeline.

Por que existe
--------------
Entre ago e out/2026 o pipeline enviou três meses seguidos relatórios com
visualizações erradas. A causa raiz comum: cada script calculava a data por
conta própria (date.today(), datetime.now(), "mês anterior ao atual"...). Uma
correção feita em 4 scripts e esquecida no 5º bastou para quebrar o envio de
01/10/2026.

Regra a partir daqui
--------------------
- Quem decide o ciclo é a DAG (a partir de data_interval_start) e passa
  `--ciclo YYYY-MM` para TODOS os scripts.
- Nenhum script calcula ciclo a partir da data do sistema. Use
  `adicionar_argumento_ciclo(parser)` para exigir `--ciclo`.
- Antes de qualquer processamento, `validar_data()` confirma que faz sentido
  processar aquele ciclo AGORA (ciclo já fechado e com dados do GA4 consolidados).

Os testes em tests/test_ciclo.py e tests/test_contrato_ciclo.py garantem estas
regras a cada push (GitHub Actions).
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    FUSO = ZoneInfo('America/Sao_Paulo')
except Exception:  # pragma: no cover — ambiente sem tzdata
    FUSO = timezone(timedelta(hours=-3))

# GA4 leva de 24 a 48h para consolidar os dados de um dia. O ciclo só é
# processado depois de fechado há pelo menos este intervalo.
LATENCIA_GA4_HORAS = 48

_RE_CICLO = re.compile(r'^(\d{4})-(0[1-9]|1[0-2])$')

MESES_PT = [
    '', 'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
]


class CicloInvalido(ValueError):
    """O ciclo informado não pode ser processado neste momento."""


def parse_ciclo(ciclo: str) -> tuple[int, int]:
    """'2026-10' -> (2026, 10). Levanta CicloInvalido se o formato for inválido."""
    m = _RE_CICLO.match(ciclo or '')
    if not m:
        raise CicloInvalido(f'Ciclo "{ciclo}" inválido — use o formato YYYY-MM (ex.: 2026-10)')
    return int(m.group(1)), int(m.group(2))


def ciclo_anterior(ciclo: str) -> str:
    ano, mes = parse_ciclo(ciclo)
    return f'{ano - 1}-12' if mes == 1 else f'{ano}-{mes - 1:02d}'


def ciclo_seguinte(ciclo: str) -> str:
    ano, mes = parse_ciclo(ciclo)
    return f'{ano + 1}-01' if mes == 12 else f'{ano}-{mes + 1:02d}'


def limites_ciclo(ciclo: str) -> tuple[datetime, datetime]:
    """Início (inclusivo) e fim (exclusivo) do ciclo, no fuso de Brasília.

    Ex.: '2026-09' -> (2026-09-01 00:00 BRT, 2026-10-01 00:00 BRT)
    """
    ano, mes = parse_ciclo(ciclo)
    ano_s, mes_s = parse_ciclo(ciclo_seguinte(ciclo))
    return (
        datetime(ano, mes, 1, tzinfo=FUSO),
        datetime(ano_s, mes_s, 1, tzinfo=FUSO),
    )


def dias_do_ciclo(ciclo: str) -> list[str]:
    """Lista de dias do ciclo em YYYYMMDD (mesmo formato da dimensão `date` do GA4)."""
    inicio, fim = limites_ciclo(ciclo)
    dias, cur = [], inicio
    while cur < fim:
        dias.append(cur.strftime('%Y%m%d'))
        cur += timedelta(days=1)
    return dias


def rotulo_ciclo(ciclo: str) -> str:
    """'2026-10' -> 'outubro/2026'."""
    ano, mes = parse_ciclo(ciclo)
    return f'{MESES_PT[mes]}/{ano}'


def ciclo_do_intervalo(data_interval_start: datetime) -> str:
    """Ciclo a partir do data_interval_start do Airflow.

    Com schedule mensal no dia 3 (`30 11 3 * *`), a execução de 03/11 tem
    data_interval_start = 03/10 -> ciclo '2026-10'. Disparos manuais recebem o
    último intervalo completo antes do disparo, com o mesmo significado.
    """
    if data_interval_start.tzinfo is not None:
        data_interval_start = data_interval_start.astimezone(FUSO)
    return data_interval_start.strftime('%Y-%m')


def ciclo_esperado(agora: datetime) -> str:
    """O único ciclo que faz sentido processar no fluxo normal: o mês anterior ao atual."""
    agora_local = _como_local(agora)
    return ciclo_anterior(agora_local.strftime('%Y-%m'))


def validar_data(ciclo: str, agora: datetime, permitir_reprocessamento: bool = False) -> dict:
    """Confirma que faz sentido processar `ciclo` no instante `agora`.

    Bloqueia (CicloInvalido) quando:
      1. o formato é inválido;
      2. o ciclo ainda não terminou (mês corrente ou futuro);
      3. o ciclo terminou há menos de LATENCIA_GA4_HORAS (dados do GA4 incompletos);
      4. o ciclo não é o mês anterior ao atual — salvo reprocessamento explícito
         (ex.: regerar setembro em novembro), que precisa ser pedido de propósito.

    Retorna um dict descrevendo a decisão (gravado no log e na validação).
    """
    parse_ciclo(ciclo)
    agora_local = _como_local(agora)
    _, fim = limites_ciclo(ciclo)
    liberado_em = fim + timedelta(hours=LATENCIA_GA4_HORAS)
    esperado = ciclo_esperado(agora)

    if agora_local < fim:
        raise CicloInvalido(
            f'Ciclo {ciclo} ainda não terminou (termina em {fim:%d/%m/%Y %H:%M} BRT; '
            f'agora: {agora_local:%d/%m/%Y %H:%M} BRT). Um relatório mensal só '
            f'pode ser gerado depois que o mês fecha.'
        )
    if agora_local < liberado_em:
        raise CicloInvalido(
            f'Ciclo {ciclo} fechou há menos de {LATENCIA_GA4_HORAS}h — o GA4 ainda pode '
            f'estar consolidando os últimos dias. Liberado a partir de '
            f'{liberado_em:%d/%m/%Y %H:%M} BRT.'
        )
    if ciclo != esperado and not permitir_reprocessamento:
        raise CicloInvalido(
            f'Ciclo {ciclo} não é o ciclo esperado para hoje ({esperado}). Para '
            f'reprocessar um ciclo antigo de propósito, dispare a DAG com '
            f'--conf \'{{"ciclo": "{ciclo}", "reprocessar": true}}\'.'
        )

    return {
        'ciclo': ciclo,
        'ciclo_esperado': esperado,
        'reprocessamento': ciclo != esperado,
        'verificado_em': agora_local.isoformat(timespec='seconds'),
        'fim_do_ciclo': fim.isoformat(timespec='seconds'),
        'liberado_desde': liberado_em.isoformat(timespec='seconds'),
    }


def adicionar_argumento_ciclo(parser: argparse.ArgumentParser) -> None:
    """Adiciona `--ciclo` OBRIGATÓRIO ao parser (formato validado)."""
    parser.add_argument(
        '--ciclo', required=True, type=_tipo_ciclo,
        help='Ciclo a processar (YYYY-MM). Definido pela DAG — nenhum script '
             'calcula ciclo a partir da data do sistema.',
    )


def _tipo_ciclo(valor: str) -> str:
    try:
        parse_ciclo(valor)
    except CicloInvalido as e:
        raise argparse.ArgumentTypeError(str(e))
    return valor


def _como_local(agora: datetime) -> datetime:
    if agora.tzinfo is None:
        raise ValueError('validar_data exige datetime com fuso (ex.: datetime.now(timezone.utc))')
    return agora.astimezone(FUSO)


if __name__ == '__main__':
    # Uso pela DAG: python scripts/ciclo.py --ciclo 2026-10 [--reprocessar]
    p = argparse.ArgumentParser(description='Valida se o ciclo pode ser processado agora')
    adicionar_argumento_ciclo(p)
    p.add_argument('--reprocessar', action='store_true',
                   help='Permite processar um ciclo que não é o mês anterior ao atual')
    a = p.parse_args()
    try:
        info = validar_data(a.ciclo, datetime.now(timezone.utc), a.reprocessar)
    except CicloInvalido as e:
        print(f'BLOQUEADO: {e}')
        raise SystemExit(1)
    print(f'OK: ciclo {info["ciclo"]} liberado para processamento '
          f'({"REPROCESSAMENTO" if info["reprocessamento"] else "fluxo normal"}).')
