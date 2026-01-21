# 📋 Guia Técnico - Pipeline ONG com Docker + Airflow

## 🎯 O que foi criado

Um ambiente de orquestração **production-ready** que coordena automaticamente a execução sequencial dos seus scripts de extração e processamento de dados de ONGs.

## 📦 Componentes

### Containers Docker
- **postgres:15-alpine** - Banco de dados do Airflow (PostgreSQL)
- **airflow-scheduler** - Executa o agendamento das DAGs
- **airflow-webserver** - Interface web para monitovrar e gerenciar DAGs
- **airflow-init** - Container de inicialização (cria usuários, aplica migrations)

### Arquivos criados

```
pipeline/
├── docker-compose.yml          # Orquestração dos containers
├── docker/
│   ├── Dockerfile.airflow      # Imagem customizada com Python + Airflow + deps
│   ├── Dockerfile              # Imagem base Python
│   ├── entrypoint.sh           # Script de inicialização do container
│   ├── quick-start.sh          # Script de inicialização automática
│   ├── manage-pipeline.sh      # CLI para gerenciar o pipeline
│   └── setup-azure-vm.sh       # Setup para VM Azure
├── quick-start.sh              # Symlink → docke./docker/quick-start.sh
├── manage-pipeline.sh          # Symlink → docke./docker/manage-pipeline.sh
├── setup-azure-vm.sh           # Symlink → docke./docker/setup-azure-vm.sh
├── .env.example                # Variáveis de ambiente de exemplo
├── doc/                        # Documentação (movido de raiz)
│   ├── AIRFLOW_SETUP.md
│   ├── TECHNICAL_GUIDE.md
│   ├── QUICK_START.md
│   ├── DEPENDENCIES.md
│   ├── DOCKER_STRUCTURE.md
│   ├── ONG_EXTRACTOR_EXPLAIN.md
│   └── API_GA4_TO_AZURE.md
├── dags/
│   └── ong_pipeline.py         # DAG que orquestra os 3 scripts
├── scripts/                    # (seus scripts existentes)
│   ├── ong_extractor.py
│   ├── generate_transparency_scores.py
│   └── dash.py
└── output/                     # (diretório de saídas)
```

## 🔄 Fluxo de Execução

```
┌─────────────────────┐
│  Agendador Airflow  │
│   (2:00 AM UTC)     │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────────────────┐
│      TASK 1: extract_ong_data        │
│  → Executa ong_extractor.py          │
│  → Gera oscs_etransparente_*.json    │
└──────────┬───────────────────────────┘
           │ (sucesso)
           ▼
┌──────────────────────────────────────┐
│  TASK 2: generate_transparency_scores│
│  → Executa generate_transparency_scores.py
│  → Gera transparency_scores_*.json   │
└──────────┬───────────────────────────┘
           │ (sucesso)
           ▼
┌──────────────────────────────────────┐
│    TASK 3: generate_dashboards       │
│  → Executa dash.py                   │
│  → Gera HTML e PDF por ONG           │
└──────────────────────────────────────┘
```

Se alguma task falhar:
- ✅ Retry automático (até 2 vezes)
- 📧 Email de notificação (se configurado)
- 📊 Logs detalhados no Airflow WebUI

## 🚀 Como usar

### Opção 1: Inicialização Automática (Recomendado)

```bash
cd /home/breia/job/etransparente.org/pipeline
./docker/quick-start.sh
```

Isto vai:
- ✅ Verificar Docker/Docker Compose
- ✅ Criar diretórios necessários
- ✅ Fazer build das images
- ✅ Iniciar todos os containers
- ✅ Aguardar inicialização
- ✅ Exibir acesso ao WebUI

### Opção 2: Inicialização Manual

```bash
# Iniciar
docker-compose up -d

# Aguardar (30s)
sleep 30

# Verificar status
docker-compose ps

# Logs
docker-compose logs -f
```

### Opção 3: Usar script gerenciador

```bash
./docker/manage-pipeline.sh start      # Iniciar
./docker/manage-pipeline.sh status     # Status
./docker/manage-pipeline.sh logs       # Logs
./docker/manage-pipeline.sh trigger    # Acionar DAG manualmente
./docker/manage-pipeline.sh shell      # Entrar em shell do container
```

## 📊 Monitoramento

### WebUI (http://localhost:8080)
- Ativar/desativar DAGs
- Acionar execuções manuais
- Ver historco de execuções
- Visualizar logs de tasks
- Monitorar métricas

### CLI (linha de comando)

```bash
# Ver DAGs disponíveis
docker exec airflow-webserver airflow dags list

# Ver histórico de execuções
docker exec airflow-webserver airflow dags list-runs --dag-id ong_pipeline

# Ver logs de uma task
docker exec airflow-webserver airflow tasks log ong_pipeline extract_ong_data 2025-12-09

# Acionar DAG via CLI
docker exec airflow-webserver airflow dags trigger ong_pipeline
```

### Docker Compose

```bash
# Status
docker-compose ps

# Logs
docker-compose logs -f [serviço]

# Entrar em container
docker exec -it airflow-webserver bash

# Reiniciar
docker-compose restart [serviço]
```

## 🔧 Customização

### Alterar schedule de execução

Edite `dags/ong_pipeline.py`:

```python
schedule_interval='0 2 * * *',  # Padrão: 2 AM UTC
```

Exemplos:
- `'@daily'` - Diariamente
- `'@hourly'` - A cada hora
- `'0 */6 * * *'` - A cada 6 horas
- `'30 9 * * 1-5'` - Segunda a sexta às 9:30 AM

### Adicionar nova task

1. Crie função no `dags/ong_pipeline.py`:

```python
def run_my_script(**context):
    script_path = '/home/airflow/scripts/my_script.py'
    result = subprocess.run(['python', script_path], ...)
    return result.stdout

my_task = PythonOperator(
    task_id='my_task',
    python_callable=run_my_script,
    dag=dag,
)
```

2. Defina dependência:

```python
# Após extract_task e antes de scores_task
extract_task >> my_task >> scores_task
```

### Aumentar paralelismo

Edite variáveis no `docker-compose.yml` ou `.env`:

```yaml
environment:
  - AIRFLOW__CORE__PARALLELISM=8        # Tasks paralelas globais
  - AIRFLOW__CORE__DAG_CONCURRENCY=4    # Tasks paralelas por DAG
```

### Configuar email de alertas

No `docker-compose.yml`:

```yaml
environment:
  - AIRFLOW__SMTP__SMTP_HOST=smtp.gmail.com
  - AIRFLOW__SMTP__SMTP_PORT=587
  - AIRFLOW__SMTP__SMTP_USER=seu_email@gmail.com
  - AIRFLOW__SMTP__SMTP_PASSWORD=sua_senha_app
  - AIRFLOW__SMTP__SMTP_MAIL_FROM=seu_email@gmail.com
```

Depois, na DAG, adicione:

```python
default_args = {
    ...
    'email': ['seu_email@gmail.com'],
    'email_on_failure': True,
    'email_on_retry': True,
}
```

## 🐛 Troubleshooting

### WebServer não inicia

```bash
# Ver logs do webserver
docker-compose logs airflow-webserver

# Verificar se postgres está saudável
docker-compose logs postgres

# Reiniciar
docker-compose restart airflow-webserver
```

### Task falha ao executar script

```bash
# Ver logs completos
docker exec airflow-webserver airflow tasks log ong_pipeline extract_ong_data

# Testar script manualmente
docker exec airflow-webserver bash -c "cd /home/airflow && python scripts/ong_extractor.py"
```

### Permissão negada em scripts

```bash
# Dar permissão de leitura
docker exec airflow-webserver chmod +x /home/airflow/scripts/*.py
```

### Reset completo (começar do zero)

```bash
docker-compose down
docker volume rm pipeline_postgres_data pipeline_airflow_home
docker-compose up -d
```

## 📈 Performance

### Recomendações

- **RAM mínima**: 4GB
- **CPU**: 2 cores
- **Disk**: 10GB livres

### Otimizações possíveis

1. **Paralelismo**: Aumentar `PARALLELISM` em docker-compose
2. **Pool de conexões**: Aumentar `max_pool_size` do PostgreSQL
3. **Logs**: Limpar logs antigos regularmente

```bash
# Limpar logs maiores que 30 dias
docker exec airflow-webserver airflow logs delete --yes --logs-before-value 30
```

## 📚 Recursos adicionais

- [Documentação Airflow](https://airflow.apache.org/docs/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [Airflow Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)
- [DAG Writing Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html#dag-writing-best-practices)

## ✅ Checklist de Verificação

- [ ] Docker e Docker Compose instalados
- [ ] Porta 8080 disponível (WebUI)
- [ ] Porta 5432 disponível (PostgreSQL)
- [ ] Scripts em `/home/breia/job/etransparente.org/pipeline/scripts/`
- [ ] 4GB RAM disponível
- [ ] Executar `./docker/quick-start.sh`
- [ ] Acessar http://localhost:8080
- [ ] Ativar DAG `ong_pipeline`
- [ ] Acionar manualmente (Trigger DAG)
- [ ] Monitorar execução no WebUI

## 🎓 Diagrama de Arquitetura

```
┌──────────────────────────────────────────────────────┐
│              Docker Network: airflow-network           │
├──────────────────────────────────────────────────────┤
│                                                       │
│  ┌────────────────┐      ┌────────────────┐         │
│  │   PostgreSQL   │      │  Airflow Init  │         │
│  │   (postgres:15)│      │  (Bootstrap)   │         │
│  │   :5432        │      └────────────────┘         │
│  │                │              │                   │
│  │  - airflow db  │              │ (upgrade DB)      │
│  │  - metadata    │              │                   │
│  └────────┬───────┘              │                   │
│           │                      │                   │
│           └──────────┬───────────┘                   │
│                      │                               │
│         ┌────────────┼────────────┐                  │
│         │            │            │                  │
│         ▼            ▼            ▼                  │
│  ┌────────────┐  ┌────────┐  ┌────────────┐        │
│  │  Scheduler │  │WebUI   │  │ (Future:   │        │
│  │   :        │  │:8080   │  │  Worker)   │        │
│  │ Monitora   │  │Monitora│  │            │        │
│  │ e aciona   │  │e       │  │ Executa    │        │
│  │ tasks      │  │gerencia│  │ tasks      │        │
│  │            │  │        │  │            │        │
│  └────────────┘  └────────┘  └────────────┘        │
│         │            │            │                  │
│         └────────────┼────────────┘                  │
│                      │                               │
│                ┌─────▼─────┐                         │
│                │    DAG     │                         │
│                │ ong_pipeline│                        │
│                │     │       │                        │
│                │  ┌──┴───────┴────┐                  │
│                │  │  Task Graph:   │                  │
│                │  │  T1 → T2 → T3  │                  │
│                │  └────────────────┘                  │
│                └────────────────────┘                 │
│                      │                               │
│         ┌────────────┼────────────┐                  │
│         │            │            │                  │
│         ▼            ▼            ▼                  │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│   │ Task 1:  │  │ Task 2:  │  │ Task 3:  │         │
│   │ Extrator │  │ Scores   │  │Dashboard │         │
│   └──────────┘  └──────────┘  └──────────┘         │
│         │            │            │                  │
│         ▼            ▼            ▼                  │
│   ┌──────────────────────────────────────────┐     │
│   │  Volumes Compartilhados:                  │     │
│   │  - /home/airflow/scripts  (RO)           │     │
│   │  - /home/airflow/output   (RW)           │     │
│   │  - /home/airflow/dags     (RO)           │     │
│   │  - /home/airflow/assets   (RW)           │     │
│   └──────────────────────────────────────────┘     │
│                                                      │
└──────────────────────────────────────────────────────┘
         │
         ▼ (Host Machine)
    ┌─────────────┐
    │  :8080      │ → Navegador
    │  :5432      │ → Postgres CLI
    │  ./output   │ → Resultados
    │  ./assets   │ → Logos e recursos
    └─────────────┘
```

## 🎨 Funcionalidade de Logos das ONGs

A partir da versão atual, o pipeline inclui processamento automático de logos das ONGs:

### Extração e Processamento (ong_extractor.py)

**Fluxo:**
1. **Detecção**: localiza logo na página HTML (elemento `<a class="profile-avatar">`)
2. **Download**: faz requisição do logo original (suporta PNG, JPG, WebP, etc.)
3. **Processamento**:
   - Converte transparência para fundo branco
   - Redimensiona para formato quadrado 1:1 (sem distorção)
   - Centraliza imagem em canvas branco
   - Salva como JPG com qualidade 90%
4. **Armazenamento**: `assets/img/logos-ongs/<nome_normalizado>.jpg`

**Dependências:**
```python
pip install pillow  # Obrigatório para processamento de imagens
```

**Estrutura de dados:**
```json
{
  "nome": "Nome da ONG",
  "logo_url": "https://example.com/logo.png",
  "logo_local_path": "/home/airflow/assets/img/logos-ongs/Nome_da_ONG.jpg"
}
```

### Uso nos Dashboards (dash.py)

Os dashboards HTML/PDF usam automaticamente os logos locais:

**Sistema de fallback:**
1. Busca `logo_local_path` no JSON
2. Se não existir, busca em `assets/img/logos-ongs/` usando nome normalizado
3. Se não encontrar, usa logo padrão ou placeholder

**Características:**
- ✅ Formato quadrado 1:1 (ótimo para círculos CSS)
- ✅ Fundo branco consistente
- ✅ Alta qualidade (90%)
- ✅ URLs absolutas com `file://` para wkhtmltopdf
- ✅ Logos persistem entre execuções

**Volume Docker:**
```yaml
volumes:
  - ./assets:/home/airflow/assets:rw  # Logos salvos e reutilizados
```

### Manutenção e Troubleshooting

**Reprocessar logos:**
```bash
# Limpar logos existentes
rm -rf assets/img/logos-ongs/*

# Executar extrator novamente
docker exec airflow-webserver python scripts/ong_extractor.py
```

**Verificar logos gerados:**
```bash
# Listar logos
ls -lh assets/img/logos-ongs/

# Verificar dimensões (requer imagemagick)
identify assets/img/logos-ongs/*.jpg | head -5

# Verificar com Python/Pillow
docker exec airflow-webserver python -c "
from PIL import Image
import os
logos = os.listdir('assets/img/logos-ongs')[:5]
for logo in logos:
    img = Image.open(f'assets/img/logos-ongs/{logo}')
    print(f'{logo}: {img.size} - {img.mode}')
"
```

**Permissões:**
```bash
# Se tiver problemas de permissão
chmod 777 assets/img/logos-ongs
```

**Logs úteis:**
```bash
# Ver logs de download de logos
docker exec airflow-webserver tail -100 logs/ong_extractor_*.log | grep -i logo
```

---

**Versão**: 1.1  
**Data**: Janeiro 2026  
**Autor**: Pipeline ONG  
**Status**: Production-Ready
