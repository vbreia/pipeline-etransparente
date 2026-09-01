#!/usr/bin/env python3
"""
Script de uso único: remove as entradas do ciclo 2026-09 de
gold/oscs_historico.json (nota/score), deixando agosto/2026 como o ciclo
mais recente visível no dashboard.

Contexto: o envio automático de 01/09/2026 rodou antes da correção do
"ciclo padrão" (que passou a usar o mês anterior, não o mês corrente) e
deixou uma entrada de setembro no histórico, calculada com base no mês que
mal tinha começado. Já reenviamos o ciclo de agosto corrigido, mas a
entrada de setembro continuava competindo como "mais recente" na leitura
do dashboard. Este script remove só essa entrada — não mexe em nenhum
outro ciclo.

Diferente de oscs_views_historico.json (já corrigido separadamente, ao
regenerar as views de agosto), este script cuida só do histórico de
score/nota.
"""
import json
import os

from azure.storage.blob import BlobServiceClient

CONTAINER = 'etransparente'
CICLO_A_REMOVER = '2026-09'


def get_client():
    conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
    if not conn_str:
        raise RuntimeError('AZURE_STORAGE_CONNECTION_STRING não definida')
    return BlobServiceClient.from_connection_string(conn_str)


def download_json(client, blob_path):
    blob = client.get_blob_client(container=CONTAINER, blob=blob_path)
    return json.loads(blob.download_blob().readall())


def upload_json(client, blob_path, data):
    blob = client.get_blob_client(container=CONTAINER, blob=blob_path)
    blob.upload_blob(json.dumps(data, ensure_ascii=False, indent=2), overwrite=True)
    print(f'Upload: {blob_path}')


def main():
    client = get_client()

    print('=== gold/oscs_historico.json (nota/score) ===')
    data = download_json(client, 'gold/oscs_historico.json')
    print(f'Total antes: {len(data)}')

    ciclos_antes = sorted({str(d.get('ciclo')) for d in data})
    print(f'Ciclos antes: {ciclos_antes}')

    removidos = [d for d in data if d.get('ciclo') == CICLO_A_REMOVER]
    mantidos = [d for d in data if d.get('ciclo') != CICLO_A_REMOVER]

    print(f'Removendo {len(removidos)} registros do ciclo {CICLO_A_REMOVER}')
    print(f'Total depois: {len(mantidos)}')

    ciclos_depois = sorted({str(d.get('ciclo')) for d in mantidos})
    print(f'Ciclos depois: {ciclos_depois}')

    idc = [d for d in mantidos if 'direito coletivo' in d.get('nome', '').lower()]
    for d in idc:
        print(f"  IDC — ciclo {d.get('ciclo')} -> nota_final: {d.get('nota_final')}")

    upload_json(client, 'gold/oscs_historico.json', mantidos)
    print('Concluído.')


if __name__ == '__main__':
    main()