#!/usr/bin/env bash
# Publica o dashboard (dashboard/) + a API de envio (api/) no Static Web App.
#
# Por que este script existe: o `swa deploy` envia o código da API mas NÃO instala
# api/requirements.txt. Sem isso a API quebra com
#   ModuleNotFoundError: No module named 'azure.storage'
# Aqui os pacotes são instalados em api/.python_packages (Linux, Python 3.11 — o
# ambiente do Azure, não o da sua máquina) e sobem junto com o código.
#
# Uso (na raiz do repositório):
#   read -s SWA_CLI_DEPLOYMENT_TOKEN   # cole o token + Enter (não aparece)
#   export SWA_CLI_DEPLOYMENT_TOKEN
#   ./envio/publicar_dashboard.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${SWA_CLI_DEPLOYMENT_TOKEN:-}" ]; then
  echo "ERRO: defina SWA_CLI_DEPLOYMENT_TOKEN antes (ver comentário no topo)." >&2
  exit 1
fi

echo "==> Conferindo cópias de envio/comum.py"
python3 envio/sincronizar_copias.py

echo "==> Instalando pacotes da API para Linux / Python 3.11"
rm -rf api/.python_packages
grep -v '^azure-functions' api/requirements.txt > /tmp/req_api_swa.txt   # azure-functions o Azure já fornece
pip install --quiet --target api/.python_packages/lib/site-packages \
  --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 \
  --python-version 3.11 --implementation cp --only-binary=:all: \
  -r /tmp/req_api_swa.txt

echo "==> Publicando"
swa deploy ./dashboard --api-location ./api --api-language python --api-version 3.11 --env production

echo "==> Pronto. Confira https://dashboard.etransparente.org/envio"
