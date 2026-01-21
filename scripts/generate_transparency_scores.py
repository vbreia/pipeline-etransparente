#!/usr/bin/env python3
"""Gera pontuações de transparência a partir do arquivo mais recente em `output/`.

Comportamento:
- localiza o arquivo mais novo em `output/` cujo nome corresponde a
  `oscs_etransparente_YYYY-MM-DD-HH-MM-SS.json` (usa o sufixo timestamp para ordenar)
- carrega o JSON (lista de ONGs)
- para cada ONG calcula: campos preenchidos e total de campos (regra simples: campos vazios/""/0/[]/{} contam como não preenchidos)
- gera um JSON de saída com a pontuação (nota = soma dos booleanos de preenchimento)

O formato de saída (por ONG):
{
  "nome": "...",
  "url": "...",
  "preenchidos": 7,
  "total": 24,
  "nota": 7
}

Arquivo gerado em: `output/transparency_scores_YYYY-MM-DD-HH-MM-SS.json`
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional


OUTPUT_DIR = os.path.join(os.getcwd(), "output")
SCORES_DIR = os.path.join(OUTPUT_DIR, "scores")
FILENAME_RE = re.compile(r"^oscs_etransparente_(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})\.json$")


def find_latest_output_file(output_dir: str = OUTPUT_DIR) -> Optional[str]:
    """Procura o arquivo mais recente em output/ baseado no sufixo timestamp.

    Retorna o caminho absoluto do arquivo ou None se não encontrar nada.
    """
    if not os.path.isdir(output_dir):
        return None

    candidates: List[Tuple[str, str]] = []  # (timestamp, fullpath)

    for name in os.listdir(output_dir):
        m = FILENAME_RE.match(name)
        if m:
            ts = m.group(1)
            candidates.append((ts, os.path.join(output_dir, name)))

    if not candidates:
        # fallback: pick most recently modified file in dir
        files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        if not files:
            return None
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return files[0]

    # timestamps formatted YYYY-MM-DD-HH-MM-SS sort lexicographically
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def is_filled(value: Any) -> bool:
    """Regra simples para considerar um campo preenchido.

    - strings não vazias => True
    - int/float != 0 => True
    - bool True => True
    - lists/dicts with len>0 => True
    - None or empty string/list/dict or 0 => False
    """
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
    # For other types, try truthiness
    return bool(value)


def calcular_info_gerais(osc: Dict[str, Any]) -> Dict[str, Any]:
    """Calcula pontos, total e percentual para campos gerais (não-termos).

    Regras tomadas por falta de especificação explícita:
    - Campos considerados: descricao_objeto_social, telefone, email, website,
      horario_funcionamento, localizacao, cnpj, redes_sociais subcampos,
      documentos subcampos.
    - Campos que não pontuam devem ser ignorados (não contamos aqui campos
      fora da lista acima).
    - Cada subcampo conta como 1 ponto se preenchido conforme is_filled().
    """
    # Apenas os 8 campos que pontuam conforme especificação:
    # 1. cnpj
    # 2. documentos.estatuto
    # 3. documentos.ata_eleicao
    # 4. documentos.balanco_2020
    # 5. documentos.balanco_2021
    # 6. documentos.balanco_2022
    # 7. documentos.balanco_2023
    # 8. documentos.balanco_2024
    filled = 0
    total = 0

    # cnpj
    total += 1
    if is_filled(osc.get('cnpj')):
        filled += 1

    documentos = osc.get('documentos') or {}
    if isinstance(documentos, dict):
        for key in ['estatuto', 'ata_eleicao', 'balanco_2020', 'balanco_2021', 'balanco_2022', 'balanco_2023', 'balanco_2024']:
            total += 1
            if is_filled(documentos.get(key)):
                filled += 1

    percentual = (filled / total * 100) if total > 0 else 0.0
    return {'pontos': filled, 'total': total, 'percentual': percentual}


def calcular_termo(termo: Dict[str, Any], tipo: str) -> Tuple[float, int]:
    """Calcula pontos (e total) para um termo individual.

    Regras especiais:
    - `situacao_termo`: avalia se o termo está em situação acionável.
      Interpretação (assunção): statuses que indiquem execução/ativo => 1 ponto;
      statuses que indiquem encerramento/cancelamento => 0 pontos.
      Exemplos mapeados:
        - positivos: 'ativo', 'em execução', 'em andamento'
        - negativos: 'encerrado', 'concluido', 'cancelado'
      Se desconhecido e não vazio, conta como 1 ponto (assumimos positivo).

    - `resultado_prestacao`: interpretação (assunção): prestações aprovadas/aceitas
      contam como 1 ponto; pendentes/negativas => 0.

    - Campos vazios/None/"" não pontuam.

    Retorna (pontos, total_campos_considerados).
    """
    pontos: float = 0.0
    total: int = 0

    # Campos específicos por tipo
    campos_base = [
        'identificacao_do_instrumento_de_parceria',
        'termo_assinado',
        'termos_aditivos',
        'termo_aditivo',
        'descricao_do_objeto_da_parceria',
        'data_da_assinatura',
        'data_final_da_vigencia',
        'valor_total_do_termo',
        'situacao_do_termo',
        'prestacao_de_contas_da_parceria',
        'data_prevista_para_a_sua_apresentacao_da_prestacao_de_contas',
        'resultado_da_prestacao_de_contas',
        'valor_total_da_remuneracao_da_equipe_de_trabalho'
    ]

    campos_estado_extra = [
        'relatorio_de_execucao_fisico_financeira',
        'demonstrativo_da_execucao_da_receita_e_despesa',
        'relacao_de_pagamentos',
        'extrato_bancario_completo_da_conta_especifica',
        'relacao_de_bens_adquiridos'
    ]

    campos_avaliar = list(campos_base)
    if tipo == 'estado':
        campos_avaliar += campos_estado_extra

    for campo in campos_avaliar:
        # some sources may use slight naming variations; try to fetch robustly
        valor = termo.get(campo)
        # if campo not present, try alternative keys without plurals/underscores
        if valor is None:
            # try small set of alternatives
            alt = campo.replace('termos_aditivos', 'termo_aditivo')
            if alt != campo:
                valor = termo.get(alt)

        # special handling
        if campo == 'situacao_do_termo':
            total += 1
            if not is_filled(valor):
                continue
            v = str(valor).strip().lower()
            # positivo if contains 'vigent','em aprov','prorrog'
            if 'vigent' in v or 'em aprov' in v or 'prorrog' in v or 'vigente' in v:
                pontos += 1
            else:
                # consider other explicit negatives
                negativos = ['encerr', 'conclu', 'cancel', 'inativ']
                if any(x in v for x in negativos):
                    pontos += 0
                else:
                    pontos += 1

        elif campo == 'resultado_da_prestacao_de_contas':
            total += 1
            if not is_filled(valor):
                continue
            v = str(valor).strip().lower()
            if 'aprov' in v or 'conforme' in v or 'aceit' in v:
                pontos += 1
            elif 'parcial' in v:
                pontos += 0.5
            else:
                # outros => 0
                pontos += 0

        else:
            # campos gerais: pontuam 1 se preenchidos
            if valor is not None:
                total += 1
                if is_filled(valor):
                    pontos += 1

    return pontos, total


def calcular_termos_tipo(termos_array: List[Dict[str, Any]], tipo: str) -> Dict[str, Any]:
    """Calcula a média aritmética de pontuação dos termos de um tipo.

    Retorna dict com: {'media_percentual': float, 'n_termos': int}
    Se não houver termos, media_percentual = 0.
    """
    if not termos_array or not isinstance(termos_array, list):
        return {'media_percentual': 0.0, 'n_termos': 0}

    percentuais = []
    for termo in termos_array:
        pontos, total = calcular_termo(termo, tipo)
        if total > 0:
            percentuais.append((pontos / total) * 100)
        else:
            percentuais.append(0.0)

    media = sum(percentuais) / len(percentuais) if percentuais else 0.0
    return {'media_percentual': media, 'n_termos': len(termos_array)}


def calcular_score_geral(componentes: Dict[str, float], termos_info: Dict[str, int]) -> Dict[str, Any]:
    """Só inclui na média os componentes que EXISTEM.

    - sempre inclui 'gerais'
    - inclui cada tipo de termo (municipio/estado/uniao/emendas_parlamentares)
      somente se termos_info[tipo] > 0
    Retorna {'percentual': float, 'classificacao': str}.
    """
    valores: List[float] = []

    # sempre incluir gerais se presente
    if 'gerais' in componentes and componentes.get('gerais') is not None:
        valores.append(componentes['gerais'])

    for tipo in ['municipio', 'estado', 'uniao', 'emendas_parlamentares']:
        if termos_info.get(tipo, 0) > 0:
            v = componentes.get(tipo)
            if v is not None:
                valores.append(v)

    percentual = sum(valores) / len(valores) if valores else 0.0

    if percentual <= 30:
        classificacao = 'Regular'
    elif percentual <= 69:
        classificacao = 'Bom'
    else:
        classificacao = 'Ótimo'

    return {'percentual': percentual, 'classificacao': classificacao}


def analyze_file(filepath: str) -> Dict[str, Any]:
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Formato inesperado: o arquivo root deve ser uma lista de ONGs")
    results = []
    for ong in data:
        nome = ong.get('nome') or ong.get('title') or 'sem_nome'
        url = ong.get('url', '')

        # 1) Info gerais
        info_gerais = calcular_info_gerais(ong)

        # 2) Termos por tipo (municipio, estado, uniao, emendas_parlamentares)
        termos = ong.get('termos') or {}
        termos_scores = {}
        componentes = {}

        for tipo in ['municipio', 'estado', 'uniao', 'emendas_parlamentares']:
            arr = []
            if isinstance(termos.get(tipo), dict) and 'termos' in termos.get(tipo):
                arr = termos.get(tipo).get('termos') or []
            elif isinstance(termos.get(tipo), list):
                arr = termos.get(tipo)

            termos_scores[tipo] = calcular_termos_tipo(arr, tipo)
            componentes[tipo] = termos_scores[tipo]['media_percentual']

        # incluir gerais como componente
        componentes['gerais'] = info_gerais['percentual']

        # preparar termos_info (número de termos por tipo)
        termos_info = {
            'municipio': termos_scores['municipio']['n_termos'],
            'estado': termos_scores['estado']['n_termos'],
            'uniao': termos_scores['uniao']['n_termos'],
            'emendas_parlamentares': termos_scores['emendas_parlamentares']['n_termos']
        }

        # 3) Agregar score geral (só inclui tipos que existem)
        geral = calcular_score_geral(componentes, termos_info)

        result = {
            'nome': nome,
            'url': url,
            'gerais': info_gerais,
            'termos': termos_scores,
            'componentes': componentes,
            'nota_percentual': geral['percentual'],
            'classificacao': geral['classificacao']
        }
        results.append(result)

    summary = {
        'arquivo_analisado': os.path.basename(filepath),
        'total_ongs': len(results),
        'gerado_em': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'resultados': results
    }
    return summary


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
    print(f"Total de ONGs analisadas: {summary['total_ongs']}")


if __name__ == '__main__':
    main()
