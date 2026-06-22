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
from azure.storage.blob import BlobServiceClient, CorsRule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_client():
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    if not conn_str:
        raise RuntimeError('AZURE_STORAGE_CONNECTION_STRING não definida')
    return BlobServiceClient.from_connection_string(conn_str)

def setup_cors(client):
    cors_rule = CorsRule(
        allowed_origins=['*'],
        allowed_methods=['GET'],
        allowed_headers=['*'],
        exposed_headers=['*'],
        max_age_in_seconds=3600
    )
    client.set_service_properties(cors=[cors_rule])
    logger.info('CORS configurado: GET de qualquer origem')

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
    setup_cors(client)

    test_mode = os.environ.get('PIPELINE_TEST_MODE', '').lower() == 'true'
    if test_mode:
        logger.info('PIPELINE_TEST_MODE: filtrando uploads apenas do IDC')

    def _idc_match(path):
        stem = Path(path).stem.lower()
        return 'idc' in stem or 'instituto-de-direito-coletivo' in stem

    # Bronze — JSONs brutos do mês
    for pattern in [f'oscs_etransparente_*.json', f'oscs_views_{month}.json']:
        for f in glob.glob(os.path.join(out, pattern)):
            if test_mode and not _idc_match(f):
                continue
            upload_file(client, container, f'bronze/{month}/{Path(f).name}', f)
    for f in glob.glob(os.path.join(out, 'scores', f'transparency_scores_*.json')):
        if test_mode and not _idc_match(f):
            continue
        upload_file(client, container, f'bronze/{month}/{Path(f).name}', f)

    # Gold — PDFs e HTMLs do mês
    dashboards = sorted(glob.glob(os.path.join(out, 'dashboards', '*')))
    if dashboards:
        latest = dashboards[-1]
        for folder in ['pdf', 'html']:
            for f in glob.glob(os.path.join(latest, folder, '*')):
                if test_mode and not _idc_match(f):
                    continue
                upload_file(client, container, f'gold/{month}/{folder}/{Path(f).name}', f)

    # Gold — verificacoes_all.json acumulado
    verificacoes_monthly = glob.glob(os.path.join(out, f'verificacoes_{month}.json'))
    if verificacoes_monthly:
        blob_client = client.get_blob_client(container=container, blob='gold/verificacoes_all.json')
        existing_all = []
        try:
            existing_data = blob_client.download_blob().readall()
            existing_all = json.loads(existing_data)
        except Exception:
            pass

        with open(verificacoes_monthly[0], 'r', encoding='utf-8') as fh:
            new_data = json.load(fh)

        if new_data:
            ciclos = set(e.get('ciclo') for e in new_data if 'ciclo' in e)
            if ciclos:
                existing_all = [e for e in existing_all if e.get('ciclo') not in ciclos]
            existing_all.extend(new_data)

        all_path = os.path.join(out, 'verificacoes_all.json')
        with open(all_path, 'w', encoding='utf-8') as fh:
            json.dump(existing_all, fh, ensure_ascii=False, indent=2)
        upload_file(client, container, 'gold/verificacoes_all.json', all_path)
        logger.info(f'verificacoes_all.json atualizado: {len(existing_all)} registros totais')

    logger.info(f'Upload concluído para {month}')

if __name__ == '__main__':
    main()
