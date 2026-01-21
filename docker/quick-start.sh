#!/bin/bash
# Quick start script para o pipeline
# Execute este script para iniciar tudo de uma vez

set -e

# Ir para a raiz do projeto (resolve symlink e sai de docker/)
SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR/.."

echo "╔═══════════════════════════════════════════════════════╗"
echo "║     Pipeline ONG - Inicialização Rápida              ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Verificar Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker não está instalado. Por favor, instale Docker primeiro."
    echo "   Ubuntu/Debian: curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose não está instalado. Por favor, instale Docker Compose."
    echo "   Ubuntu/Debian: sudo apt-get install docker-compose-plugin"
    exit 1
fi

echo "✓ Docker e Docker Compose encontrados"
echo ""

# Verificar se Docker está rodando
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker não está rodando. Inicie o serviço Docker:"
    echo "   sudo systemctl start docker"
    exit 1
fi

echo "✓ Docker está rodando"
echo ""

# Criar diretórios necessários
echo "📁 Criando diretórios necessários..."
mkdir -p dags scripts output logs output/dashboards output/scores
echo "✓ Diretórios criados"
echo ""

# Configurar permissões corretas
echo "🔐 Configurando permissões..."
chmod -R 777 output logs dags scripts
echo "✓ Permissões configuradas"
echo ""

# Verificar arquivos essenciais
echo "📋 Verificando arquivos essenciais..."
MISSING_FILES=0

if [ ! -f "docker-compose.yml" ]; then
    echo "❌ docker-compose.yml não encontrado"
    MISSING_FILES=1
fi

if [ ! -f "docker/Dockerfile.airflow" ]; then
    echo "❌ docker/Dockerfile.airflow não encontrado"
    MISSING_FILES=1
fi

if [ ! -d "dags" ] || [ -z "$(ls -A dags)" ]; then
    echo "❌ Pasta dags/ vazia ou não existe"
    MISSING_FILES=1
fi

if [ ! -d "scripts" ] || [ -z "$(ls -A scripts)" ]; then
    echo "❌ Pasta scripts/ vazia ou não existe"
    MISSING_FILES=1
fi

if [ $MISSING_FILES -eq 1 ]; then
    echo ""
    echo "❌ Arquivos essenciais faltando. Clone o repositório completo:"
    echo "   git clone <repo-url> pipeline-etransparente"
    exit 1
fi

echo "✓ Todos os arquivos essenciais presentes"
echo ""

# Build das images
echo "🏗️  Fazendo build das images Docker..."
echo "   ⚠️  Isso pode levar 5-10 minutos na primeira vez"
echo "   (baixando wkhtmltopdf e dependências...)"
echo ""
docker-compose build --progress=plain 2>&1 | tee /tmp/docker-build.log | grep -E "(Step|Downloading|Installing|Successfully|ERROR)" || true
echo ""

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "❌ Erro no build. Verifique o log em /tmp/docker-build.log"
    exit 1
fi

echo "✓ Build concluído com sucesso"
echo ""

# Iniciar containers
echo "🚀 Iniciando containers..."
docker-compose up -d

if [ $? -ne 0 ]; then
    echo "❌ Erro ao iniciar containers"
    exit 1
fi

echo "✓ Containers iniciados"
echo ""

# Aguardar inicialização
echo "⏳ Aguardando inicialização do banco de dados..."
sleep 30

echo "⏳ Aguardando Airflow WebServer ficar online..."
for i in {1..12}; do
    if docker exec airflow-webserver airflow version >/dev/null 2>&1; then
        echo "✓ Airflow está pronto!"
        break
    fi
    if [ $i -eq 12 ]; then
        echo "⚠️  Airflow ainda não respondeu após 2 minutos"
        echo "   Verifique os logs: docker logs airflow-webserver"
    else
        echo "   Tentativa $i/12 (aguardando 10s)..."
        sleep 10
    fi
done
echo ""

# Verificar status
echo ""
echo "📊 Status dos containers:"
docker-compose ps
echo ""

# Health check
echo "🔍 Verificando saúde dos serviços..."
for i in {1..5}; do
    if curl -s http://localhost:8080/health >/dev/null 2>&1; then
        echo "✓ Airflow WebServer está respondendo"
        break
    else
        echo "⏳ Tentativa $i/5 - aguardando WebServer..."
        sleep 5
    fi
done

echo ""
# Verificar se wkhtmltopdf foi instalado corretamente
echo "🔍 Verificando instalação do wkhtmltopdf..."
if docker exec airflow-scheduler wkhtmltopdf --version >/dev/null 2>&1; then
    WKHTMLTOPDF_VERSION=$(docker exec airflow-scheduler wkhtmltopdf --version 2>&1 | head -1)
    echo "✓ wkhtmltopdf instalado: $WKHTMLTOPDF_VERSION"
else
    echo "⚠️  wkhtmltopdf não encontrado - PDFs não serão gerados"
    echo "   HTMLs ainda serão gerados normalmente"
fi
echo ""

# Verificar DAGs disponíveis
echo "📋 Verificando DAGs disponíveis..."
if docker exec airflow-scheduler airflow dags list 2>/dev/null | grep -q "ong_pipeline"; then
    echo "✓ DAG 'ong_pipeline' encontrada e carregada"
else
    echo "⚠️  DAG 'ong_pipeline' não foi carregada"
    echo "   Verifique: docker exec airflow-scheduler airflow dags list-import-errors"
fi
echo ""

echo "╔═══════════════════════════════════════════════════════╗"
echo "║                   ✓ INICIALIZAÇÃO CONCLUÍDA          ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""
echo "📍 Próximos passos:"
echo ""
echo "1. Abra no navegador:"
echo "   🌐 http://localhost:8080"
echo ""
echo "2. Faça login com:"
echo "   👤 Username: admin"
echo "   🔑 Password: admin"
echo ""
echo "3. Encontre a DAG 'ong_pipeline' e:"
echo "   ✅ Ative a DAG (toggle no topo)"
echo "   ▶️  Clique 'Trigger DAG' para executar manualmente"
echo ""
echo "4. Monitore a execução em tempo real"
echo ""
echo "📖 Documentação completa em: ./README.md"
echo ""
echo "💡 Comandos úteis:"
echo "   Ver logs:              docker-compose logs -f"
echo "   Ver logs do scheduler: docker logs -f airflow-scheduler"
echo "   Executar DAG via CLI:  docker exec airflow-webserver airflow dags trigger ong_pipeline"
echo "   Parar tudo:            docker-compose down"
echo "   Reiniciar:             docker-compose restart"
echo ""
echo "⏰ Próxima execução automática: Diariamente às 02:00 AM UTC"
echo ""
echo "📂 Outputs serão salvos em: ./output/"
echo "   - oscs_etransparente_*.json (dados extraídos)"
echo "   - scores/transparency_scores_*.json (scores)"
echo "   - dashboards/*/html/*.html (dashboards HTML)"
echo "   - dashboards/*/pdf/*.pdf (dashboards PDF)"
echo ""
