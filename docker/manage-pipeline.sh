#!/bin/bash
# Script auxiliar para gerenciar o pipeline do Airflow
# Uso: ./manage-pipeline.sh [comando]

set -e

SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
cd "$SCRIPT_DIR/.."

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funções auxiliares
print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Comandos
start() {
    print_header "Iniciando containers do Airflow"
    docker-compose up -d
    print_success "Containers iniciados"
    print_info "Aguardando inicialização..."
    sleep 10
    
    echo ""
    print_header "Informações de Acesso"
    echo -e "WebUI: ${GREEN}http://localhost:8080${NC}"
    echo -e "Username: ${GREEN}admin${NC}"
    echo -e "Password: ${GREEN}admin${NC}"
    echo ""
    print_info "Aguarde alguns segundos até o webserver ficar pronto (verifique com 'docker-compose logs')"
}

stop() {
    print_header "Parando containers"
    docker-compose down
    print_success "Containers parados"
}

restart() {
    print_header "Reiniciando containers"
    stop
    sleep 2
    start
}

logs() {
    local service="${1:-all}"
    if [ "$service" == "all" ]; then
        print_header "Exibindo logs de todos os serviços"
        docker-compose logs -f
    else
        print_header "Exibindo logs de $service"
        docker-compose logs -f "$service"
    fi
}

status() {
    print_header "Status dos containers"
    docker-compose ps
}

shell() {
    local container="${1:-airflow-webserver}"
    print_header "Acessando shell de $container"
    docker exec -it "$container" bash
}

shell_postgres() {
    print_header "Acessando Postgres"
    docker exec -it airflow-postgres psql -U airflow -d airflow
}

trigger_dag() {
    print_header "Acionando DAG ong_pipeline"
    docker exec airflow-webserver airflow dags trigger ong_pipeline
    print_success "DAG acionada"
    print_info "Monitore em: http://localhost:8080/dags/ong_pipeline"
}

dag_status() {
    print_header "Status das execuções da DAG"
    docker exec airflow-webserver airflow dags list-runs --dag-id ong_pipeline
}

task_logs() {
    local task="${1:-extract_ong_data}"
    print_header "Logs da task: $task"
    docker exec airflow-webserver airflow tasks log ong_pipeline "$task" --num-logs 50
}

reset() {
    print_header "RESET COMPLETO (remover todos os dados)"
    print_error "Aviso: Isto irá deletar todos os dados do Postgres e Airflow!"
    read -p "Tem certeza? (s/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        print_info "Parando containers..."
        docker-compose down
        
        print_info "Removendo volumes..."
        docker volume rm pipeline_postgres_data pipeline_airflow_home 2>/dev/null || true
        
        print_success "Reset completo realizado"
        print_info "Execute 'start' para reiniciar do zero"
    else
        print_info "Reset cancelado"
    fi
}

health_check() {
    print_header "Health Check do Airflow"
    
    echo -n "Verificando PostgreSQL... "
    if docker exec airflow-postgres pg_isready -U airflow &>/dev/null; then
        print_success "PostgreSQL OK"
    else
        print_error "PostgreSQL FALHOU"
    fi
    
    echo -n "Verificando Airflow WebServer... "
    if curl -s http://localhost:8080/health >/dev/null 2>&1; then
        print_success "WebServer OK"
    else
        print_error "WebServer FALHOU"
    fi
    
    echo -n "Verificando Scheduler... "
    if docker exec airflow-scheduler airflow jobs check >/dev/null 2>&1; then
        print_success "Scheduler OK"
    else
        print_error "Scheduler pode estar indisponível"
    fi
}

list_dags() {
    print_header "DAGs disponíveis"
    docker exec airflow-webserver airflow dags list
}

clean_logs() {
    print_header "Limpando logs antigos do Airflow"
    docker exec airflow-webserver airflow logs delete --yes --logs-before-value 30
    print_success "Logs limpados"
}

# Menu de ajuda
usage() {
    cat << EOF
${BLUE}=== Gerenciador de Pipeline Airflow ===${NC}

Uso: $0 [COMANDO]

Comandos principais:
  ${GREEN}start${NC}              Iniciar todos os containers
  ${GREEN}stop${NC}               Parar todos os containers
  ${GREEN}restart${NC}            Reiniciar todos os containers
  
Monitoramento:
  ${GREEN}status${NC}             Exibir status dos containers
  ${GREEN}logs${NC}               Ver logs (padrão: todos)
  ${GREEN}logs${NC} [SERVICE]     Ver logs de um serviço específico
  ${GREEN}health-check${NC}       Verificar saúde dos serviços
  
Gerenciamento de DAG:
  ${GREEN}list-dags${NC}          Listar DAGs disponíveis
  ${GREEN}trigger${NC}            Acionar a DAG ong_pipeline
  ${GREEN}dag-status${NC}         Ver status das execuções
  ${GREEN}task-logs${NC} [TASK]   Ver logs de uma task específica
  
Acesso direto:
  ${GREEN}shell${NC} [CONTAINER]  Acessar shell de um container (padrão: airflow-webserver)
  ${GREEN}shell-postgres${NC}     Acessar PostgreSQL
  
Limpeza:
  ${GREEN}clean-logs${NC}         Limpar logs antigos
  ${GREEN}reset${NC}              RESET COMPLETO (deleta todos os dados)
  
Exemplos:
  $0 start                    # Inicia o Airflow
  $0 logs airflow-scheduler   # Ver logs do scheduler
  $0 trigger                  # Aciona a DAG
  $0 task-logs generate_transparency_scores  # Logs de task específica

EOF
}

# Executar comando
case "${1:-help}" in
    start)          start ;;
    stop)           stop ;;
    restart)        restart ;;
    status)         status ;;
    logs)           logs "$2" ;;
    shell)          shell "$2" ;;
    shell-postgres) shell_postgres ;;
    trigger)        trigger_dag ;;
    dag-status)     dag_status ;;
    task-logs)      task_logs "$2" ;;
    list-dags)      list_dags ;;
    health-check)   health_check ;;
    clean-logs)     clean_logs ;;
    reset)          reset ;;
    help|--help|-h) usage ;;
    *)
        print_error "Comando desconhecido: $1"
        echo ""
        usage
        exit 1
        ;;
esac
