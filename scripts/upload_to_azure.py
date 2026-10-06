#!/usr/bin/env python3
"""
Upload mensal de outputs para o Azure Data Lake Gen2.
Arquitetura Medallion (Bronze/Prata/Ouro):
  - bronze/YYYY-MM/ ← JSONs brutos que geraram os relatórios do ciclo
  - silver/         ← histórico acumulado (historico_scores.parquet)
  - gold/YYYY-MM/   ← outputs finais (PDFs, HTMLs, relatorios.json)

Uso: python scripts/upload_to_azure.py --ciclo YYYY-MM  (ciclo obrigatório, vem da DAG)
"""
import argparse
import os
import glob
import json
import logging
import sys
from pathlib import Path
from azure.storage.blob import BlobServiceClient, CorsRule

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ciclo import adicionar_argumento_ciclo  # noqa: E402
from artefatos import localizar_dashboards_do_ciclo  # noqa: E402

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
    parser = argparse.ArgumentParser(description='Upload mensal de outputs para o Azure Data Lake Gen2')
    adicionar_argumento_ciclo(parser)
    args = parser.parse_args()
    ciclo = args.ciclo

    base = '/home/airflow' if os.path.exists('/home/airflow/output') else os.getcwd()
    out = os.path.join(base, 'output')
    container = 'etransparente'

    pasta_dash, manifesto_path = localizar_dashboards_do_ciclo(out, ciclo)
    if not pasta_dash:
        raise RuntimeError(
            f'Nenhuma pasta em output/dashboards/ com relatorios.json do ciclo {ciclo}. '
            f'Rode dash.py --ciclo {ciclo} antes do upload.'
        )
    with open(manifesto_path, 'r', encoding='utf-8') as fh:
        manifesto = json.load(fh)
    logger.info(f'Ciclo {ciclo}: publicando {pasta_dash}')

    client = get_client()
    setup_cors(client)

    test_mode = os.environ.get('PIPELINE_TEST_MODE', '').lower() == 'true'
    if test_mode:
        logger.info('PIPELINE_TEST_MODE: filtrando uploads apenas do IDC')

    def _idc_match(path):
        stem = Path(path).stem.lower()
        return 'idc' in stem or 'instituto-de-direito-coletivo' in stem

    # Bronze — exatamente os arquivos que geraram os relatórios deste ciclo
    # (registrados no relatorios.json), não "todos os arquivos da pasta".
    bronze = [
        os.path.join(out, manifesto.get('arquivo_extracao', '')),
        os.path.join(out, 'scores', manifesto.get('arquivo_scores', '')),
        os.path.join(out, f'oscs_views_{ciclo}.json'),
    ]
    for f in bronze:
        if not os.path.isfile(f):
            raise RuntimeError(f'Arquivo de entrada do ciclo não encontrado: {f}')
        if test_mode and not _idc_match(f):
            continue
        upload_file(client, container, f'bronze/{ciclo}/{Path(f).name}', f)

    # Gold — PDFs, HTMLs e o manifesto dos relatórios do ciclo
    for folder in ['pdf', 'html']:
        for f in glob.glob(os.path.join(pasta_dash, folder, '*')):
            if test_mode and not _idc_match(f):
                continue
            upload_file(client, container, f'gold/{ciclo}/{folder}/{Path(f).name}', f)
    upload_file(client, container, f'gold/{ciclo}/relatorios.json', manifesto_path)

    # Gold — verificacoes_all.json acumulado (dash.py grava verificacoes_{ciclo}.json)
    verificacoes_monthly = glob.glob(os.path.join(out, f'verificacoes_{ciclo}.json'))
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
            seen = set()
            existing_all = [v for v in existing_all if v.get('hash') not in seen and not seen.add(v.get('hash'))]

        all_path = os.path.join(out, 'verificacoes_all.json')
        with open(all_path, 'w', encoding='utf-8') as fh:
            json.dump(existing_all, fh, ensure_ascii=False, indent=2)
        upload_file(client, container, 'gold/verificacoes_all.json', all_path)
        logger.info(f'verificacoes_all.json atualizado: {len(existing_all)} registros totais')

    # Gold — oscs_atual.json: a MESMA extração usada nos relatórios do ciclo
    upload_file(client, container, 'gold/oscs_atual.json', bronze[0])
    logger.info('gold/oscs_atual.json atualizado')

    logger.info(f'Upload concluído para o ciclo {ciclo}')

if __name__ == '__main__':
    main()
