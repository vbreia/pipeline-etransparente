#!/usr/bin/env python3
"""Copia envio/comum.py (canônico) para a API do dashboard e para a Function de envio.

Rode depois de editar envio/comum.py:  python envio/sincronizar_copias.py
O teste tests/test_envio_comum.py falha se as cópias estiverem diferentes.
"""
import pathlib
import shutil

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / 'envio' / 'comum.py'
DESTINOS = [RAIZ / 'api' / 'shared_code' / 'comum.py', RAIZ / 'functions' / 'comum.py']

AVISO = ('# ARQUIVO GERADO — NÃO EDITE AQUI. Edite envio/comum.py e rode envio/sincronizar_copias.py\n')

if __name__ == '__main__':
    conteudo = AVISO + ORIGEM.read_text(encoding='utf-8')
    for d in DESTINOS:
        d.write_text(conteudo, encoding='utf-8')
        print(f'atualizado: {d.relative_to(RAIZ)}')
