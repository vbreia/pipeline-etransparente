# CLAUDE.md — pipeline-etransparente

Arquivo de contexto para o Claude Code. Lido automaticamente a cada sessão.

---

## O que é este projeto

Pipeline automatizada de transparência para ONGs cadastradas no **etransparente.org**.
Extrai dados públicos (scraping + API WordPress), calcula scores de transparência e gera dashboards HTML/PDF por ONG.

Repositório: `github.com/vbreia/pipeline-etransparente`
Mantido por Victor Breia com equipe de voluntários.

---

## Arquitetura em uma linha

```
etransparente.org → ong_extractor.py → generate_transparency_scores.py → dash.py → output/
```

Orquestrado pelo **Airflow** (DAG `ong_pipeline`, diário às 02:00 UTC) dentro de **Docker Compose**.

---

## Estrutura de diretórios

```
pipeline-etransparente/
├── dags/                        # DAGs do Airflow
├── scripts/
│   ├── ong_extractor.py         # Etapa 1: extração (scraping + API)
│   ├── generate_transparency_scores.py  # Etapa 2: cálculo de scores
│   └── dash.py                  # Etapa 3: geração de dashboards
├── docker/
│   ├── Dockerfile.airflow       # Imagem customizada (inclui Playwright/Chromium)
│   ├── quick-start.sh           # Setup em 1 comando
│   └── setup-azure-vm.sh        # Setup para Azure VM
├── output/
│   ├── oscs_etransparente_*.json        # Dados brutos extraídos
│   ├── scores/transparency_scores_*.json # Scores calculados
│   └── dashboards/*/
│       ├── html/                # ~52 HTMLs por execução
│       └── pdf/                 # ~52 PDFs por execução
├── assets/
│   └── img/logos-ongs/          # Logos das ONGs (JPG 1:1 fundo branco)
├── doc/                         # Documentação técnica detalhada
└── README.md                    # Documentação principal
```

---

## DAG: ong_pipeline

Três tarefas sequenciais com retry (2x, intervalo 5min):

```
extract_ong_data → generate_transparency_scores → generate_dashboards
```

| Tarefa | Script | Duração típica |
|--------|--------|----------------|
| Extração | `ong_extractor.py` | ~2 min |
| Scoring | `generate_transparency_scores.py` | < 1 seg |
| Dashboards | `dash.py` | < 1 seg |

---

## Classes principais

### `ong_extractor.py`
- `ONGExtractor` — orquestra todo o processo, gerencia stats e logging
- `WebScraper` — scraping HTML (contato, documentos, redes sociais, logo)
  - `categorizar_documentos_por_bloco(soup)` — categoriza documentos lendo a classe CSS `block-field-<slug>` do bloco HTML que os contém (substitui abordagem por nome de arquivo)
  - Seletor de horário busca `timing-today` e `open-hours`
- `APIExtractor` — API REST WordPress (`/wp-json/wp/v2/job_listing`), campos ACF

### Dataclasses
- `ONGData` — estrutura principal por ONG
- `RedesSociais` — instagram, linkedin, youtube, outras
- `Documentos` — cneas, cebas, estatuto, balanços por ano
- `TermosInfo` — contratos com município, estado, união, emendas
- `EstatisticasTermos` — métricas agregadas de contratos

---

## Configurações críticas

```python
# Endpoint da API
endpoint_base = "https://etransparente.org/wp-json/wp/v2/job_listing"

# Rate limiting
pausa_entre_requisicoes = 0.5  # segundos

# Logos
output_logo = "assets/img/logos-ongs/<nome_normalizado>.jpg"
# Formato: JPG quadrado 1:1, fundo branco, compressão 90%
```

---

## Infraestrutura Docker

4 serviços no Docker Compose:

| Serviço | Imagem | Porta |
|---------|--------|-------|
| PostgreSQL 15 | postgres:15 | 5432 |
| airflow-init | custom (Dockerfile.airflow) | — |
| airflow-scheduler | custom | — |
| airflow-webserver | custom | 8080 |

**Imagem customizada inclui:** Playwright/Chromium, fontes Montserrat (woff2), fontes DejaVu/Liberation.

Volumes mapeados:
```yaml
./dags     → /home/airflow/dags
./scripts  → /home/airflow/scripts
./output   → /home/airflow/output
./logs     → /home/airflow/logs
```

---

## Convenções de código

- Orientação a objetos: toda lógica encapsulada em classes
- Dataclasses para estruturas de dados tipadas
- Logging com níveis INFO/WARNING/ERROR em arquivo `.log`
- Tratamento de exceções em todas as operações de I/O
- Pausas entre requisições para não sobrecarregar o servidor
- Nomes de arquivo com timestamp: `nome_YYYY-MM-DD-HH-MM-SS.ext`

---

## Dependências Python

```
beautifulsoup4   # scraping HTML
requests         # requisições HTTP
pillow           # processamento de logos
playwright       # geração de PDFs via Chromium (substituiu pdfkit/wkhtmltopdf)
qrcode           # geração de QR codes nas páginas finais (opcional)
pandas           # manipulação de dados
plotly           # gráficos nos dashboards
openpyxl         # exportação Excel
streamlit        # dashboards web (exploratório)
```

Instaladas via `_PIP_ADDITIONAL_REQUIREMENTS` no Docker Compose.
Após instalação do pacote playwright, é necessário instalar os browsers: `playwright install chromium`.

---

## Comandos úteis

```bash
# Iniciar pipeline
./docker/quick-start.sh

# Trigger manual da DAG
docker exec airflow-webserver airflow dags trigger ong_pipeline

# Ver logs do scheduler
docker logs airflow-scheduler --tail 50

# Verificar instalação do Playwright/Chromium
docker exec airflow-scheduler python -c "from playwright.sync_api import sync_playwright; print('OK')"

# Status dos containers
docker-compose ps

# Parar tudo
docker-compose down
```

---

## Histórico de execuções

| Data | ONGs | HTMLs | PDFs | Tempo total |
|------|------|-------|------|-------------|
| 2025-12-11 | 52 | 52 | 52 | ~3 min |

---

## Decisões arquiteturais

| Decisão | Escolha | Motivo |
|---------|---------|--------|
| Orquestração | Airflow | Retry nativo, UI de monitoramento, agendamento cron |
| Containerização | Docker Compose | Reprodutibilidade, sem dependências no host |
| PDF | Playwright/Chromium | Renderização fiel de CSS moderno (Chart.js, ícones Phosphor, fontes woff2), suporte a header/footer por página |
| Logos | Pillow + JPG 1:1 | Uniformidade visual nos dashboards |
| Deploy | Azure VM B2s | Custo/benefício, Ubuntu 22.04 estável |
| Score | Escala 0-30 | 15 pts gerais + 0-15 pts termos/emendas; classificação Regular/Bom/Ótimo |
| Categorização docs | `block-field-<slug>` CSS | Identificação confiável pelo campo ACF de origem, não pelo nome do arquivo |
| QR code | biblioteca `qrcode` | Verificação de autenticidade no PDF final (opcional, degradação graciosa) |

---

## Próximos passos / backlog

<!-- Atualizar aqui após cada sessão de trabalho -->

- [ ] ...

---

## Contexto da equipe

Projeto open-source com equipe de voluntários.
Ao sugerir mudanças, considerar:
- Clareza para contribuidores com diferentes níveis de experiência
- Compatibilidade com o stack atual (não introduzir dependências sem justificativa)
- Documentação de qualquer nova decisão neste arquivo

---

*Atualizado em: 2026-06-16 | Versão: 1.1*