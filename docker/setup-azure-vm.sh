#!/bin/bash
# Setup completo para VM Azure Ubuntu
# Execute como usuário normal (não root)

set -e

echo "╔═══════════════════════════════════════════════════════╗"
echo "║     Setup Pipeline - Azure VM Ubuntu                 ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Verificar se está rodando no Azure
if [ -f /var/lib/cloud/instance/vendor-data.txt ]; then
    echo "✓ Detectada VM Azure"
else
    echo "⚠️  Esta VM pode não ser Azure. Continue? (y/n)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi
echo ""

# Atualizar sistema
echo "📦 Atualizando sistema..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
echo "✓ Sistema atualizado"
echo ""

# Instalar dependências básicas
echo "📦 Instalando dependências..."
sudo apt-get install -y -qq \
    curl \
    wget \
    git \
    ca-certificates \
    gnupg \
    lsb-release
echo "✓ Dependências instaladas"
echo ""

# Instalar Docker
echo "🐳 Instalando Docker..."
if command -v docker &> /dev/null; then
    echo "✓ Docker já instalado ($(docker --version))"
else
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
    echo "✓ Docker instalado"
fi
echo ""

# Adicionar usuário ao grupo docker
echo "👤 Configurando permissões Docker..."
sudo usermod -aG docker $USER
echo "✓ Usuário $USER adicionado ao grupo docker"
echo ""

# Instalar Docker Compose
echo "🐳 Instalando Docker Compose..."
if docker compose version &> /dev/null; then
    echo "✓ Docker Compose já instalado ($(docker compose version))"
else
    sudo apt-get install -y docker-compose-plugin
    echo "✓ Docker Compose instalado"
fi
echo ""

# Verificar RAM
echo "💾 Verificando recursos..."
TOTAL_RAM=$(free -g | awk '/^Mem:/{print $2}')
if [ "$TOTAL_RAM" -lt 4 ]; then
    echo "⚠️  RAM insuficiente: ${TOTAL_RAM}GB (mínimo 4GB)"
    echo "   Criando swap de 4GB..."
    
    if [ ! -f /swapfile ]; then
        sudo fallocate -l 4G /swapfile
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
        sudo swapon /swapfile
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
        echo "✓ Swap de 4GB criado"
    else
        echo "✓ Swap já existe"
    fi
else
    echo "✓ RAM: ${TOTAL_RAM}GB (suficiente)"
fi
echo ""

# Verificar espaço em disco
DISK_FREE=$(df -BG / | awk 'NR==2 {print $4}' | sed 's/G//')
if [ "$DISK_FREE" -lt 10 ]; then
    echo "⚠️  Espaço em disco baixo: ${DISK_FREE}GB livre"
    echo "   Recomendado: 10GB+ livre"
else
    echo "✓ Espaço em disco: ${DISK_FREE}GB livre"
fi
echo ""

# Configurar firewall (se UFW estiver ativo)
if sudo ufw status | grep -q "Status: active"; then
    echo "🔥 Configurando firewall UFW..."
    sudo ufw allow 8080/tcp
    sudo ufw allow 22/tcp
    echo "✓ Portas 8080 e 22 liberadas"
else
    echo "ℹ️  UFW não está ativo"
fi
echo ""

# Clonar repositório (se ainda não existe)
echo "📥 Preparando código..."
REPO_DIR="pipeline-etransparente"
if [ -d "$REPO_DIR" ]; then
    echo "✓ Repositório já existe em ./$REPO_DIR"
    cd "$REPO_DIR"
    git pull
else
    echo "📥 Clonando repositório..."
    git clone https://github.com/vbreia/pipeline-etransparente.git
    cd "$REPO_DIR"
    echo "✓ Repositório clonado"
fi
echo ""

# Dar permissão de execução nos scripts
chmod +x quick-start.sh 2>/dev/null || true
chmod +x manage-pipeline.sh 2>/dev/null || true

echo "╔═══════════════════════════════════════════════════════╗"
echo "║            ✓ SETUP AZURE VM CONCLUÍDO                ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""
echo "📍 Próximos passos:"
echo ""
echo "1. IMPORTANTE - Aplicar permissões Docker:"
echo "   newgrp docker"
echo "   (ou faça logout e login novamente)"
echo ""
echo "2. Executar pipeline:"
echo "   ./docker/quick-start.sh"
echo ""
echo "3. Configurar NSG no Portal Azure:"
echo "   • Acesse: VM → Networking → Add inbound port rule"
echo "   • Port: 8080"
echo "   • Protocol: TCP"
echo "   • Source: Seu IP público"
echo ""
echo "4. Acessar Airflow:"
echo "   http://$(curl -s ifconfig.me):8080"
echo "   Username: admin"
echo "   Password: admin"
echo ""
echo "💡 Dica: Salve seu IP público para acesso futuro"
echo "   echo \"\$(curl -s ifconfig.me)\" > ~/my-ip.txt"
echo ""
