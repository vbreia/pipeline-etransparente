# 🎯 INÍCIO RÁPIDO - Pipeline ONG com Docker + Airflow

## ⚡ 5 Minutos para começar

### Passo 1: Abra o terminal e vá para a pasta do projeto

```bash
cd /home/breia/job/etransparente.org/pipeline
```

### Passo 2: Execute o script de inicialização automática

```bash
./docker/quick-start.sh
```

Este script vai:
- ✅ Verificar Docker/Docker Compose
- ✅ Criar diretórios necessários
- ✅ Fazer build das imagens
- ✅ Iniciar todos os containers
- ✅ Mostrar a URL de acesso

### Passo 3: Abra o navegador

Acesse: **http://localhost:8080**

**Login padrão:**
- Usuário: `admin`
- Senha: `admin`

### Passo 4: Ative e execute a DAG

1. Na página do Airflow, procure por `ong_pipeline` na lista de DAGs
2. Clique no toggle para **ATIVAR** a DAG
3. Clique em **"Trigger DAG"** para executar agora
4. Veja o progresso em tempo real

## 📊 O que vai acontecer

Sua pipeline vai executar em sequência:

1. **ong_extractor.py** (1-5 minutos)
   - Extrai dados de ONGs do site etransparente.org
   - Gera arquivo: `output/oscs_etransparente_*.json`

2. **generate_transparency_scores.py** (1-2 minutos)
   - Calcula pontuações de transparência
   - Gera arquivo: `output/scores/transparency_scores_*.json`

3. **dash.py** (3-10 minutos)
   - Gera dashboards HTML por ONG (multi-página com Chart.js e Phosphor Icons)
   - Converte para PDF via Playwright/Chromium (requer `playwright install chromium`)
   - Gera em: `output/dashboards/*/html` e `/pdf`
   - Salva registros de autenticidade em `output/verificacoes_YYYY-MM.json`

## 🛠️ Utilitários Principais

### Ver logs em tempo real

```bash
docker-compose logs -f
```

### Parar tudo

```bash
docker-compose down
```

### Reiniciar

```bash
docker-compose restart
```

### Usar o gerenciador de pipeline

```bash
./docker/manage-pipeline.sh --help
```

Exemplos:
```bash
./docker/manage-pipeline.sh status              # Ver status dos containers
./docker/manage-pipeline.sh logs                # Ver logs de tudo
./docker/manage-pipeline.sh logs airflow-scheduler  # Logs apenas do scheduler
./docker/manage-pipeline.sh trigger             # Acionar DAG via CLI
./docker/manage-pipeline.sh shell               # Entrar em shell do container
./docker/manage-pipeline.sh health-check        # Verificar saúde
```

## 📁 Arquivos importantes

| Arquivo | Propósito |
|---------|-----------|
| `docker-compose.yml` | Configuração dos containers |
| `Dockerfile` | Image customizada do Airflow |
| `dags/ong_pipeline.py` | A DAG que orquestra os scripts |
| `manage-pipeline.sh` | CLI para gerenciar o pipeline |
| `AIRFLOW_SETUP.md` | Documentação completa |
| `TECHNICAL_GUIDE.md` | Guia técnico detalhado |

## 🔄 Agendamento Automático

Por padrão, a pipeline executa **todos os dias às 2:00 AM (UTC)**.

Para alterar, edite `dags/ong_pipeline.py` e mude:

```python
schedule_interval='0 2 * * *',  # Mude para seu horário desejado
```

Exemplos:
- `'@daily'` → Diariamente à meia-noite
- `'0 12 * * *'` → Diariamente ao meio-dia
- `'0 */6 * * *'` → A cada 6 horas
- `'0 0 * * 1'` → Toda segunda-feira à meia-noite

## 🆘 Algo deu errado?

### WebUI não abre (http://localhost:8080)

```bash
# Aguarde mais 30 segundos (primeira inicialização é lenta)
sleep 30

# Verifique os logs
docker-compose logs airflow-webserver

# Se ainda não funcionar, reinicie
docker-compose restart airflow-webserver
```

### Task falha ao executar

```bash
# Ver logs detalhados no WebUI: clique na task e vá em "Logs"
# Ou via CLI:
docker exec airflow-webserver airflow tasks log ong_pipeline extract_ong_data
```

### Permissão negada

```bash
docker-compose exec airflow-webserver chmod +x /home/airflow/scripts/*.py
docker-compose restart airflow-scheduler
```

### PostgreSQL não inicia

```bash
# Aumentar limites do sistema
docker run --rm --privileged -v /:/host ubuntu /bin/bash -c "echo vm.max_map_count=262144 >> /host/etc/sysctl.conf"

# Reiniciar Docker
docker-compose down
docker-compose up -d
```

## 📞 Próximos passos (opcional)

### 1. Configurar email de alertas

No `docker-compose.yml`, adicione:
```yaml
environment:
  - AIRFLOW__SMTP__SMTP_HOST=smtp.seu_provedor.com
  - AIRFLOW__SMTP__SMTP_PORT=587
  - AIRFLOW__SMTP__SMTP_USER=seu_email@exemplo.com
  - AIRFLOW__SMTP__SMTP_PASSWORD=sua_senha
```

### 2. Aumentar paralelismo

Para executar mais tasks em paralelo, no `docker-compose.yml`:
```yaml
environment:
  - AIRFLOW__CORE__PARALLELISM=8
  - AIRFLOW__CORE__DAG_CONCURRENCY=4
```

### 3. Fazer backup do banco de dados

```bash
docker exec airflow-postgres pg_dump -U airflow airflow > backup.sql
```

### 4. Restaurar backup

```bash
docker exec -i airflow-postgres psql -U airflow airflow < backup.sql
```

## 💡 Dicas

1. **Primeira execução**: Pode levar mais tempo (setup inicial)
2. **Monitorar logs**: Sempre útil para debug
3. **Testar manualmente**: Use `Trigger DAG` antes de confiar no agendamento
4. **Backup regular**: Faça backup do banco Postgres periodicamente
5. **Recursos**: Se ficar lento, aumente RAM/CPU ou paralelismo

## 📚 Documentação Completa

Para informações detalhadas:
- `AIRFLOW_SETUP.md` - Setup e configuração completa
- `TECHNICAL_GUIDE.md` - Arquitetura e customização avançada

## 🎓 Aprender mais

- [Apache Airflow Docs](https://airflow.apache.org/docs/)
- [Docker Compose Docs](https://docs.docker.com/compose/)
- [DAGs Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)

---

**Agora é só rodar `./docker/quick-start.sh` e aproveitar! 🚀**
