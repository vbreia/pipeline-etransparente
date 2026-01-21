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
- **pdfkit** (>=1.0.0): Wrapper Python para wkhtmltopdf

#### Processamento de Imagens
- **Pillow** (>=10.0.0): Para manipulação de imagens (logos)
  - Conversão RGBA → RGB com fundo branco
  - Redimensionamento para formato 1:1 (quadrado)
  - Conversão para JPG

## Ferramentas Externas

### wkhtmltopdf
Ferramenta de linha de comando para converter HTML em PDF.

**Instalação:**
- Ubuntu/Debian: `apt-get install wkhtmltopdf`
- No Docker: Já incluído no `docker/Dockerfile.airflow`

**Versão recomendada:** 0.12.6.1-2

**Uso no projeto:** Conversão de dashboards HTML em PDF via biblioteca `pdfkit`

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
- ✅ Ferramentas externas (wkhtmltopdf)
- ⚠️  Dependências opcionais (apache-airflow)

## Estrutura de Arquivos

```
pipeline/
├── requirements.txt              # Dependências Python
├── docker-compose.yml            # Configuração Docker com dependências
├── docker/
│   ├── Dockerfile.airflow        # Imagem Docker com wkhtmltopdf
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

### Erro: "wkhtmltopdf command not found"
No Docker: Reconstrua a imagem
```bash
docker-compose build --no-cache
```

Local: Instale o wkhtmltopdf
```bash
# Ubuntu/Debian
sudo apt-get install wkhtmltopdf

# macOS
brew install wkhtmltopdf
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
- **wkhtmltopdf é obrigatório**: Necessário para gerar PDFs dos dashboards
- **cairosvg foi removido**: Não está sendo usado no projeto
- Todas as versões seguem o padrão semver (>=X.Y.Z)
