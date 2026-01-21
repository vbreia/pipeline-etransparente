#!/bin/bash
# Entrypoint script para inicializar e executar o Airflow com Docker

set -e

AIRFLOW_HOME="${AIRFLOW_HOME:-/home/airflow}"
AIRFLOW__CORE__SQL_ALCHEMY_CONN="${AIRFLOW__CORE__SQL_ALCHEMY_CONN:-postgresql+psycopg2://airflow:airflow@postgres:5432/airflow}"

echo "=== Airflow Pipeline Startup ==="
echo "AIRFLOW_HOME: $AIRFLOW_HOME"
echo "Initializing database..."

# Upgrade Airflow database
airflow db upgrade

# Create default admin user if not exists
echo "Creating admin user..."
airflow users create \
    --firstname admin \
    --lastname user \
    --username admin \
    --role Admin \
    --email admin@example.com \
    --password admin 2>/dev/null || true

echo "=== Setup Complete ==="
echo ""
echo "Airflow WebUI: http://localhost:8080"
echo "Username: admin"
echo "Password: admin"
echo ""

exec "$@"
