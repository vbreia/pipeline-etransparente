#!/usr/bin/env python3
"""Gera pontuações de transparência com metodologia de rubrica fixa.

Escala:
- Informações gerais:  0–15 pts  (15 campos pontuáveis, 1 pt cada)
- Termos/emendas:      0–15 pts  (média de todos os itens individuais × 15)

Nota final:
- Com termos/emendas:  nota_gerais + nota_termos   → escala 0–30
- Sem termos/emendas:  nota_gerais                 → escala 0–15

Classificação (percentual = nota_final / max_nota × 100):
- Regular : ≤ 30%
- Bom     : ≤ 69%
- Ótimo   : > 69%
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


OUTPUT_DIR = os.path.join(os.getcwd(), "output")
SCORES_DIR = os.path.join(OUTPUT_DIR, "scores")
FILENAME_RE = re.compile(r"^oscs_etransparente_(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})\.json$")


# ---------------------------------------------------------------------------
# Configuração declarativa de pontuação
# ---------------------------------------------------------------------------

# Campos de informações gerais que pontuam (1 pt cada, máx 15)
# Tupla (parent, key) indica subcampo de 'documentos'.
# String simples indica campo direto na OSC.
# 'redes_sociais' tem tratamento especial: qualquer subcampo preenchido = 1 pt.
GERAIS_SCORE_FIELDS: List = [
    'logo_local_path',
    'descricao_objeto_social',
    'telefone',
    'email',
    'website',
    'redes_sociais',
    'horario_funcionamento',
    'localizacao',
    'cnpj',
    ('documentos', 'cneas'),
    ('documentos', 'plano_acao'),
    ('documentos', 'estatuto'),
    ('documentos', 'ata_eleicao'),
    ('documentos', 'balanco_2024'),
    ('documentos', 'balanco_2023'),
]
GERAIS_MAX = 15

# Emblemas: não entram na nota, mas são persistidos na saída
GERAIS_BADGE_FIELDS = ['cebas', 'utilidade_publica']  # subcampos de 'documentos'

# Campos pontuáveis por tipo de termo (presença = 1 pt, ausência = 0 pt)
# municipio e uniao têm a mesma estrutura de campos (11 campos, divisor 11)
# estado: 14 campos, divisor 14
# emendas_parlamentares: 15 campos, divisor 15
TERMO_CONFIG: Dict[str, Dict] = {
    'municipio': {
        'max_fields': 11,
        'score_fields': [
            'identificacao_do_instrumento_de_parceria',
            'termo_assinado',
            'descricao_do_objeto_da_parceria',
            'data_da_assinatura',
            'data_final_da_vigencia',
            'valor_total_do_termo',
            'situacao_do_termo',
            'prestacao_de_contas_da_parceria',
            'data_prevista_para_a_sua_apresentacao_da_prestacao_de_contas',
            'resultado_da_prestacao_de_contas',
            'valor_total_da_remuneracao_da_equipe_de_trabalho',
        ],
    },
    'uniao': {
        'max_fields': 11,
        'score_fields': [
            'identificacao_do_instrumento_de_parceria',
            'termo_assinado',
            'descricao_do_objeto_da_parceria',
            'data_da_assinatura',
            'data_final_da_vigencia',
            'valor_total_do_termo',
            'situacao_do_termo',
            'prestacao_de_contas_da_parceria',
            'data_prevista_para_a_sua_apresentacao_da_prestacao_de_contas',
            'resultado_da_prestacao_de_contas',
            'valor_total_da_remuneracao_da_equipe_de_trabalho',
        ],
    },
    'estado': {
        'max_fields': 14,
        'score_fields': [
            'numero_do_contrato_ou_do_convenio',
            'termo_assinado',
            'descricao_do_objeto_da_parceria',
            'data_de_assinatura_do_termo',
            'data_final_da_vigencia',
            'valor_total_do_termo',
            'situacao_do_termo',
            'data_prevista_para_apresentacao_da_prestacao_de_contas',
            'resultado_da_prestacao_de_contas',
            'relatorio_de_execucao_fisico_financeira',
            'demonstrativo_da_execucao_da_receita_e_despesa',
            'relacao_de_pagamentos',
            'extrato_bancario_completo_da_conta_especifica',
            'relacao_de_bens_adquiridos',
        ],
    },
    'emendas_parlamentares': {
        'max_fields': 15,
        'score_fields': [
            'estado',
            'municipio',
            'tipo',
            'num',
            'num_processo',
            'termo_assinado',
            'plano_trabalho',
            'data_de_liberacao_recurso',
            'data_final',
            'nome_do_parlamentar',
            'area_tematica',
            'orgao_responsavel_pela_gestao_do_recurso',
            'valor',
            'objeto',
            'prestacao_de_contas',
        ],
    },
}


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def find_latest_output_file(output_dir: str = OUTPUT_DIR) -> Optional[str]:
    if not os.path.isdir(output_dir):
        return None
    candidates: List[Tuple[str, str]] = []
    for name in os.listdir(output_dir):
        m = FILENAME_RE.match(name)
        if m:
            candidates.append((m.group(1), os.path.join(output_dir, name)))
    if not candidates:
        files = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if os.path.isfile(os.path.join(output_dir, f))
        ]
        if not files:
            return None
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return files[0]
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    return bool(value)


def classificar(nota_final: float, max_nota: float) -> str:
    percentual = nota_final / max_nota * 100 if max_nota > 0 else 0.0
    if percentual <= 30:
        return 'Regular'
    if percentual <= 69:
        return 'Bom'
    return 'Ótimo'


# ---------------------------------------------------------------------------
# Cálculo de informações gerais
# ---------------------------------------------------------------------------

def calcular_gerais(osc: Dict[str, Any]) -> Dict[str, Any]:
    pontos = 0
    documentos = osc.get('documentos') or {}

    for field in GERAIS_SCORE_FIELDS:
        if isinstance(field, tuple):
            _, key = field
            val = documentos.get(key)
        elif field == 'redes_sociais':
            redes = osc.get('redes_sociais') or {}
            val = any(is_filled(v) for v in redes.values()) if isinstance(redes, dict) else redes
        else:
            val = osc.get(field)

        if is_filled(val):
            pontos += 1

    badges = {badge: is_filled(documentos.get(badge)) for badge in GERAIS_BADGE_FIELDS}

    return {
        'pontos': pontos,
        'max': GERAIS_MAX,
        'percentual': round(pontos / GERAIS_MAX * 100, 1),
        'badges': badges,
    }


# ---------------------------------------------------------------------------
# Cálculo de termos e emendas
# ---------------------------------------------------------------------------

def calcular_termo_individual(termo: Dict[str, Any], tipo: str) -> Dict[str, Any]:
    config = TERMO_CONFIG[tipo]
    max_fields = config['max_fields']
    pontos = sum(1 for f in config['score_fields'] if is_filled(termo.get(f)))
    return {
        'pontos': pontos,
        'max': max_fields,
        'percentual': round(pontos / max_fields * 100, 1),
    }


def calcular_bloco_termos(osc: Dict[str, Any]) -> Dict[str, Any]:
    termos_raw = osc.get('termos') or {}
    todos_percentuais: List[float] = []
    por_tipo: Dict[str, List[Dict]] = {}

    for tipo in ['municipio', 'estado', 'uniao', 'emendas_parlamentares']:
        bloco = termos_raw.get(tipo) or {}
        arr = bloco.get('termos') or [] if isinstance(bloco, dict) else (bloco if isinstance(bloco, list) else [])

        individuais = []
        for termo in arr:
            if isinstance(termo, dict):
                res = calcular_termo_individual(termo, tipo)
                individuais.append(res)
                todos_percentuais.append(res['percentual'])

        if individuais:
            por_tipo[tipo] = individuais

    tem_termos = len(todos_percentuais) > 0
    media_percentual = sum(todos_percentuais) / len(todos_percentuais) if tem_termos else 0.0
    nota_termos = round(media_percentual / 100 * 15, 2) if tem_termos else 0.0

    return {
        'tem_termos_emendas': tem_termos,
        'total_itens': len(todos_percentuais),
        'media_percentual': round(media_percentual, 1),
        'nota_termos_emendas': nota_termos,
        'por_tipo': por_tipo,
    }


# ---------------------------------------------------------------------------
# Score final por OSC
# ---------------------------------------------------------------------------

def calcular_score_osc(osc: Dict[str, Any]) -> Dict[str, Any]:
    nome = osc.get('nome') or osc.get('title') or 'sem_nome'
    url = osc.get('url', '')

    gerais = calcular_gerais(osc)
    termos = calcular_bloco_termos(osc)

    nota_gerais = gerais['pontos']  # 0–15

    if termos['tem_termos_emendas']:
        nota_termos = termos['nota_termos_emendas']  # 0–15
        nota_final = round(nota_gerais + nota_termos, 2)
        max_nota = 30
        tag = 'com_termos_emendas'
    else:
        nota_termos = 0.0
        nota_final = float(nota_gerais)
        max_nota = 15
        tag = 'sem_termos_emendas'

    return {
        'nome': nome,
        'url': url,
        'tag': tag,
        'nota_gerais': nota_gerais,
        'nota_termos_emendas': nota_termos,
        'nota_final': nota_final,
        'max_nota': max_nota,
        'classificacao': classificar(nota_final, max_nota),
        'badges': gerais['badges'],
        'gerais': {
            'pontos': gerais['pontos'],
            'max': gerais['max'],
            'percentual': gerais['percentual'],
        },
        'termos': {
            'total_itens': termos['total_itens'],
            'media_percentual': termos['media_percentual'],
            'por_tipo': termos['por_tipo'],
        },
    }


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def analyze_file(filepath: str) -> Dict[str, Any]:
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Formato inesperado: o arquivo root deve ser uma lista de OSCs")

    results = [calcular_score_osc(osc) for osc in data]

    return {
        'arquivo_analisado': os.path.basename(filepath),
        'total_oscs': len(results),
        'gerado_em': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'resultados': results,
    }


def save_summary(summary: Dict[str, Any], output_dir: str = SCORES_DIR) -> str:
    ts = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    filename = f"transparency_scores_{ts}.json"
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return path


def main():
    latest = find_latest_output_file()
    if not latest:
        print("Nenhum arquivo de output encontrado em 'output/'. Execute o extrator primeiro.")
        return

    print(f"Arquivo mais novo encontrado: {latest}")
    summary = analyze_file(latest)

    outpath = save_summary(summary)
    print(f"Relatório de pontuações salvo em: {outpath}")
    print(f"Total de OSCs analisadas: {summary['total_oscs']}")


if __name__ == '__main__':
    main()
