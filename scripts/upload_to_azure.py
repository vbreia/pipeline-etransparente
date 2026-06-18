#!/usr/bin/env python3
"""
Upload mensal de outputs para o Azure Data Lake Gen2.
Arquitetura Medallion (Bronze/Prata/Ouro):
  - bronze/YYYY-MM/ ← JSONs brutos (oscs_etransparente_*.json, transparency_scores_*.json, oscs_views_*.json)
  - silver/         ← histórico acumulado (historico_scores.parquet)
  - gold/YYYY-MM/   ← outputs finais (PDFs, HTMLs)
"""
import os
import glob
import json
import logging
from datetime import date
from pathlib import Path
from azure.storage.blob import BlobServiceClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_client():
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    if not conn_str:
        raise RuntimeError('AZURE_STORAGE_CONNECTION_STRING não definida')
    return BlobServiceClient.from_connection_string(conn_str)

def upload_file(client, container, blob_path, local_path):
    with open(local_path, 'rb') as f:
        client.get_blob_client(container=container, blob=blob_path).upload_blob(f, overwrite=True)
    logger.info(f'Upload: {blob_path}')

def main():
    month = date.today().strftime('%Y-%m')
    base = '/home/airflow' if os.path.exists('/home/airflow/output') else os.getcwd()
    out = os.path.join(base, 'output')
    container = 'etransparente'
    client = get_client()

    # Bronze — JSONs brutos do mês
    for pattern in [f'oscs_etransparente_*.json', f'oscs_views_{month}.json']:
        for f in glob.glob(os.path.join(out, pattern)):
            upload_file(client, container, f'bronze/{month}/{Path(f).name}', f)
    for f in glob.glob(os.path.join(out, 'scores', f'transparency_scores_*.json')):
        upload_file(client, container, f'bronze/{month}/{Path(f).name}', f)

    # Gold — PDFs e HTMLs do mês
    dashboards = sorted(glob.glob(os.path.join(out, 'dashboards', '*')))
    if dashboards:
        latest = dashboards[-1]
        for folder in ['pdf', 'html']:
            for f in glob.glob(os.path.join(latest, folder, '*')):
                upload_file(client, container, f'gold/{month}/{folder}/{Path(f).name}', f)

    logger.info(f'Upload concluído para {month}')

if __name__ == '__main__':
    main()
