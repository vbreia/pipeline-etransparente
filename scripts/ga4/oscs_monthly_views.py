#!/usr/bin/env python3
"""
Generate daily views per OSC for a calendar month.

Reads an input JSON produced by `ong_extractor` (array of objects with at least
`nome` and `url`), extracts the path from each URL (e.g. `/oscs/123/`) and
queries the GA4 Data API to return daily `screenPageViews` for the full calendar
month requested.

Behavior:
- Default month: previous calendar month (e.g. today=2025-12-02 -> month=2025-11)
- Batches multiple pagePaths per RunReportRequest to reduce API calls
- Outputs a JSON file with objects: `{ "nome": "", "url": "", "views": [int,...] }`

Usage examples:
  # previous month (default)
  export GA4_PROPERTY_ID=414902979
  python3 oscs_monthly_views.py --input output/oscs_etransparente_2025-12-02-21-04-43.json

  # explicit month
  python3 oscs_monthly_views.py --input output/oscs_etransparente_2025-12-02-21-04-43.json --month 2025-11

Options:
  --batch-size N   Number of pagePaths per GA4 request (default 40)
  --output FILE    Output JSON file (default: output/oscs_views_YYYY-MM.json)

Notes:
- The script uses Application Default Credentials (ADC). Make sure WIF/ADC is
  configured in the VM environment as you already do for other scripts.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    Dimension,
    Metric,
    DateRange,
    FilterExpression,
    FilterExpressionList,
    Filter,
)


def month_range_from_string(month_str: str) -> Tuple[str, str, List[str]]:
    """Return start_date, end_date and list of ISO yyyymmdd strings for the month.

    month_str: YYYY-MM
    """
    dt = datetime.strptime(month_str + "-01", "%Y-%m-%d").date()
    # start is first day
    start = dt.replace(day=1)
    # end is last day of that month
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    end = next_month - timedelta(days=1)

    # build list of yyyymmdd strings
    days = []
    cur = start
    while cur <= end:
        days.append(cur.strftime("%Y%m%d"))
        cur = cur + timedelta(days=1)

    return start.isoformat(), end.isoformat(), days


def default_current_month() -> str:
    today = date.today()
    return today.strftime("%Y-%m")


def read_input_json(path: str) -> List[Dict]:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def extract_path_from_url(url: str) -> str:
    if not url:
        return ""
    p = urlparse(url)
    path = p.path or ""
    # Normalize: ensure leading slash
    if not path.startswith("/"):
        path = "/" + path
    return path


def chunked(iterable, n):
    for i in range(0, len(iterable), n):
        yield iterable[i:i + n]


def build_or_filter_for_paths(paths: List[str]) -> FilterExpression:
    exps = []
    seen = set()
    for p in paths:
        if not p or p in seen:
            continue
        seen.add(p)
        exps.append(FilterExpression(filter=Filter(field_name="pagePath",
                                                   string_filter=Filter.StringFilter(value=p,
                                                                                    match_type=Filter.StringFilter.MatchType.EXACT))))
    return FilterExpression(or_group=FilterExpressionList(expressions=exps))


def query_batch_daily(client: BetaAnalyticsDataClient, property_id: str, paths: List[str], start_date: str, end_date: str) -> List[Tuple[str, str, int]]:
    """Query GA4 for dimensions (pagePath, date) and return list of (pagePath, date, views)
    date format returned as YYYYMMDD strings.
    """
    if not paths:
        return []

    dim_filter = build_or_filter_for_paths(paths)

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="pagePath"), Dimension(name="date")],
        metrics=[Metric(name="screenPageViews")],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        dimension_filter=dim_filter,
        limit=100000,
    )

    resp = client.run_report(request=request)
    out = []
    for row in resp.rows:
        page = row.dimension_values[0].value
        day = row.dimension_values[1].value
        views = int(row.metric_values[0].value) if row.metric_values and row.metric_values[0].value.isdigit() else 0
        out.append((page, day, views))
    return out


def main():
    parser = argparse.ArgumentParser(description="Generate daily views per OSC for a month")
    parser.add_argument("--input", required=False, help="Input JSON file produced by ong_extractor (defaults to latest output/oscs_etransparente_*.json)")
    parser.add_argument("--month", help="Month in YYYY-MM (default: previous month)")
    parser.add_argument("--batch-size", type=int, default=40, help="Number of pagePaths per GA4 request (default 40)")
    parser.add_argument("--output", help="Output JSON file path")
    args = parser.parse_args()

    month = args.month or default_current_month()
    start_date, end_date, days = month_range_from_string(month)

    input_path = args.input
    # If input not provided, pick the latest generated file in ./output matching pattern
    if not input_path:
        pattern = os.path.join(os.getcwd(), 'output', 'oscs_etransparente_*.json')
        matches = glob.glob(pattern)
        if not matches:
            raise RuntimeError(f"Nenhum arquivo encontrado em {pattern}. Execute primeiro o `ong_extractor` ou passe --input.")

        # Prefer selection by date embedded in filename (YYYY-MM-DD). If multiple
        # files share the same date, pick the most recent by mtime. If no filenames
        # contain a date, fall back to choosing by mtime.
        import re
        date_map = {}  # date_str -> list of files
        for p in matches:
            base = os.path.basename(p)
            m = re.search(r"(\d{4}-\d{2}-\d{2})", base)
            if m:
                ds = m.group(1)
                date_map.setdefault(ds, []).append(p)

        if date_map:
            # choose the latest date (string compare works for YYYY-MM-DD)
            latest_date = max(date_map.keys())
            candidates = date_map[latest_date]
            # pick newest among candidates by mtime
            input_path = max(candidates, key=os.path.getmtime)
            print(f"Sem --input: usando arquivo por data mais recente {latest_date}: {input_path}")
        else:
            # fallback to mtime
            input_path = max(matches, key=os.path.getmtime)
            print(f"Sem --input e sem data no nome: usando arquivo por mtime: {input_path}")
    items = read_input_json(input_path)

    if os.environ.get('PIPELINE_TEST_MODE', '').lower() == 'true':
        items = [o for o in items if 'direito coletivo' in (o.get('nome') or o.get('title', '')).lower() or 'idc' in (o.get('nome') or o.get('title', '')).lower()]
        print(f'PIPELINE_TEST_MODE: filtrando apenas IDC ({len(items)} ONG)')

    # Prepare mapping idx -> (nome, url, path)
    prepared = []
    for obj in items:
        nome = obj.get('nome') or obj.get('title') or ''
        url = obj.get('url') or ''
        path = extract_path_from_url(url)
        prepared.append({'nome': nome, 'url': url, 'path': path})

    property_id = os.environ.get('GA4_PROPERTY_ID')
    if not property_id:
        raise RuntimeError('Defina GA4_PROPERTY_ID no ambiente')

    client = BetaAnalyticsDataClient()

    # Build list of unique paths to query
    unique_paths = []
    for p in prepared:
        if p['path'] and p['path'] not in unique_paths:
            unique_paths.append(p['path'])

    # Results structure: map (path -> day -> views)
    per_path_day: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    # Query in batches
    for batch in chunked(unique_paths, args.batch_size):
        print(f"Querying batch of {len(batch)} paths...")
        rows = query_batch_daily(client, property_id, batch, start_date, end_date)
        for page, day, views in rows:
            per_path_day[page][day] = views

    # Build final output array
    output = []
    for entry in prepared:
        path = entry['path']
        # Try direct path, else try with/without trailing slash
        if path in per_path_day:
            daymap = per_path_day[path]
        else:
            alt = path.rstrip('/') if path.endswith('/') else path + '/'
            daymap = per_path_day.get(alt, {})

        views_list = [int(daymap.get(d, 0)) for d in days]

        output.append({
            'nome': entry['nome'],
            'url': entry['url'],
            'views': views_list,
        })

    # Write output
    outpath = args.output
    if not outpath:
        outdir = os.path.join(os.getcwd(), 'output')
        os.makedirs(outdir, exist_ok=True)
        outpath = os.path.join(outdir, f"oscs_views_{month}.json")

    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(output)} entries to {outpath}")


if __name__ == '__main__':
    main()
