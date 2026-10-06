"""
DAG mensal do etransparente — gera, valida e PREPARA o envio. Não envia.

Fluxo (dia 3, 11:30 UTC):
  validar_data → extração → scores → GA4 → PDFs → upload → silver → doc_changes
  → validar_ciclo → preparar_envios

O envio às OSCs acontece fora desta DAG: a presidência confere uma amostra em
dashboard.etransparente.org/envio e confirma; uma Azure Function envia exatamente
os e-mails preparados aqui (ver claude/PLANO_VALIDACAO_E_ENVIO.md no Project).

Ciclo
-----
O ciclo é decidido UMA vez, aqui, e passado como --ciclo a todos os scripts.
Nenhum script calcula data sozinho (causa raiz dos incidentes de set e out/2026).

- Execução agendada de 03/11 → data_interval_start = 03/10 → ciclo 2026-10.
- Reprocessar um ciclo antigo de propósito:
    airflow dags trigger ong_pipeline --conf '{"ciclo": "2026-09", "reprocessar": true}'
"""

import os
import subprocess
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

BASE = os.environ.get('AIRFLOW_HOME', '/home/airflow')
SCRIPTS = os.path.join(BASE, 'scripts')

default_args = {
    'owner': 'data-team',
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'email': ['transparencia@direitocoletivo.org.br', 'comunicacao@direitocoletivo.org.br'],
    'email_on_failure': True,
    'email_on_retry': False,
}

dag = DAG(
    'ong_pipeline',
    default_args=default_args,
    description='Gera, valida e prepara o envio mensal dos relatórios de transparência',
    # Dia 3 às 11:30 UTC (08:30 BRT): o ciclo fechou há 48h+, tempo para o GA4
    # consolidar os últimos dias do mês.
    schedule_interval='30 11 3 * *',
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=['ong', 'etransparente', 'pipeline'],
)


def resolver_ciclo(context) -> tuple[str, bool]:
    """Ciclo desta execução: conf explícita (reprocessamento) ou o intervalo do Airflow."""
    import sys
    sys.path.insert(0, SCRIPTS)
    from ciclo import ciclo_do_intervalo, parse_ciclo

    conf = (context.get('dag_run').conf or {}) if context.get('dag_run') else {}
    if conf.get('ciclo'):
        parse_ciclo(conf['ciclo'])
        return conf['ciclo'], bool(conf.get('reprocessar'))
    return ciclo_do_intervalo(context['data_interval_start']), False


def rodar(script: str, args: list[str], context, env_extra: dict | None = None):
    """Executa um script do pipeline sempre com --ciclo, a partir de /home/airflow."""
    ciclo, _ = resolver_ciclo(context)
    caminho = os.path.join(SCRIPTS, script)
    cmd = ['python', caminho, '--ciclo', ciclo, *args]
    env = os.environ.copy()
    env.update(env_extra or {})
    print(f'[ciclo {ciclo}] $ {" ".join(cmd)}')
    result = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, env=env)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        detalhe = (result.stderr.strip() or result.stdout.strip())[-3000:]
        raise Exception(f'{script} falhou (código {result.returncode}) no ciclo {ciclo}:\n{detalhe}')
    return result.stdout


def rodar_sem_ciclo(script: str):
    """Extração e scores não dependem de data: leem o estado atual do site."""
    def _run(**context):
        caminho = os.path.join(SCRIPTS, script)
        result = subprocess.run(['python', caminho], cwd=BASE, capture_output=True, text=True)
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
            detalhe = (result.stderr.strip() or result.stdout.strip())[-3000:]
            raise Exception(f'{script} falhou (código {result.returncode}):\n{detalhe}')
    return _run


def task_validar_data(**context):
    ciclo, reprocessar = resolver_ciclo(context)
    return rodar('ciclo.py', ['--reprocessar'] if reprocessar else [], context)


def task_script(script: str, extra_args: list[str] | None = None, repassa_reprocessar: bool = False):
    def _run(**context):
        args = list(extra_args or [])
        if repassa_reprocessar and resolver_ciclo(context)[1]:
            args.append('--reprocessar')
        return rodar(script, args, context)
    return _run


validar_data_task = PythonOperator(
    task_id='validar_data', python_callable=task_validar_data, retries=0, dag=dag)
extract_task = PythonOperator(
    task_id='extract_ong_data', python_callable=rodar_sem_ciclo('ong_extractor.py'), dag=dag)
scores_task = PythonOperator(
    task_id='generate_transparency_scores',
    python_callable=rodar_sem_ciclo('generate_transparency_scores.py'), dag=dag)
fetch_ga4_task = PythonOperator(
    task_id='fetch_ga4_views', python_callable=task_script('ga4/oscs_monthly_views.py'), dag=dag)
dashboard_task = PythonOperator(
    task_id='generate_dashboards', python_callable=task_script('dash.py'), dag=dag)
upload_task = PythonOperator(
    task_id='upload_to_azure', python_callable=task_script('upload_to_azure.py'), dag=dag)
silver_task = PythonOperator(
    task_id='generate_silver', python_callable=task_script('generate_silver.py'), dag=dag)
doc_changes_task = PythonOperator(
    task_id='detect_doc_changes', python_callable=task_script('detect_doc_changes.py'), dag=dag)
# Validação e preparação não têm retry: se bloquearem, é por dado errado —
# repetir não resolve, e o e-mail de falha avisa a equipe.
validar_ciclo_task = PythonOperator(
    task_id='validar_ciclo', python_callable=task_script('validar_ciclo.py', repassa_reprocessar=True), retries=0, dag=dag)
preparar_envios_task = PythonOperator(
    task_id='preparar_envios', python_callable=task_script('preparar_envios.py'), retries=0, dag=dag)

(validar_data_task >> extract_task >> scores_task >> fetch_ga4_task >> dashboard_task
 >> upload_task >> silver_task >> doc_changes_task >> validar_ciclo_task >> preparar_envios_task)
