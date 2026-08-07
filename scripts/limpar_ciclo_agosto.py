#!/usr/bin/env python3
"""
Script de uso único: remove as entradas do ciclo 2026-08 de
gold/oscs_historico.json (nota/score) e gold/oscs_views_historico.json (GA4),
deixando julho/2026 como o ciclo mais recente visível no dashboard.

Rode DEPOIS de:
  python3 scripts/generate_silver.py --ciclo 2026-07

Não mexe em nenhum outro mês. Mostra um resumo antes e depois, para conferência.
"""
import json
import os

from azure.storage.blob import BlobServiceClient

CONTAINER = 'etransparente'
CICLO_A_REMOVER_SCORE = '2026-08'
MES_A_REMOVER_VIEWS = '2026-08'


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


def limpar_score_historico(client):
    print('=== gold/oscs_historico.json (nota/score) ===')
    data = download_json(client, 'gold/oscs_historico.json')
    print(f'Total antes: {len(data)}')

    ciclos_antes = sorted({d.get('ciclo') for d in data})
    print(f'Ciclos antes: {ciclos_antes}')

    removidos = [d for d in data if d.get('ciclo') == CICLO_A_REMOVER_SCORE]
    mantidos = [d for d in data if d.get('ciclo') != CICLO_A_REMOVER_SCORE]

    print(f'Removendo {len(removidos)} registros do ciclo {CICLO_A_REMOVER_SCORE}')
    print(f'Total depois: {len(mantidos)}')

    ciclos_depois = sorted({d.get('ciclo') for d in mantidos})
    print(f'Ciclos depois: {ciclos_depois}')

    idc = [d for d in mantidos if 'direito coletivo' in d.get('nome', '').lower()]
    for d in idc:
        print(f"  IDC — ciclo {d.get('ciclo')} -> nota_final: {d.get('nota_final')}")

    upload_json(client, 'gold/oscs_historico.json', mantidos)
    print()


def limpar_views_historico(client):
    print('=== gold/oscs_views_historico.json (GA4) ===')
    data = download_json(client, 'gold/oscs_views_historico.json')
    print(f'Total antes: {len(data)} meses')

    meses_antes = sorted(e.get('mes') for e in data)
    print(f'Meses antes: {meses_antes}')

    mantidos = [e for e in data if e.get('mes') != MES_A_REMOVER_VIEWS]
    removido = [e for e in data if e.get('mes') == MES_A_REMOVER_VIEWS]

    print(f'Removendo entrada do mês {MES_A_REMOVER_VIEWS} '
          f'({len(removido[0]["oscs"]) if removido else 0} OSCs nela)')
    print(f'Total depois: {len(mantidos)} meses')

    meses_depois = sorted(e.get('mes') for e in mantidos)
    print(f'Meses depois: {meses_depois}')

    upload_json(client, 'gold/oscs_views_historico.json', mantidos)
    print()


def main():
    client = get_client()
    limpar_score_historico(client)
    limpar_views_historico(client)
    print('Concluído. O dashboard deve agora exibir julho/2026 como ciclo mais recente.')


if __name__ == '__main__':
    main()