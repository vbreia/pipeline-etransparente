# Estrutura Docker

## 📁 Organização

Todos os arquivos relacionados ao Docker foram consolidados na pasta `docker/`:

```
pipeline/
├── docker/                          # Arquivos Docker
│   ├── Dockerfile.airflow           # Imagem Apache Airflow com dependências
│   ├── Dockerfile                   # Imagem base Python (alternativa)
│   ├── entrypoint.sh                # Script de inicialização do container
│   ├── .dockerignore                # Arquivos ignorados no build
│   └── wkhtmltox_*.deb              # Pacotes wkhtmltopdf legados (não mais usados)
├── docker-compose.yml               # Orquestração de containers (RAIZ)
├── requirements.txt                 # Dependências Python
└── ...
```

## 📌 Por que essa estrutura?

### ✅ Vantagens

1. **Organização:** Todos os arquivos Docker em um único lugar
2. **Clareza:** Fácil identificar arquivos do projeto vs. Docker
3. **Manutenção:** Separação de responsabilidades
4. **Escalabilidade:** Pronto para múltiplos ambientes (dev, staging, prod)
5. **Docker-compose na raiz:** Mantém os comandos simples (`docker-compose up`)

## 🔧 Arquivos

### `docker/Dockerfile.airflow`
Imagem principal do projeto com:
- Base: `apache/airflow:2.8.3-python3.11`
- Playwright/Chromium (headless PDF) — instalado via `playwright install chromium --with-deps`
- Todas as bibliotecas do `requirements.txt`

**Usado por:** airflow-init, airflow-scheduler, airflow-webserver

### `docker/Dockerfile`
Alternativa leve com:
- Base: `python:3.11-slim`
- Apache Airflow 2.7.3
- Pacotes Python mínimos

### `docker/entrypoint.sh`
Script de inicialização do container Airflow. Pode ser customizado para:
- Migrations do banco de dados
- Criação de usuários
- Inicialização de variáveis de ambiente

### `docker/.dockerignore`
Define arquivos que **não** são copiados ao build:
- Python cache (`__pycache__/`, `*.pyc`)
- Git (`.git/`, `.gitignore`)
- Logs e outputs
- Documentação
- Testes

### `docker/wkhtmltox_*.deb`
Pacotes legados do wkhtmltopdf (não mais utilizados — Playwright/Chromium substituiu). Podem ser removidos.

## 🚀 Como usar

### Build dos containers

```bash
docker-compose build --progress=plain
```

Docker automaticamente:
1. Lê `docker-compose.yml`
2. Encontra `docker/Dockerfile.airflow`
3. Executa o build
4. Executa `_PIP_ADDITIONAL_REQUIREMENTS` para instalar dependências

### Iniciação

```bash
docker-compose up -d
```

### Logs

```bash
# Todos
docker-compose logs -f

# Específico
docker-compose logs -f airflow-webserver
```

### Parar

```bash
docker-compose down
```

## 📝 Referência de caminhos

| Arquivo | Novo caminho | Referências |
|---------|--------------|-------------|
| `Dockerfile` | `docker/Dockerfile` | (não usado) |
| `Dockerfile.airflow` | `docker/Dockerfile.airflow` | docker-compose.yml |
| `entrypoint.sh` | `docker/entrypoint.sh` | (opcional) |
| `.dockerignore` | `docker/.dockerignore` | Docker |
| `wkhtmltox_*.deb` | `docker/wkhtmltox_*.deb` | (legado, não mais usado) |

## ✨ Benefícios da reorganização

- **Mais profissional:** Segue padrões da indústria
- **Mais limpo:** Raiz do projeto desembaraçada
- **Mais escalável:** Pronto para múltiplos Dockerfiles
- **Mais documentado:** Docker separado facilita compreensão

## 🔍 Verificação

Para confirmar que tudo está funcionando:

```bash
# Verificar estrutura
ls -la docker/

# Build test
docker-compose build

# Up test
docker-compose up -d

# Status
docker-compose ps

# Down
docker-compose down
```

## 📚 Mais informações

- [docker-compose.yml](../docker-compose.yml) - Configuração de containers
- [DEPENDENCIES.md](../DEPENDENCIES.md) - Dependências do projeto
- [AIRFLOW_SETUP.md](../AIRFLOW_SETUP.md) - Setup do Airflow
