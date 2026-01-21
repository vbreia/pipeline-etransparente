## Pipeline de Transparência de ONGs — Arquitetura e Scripts

Este documento explica a arquitetura completa do pipeline de transparência de ONGs executado via **Apache Airflow**. O sistema é composto por 3 scripts principais em `/scripts` que são orquestrados pela DAG `ong_pipeline`.

---

## Visão Geral da Arquitetura

O pipeline implementa um fluxo ETL (Extract, Transform, Load) completo para processar dados de Organizações da Sociedade Civil (ONGs) do site `etransparente.org`:

```
┌─────────────────────────────────────────────────────────────┐
│                    Apache Airflow DAG                        │
│                      (ong_pipeline)                          │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────────┐   ┌──────────────┐
│   Task 1     │    │     Task 2       │   │   Task 3     │
│ Extract Data │───▶│ Generate Scores  │──▶│   Generate   │
│              │    │                  │   │  Dashboards  │
└──────────────┘    └──────────────────┘   └──────────────┘
       │                     │                     │
       ▼                     ▼                     ▼
  ong_extractor.py   generate_transparency   dash.py
                          _scores.py
       │                     │                     │
       ▼                     ▼                     ▼
  oscs_*.json      transparency_scores    HTML/PDF
   (output/)         _*.json              Dashboards
                    (output/scores/)     (output/dashboards/)
```

### Fluxo de Execução

1. **Extração** → `ong_extractor.py` coleta dados via scraping + API
2. **Análise** → `generate_transparency_scores.py` calcula pontuações
3. **Visualização** → `dash.py` gera dashboards individuais

**Agendamento**: Executa diariamente às 2 AM (schedule: `0 2 * * *`)

---

## Scripts do Pipeline

### 📍 Localização dos Scripts

Todos os scripts estão em `/scripts`:
- [`scripts/ong_extractor.py`](../scripts/ong_extractor.py) - Extração de dados
- [`scripts/generate_transparency_scores.py`](../scripts/generate_transparency_scores.py) - Cálculo de scores
- [`scripts/dash.py`](../scripts/dash.py) - Geração de dashboards

---

## 1. ong_extractor.py — Extração de Dados

**Task Airflow**: `extract_ong_data`  
**Tempo médio**: 2-3 minutos  
**Output**: `output/oscs_etransparente_YYYY-MM-DD-HH-MM-SS.json`

### Funcionalidade

Script ETL que combina duas fontes de dados sobre ONGs:
- **Web Scraping**: extrai contatos, documentos, redes sociais, descrição
- **API REST**: consulta termos/contratos (municipais, estaduais, federais, emendas)

### Componentes Principais

#### Dataclasses (Modelos de Dados)
- `ONGData` — estrutura principal com todos os dados da ONG
- `RedesSociais` — Instagram, LinkedIn, YouTube, outras
- `Documentos` — CNEAS, CEBAS, estatuto, balanços, etc.
- `TermosInfo` — contratos/termos por categoria
- `EstatisticasTermos` — resumo de termos (apenas em memória)

#### Classes de Extração
- `WebScraper` — faz requests + parsing HTML (BeautifulSoup)
- `APIExtractor` — consulta REST API e organiza termos por tipo
- `ONGExtractor` — orquestra o processo completo e salva JSON final

### Formato de Saída (JSON)

```json
{
  "nome": "Nome da ONG",
  "url": "https://etransparente.org/ong/...",
  "descricao_objeto_social": "Descrição...",
  "telefone": "(11) 1234-5678",
  "email": "contato@ong.org",
  "website": "https://ong.org",
  "redes_sociais": {
    "instagram": "@ong",
    "linkedin": "linkedin.com/company/ong",
    "youtube": "youtube.com/@ong",
    "outras": ""
  },
  "horario_funcionamento": "Seg-Sex: 9h-17h",
  "localizacao": "Rua X, São Paulo-SP",
  "cnpj": "12.345.678/0001-90",
  "documentos": {
    "estatuto": "https://...",
    "balanco_2021": "https://...",
    ...
  },
  "termos": {
    "municipio": {"quantidade": 5, "termos": [...]},
    "estado": {"quantidade": 2, "termos": [...]},
    "uniao": {"quantidade": 1, "termos": [...]},
    "emendas": {"quantidade": 0, "termos": []}
  }
}
```

### Execução Manual (Debug)

```bash
# Via Airflow (modo normal)
docker compose exec airflow-webserver python scripts/ong_extractor.py

# Logs gerados em:
logs/ong_extractor_YYYY-MM-DD-HH-MM-SS.log
```

---

## 2. generate_transparency_scores.py — Cálculo de Pontuações

**Task Airflow**: `generate_transparency_scores`  
**Tempo médio**: < 10 segundos  
**Input**: Último `output/oscs_etransparente_*.json`  
**Output**: `output/scores/transparency_scores_YYYY-MM-DD-HH-MM-SS.json`

### Funcionalidade

Calcula pontuações de transparência para cada ONG baseado no **preenchimento de campos**:
- Conta campos preenchidos vs total de campos
- Considera vazio: `""`, `0`, `[]`, `{}`, `null`
- Gera nota simples: soma de campos preenchidos

### Algoritmo

```python
# Para cada ONG:
1. Itera sobre todos os campos da estrutura ONGData
2. Verifica se campo está preenchido (não vazio)
3. Conta: preenchidos / total
4. Nota = número de campos preenchidos
```

### Formato de Saída (JSON)

```json
{
  "nome": "Nome da ONG",
  "url": "https://etransparente.org/ong/...",
  "preenchidos": 18,
  "total": 24,
  "nota": 18
}
```

### Critérios de Avaliação

- **Alta transparência** (18-24): Maioria dos campos preenchidos
- **Média transparência** (12-17): Campos básicos preenchidos
- **Baixa transparência** (0-11): Poucos dados disponíveis

### Execução Manual

```bash
docker compose exec airflow-webserver python scripts/generate_transparency_scores.py
```

---

## 3. dash.py — Geração de Dashboards

**Task Airflow**: `generate_dashboards`  
**Tempo médio**: 30-60 segundos  
**Input**: Último `output/oscs_etransparente_*.json`  
**Output**: 
- HTML: `output/dashboards/<timestamp>/html/*.html`
- PDF: `output/dashboards/<timestamp>/pdf/*.pdf`

### Funcionalidade

Gera **um dashboard individual** para cada ONG contendo:
- Informações principais (contato, localização, CNPJ)
- Documentos disponíveis com links
- Redes sociais ativas
- Termos/contratos por categoria
- Indicadores visuais de preenchimento

### Componentes do Dashboard

#### 1. Header
- Nome da ONG
- Link para página no etransparente.org
- Data de geração

#### 2. Informações Principais
- Telefone, email, website
- Horário de funcionamento
- Localização, CNPJ
- Descrição do objeto social

#### 3. Documentos
- Lista visual de documentos disponíveis
- Links diretos para download
- Categorias: Estatuto, Balanços, CEBAS, CNEAS, etc.

#### 4. Redes Sociais
- Ícones com links ativos
- Instagram, LinkedIn, YouTube

#### 5. Termos e Contratos
- Tabela por categoria (Municipal, Estadual, Federal, Emendas)
- Quantidade total por tipo
- Expandível para ver detalhes

### Tecnologias

- **HTML/CSS**: Templates responsivos
- **wkhtmltopdf**: Conversão HTML → PDF (via pdfkit)
- **Bootstrap** (embutido): Styling dos dashboards

### Estrutura de Saída

```
output/dashboards/20260121234015/
├── html/
│   ├── ong-nome-1.html
│   ├── ong-nome-2.html
│   └── ...
└── pdf/
    ├── ong-nome-1.pdf
    ├── ong-nome-2.pdf
    └── ...
```

### Execução Manual

```bash
docker compose exec airflow-webserver python scripts/dash.py
```

---

## Execução via Airflow

### Acionar Pipeline Completo

```bash
# Usando script de gerenciamento
./docker/manage-pipeline.sh trigger

# Ou via Airflow CLI
docker compose exec airflow-webserver airflow dags trigger ong_pipeline
```

### Monitorar Execução

```bash
# Status da DAG
./docker/manage-pipeline.sh dag-status

# Logs de container
docker compose logs -f airflow-scheduler

# WebUI
http://localhost:8080
Username: admin
Password: admin
```

---

## Estrutura de Diretórios

```
pipeline/
├── dags/
│   └── ong_pipeline.py          # DAG do Airflow
├── scripts/                      # Scripts Python
│   ├── ong_extractor.py         # Task 1: Extração
│   ├── generate_transparency_scores.py  # Task 2: Scores
│   └── dash.py                  # Task 3: Dashboards
├── output/                       # Outputs gerados
│   ├── oscs_*.json              # Dados extraídos
│   ├── scores/
│   │   └── transparency_scores_*.json
│   └── dashboards/
│       └── <timestamp>/
│           ├── html/
│           └── pdf/
└── logs/                         # Logs de execução
    ├── ong_extractor_*.log
    └── dag_id=ong_pipeline/
```

---

## Desenvolvimento e Debug

### Testar Script Isolado

```bash
# Entrar no container
docker compose exec airflow-webserver bash

# Executar script individual
cd /home/airflow
python scripts/ong_extractor.py
python scripts/generate_transparency_scores.py
python scripts/dash.py
```

### Verificar Logs

```bash
# Logs do extractor
tail -f logs/ong_extractor_*.log

# Logs da DAG
./docker/manage-pipeline.sh logs airflow-scheduler
```

### Limpeza de Outputs Antigos

```bash
# Remover arquivos com mais de 30 dias
find output/ -name "*.json" -mtime +30 -delete
find output/dashboards/ -type d -mtime +30 -exec rm -rf {} +
```

---

## Próximos Passos

### Melhorias Sugeridas

1. **Caching**: Implementar cache Redis para dados da API
2. **Paralelização**: Usar Airflow TaskGroups para processar ONGs em paralelo
3. **Notificações**: Email/Slack quando pipeline falhar ou completar
4. **Validação**: Schema validation dos JSONs gerados (jsonschema)
5. **Testes**: Unit tests para cada script (`pytest`)
6. **Métricas**: Enviar métricas para Grafana/Prometheus

### Documentação Relacionada

- [README.md](../README.md) — Visão geral do projeto
- [TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md) — Guia técnico completo
- [AIRFLOW_SETUP.md](AIRFLOW_SETUP.md) — Configuração do Airflow
- [QUICK_START.md](QUICK_START.md) — Início rápido

---

## Suporte

Problemas? Abra uma issue no GitHub ou consulte os logs de execução para diagnóstico.

**Pipeline desenvolvido para etransparente.org**

---
