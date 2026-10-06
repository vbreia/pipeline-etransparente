#!/usr/bin/env python3
"""Diagnóstico pontual: em que etapa a contagem de OSCs cai de 55/56 para 54?

Compara a contagem em cada camada do pipeline, do site até o dashboard:
  1. API WordPress (X-WP-Total, só listagens publicadas)
  2. Extração local mais recente (output/oscs_etransparente_*.json)
  3. Scores mais recentes (output/scores/transparency_scores_*.json)
  4. Views GA4 do ciclo (output/oscs_views_{ciclo}.json)
  5. gold/oscs_historico.json no Azure (fonte do KPI "OSCs Monitoradas")

Também lista nomes duplicados (o dashboard deduplica por nome) e as OSCs
presentes numa camada e ausentes na seguinte.

Uso (na VM, depois de git pull):
  docker exec -w /home/airflow airflow-scheduler \
      python /home/airflow/scripts/diagnostico_contagem_oscs.py 2026-09
"""
import glob
import json
import os
import sys
from collections import Counter

import requests

CICLO = sys.argv[1] if len(sys.argv) > 1 else '2026-09'
OUT = '/home/airflow/output'
API = 'https://etransparente.org/wp-json/wp/v2/job_listing'
# Mesmo User-Agent do ong_extractor.py — o site recusa o UA padrão do requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0 Safari/537.36"
}


def latest(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def nomes(lista):
    return [(o.get('nome') or o.get('title') or '').strip() for o in lista]


camadas = {}

# 1. API
r = requests.get(API, params={'per_page': 100, '_fields': 'id,slug,title,date,status'},
                 headers=HEADERS, timeout=30)
try:
    api = r.json()
except ValueError:
    print(f"[1] API WordPress  ERRO: HTTP {r.status_code}, resposta não é JSON: {r.text[:200]!r}")
    api = []
if api:
    print(f"[1] API WordPress  X-WP-Total={r.headers.get('X-WP-Total')}  retornados={len(api)}")
    for o in sorted(api, key=lambda x: x['date'], reverse=True)[:5]:
        print(f"      mais recente: {o['date'][:10]}  id={o['id']}  {o['slug']}")
camadas['api'] = {o['slug'] for o in api}

# 2. Extração
f = latest(f'{OUT}/oscs_etransparente_*.json')
ext = json.load(open(f, encoding='utf-8'))
print(f"[2] Extração        {len(ext)}  ({os.path.basename(f)})")
camadas['extracao'] = {(o.get('url') or '').rstrip('/').split('/')[-1] for o in ext}
dup = [n for n, c in Counter(nomes(ext)).items() if c > 1]
if dup:
    print(f"      ATENÇÃO nomes duplicados na extração (dashboard junta por nome): {dup}")

# 3. Scores
f = latest(f'{OUT}/scores/transparency_scores_*.json')
sc = json.load(open(f, encoding='utf-8')).get('resultados', [])
print(f"[3] Scores          {len(sc)}  ({os.path.basename(f)})")

# 4. Views do ciclo
f = f'{OUT}/oscs_views_{CICLO}.json'
if os.path.exists(f):
    print(f"[4] Views {CICLO}   {len(json.load(open(f, encoding='utf-8')))}")
else:
    print(f"[4] Views {CICLO}   arquivo não existe")

# 5. gold/oscs_historico.json
try:
    from azure.storage.blob import BlobServiceClient
    c = BlobServiceClient.from_connection_string(os.environ['AZURE_STORAGE_CONNECTION_STRING'])
    hist = json.loads(c.get_blob_client('etransparente', 'gold/oscs_historico.json').download_blob().readall())
    por_ciclo = Counter(h.get('ciclo') for h in hist)
    for ciclo in sorted(por_ciclo)[-4:]:
        unicos = len({h.get('nome') for h in hist if h.get('ciclo') == ciclo})
        print(f"[5] gold histórico  ciclo {ciclo}: {por_ciclo[ciclo]} linhas / {unicos} nomes únicos")
except Exception as e:
    print(f"[5] gold histórico  erro ao ler: {e}")

# Diferença API x extração
if not camadas['api']:
    print("\nSem dados da API — comparação API x extração não realizada.")
    sys.exit(0)
falta = camadas['api'] - camadas['extracao']
sobra = camadas['extracao'] - camadas['api']
if falta:
    print(f"\nNa API mas fora da extração: {sorted(falta)}")
if sobra:
    print(f"Na extração mas fora da API: {sorted(sobra)}")
if not falta and not sobra:
    print("\nAPI e extração batem por slug.")
