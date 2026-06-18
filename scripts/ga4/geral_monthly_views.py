#!/usr/bin/env python3
import argparse
import json
import os
from datetime import date, datetime, timedelta

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    Dimension,
    Metric,
    DateRange,
)


def days_in_month(year: int, month: int) -> int:
    first = date(year, month, 1)
    next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = (next_month - timedelta(days=1)).day
    return last


def month_default_previous() -> str:
    today = date.today()
    first_this = today.replace(day=1)
    prev_last = first_this - timedelta(days=1)
    return prev_last.strftime("%Y-%m")


def main():
    parser = argparse.ArgumentParser(description="Gera views diárias do site por mês e salva JSON 'geral_views_YYYY-MM.json'.")
    parser.add_argument("--month", help="Mês no formato YYYY-MM (padrão: mês anterior)")
    args = parser.parse_args()

    month_str = args.month or month_default_previous()
    try:
        year, month = map(int, month_str.split("-"))
    except Exception:
        raise RuntimeError("Mês inválido. Use YYYY-MM")

    last_day = days_in_month(year, month)
    start_date = date(year, month, 1).isoformat()
    end_date = date(year, month, last_day).isoformat()

    print(f"Período: {start_date} até {end_date}")

    property_id = os.getenv("GA4_PROPERTY_ID")
    if not property_id:
        raise RuntimeError("A variável de ambiente GA4_PROPERTY_ID não está definida")

    client = BetaAnalyticsDataClient()

    # relatório por data (site-wide)
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="date")],
        metrics=[Metric(name="screenPageViews")],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
    )

    response = client.run_report(request)

    # Mapear date->views
    day_map = {row.dimension_values[0].value: int(row.metric_values[0].value or 0) for row in response.rows}

    # Construir lista diária do dia 1 até last_day
    daily = []
    total = 0
    for d in range(1, last_day + 1):
        dt = date(year, month, d)
        key = dt.strftime("%Y%m%d")
        views = int(day_map.get(key, 0))
        daily.append({"date": dt.isoformat(), "views": views})
        total += views

    # Garantir diretório output
    outdir = os.path.join(os.getcwd(), "output")
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, f"geral_views_{month_str}.json")

    result = {"month": month_str, "days": daily, "total": total}

    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Wrote daily views for {month_str} ({len(daily)} days) to {outpath}")


if __name__ == "__main__":
    main()
