FROM python:3.11-slim

# Install system dependencies (minimal set)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-client \
    git \
    curl \
    pkg-config \
    libcairo2-dev \
    && rm -rf /var/lib/apt/lists/*

# Create airflow user and directory
RUN useradd -ms /bin/bash airflow && \
    mkdir -p /home/airflow && \
    chown -R airflow:airflow /home/airflow

WORKDIR /home/airflow

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install Airflow with base provider packages
RUN pip install --no-cache-dir \
    apache-airflow==2.7.3 \
    apache-airflow-providers-postgres==5.11.3 \
    apache-airflow-providers-http==4.12.0 \
    psycopg2-binary \
    flask-session \
    requests \
    beautifulsoup4

# Switch to airflow user
USER airflow

# Set environment variables
ENV AIRFLOW_HOME=/home/airflow
ENV PYTHONUNBUFFERED=1

# Expose Airflow webserver port
EXPOSE 8080

CMD ["airflow", "webserver"]
