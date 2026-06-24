#!/usr/bin/env python3
"""
Gera camada Silver (Parquet histórico) a partir do Bronze no Azure.
Le JSON bruto + scores do Azure Blob, merge em DataFrame e acumula em
silver/oscs_historico.parquet.
"""
import json
import logging
import os
import re
from datetime import date
from io import BytesIO
from azure.storage.blob import BlobServiceClient
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONTAINER = 'etransparente'
DOC_CAMPOS = [
    'estatuto', 'cneas', 'cebas', 'plano_acao', 'ata_eleicao',
    'relatorio_atividades', 'balanco_2021', 'balanco_2022',
    'balanco_2023', 'balanco_2024',
]

def get_client():
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    if not conn_str:
        raise RuntimeError('AZURE_STORAGE_CONNECTION_STRING não definida')
    return BlobServiceClient.from_connection_string(conn_str)

def list_blobs(client, prefix):
    return [b.name for b in client.get_container_client(CONTAINER).list_blobs(name_starts_with=prefix)]

def download_json(client, blob_path):
    blob = client.get_blob_client(container=CONTAINER, blob=blob_path)
    return json.loads(blob.download_blob().readall())

def download_parquet(client, blob_path):
    blob = client.get_blob_client(container=CONTAINER, blob=blob_path)
    return pd.read_parquet(BytesIO(blob.download_blob().readall()))

def upload_parquet(client, blob_path, df):
    buf = BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    client.get_blob_client(container=CONTAINER, blob=blob_path).upload_blob(buf, overwrite=True)
    logger.info(f'Upload silver: {blob_path} ({len(df)} linhas)')

def main():
    month = date.today().strftime('%Y-%m')
    ciclo = month
    client = get_client()

    bronze_prefix = f'bronze/{month}/oscs_etransparente_'
    score_prefix = f'bronze/{month}/transparency_scores_'
    silver_blob = 'silver/oscs_historico.parquet'
    local_parquet = os.path.join(
        os.path.dirname(__file__), '..', 'output', 'oscs_historico.parquet'
    )

    # 1. Baixar JSON bronze do mês (ONGs)
    bronze_files = sorted(list_blobs(client, bronze_prefix))
    if not bronze_files:
        raise RuntimeError(f'Nenhum arquivo bronze/{month}/oscs_etransparente_*.json encontrado')
    latest_bronze = bronze_files[-1]
    logger.info(f'Lendo bronze: {latest_bronze}')
    bronze_data = download_json(client, latest_bronze)

    # 2. Baixar scores do mês
    score_files = sorted(list_blobs(client, score_prefix))
    scores_map = {}
    if score_files:
        latest_score = score_files[-1]
        logger.info(f'Lendo scores: {latest_score}')
        score_data = download_json(client, latest_score)
        resultados = score_data.get('resultados', score_data if isinstance(score_data, list) else [])
        scores_map = {s['nome']: s for s in resultados}

    # 3. Construir DataFrame do ciclo atual
    rows = []
    for ong in bronze_data:
        nome = ong.get('nome') or ong.get('title') or ''
        if not nome:
            continue
        docs = ong.get('documentos') or {}
        score = scores_map.get(nome, {})
        row = {
            'ciclo': ciclo,
            'nome': nome,
            'url': ong.get('url', ''),
            'nota_final': float(score.get('nota_final', 0)),
            'max_nota': float(score.get('max_nota', 30)),
            'classificacao': score.get('classificacao', ''),
        }
        for campo in DOC_CAMPOS:
            row[campo] = docs.get(campo, '')
        rows.append(row)

    df_novo = pd.DataFrame(rows)

    # 4. Baixar Parquet existente se houver
    df_existente = None
    try:
        df_existente = download_parquet(client, silver_blob)
        logger.info(f'Silver existente: {len(df_existente)} registros')
    except Exception:
        logger.info('Nenhum silver existente — criando novo')

    # 5. Remover entradas do ciclo atual (evita duplicatas)
    if df_existente is not None and not df_existente.empty:
        if 'ciclo' in df_existente.columns:
            df_existente = df_existente[df_existente['ciclo'] != ciclo]
        df_final = pd.concat([df_existente, df_novo], ignore_index=True)
    else:
        df_final = df_novo

    # 6. Salvar local
    os.makedirs(os.path.dirname(local_parquet), exist_ok=True)
    df_final.to_parquet(local_parquet, index=False)
    logger.info(f'Salvo local: {local_parquet}')

    # 7. Upload
    upload_parquet(client, silver_blob, df_final)

    # 8. Log
    logger.info(f'Silver atualizado: {len(df_final)} registros acumulados '
                f'(+{len(df_novo)} do ciclo {ciclo})')

if __name__ == '__main__':
    main()
