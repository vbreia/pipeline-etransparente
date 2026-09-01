#!/usr/bin/env python3
"""
Script de uso único: remove as entradas do ciclo 2026-09 de
silver/oscs_historico.parquet E gold/oscs_historico.json, nessa ordem.

Diferente da primeira tentativa (que só limpou o JSON): o JSON é sempre
derivado do parquet no final de generate_silver.py — limpar só o JSON é
temporário, porque a próxima execução do generate_silver.py reescreve o
JSON a partir do parquet (ainda sujo) e traz o ciclo removido de volta.
Este script limpa os dois arquivos juntos, para que fiquem consistentes
de forma duradoura.
"""
import json
import os
from io import BytesIO

import pandas as pd
from azure.storage.blob import BlobServiceClient

CONTAINER = 'etransparente'
CICLO_A_REMOVER = '2026-09'


def get_client():
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    if not conn_str:
        raise RuntimeError('AZURE_STORAGE_CONNECTION_STRING não definida')
    return BlobServiceClient.from_connection_string(conn_str)


def main():
    client = get_client()

    print('=== silver/oscs_historico.parquet ===')
    blob = client.get_blob_client(container=CONTAINER, blob='silver/oscs_historico.parquet')
    df = pd.read_parquet(BytesIO(blob.download_blob().readall()))
    print(f'Total antes: {len(df)}')
    ciclos_antes = sorted(df['ciclo'].astype(str).unique().tolist())
    print(f'Ciclos antes: {ciclos_antes}')

    df_limpo = df[df['ciclo'] != CICLO_A_REMOVER].reset_index(drop=True)
    print(f'Removendo {len(df) - len(df_limpo)} registros do ciclo {CICLO_A_REMOVER}')
    print(f'Total depois: {len(df_limpo)}')
    ciclos_depois = sorted(df_limpo['ciclo'].astype(str).unique().tolist())
    print(f'Ciclos depois: {ciclos_depois}')

    idc = df_limpo[df_limpo['nome'].str.contains('direito coletivo', case=False, na=False)]
    for _, row in idc.iterrows():
        print(f"  IDC — ciclo {row['ciclo']} -> nota_final: {row['nota_final']}")

    buf = BytesIO()
    df_limpo.to_parquet(buf, index=False)
    buf.seek(0)
    client.get_blob_client(container=CONTAINER, blob='silver/oscs_historico.parquet').upload_blob(
        buf, overwrite=True
    )
    print('Upload: silver/oscs_historico.parquet')

    print()
    print('=== gold/oscs_historico.json (derivado do parquet limpo, para consistência imediata) ===')
    gold_records = df_limpo.to_dict(orient='records')
    blob_json = client.get_blob_client(container=CONTAINER, blob='gold/oscs_historico.json')
    blob_json.upload_blob(
        json.dumps(gold_records, ensure_ascii=False, indent=2), overwrite=True
    )
    print(f'Upload: gold/oscs_historico.json ({len(gold_records)} registros)')
    print()
    print('Concluído. Parquet e JSON agora estão sincronizados, sem o ciclo', CICLO_A_REMOVER)


if __name__ == '__main__':
    main()