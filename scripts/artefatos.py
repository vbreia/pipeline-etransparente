#!/usr/bin/env python3
"""
Utilitários de leitura/gravação dos artefatos do ciclo, com hash.

Todo artefato que vira relatório (views, relatórios gerados, validação,
manifesto de envio) é gravado com hash SHA-256, para que as etapas seguintes
possam provar que estão usando EXATAMENTE os mesmos dados que foram validados.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
from typing import Any

VERSAO_FORMATO_VIEWS = 2


def sha256_arquivo(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 16), b''):
            h.update(bloco)
    return h.hexdigest()


def sha256_json(obj: Any) -> str:
    """Hash estável de uma estrutura JSON (chaves ordenadas, sem espaços)."""
    canon = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()


def gravar_json(caminho: str, dados: Any) -> str:
    os.makedirs(os.path.dirname(caminho) or '.', exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    return sha256_arquivo(caminho)


def ler_json(caminho: str) -> Any:
    with open(caminho, 'r', encoding='utf-8') as f:
        return json.load(f)


def carregar_views(caminho: str) -> tuple[dict | None, list[dict]]:
    """Lê oscs_views_{ciclo}.json nos dois formatos.

    - Formato 2 (atual): {"meta": {...}, "oscs": [{nome, url, views}, ...]}
    - Formato 1 (legado, até out/2026): lista [{nome, url, views}, ...] — meta = None

    Retorna (meta, oscs).
    """
    dados = ler_json(caminho)
    if isinstance(dados, dict) and 'oscs' in dados:
        return dados.get('meta'), dados['oscs']
    if isinstance(dados, list):
        return None, dados
    raise ValueError(f'Formato inesperado em {caminho}')


def total_views(oscs: list[dict]) -> int:
    return sum(sum(o.get('views') or []) for o in oscs)


def localizar_dashboards_do_ciclo(dir_output: str, ciclo: str) -> tuple[str | None, str | None]:
    """Pasta de dashboards mais recente cujo relatorios.json declara este ciclo.

    Nunca "a pasta mais recente" às cegas: se uma geração de teste ou de outro
    ciclo rodou depois, ela é ignorada.
    """
    candidatas = sorted(glob.glob(os.path.join(dir_output, 'dashboards', '*')), reverse=True)
    for pasta in candidatas:
        manifesto = os.path.join(pasta, 'relatorios.json')
        if os.path.isfile(manifesto):
            try:
                if ler_json(manifesto).get('ciclo') == ciclo:
                    return pasta, manifesto
            except Exception:
                continue
    return None, None
