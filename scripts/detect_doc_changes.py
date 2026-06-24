#!/usr/bin/env python3
"""
Detecta alterações nas URLs de documentos entre o ciclo atual e o anterior
no silver/oscs_historico.parquet e gera gold/tempestividade_YYYY-MM.json.
"""
import json
import logging
import os
from datetime import date
from io import BytesIO
from azure.storage.blob import BlobServiceClient
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONTAINER = 'etransparente'
SILVER_BLOB = 'silver/oscs_historico.parquet'
DOC_CAMPOS = [
    'estatuto', 'cneas', 'cebas', 'plano_acao', 'ata_eleicao',
    'relatorio_atividades', 'balanco_2021', 'balanco_2022',
    'balanco_2023', 'balanco_2024',
]

MESES = [
    '', 'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
]

def get_client():
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    if not conn_str:
        raise RuntimeError('AZURE_STORAGE_CONNECTION_STRING não definida')
    return BlobServiceClient.from_connection_string(conn_str)

def download_parquet(client, blob_path):
    blob = client.get_blob_client(container=CONTAINER, blob=blob_path)
    return pd.read_parquet(BytesIO(blob.download_blob().readall()))

def upload_json(client, blob_path, data):
    blob_client = client.get_blob_client(container=CONTAINER, blob=blob_path)
    blob_client.upload_blob(json.dumps(data, ensure_ascii=False, indent=2), overwrite=True)
    logger.info(f'Upload gold: {blob_path}')

def mes_ano_label(ano, mes):
    return f'{MESES[mes]}-{ano}'

def main():
    hoje = date.today()
    ciclo_atual = hoje.strftime('%Y-%m')
    ciclo_anterior = date(hoje.year, hoje.month, 1) - pd.offsets.MonthBegin(1)
    if hasattr(ciclo_anterior, 'strftime'):
        ciclo_anterior_str = ciclo_anterior.strftime('%Y-%m')
    else:
        if hoje.month == 1:
            ciclo_anterior_str = f'{hoje.year - 1}-12'
        else:
            ciclo_anterior_str = f'{hoje.year}-{hoje.month - 1:02d}'

    if hoje.month == 1:
        mes_ant, ano_ant = 12, hoje.year - 1
    else:
        mes_ant, ano_ant = hoje.month - 1, hoje.year

    client = get_client()

    # 1. Baixar silver
    try:
        df = download_parquet(client, SILVER_BLOB)
    except Exception as e:
        raise RuntimeError(f'Erro ao baixar {SILVER_BLOB}: {e}')

    if df.empty or 'ciclo' not in df.columns:
        logger.info('Silver vazio — nenhuma alteração para detectar')
        upload_json(client, f'gold/tempestividade_{ciclo_atual}.json', [])
        return

    # 2. Filtrar ciclos atual e anterior
    df_atual = df[df['ciclo'] == ciclo_atual]
    df_anterior = df[df['ciclo'] == ciclo_anterior_str]

    if df_atual.empty:
        logger.info(f'Nenhum registro para o ciclo atual {ciclo_atual}')
        upload_json(client, f'gold/tempestividade_{ciclo_atual}.json', [])
        return
    if df_anterior.empty:
        logger.info(f'Nenhum registro para o ciclo anterior {ciclo_anterior_str} — primeira execução')
        upload_json(client, f'gold/tempestividade_{ciclo_atual}.json', [])
        return

    # 3. Merge por nome para comparar
    merged = df_atual.merge(df_anterior, on='nome', suffixes=('_atual', '_anterior'))
    if merged.empty:
        logger.info('Nenhuma ONG em comum entre os dois ciclos')
        upload_json(client, f'gold/tempestividade_{ciclo_atual}.json', [])
        return

    alteracoes = []
    for _, row in merged.iterrows():
        nome = row['nome']
        for campo in DOC_CAMPOS:
            url_atual = str(row.get(f'{campo}_atual', '') or '')
            url_anterior = str(row.get(f'{campo}_anterior', '') or '')
            if url_atual and url_anterior and url_atual != url_anterior:
                alteracoes.append({
                    'nome': nome,
                    'campo': campo,
                    'url_anterior': url_anterior,
                    'url_nova': url_atual,
                    'ciclo_deteccao': mes_ano_label(hoje.year, hoje.month),
                    'ciclo_anterior': mes_ano_label(ano_ant, mes_ant),
                })

    # 4. Salvar local
    gold_file = f'tempestividade_{ciclo_atual}.json'
    local_path = os.path.join(
        os.path.dirname(__file__), '..', 'output', gold_file
    )
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, 'w', encoding='utf-8') as f:
        json.dump(alteracoes, f, ensure_ascii=False, indent=2)
    logger.info(f'Salvo local: {local_path}')

    # 5. Upload para gold
    gold_blob = f'gold/{gold_file}'
    upload_json(client, gold_blob, alteracoes)

    # 6. Log
    if alteracoes:
        logger.info(f'{len(alteracoes)} alteração(ões) detectada(s)')
        for alt in alteracoes:
            logger.info(f'  {alt["nome"]}: {alt["campo"]} alterado')
    else:
        logger.info('Nenhuma alteração detectada')

if __name__ == '__main__':
    main()
