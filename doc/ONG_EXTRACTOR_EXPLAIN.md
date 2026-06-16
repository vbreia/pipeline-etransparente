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

Comportamentos importantes:
- **Categorização de documentos**: usa `categorizar_documentos_por_bloco(soup)` — lê a classe CSS `block-field-<slug>` do bloco HTML (campo ACF) em vez de adivinhar pela URL do arquivo
- **Horário de funcionamento**: busca `timing-today` e `open-hours` no HTML
- **Termos fantasma**: entradas de termos onde só `situacao_do_termo` está preenchido são descartadas antes de salvar

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

Calcula pontuações de transparência para cada ONG com metodologia de rubrica fixa em duas dimensões:

- **Informações gerais** (0–15 pts): 15 campos pontuáveis, 1 pt cada
- **Termos/emendas** (0–15 pts): média percentual de preenchimento dos campos de cada termo × 15

Campos gerais pontuáveis: `logo_url`, `descricao_objeto_social`, `telefone`, `email`, `website`, `redes_sociais`, `horario_funcionamento`, `localizacao`, `cnpj`, `documentos.cneas`, `documentos.plano_acao`, `documentos.estatuto`, `documentos.ata_eleicao`, `documentos.balanco_2024`, `documentos.balanco_2023`.

Badges (aparecem no dashboard mas não pontuam): `cebas`, `utilidade_publica`.

Termos fantasma (entradas onde só `situacao_do_termo` está preenchido) são ignorados no cálculo.

### Algoritmo

```
nota_gerais  = soma dos 15 campos gerais preenchidos   (0–15)
nota_termos  = média_percentual_termos / 100 × 15      (0–15, só se houver termos)

Com termos/emendas:  nota_final = nota_gerais + nota_termos  → max_nota = 30
Sem termos/emendas:  nota_final = nota_gerais                → max_nota = 15

Classificação (percentual = nota_final / max_nota × 100):
  Regular : ≤ 30%
  Bom     : ≤ 69%
  Ótimo   : > 69%
```

### Formato de Saída (JSON)

```json
{
  "nome": "Nome da ONG",
  "url": "https://etransparente.org/oscs/...",
  "tag": "com_termos_emendas",
  "nota_gerais": 12,
  "nota_termos_emendas": 9.5,
  "nota_final": 21.5,
  "max_nota": 30,
  "classificacao": "Bom",
  "badges": { "cebas": true, "utilidade_publica": false },
  "gerais": { "pontos": 12, "max": 15, "percentual": 80.0 },
  "termos": { "total_itens": 4, "media_percentual": 63.3, "por_tipo": {} }
}
```

### Critérios de Avaliação

- **Ótimo** (> 69% da nota máxima): organização com alta transparência
- **Bom** (30–69%): campos básicos preenchidos, alguns dados ausentes
- **Regular** (≤ 30%): poucos dados disponíveis ou sem termos

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

Gera **um dashboard multi-página individual** para cada ONG. O dashboard é gerado primeiro como HTML e depois convertido para PDF via Playwright/Chromium.

### Estrutura do Dashboard (2-3 páginas)

#### Página 1 — Relatório principal
- **Card de identidade**: logo, nome, classificação, nota (ex.: 21/30), status (com/sem termos), badges (CEBAS, Utilidade Pública Federal)
- **Sobre a organização**: descrição do objeto social
- **Gráfico de visualizações**: Chart.js com dados diários do mês (Google Analytics)
- **Informações de contato**: telefone, e-mail, website, localização, CNPJ
- **Contratos e parcerias**: gráfico doughnut por esfera (município/estado/união/emendas)
- **Redes sociais**: ícones Phosphor com links
- **Documentos disponíveis**: grid de documentos com links
- **Alerta ou parabéns**: lista de dados pendentes ou confirmação de completude

#### Página final — Institucional
- **Seção hero**: gradiente escuro com título e subtítulo
- **Três colunas**: Sobre o etransparente.org / Emendas parlamentares / Finalidade do relatório
- **Quem utiliza**: ícones representando público-alvo
- **Autenticidade e validação**: hash SHA-256, QR code, data/hora de emissão
- **Rodapé institucional**: logo IDC, data de emissão, slogan

O rodapé com hash + QR code mini é repetido em **todas as páginas** via `footerTemplate` nativo do Playwright.

### Tecnologias

- **HTML/CSS**: layout com tabelas e CSS print-safe (`break-inside:avoid`)
- **Chart.js** (CDN): gráfico de linha (visualizações) e doughnut (contratos)
- **Phosphor Icons** (CDN): ícones consistentes
- **Playwright/Chromium**: conversão HTML → PDF com suporte a header/footer por página
- **qrcode** (Python, opcional): QR code em base64 inline no HTML
- **hashlib.sha256**: hash de autenticidade baseado em nome + data + nota + classificação
- **Fonte Montserrat** (woff2 local): tipografia consistente offline

### Saídas adicionais

Além dos arquivos HTML/PDF, o script salva um arquivo de verificações:
```
output/verificacoes_YYYY-MM.json   # hash + metadados de autenticidade de cada relatório
```

### Estrutura de Saída

```
output/dashboards/<timestamp>/
├── html/
│   ├── Relatório-etransparente-<mes>-de-<ano>-<slug>.html
│   └── ...
└── pdf/
    ├── Relatório-etransparente-<mes>-de-<ano>-<slug>.pdf
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
