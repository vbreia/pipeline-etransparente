# 🏢 Pipeline de Transparência - etransparente.org

Pipeline automatizada com Docker + Airflow para extração, análise e geração de dashboards de transparência de ONGs do site **etransparente.org**.

## � Documentação

Documentação completa disponível em `/doc`:

- **[Quick Start](doc/QUICK_START.md)** - Guia de início rápido
- **[Airflow Setup](doc/AIRFLOW_SETUP.md)** - Configuração detalhada do Airflow
- **[Guia Técnico](doc/TECHNICAL_GUIDE.md)** - Arquitetura e detalhes técnicos
- **[Dependências](doc/DEPENDENCIES.md)** - Lista completa de dependências
- **[Estrutura Docker](doc/DOCKER_STRUCTURE.md)** - Organização dos arquivos Docker
- **[ONG Extractor](doc/ONG_EXTRACTOR_EXPLAIN.md)** - Explicação do extrator de dados
- **[API GA4 para Azure](doc/API_GA4_TO_AZURE.md)** - Integração Google Analytics 4

## �🚀 Quick Start (1 comando)

```bash
./docke./docker/quick-start.sh
```

Acesse http://localhost:8080 (admin/admin) e execute a DAG `ong_pipeline`!

## 📋 Pré-requisitos

### **Sistema Operacional**
- Linux (Ubuntu, Debian, CentOS, etc.)
- macOS
- Windows com WSL2

### **Software Necessário**

1. **Docker** (versão 20.10+)
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

2. **Docker Compose** (versão 2.0+)
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install docker-compose-plugin
```

3. **Git**
```bash
# Ubuntu/Debian
sudo apt-get install git
```

### **Recursos Mínimos Recomendados**
- **CPU**: 2 cores
- **RAM**: 4 GB (recomendado 8 GB)
- **Disco**: 10 GB livres
- **Rede**: Conexão estável com internet

### **Setup em VM Azure (Recomendado) ⭐**

**Configuração testada e otimizada:**
- **Tamanho**: Standard B2s ou superior (8 GB RAM) ✅
- **OS**: Ubuntu 22.04 LTS
- **Disco**: 30 GB Premium SSD
- **Região**: Escolha mais próxima para melhor performance

**Setup Automático (1 comando):**

```bash
# Conectar via SSH
ssh azureuser@<seu-ip-publico>

# Executar setup completo
curl -fsSL https://raw.githubusercontent.com/vbreia/pipeline-etransparente/main/docke./docker/setup-azure-vm.sh | bash
```

**Ou Setup Manual:**

```bash
# 1. Conectar via SSH
ssh azureuser@<seu-ip-publico>

# 2. Clonar repositório
git clone https://github.com/vbreia/pipeline-etransparente.git
cd pipeline-etransparente

# 3. Executar setup Azure
chmod +x docke./docker/setup-azure-vm.sh
./docke./docker/setup-azure-vm.sh

# 4. Aplicar permissões Docker
newgrp docker

# 5. Iniciar pipeline
./docke./docker/quick-start.sh
```

**O script `setup-azure-vm.sh` configura automaticamente:**
- ✅ Atualização do sistema
- ✅ Instalação do Docker e Docker Compose
- ✅ Permissões corretas para o usuário
- ✅ Criação de swap (se RAM < 4GB)
- ✅ Configuração de firewall UFW
- ✅ Clone do repositório

**Configurar NSG (Network Security Group):**

No Portal Azure:
1. Acesse sua VM → **Networking** → **Add inbound port rule**
2. Configure:
   - **Port**: 8080
   - **Protocol**: TCP
   - **Source**: Seu IP público (mais seguro) ou Any
   - **Action**: Allow
   - **Name**: Airflow-WebUI

**Descobrir seu IP público da VM:**
```bash
curl ifconfig.me
```

**Acessar remotamente:**
```
http://<ip-publico-da-vm>:8080
Username: admin
Password: admin
```

**Monitoramento de recursos:**
```bash
# Ver uso de RAM
free -h

# Ver uso de disco
df -h

# Ver containers rodando
docker stats
```

## 🎯 Funcionalidades

### 📊 **Dados Extraídos**

**🌐 Informações Web (Scraping)**
- **Contato**: Telefone, Email, Website
- **Identificação**: CNPJ, Localização, Descrição do objeto social
- **Redes Sociais**: Instagram, LinkedIn, YouTube (separados automaticamente)
- **Documentos**: CNEAS, CEBAS, Estatuto, Balanços contábeis (categorizados por ano)
- **🎨 Logos**: Download automático, conversão para JPG quadrado 1:1 com fundo branco

**📋 Termos e Contratos (API)**
- **Termos com Município**: Contratos e colaborações municipais
- **Termos com Estado**: Parcerias estaduais
- **Termos com União**: Convênios federais
- **Emendas Parlamentares**: Recursos de emendas parlamentares

### 🖼️ **Processamento de Logos**

- **Detecção Automática**: Localiza logo na página HTML
- **Download Inteligente**: Suporta múltiplos formatos (PNG, JPG, WebP)
- **Processamento com Pillow**:
  - Conversão de transparência para fundo branco
  - Redimensionamento para formato quadrado 1:1 (sem distorção)
  - Centralização automática da imagem
  - Compressão JPG de alta qualidade (90%)
- **Armazenamento**: `assets/img/logos-ongs/<nome_normalizado>.jpg`
- **Integração**: Logos aparecem automaticamente nos dashboards HTML/PDF

### 🔧 **Características Técnicas**

- **Orientação a Objetos**: Código modular e reutilizável
- **Logging Completo**: Registros detalhados de execução
- **Tratamento de Erros**: Robustez na extração de dados
- **Dataclasses**: Estruturas de dados tipadas e organizadas
- **Proteção contra Sobrecarga**: Pausas entre requisições
- **Estatísticas Integradas**: Relatórios de completude automáticos
- **Processamento de Imagens**: Pillow para manipulação avançada de logos

## 📦 Dependências

```bash
pip install beautifulsoup4 requests pillow playwright qrcode
playwright install chromium
```

**Bibliotecas:**
- `beautifulsoup4`: Parsing HTML para scraping
- `requests`: Requisições HTTP
- `pillow`: Processamento de imagens (logos)
- `playwright`: Conversão HTML → PDF via Chromium headless (substitui pdfkit/wkhtmltopdf)
- `qrcode`: Geração de QR codes para verificação de autenticidade (opcional)

## 🚀 Como Usar

### **Execução Básica**

```bash
python3 ong_extractor.py
```

### **Personalização**

```python
from ong_extractor import ONGExtractor

# Criar instância
extrator = ONGExtractor()

# Extrair dados (padrão: 10 ONGs para teste)
dados = extrator.extrair_todas_ongs(max_ongs=10)

# Processar todas as ONGs disponíveis
# dados = extrator.extrair_todas_ongs()

# Salvar dados
extrator.salvar_dados(dados, "meus_dados.json")

# Gerar relatório
extrator.gerar_relatorio_estatisticas()
```

## 📁 Arquivos Gerados

### **`dados_pre_tratados.json`**
Arquivo principal com todos os dados extraídos em formato JSON estruturado.

### **`ong_extractor.log`**
Log detalhado da execução com timestamps e níveis de log.

## 📊 Estrutura dos Dados

```json
{
  "nome": "Nome da ONG",
  "url": "URL da página",
  "logo_url": "https://example.com/logo.png",
  "logo_local_path": "/home/airflow/assets/img/logos-ongs/Nome_da_ONG.jpg",
  "descricao_objeto_social": "Descrição das atividades",
  "telefone": "Telefone de contato",
  "email": "Email de contato",
  "website": "Site oficial",
  "redes_sociais": {
    "instagram": "URL do Instagram",
    "linkedin": "URL do LinkedIn", 
    "youtube": "URL do YouTube",
    "outras": "Outras redes sociais"
  },
  "localizacao": "Endereço físico",
  "cnpj": "CNPJ da organização",
  "documentos": {
    "cneas": "URL do certificado CNEAS",
    "cebas": "URL do certificado CEBAS",
    "estatuto": "URL do estatuto",
    "balanco_2023": "URL do balanço 2023",
    "balanco_2024": "URL do balanço 2024",
    "outros_documentos": "Outros documentos"
  },
  "termos": {
    "municipio": {
      "quantidade": 2,
      "termos": [
        {
          "identificacao_do_instrumento_de_parceria": "TERMO DE COLABORAÇÃO Nº 026/2022",
          "valor_total_do_termo": "R$960.900,00",
          "data_da_assinatura": "2022-05-15",
          "situacao_do_termo": "Ativo"
        }
      ]
    },
    "estado": { "quantidade": 0, "termos": [] },
    "uniao": { "quantidade": 1, "termos": [...] },
    "emendas_parlamentares": { "quantidade": 0, "termos": [] }
  },
  "estatisticas_termos": {
    "total_contratos_parcerias": 3,
    "tem_termos_municipio": true,
    "tem_termos_estado": false,
    "tem_termos_uniao": true,
    "tem_emendas_parlamentares": false,
    "distribuicao": {
      "municipio": 2,
      "estado": 0,
      "uniao": 1,
      "emendas_parlamentares": 0
    }
  }
}
```

## 🏗️ Arquitetura do Sistema

### **Classes Principais**

#### **`ONGExtractor`**
- Classe principal que orquestra todo o processo
- Gerencia estatísticas e logging
- Coordena extração web e API

#### **`WebScraper`**
- Responsável pelo scraping das páginas web
- Extrai informações de contato, documentos e redes sociais
- Categoriza documentos automaticamente

#### **`APIExtractor`**
- Gerencia comunicação com a API REST
- Extrai dados de termos e contratos
- Processa campos ACF (Advanced Custom Fields)

#### **`Dataclasses`**
- **`ONGData`**: Estrutura principal dos dados
- **`RedesSociais`**: Organização das redes sociais
- **`Documentos`**: Categorização de documentos
- **`TermosInfo`**: Informações de contratos
- **`EstatisticasTermos`**: Métricas de contratos

## 📈 Relatório de Estatísticas

O script gera automaticamente um relatório detalhado:

```
📊 RELATÓRIO DE ESTATÍSTICAS - EXTRAÇÃO DE ONGs
============================================================

🎯 RESUMO GERAL:
• Total processadas: 10
• Sucessos: 10 (100.0%)
• Erros: 0 (0.0%)

🌐 DADOS WEB (Scraping):
• Telefone: 8/10 (80.0%)
• Email: 8/10 (80.0%)
• Website: 6/10 (60.0%)
• Cnpj: 10/10 (100.0%)
• Instagram: 6/10 (60.0%)
• Linkedin: 2/10 (20.0%)
• Youtube: 3/10 (30.0%)

📋 TERMOS E CONTRATOS (API):
• ONGs com contratos: 6/10 (60.0%)
• Total de contratos: 15

📊 DISTRIBUIÇÃO POR TIPO:
• Municipio: 10 (66.7%)
• Estado: 2 (13.3%)
• Uniao: 3 (20.0%)
```

## ⚙️ Configurações

### **Endpoint da API**
```python
endpoint_base = "https://etransparente.org/wp-json/wp/v2/job_listing"
```

### **Headers HTTP**
```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
```

### **Logging**
- Arquivo: `ong_extractor.log`
- Níveis: INFO, ERROR, WARNING
- Formato: `timestamp - level - message`

## 🚦 Limitações e Boas Práticas

### **Rate Limiting**
- Pausa de 0.5s entre requisições para não sobrecarregar o servidor
- Tratamento de erros HTTP

### **Robustez**
- Tratamento de exceções em todas as operações
- Logging detalhado para debug
- Validação de dados antes do processamento

### **Escalabilidade**
- Código modular permite fácil extensão
- Dataclasses facilitam manutenção
- Arquitetura orientada a objetos permite reutilização

## 🔍 Troubleshooting

### **Erro de Módulos**
```bash
pip install beautifulsoup4 requests
```

### **Erro de Timeout**
- Verificar conexão com internet
- Ajustar timeout nas requisições

### **Dados Incompletos**
- Verificar logs para identificar problemas específicos
- Algumas ONGs podem não ter todos os campos preenchidos

## 📝 Exemplo de Uso Avançado

```python
import logging
from ong_extractor import ONGExtractor

# Configurar logging personalizado
logging.basicConfig(level=logging.DEBUG)

# Criar extrator
extrator = ONGExtractor()

# Processar apenas ONGs com contratos
dados = extrator.extrair_todas_ongs(max_ongs=50)

# Filtrar ONGs com contratos ativos
ongs_com_contratos = [
    ong for ong in dados 
    if ong.estatisticas_termos.total_contratos_parcerias > 0
]

# Salvar apenas ONGs com contratos
extrator.salvar_dados(ongs_com_contratos, "ongs_com_contratos.json")

print(f"Encontradas {len(ongs_com_contratos)} ONGs com contratos ativos")
```

## 🐳 Pipeline com Docker + Airflow

### **Setup Inicial (Máquina Nova)**

```bash
# 1. Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker  # ou faça logout/login

# 2. Instalar Docker Compose
sudo apt-get update
sudo apt-get install docker-compose-plugin

# 3. Clonar o repositório
git clone https://github.com/vbreia/pipeline-etransparente.git
cd pipeline-etransparente

# 4. Executar o quick start
chmod +x docke./docker/quick-start.sh
./docke./docker/quick-start.sh
```

**O script `docke./docker/quick-start.sh` fará automaticamente:**
- ✅ Verificar Docker e Docker Compose
- ✅ Criar diretórios necessários (dags, scripts, output, logs)
- ✅ Configurar permissões corretas (chmod 777)
- ✅ Fazer build das imagens Docker (incluindo Playwright/Chromium)
- ✅ Iniciar todos os containers
- ✅ Verificar se Playwright está instalado
- ✅ Validar que a DAG foi carregada
- ✅ Exibir instruções de acesso

**Tempo estimado**: 5-10 minutos na primeira execução (download de imagens e build)

### **Arquitetura**

A pipeline foi implementada usando **Docker Compose** com 4 serviços:

1. **PostgreSQL 15**: Banco de dados do Airflow
2. **Airflow Init**: Inicialização do banco e criação do usuário admin
3. **Airflow Scheduler**: Orquestrador de tarefas (execução da DAG)
4. **Airflow Webserver**: Interface web (http://localhost:8080)

### **Estrutura da DAG**

```
extract_ong_data (ong_extractor.py)
    ↓
generate_transparency_scores (generate_transparency_scores.py)
    ↓
generate_dashboards (dash.py)
```

**Agendamento**: Diariamente às 02:00 AM UTC  
**Retry**: 2 tentativas com intervalo de 5 minutos

### **Como Executar**

#### **1. Iniciar a Pipeline**

```bash
docker-compose up -d
```

#### **2. Acessar Interface Web**

- **URL**: http://localhost:8080
- **Usuário**: admin
- **Senha**: admin

#### **3. Verificar Status**

```bash
# Status dos containers
docker-compose ps

# Logs do scheduler
docker logs airflow-scheduler

# Logs do webserver
docker logs airflow-webserver
```

#### **4. Executar DAG Manualmente**

```bash
docker exec airflow-webserver airflow dags trigger ong_pipeline
```

#### **5. Parar a Pipeline**

```bash
docker-compose down
```

### **Outputs Gerados**

```
output/
├── oscs_etransparente_YYYY-MM-DD-HH-MM-SS.json          # Dados extraídos
├── scores/
│   └── transparency_scores_YYYY-MM-DD-HH-MM-SS.json     # Scores de transparência
└── dashboards/
    └── YYYYMMDDHHMMSS/
        ├── html/                                         # 52 dashboards HTML
        │   ├── 001_Nome_da_ONG.html
        │   └── ...
        └── pdf/                                          # 52 dashboards PDF
            ├── 001_Nome_da_ONG.pdf
            └── ...
```

### **Configuração do Playwright/Chromium**

Para gerar PDFs, o `dash.py` usa Playwright com Chromium headless. A instalação acontece em duas etapas:

1. **Instalação do pacote Python** via `_PIP_ADDITIONAL_REQUIREMENTS`: `playwright`
2. **Instalação do Chromium** (navegador headless): `playwright install chromium --with-deps`

**docker/Dockerfile.airflow (trecho relevante):**
```dockerfile
FROM apache/airflow:2.8.3-python3.11

USER root

# Instalar dependências do sistema para Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu fonts-liberation fontconfig \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow

# Instalar Playwright e Chromium
RUN pip install playwright && playwright install chromium --with-deps
```

**Verificar no container:**
```bash
docker exec airflow-scheduler python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"
```

### **Dependências Python**

As seguintes bibliotecas são instaladas automaticamente via `_PIP_ADDITIONAL_REQUIREMENTS`:

- `playwright` - Conversão HTML → PDF via Chromium headless (substitui pdfkit)
- `qrcode` - QR codes de autenticidade nos dashboards (opcional)
- `requests` - Requisições HTTP
- `pandas` - Manipulação de dados
- `beautifulsoup4` - Web scraping
- `openpyxl` - Manipulação de Excel
- `plotly` - Gráficos interativos
- `streamlit` - Dashboards web

### **Volumes Docker**

```yaml
volumes:
  - ./dags:/home/airflow/dags           # DAGs do Airflow
  - ./scripts:/home/airflow/scripts     # Scripts Python
  - ./output:/home/airflow/output       # Outputs gerados
  - ./logs:/home/airflow/logs           # Logs da pipeline
```

### **Troubleshooting**

#### **Container reiniciando constantemente**

```bash
# Ver logs de erro
docker logs airflow-scheduler --tail 50

# Verificar permissões dos diretórios
chmod -R 777 output logs dags scripts
```

#### **DAG não aparece na interface**

```bash
# Verificar se a DAG está válida
docker exec airflow-scheduler airflow dags list

# Ver erros de parsing
docker exec airflow-scheduler airflow dags list-import-errors
```

#### **Playwright/Chromium não encontrado**

```bash
# Verificar se Playwright está instalado
docker exec airflow-scheduler python -c "from playwright.sync_api import sync_playwright; print('OK')"

# Reinstalar Chromium se necessário
docker exec airflow-scheduler playwright install chromium --with-deps
```

#### **Problemas específicos de Azure VM**

**Porta 8080 não acessível:**
```bash
# 1. Verificar se o container está rodando
docker ps | grep airflow-webserver

# 2. Verificar se a porta está aberta localmente
curl http://localhost:8080

# 3. Se funciona local mas não remoto, configure NSG:
# - Portal Azure → VM → Networking → Add inbound port rule
# - Port: 8080
# - Protocol: TCP
# - Source: Seu IP ou Any (menos seguro)
```

**Falta de espaço em disco:**
```bash
# Verificar espaço
df -h

# Limpar imagens Docker antigas
docker system prune -a

# Limpar logs antigos
sudo find /var/log -type f -name "*.log" -mtime +7 -delete
```

**VM com pouca memória (menos de 8GB):**
```bash
# Criar swap de 4GB
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**Firewall UFW bloqueando:**
```bash
# Verificar status
sudo ufw status

# Permitir porta 8080
sudo ufw allow 8080/tcp
```

## 📊 Histórico de Execuções

### 11 de Dezembro de 2025

- ✅ **52 ONGs** processadas com sucesso
- ✅ **52 HTMLs** gerados
- ✅ **52 PDFs** gerados
- ⏱️ Tempo de execução: ~3 minutos
  - Extract: ~2 min
  - Scores: <1 seg
  - Dashboards: <1 seg

## 👥 Contribuição

Para contribuir com melhorias:

1. **Fork** o projeto
2. **Crie** uma branch para sua feature
3. **Commit** suas mudanças
4. **Push** para a branch
5. **Abra** um Pull Request

## 📄 Licença

Este projeto está sob licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

---

**Pipeline automatizada para análise de transparência de ONGs brasileiras** 🇧🇷
