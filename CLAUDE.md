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

Orquestrado pelo **Airflow** (DAG `ong_pipeline`, mensal, **dia 3 às 11:30 UTC**) dentro de **Docker Compose**.

> **Regra do ciclo:** o mês do relatório (`--ciclo YYYY-MM`) é decidido só pela DAG e repassado
> a todos os scripts. Nenhum script calcula ciclo pela data do sistema. Ver `doc/CICLO_E_VALIDACAO.md`
> e `tests/test_contrato_ciclo.py`.

---

## Estrutura de diretórios

```
pipeline-etransparente/
├── dags/                        # DAGs do Airflow
├── scripts/
│   ├── ong_extractor.py         # Etapa 1: extração (scraping + API)
│   ├── generate_transparency_scores.py  # Etapa 2: cálculo de scores
│   ├── dash.py                  # Etapa 3: geração de dashboards
│   ├── ciclo.py                 # Fonte única do ciclo (--ciclo) e da checagem de data
│   ├── validar_ciclo.py         # 12 verificações antes de qualquer envio
│   ├── preparar_envios.py       # Monta e-mails + amostra + código (não envia)
│   └── desbloquear_envio.py     # Libera bloqueio por falso alarme
├── api/                         # API do Static Web App (status, abrir-pdf, aprovar, reportar-erro)
├── functions/                   # Azure Function etransparente-envio (envio pela fila)
├── envio/                       # comum.py canônico, sincronizar_copias.py, publicar_dashboard.sh
├── dashboard/                   # Static Web App (inclui envio.html)
├── tests/                       # pytest (rodado no GitHub Actions)
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

Gera, valida e **prepara** o envio — não envia. Retry 2x (5 min), exceto validações:

```
validar_data → extract_ong_data → generate_transparency_scores → fetch_ga4_views
→ generate_dashboards → upload_to_azure → generate_silver → detect_doc_changes
→ validar_ciclo → preparar_envios
```

O envio às OSCs ocorre fora da DAG, após conferência por amostra e confirmação de uma pessoa
autorizada (`dashboard.etransparente.org/envio`). Detalhes: `doc/CICLO_E_VALIDACAO.md` e
`doc/ENVIO_COM_APROVACAO.md`.

---

## Envio com aprovação (desde v1.7.0)

```
DAG (VM) preparar_envios → envios/{ciclo}/ no Blob → aviso "ciclo pronto"
→ /envio (Static Web App + api/) conferência de 3 PDFs + "Eu ___ confirmo"
→ fila `envios` → Function `etransparente-envio` envia 1 e-mail por mensagem
```

| Recurso Azure | Nome | Observação |
|---|---|---|
| Static Web App (Standard) | `etransparente-dashboard` | página `/envio` + API gerenciada Python 3.11 (`api/`) |
| Function App (Consumo Flexível, Brazil South) | `etransparente-envio` | `functions/`, gatilhos de fila `enviar` e `desistir` |
| Storage | `etransparentedata` / container `etransparente` | dados em `envios/{ciclo}/` (fora de `gold/`); filas `envios`, `envios-poison` |

- **Quem aprova:** lista de e-mails na configuração `APROVADORES` do SWA (Tatiana, Cinthia, Victor).
  Não usar papéis do SWA para isso (chegavam à API de forma intermitente).
- **Acesso ao dashboard:** papel `etransparente_acesso` (convite em Gerenciamento de funções).
- **Regras comuns:** `envio/comum.py` é o canônico; rodar `python3 envio/sincronizar_copias.py`
  depois de editar (gera `api/shared_code/comum.py` e `functions/comum.py`; um teste confere).
- **Publicar dashboard + API:** `./envio/publicar_dashboard.sh` (com `SWA_CLI_DEPLOYMENT_TOKEN`).
  Nunca `swa deploy` direto: ele não instala `api/requirements.txt`.
- **Publicar a Function:** `cd functions && func azure functionapp publish etransparente-envio --python`.
- **Ensaio:** `preparar_envios.py --ciclo X --destino-teste <email>`; depois o mesmo ciclo pode ser
  preparado de verdade. Ciclo com envio real nunca é preparado de novo.
- **Falso alarme de "Reportar erro":** `scripts/desbloquear_envio.py --ciclo --responsavel --motivo`.

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
| PostgreSQL 15 | postgres:15 | 127.0.0.1:5432 |
| airflow-init | custom (Dockerfile.airflow) | — |
| airflow-scheduler | custom | — |
| airflow-webserver | custom | 127.0.0.1:8080 (acesso por túnel SSH) |

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
pypdf            # merge do PDF institucional (com margem/footerTemplate) + PDF da página final (sem margem)
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

# Status dos containers (sempre Compose V2 — `docker compose`, sem hífen)
docker compose ps

# Parar tudo
docker compose down

# Testes
python -m pytest tests
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
| Ciclo do relatório | Decidido só pela DAG (`--ciclo`) | Incidente ago–out/2026: cada script calculava o mês sozinho (v1.6.0) |
| Envio às OSCs | Fora da VM, após conferência humana por amostra | Gestão exigiu certeza do que é enviado; VM pode ficar desligada (v1.7.0) |
| Quem aprova | Lista `APROVADORES` (e-mails) no SWA | Papéis personalizados do SWA chegavam à API de forma intermitente |
| Dados de envio | `envios/` fora de `gold/` | `gold/` é legível pelo token SAS do dashboard; envios têm e-mails de OSCs |
| Orquestração | Airflow | Retry nativo, UI de monitoramento, agendamento cron |
| Containerização | Docker Compose | Reprodutibilidade, sem dependências no host |
| PDF | Playwright/Chromium | Renderização fiel de CSS moderno (Chart.js, ícones Phosphor, fontes woff2), suporte a header/footer por página |
| Logos | Pillow + JPG 1:1 | Uniformidade visual nos dashboards |
| Deploy | Azure VM F2as_v6 (liga/desliga por Logic Apps no dia 3) | Custo/benefício; VM só fica ligada no processamento |
| Score | Escala 0-30 | 15 pts gerais + 0-15 pts termos/emendas; classificação Regular/Bom/Ótimo |
| Categorização docs | `block-field-<slug>` CSS | Identificação confiável pelo campo ACF de origem, não pelo nome do arquivo |
| QR code | biblioteca `qrcode` | Verificação de autenticidade no PDF final (opcional, degradação graciosa) |
| PDF final sem margem | 2 passagens Playwright + merge `pypdf` | Chromium aplica margin/footerTemplate uniformemente a todas as páginas de uma mesma `page.pdf()`; a página final (layout estático) é impressa sem margem em uma chamada separada e unida ao PDF institucional |

---

## Próximos passos / backlog

<!-- Atualizar aqui após cada sessão de trabalho -->

- [ ] APAE de Miracema: saiu da API entre jun e jul/2026 — verificar no WP Admin
- [ ] Application Insights na Function e no SWA (logs sem depender do banner de erro)
- [ ] Registrar na política interna (LGPD) o uso de IP/localização para segurança

---

## Contexto da equipe

Projeto open-source com equipe de voluntários.
Ao sugerir mudanças, considerar:
- Clareza para contribuidores com diferentes níveis de experiência
- Compatibilidade com o stack atual (não introduzir dependências sem justificativa)
- Documentação de qualquer nova decisão neste arquivo

---

*Atualizado em: 2026-10-06 | Versão do sistema: 1.7.0*