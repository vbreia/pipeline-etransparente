# Airflow + Docker Pipeline para Orquestração de Scripts de ONGs

## Visão Geral

Este setup cria um ambiente Docker com Apache Airflow para orquestrar os seguintes scripts em sequência:

1. **ong_extractor.py** - Extrai dados de ONGs do site etransparente.org
2. **generate_transparency_scores.py** - Calcula pontuações de transparência a partir dos dados extraídos
3. **dash.py** - Gera dashboards HTML e PDF por ONG

## Estrutura de Arquivos

```
pipeline/
├── docker-compose.yml        # Configuração Docker Compose (Postgres + Airflow)
├── docker/
│   ├── Dockerfile.airflow   # Imagem do Airflow com dependências
│   ├── Dockerfile           # Imagem base Python
│   └── entrypoint.sh        # Script de inicialização
├── dags/
│   └── ong_pipeline.py      # DAG principal do Airflow
├── scripts/                 # Seus scripts (ong_extractor.py, etc)
├── output/                  # Diretório para saídas dos scripts
└── requirements.txt         # Dependências Python
```

## Requisitos

- Docker >= 20.10
- Docker Compose >= 1.29
- ~4GB RAM disponível para os containers

## Instalação e Execução

### 1. Preparar o ambiente

```bash
cd /home/breia/job/etransparente.org/pipeline

# Garantir que os diretórios existem
mkdir -p dags scripts output docker
chmod +x docker/entrypoint.sh

# Se houver um arquivo .env, carregá-lo (opcional)
# export $(cat .env | grep -v '#' | xargs)
```

### 2. Iniciar os containers

```bash
# Build das images e start dos containers
docker-compose up -d

# Ver logs
docker-compose logs -f

# Status dos containers
docker-compose ps
```

### 3. Acessar o Airflow WebUI

Abra o navegador em: **http://localhost:8080**

Credenciais padrão:
- Username: `admin`
- Password: `admin`

### 4. Ativar e monitorar a DAG

No WebUI do Airflow:
1. Localize a DAG `ong_pipeline` na lista de DAGs
2. Clique em "Enable" (ou no toggle) para ativar a DAG
3. Clique em "Trigger DAG" para executar manualmente
4. Monitore o progresso na página da DAG

## Schedule

Por padrão, a DAG está configurada para executar automaticamente **todos os dias às 2:00 AM** (UTC).

Para alterar o schedule, edite em `dags/ong_pipeline.py`:
```python
schedule_interval='0 2 * * *',  # Cron format: hora minuto dia mês dia_semana
```

Exemplos de schedules:
- `'@daily'` - Diariamente à meia-noite
- `'@hourly'` - A cada hora
- `'0 */6 * * *'` - A cada 6 horas
- `'0 0 * * 0'` - Toda segunda-feira às 00:00

## Logs e Troubleshooting

### Ver logs dos containers

```bash
# Logs gerais do Airflow
docker-compose logs airflow-webserver

# Logs do scheduler
docker-compose logs airflow-scheduler

# Logs do Postgres
docker-compose logs postgres

# Logs em tempo real (últimas 100 linhas)
docker-compose logs -f --tail=100
```

### Acessar shell de um container

```bash
# Shell do Airflow webserver
docker exec -it airflow-webserver bash

# Shell do Postgres
docker exec -it airflow-postgres psql -U airflow -d airflow
```

### Reset do Airflow (limpar tudo)

```bash
# Parar containers
docker-compose down

# Remover volumes (dados persistidos)
docker volume rm pipeline_postgres_data pipeline_airflow_home

# Reiniciar
docker-compose up -d
```

## Variáveis de Ambiente

Você pode criar um arquivo `.env` na raiz do projeto com variáveis customizadas:

```bash
# .env
AIRFLOW__CORE__PARALLELISM=4
AIRFLOW__CORE__DAG_CONCURRENCY=2
AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG=1
POSTGRES_PASSWORD=seu_password_seguro
```

Depois carregue com:
```bash
export $(cat .env | grep -v '#' | xargs)
docker-compose up -d
```

## Customização

### Alterar horário de execução da DAG

Edite `dags/ong_pipeline.py` e mude `schedule_interval`.

### Adicionar nova task à pipeline

1. Crie uma função `PythonOperator` em `dags/ong_pipeline.py`
2. Defina a dependência entre tasks (ex: `task1 >> task2`)

Exemplo:
```python
new_task = PythonOperator(
    task_id='new_task_name',
    python_callable=run_my_function,
    dag=dag,
)

# Adicionar ao pipeline
some_previous_task >> new_task >> some_next_task
```

### Aumentar recursos

Se os containers precisarem de mais memória/CPU, edite `docker-compose.yml`:

```yaml
airflow-webserver:
  ...
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 2G
      reservations:
        cpus: '1'
        memory: 1G
```

## Monitoramento Avançado

### Verificar se uma DAG foi executada com sucesso

```bash
# Via CLI do Airflow
docker exec airflow-webserver airflow dags list

# Via logs
docker exec airflow-webserver airflow tasks log ong_pipeline extract_ong_data <data_da_execução>
```

### Métricas e Health Checks

O Airflow expõe métricas em: **http://localhost:8080/health**

## Próximos Passos Opcionais

1. **Adicionar alertas por email**: Configure SMTP em `docker-compose.yml`
2. **Integrar com GitHub**: Configure pull de código automático
3. **Adicionar testes**: Use `pytest` nas tasks do Airflow
4. **Backups automáticos**: Configure backup do Postgres
5. **Deploy em produção**: Use Kubernetes ou AWS ECS

## Suporte

Para mais informações sobre Airflow:
- [Documentação oficial do Airflow](https://airflow.apache.org/docs/)
- [DAG Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)

---

Criado: Dezembro 2025
