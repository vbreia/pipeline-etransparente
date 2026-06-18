"""
Pipeline DAG para orquestração dos scripts de extração e geração de dashboards de ONGs.

Pipeline:
1. ong_extractor.py - Extrai dados de ONGs do site etransparente.org
2. generate_transparency_scores.py - Calcula pontuações de transparência
3. dash.py - Gera dashboards HTML/PDF por ONG
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago
import os
import sys
import subprocess

# Configuração do DAG
default_args = {
    'owner': 'data-team',
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'email': ['transparencia@direitocoletivo.org.br'],
    'email_on_failure': True,
    'email_on_retry': False,
}

dag = DAG(
    'ong_pipeline',
    default_args=default_args,
    description='Pipeline para extração e processamento de dados de ONGs',
    # Executa mensalmente, no dia 1 às 02:00 UTC
    schedule_interval='0 2 1 * *',
    start_date=days_ago(1),
    catchup=False,
    tags=['ong', 'etransparente', 'pipeline'],
)


def run_ong_extractor(**context):
    """Executa o script de extração de dados de ONGs"""
    script_path = os.path.join(os.environ.get('AIRFLOW_HOME', '/home/airflow'), 
                               'scripts', 'ong_extractor.py')
    
    result = subprocess.run(
        ['python', script_path],
        cwd=os.path.dirname(os.path.dirname(script_path)),
        capture_output=True,
        text=True
    )
    
    print(f"STDOUT: {result.stdout}")
    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        raise Exception(f"ong_extractor.py failed with return code {result.returncode}")
    
    return result.stdout


def run_transparency_scores(**context):
    """Executa o script de geração de pontuações de transparência"""
    script_path = os.path.join(os.environ.get('AIRFLOW_HOME', '/home/airflow'), 
                               'scripts', 'generate_transparency_scores.py')
    
    result = subprocess.run(
        ['python', script_path],
        cwd=os.path.dirname(os.path.dirname(script_path)),
        capture_output=True,
        text=True
    )
    
    print(f"STDOUT: {result.stdout}")
    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        raise Exception(f"generate_transparency_scores.py failed with return code {result.returncode}")
    
    return result.stdout


def run_dashboard_generator(**context):
    """Executa o script de geração de dashboards"""
    script_path = os.path.join(os.environ.get('AIRFLOW_HOME', '/home/airflow'), 
                               'scripts', 'dash.py')
    
    result = subprocess.run(
        ['python', script_path],
        cwd=os.path.dirname(os.path.dirname(script_path)),
        capture_output=True,
        text=True
    )
    
    print(f"STDOUT: {result.stdout}")
    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        raise Exception(f"dash.py failed with return code {result.returncode}")
    
    return result.stdout


def run_fetch_ga4_views(**context):
    """Executa o script de busca de visualizações GA4"""
    script_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'ga4', 'oscs_monthly_views.py')
    script_path = os.path.abspath(script_path)
    result = subprocess.run(
        ['python', script_path],
        capture_output=True, text=True,
        cwd='/home/airflow'
    )
    if result.returncode != 0:
        raise Exception(f"fetch_ga4_views falhou:\n{result.stderr}")
    print(result.stdout)


# Tasks
extract_task = PythonOperator(
    task_id='extract_ong_data',
    python_callable=run_ong_extractor,
    dag=dag,
)

scores_task = PythonOperator(
    task_id='generate_transparency_scores',
    python_callable=run_transparency_scores,
    dag=dag,
)

fetch_ga4_task = PythonOperator(
    task_id='fetch_ga4_views',
    python_callable=run_fetch_ga4_views,
    dag=dag,
)

dashboard_task = PythonOperator(
    task_id='generate_dashboards',
    python_callable=run_dashboard_generator,
    dag=dag,
)

def run_upload_to_azure(**context):
    """Executa o upload dos outputs para o Azure Data Lake Gen2"""
    script_path = '/home/airflow/scripts/upload_to_azure.py'
    result = subprocess.run(
        ['python', script_path],
        capture_output=True, text=True,
        cwd='/home/airflow'
    )
    if result.returncode != 0:
        raise Exception(f'upload_to_azure falhou:\n{result.stderr}')
    print(result.stdout)

upload_task = PythonOperator(
    task_id='upload_to_azure',
    python_callable=run_upload_to_azure,
    dag=dag,
)

# Define task dependencies
extract_task >> scores_task >> fetch_ga4_task >> dashboard_task >> upload_task
