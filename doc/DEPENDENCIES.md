# Dependências do Projeto

Este documento lista todas as dependências necessárias para executar o pipeline de extração e geração de dashboards de ONGs.

## Dependências Python

Todas as dependências Python estão listadas no arquivo `requirements.txt`.

### Principais bibliotecas:

#### HTTP e Web Scraping
- **requests** (>=2.31.0): Para fazer requisições HTTP à API e páginas web
- **beautifulsoup4** (>=4.12.0): Para parsing e extração de dados HTML

#### Processamento de Dados
- **pandas** (>=2.0.0): Para manipulação e análise de dados estruturados

#### Manipulação de Arquivos
- **openpyxl** (>=3.1.0): Para leitura/escrita de arquivos Excel (.xlsx)

#### Visualização e Dashboards
- **plotly** (>=5.18.0): Para criação de gráficos interativos
- **streamlit** (>=1.28.0): Para criação de dashboards web interativos

#### Geração de PDFs
- **playwright** (>=1.40.0): Biblioteca Python para controlar Chromium headless — converte HTML em PDF com suporte a `footerTemplate` por página (substituiu pdfkit/wkhtmltopdf)

#### QR Code (opcional)
- **qrcode** (>=7.4.0): Geração de QR codes embutidos em base64 nos dashboards (degradação graciosa se ausente)

#### Processamento de Imagens
- **Pillow** (>=10.0.0): Para manipulação de imagens (logos)
  - Conversão RGBA → RGB com fundo branco
  - Redimensionamento para formato 1:1 (quadrado)
  - Conversão para JPG

## Ferramentas Externas

### Playwright / Chromium
Navegador headless utilizado para converter dashboards HTML em PDF.

**Instalação do pacote Python:**
```bash
pip install playwright
```

**Instalação do Chromium (obrigatória após pip install):**
```bash
playwright install chromium
```

No Docker: instalado no `docker/Dockerfile.airflow` via `RUN playwright install chromium --with-deps`

**Uso no projeto:** `dash.py` usa `playwright.sync_api.sync_playwright` para renderizar cada HTML e exportar PDF com `page.pdf()`, suportando `footerTemplate` nativo do Chromium para rodapé em todas as páginas.

## Instalação

### Local (desenvolvimento)
```bash
pip install -r requirements.txt
```

### Docker (produção)
As dependências são instaladas automaticamente via `docker-compose.yml` usando a variável `_PIP_ADDITIONAL_REQUIREMENTS`.

```bash
docker-compose up -d
```

## Verificação de Dependências

Execute o script de verificação para confirmar que todas as dependências estão instaladas:

```bash
python check_dependencies.py
```

Este script verifica:
- ✅ Todas as bibliotecas Python críticas
- ✅ Ferramentas externas (Playwright/Chromium)
- ⚠️  Dependências opcionais (apache-airflow)

## Estrutura de Arquivos

```
pipeline/
├── requirements.txt              # Dependências Python
├── docker-compose.yml            # Configuração Docker com dependências
├── docker/
│   ├── Dockerfile.airflow        # Imagem Docker com Playwright/Chromium
│   ├── Dockerfile                # Imagem base Python
│   └── entrypoint.sh             # Script de inicialização
├── check_dependencies.py         # Script de verificação
└── .dockerignore                 # Arquivos ignorados no build Docker
```

## Troubleshooting

### Erro: "No module named 'PIL'"
```bash
pip install Pillow
```

### Erro: "playwright._impl._api_types.Error: Executable doesn't exist"
O Chromium não foi instalado após o `pip install playwright`:
```bash
playwright install chromium
```

No Docker: Reconstrua a imagem para incluir o passo de instalação:
```bash
docker-compose build --no-cache
```

### Erro: ImportError ao importar bibliotecas
Verifique se o ambiente virtual está ativado e as dependências instaladas:
```bash
pip list
```

## Atualizando Dependências

Para atualizar uma dependência:

1. Edite `requirements.txt` com a nova versão
2. Atualize `docker-compose.yml` na variável `_PIP_ADDITIONAL_REQUIREMENTS`
3. Reconstrua os containers:
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Notas Importantes

- **Pillow é obrigatório**: Usado para processar logos das ONGs
- **playwright + Chromium são obrigatórios**: Necessários para gerar PDFs dos dashboards (substituíram pdfkit/wkhtmltopdf)
- **qrcode é opcional**: Se ausente, o QR code é substituído por um placeholder cinza; o restante do dashboard funciona normalmente
- **cairosvg foi removido**: Não está sendo usado no projeto
- **pdfkit foi removido**: Substituído por playwright
- Todas as versões seguem o padrão semver (>=X.Y.Z)
