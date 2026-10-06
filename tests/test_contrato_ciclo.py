"""
Contrato: NENHUM script calcula o ciclo pela data do sistema; todos exigem --ciclo.

Por que este teste existe: em 01/09/2026 o "mês padrão" foi corrigido em 4
scripts e esquecido no 5º (oscs_monthly_views.py). Em 01/10/2026 os PDFs
saíram com 0 visualizações. Este teste lê o código-fonte (sem executar nada) e
falha se qualquer script voltar a calcular ciclo sozinho — uma correção
parcial quebra o GitHub Actions antes de chegar à VM.
"""
import ast
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / 'scripts'

# Scripts que trabalham "por ciclo" e portanto precisam receber --ciclo
SCRIPTS_COM_CICLO = [
    'ga4/oscs_monthly_views.py',
    'dash.py',
    'upload_to_azure.py',
    'generate_silver.py',
    'detect_doc_changes.py',
    'validar_ciclo.py',
    'preparar_envios.py',
    'send_reports.py',
]

# Funções que já existiram e calculavam o ciclo pelo relógio
NOMES_PROIBIDOS = {
    'default_current_month', 'default_previous_month', '_mes_anterior_ao_atual',
}

# Scripts de uso único (limpezas pontuais de incidentes passados) ficam fora
IGNORAR = {'limpar_ciclo_agosto.py', 'limpar_ciclo_setembro.py', 'limpar_ciclo_setembro_v2.py'}


def _arvore(rel):
    return ast.parse((SCRIPTS / rel).read_text(encoding='utf-8'))


def _exige_ciclo(tree) -> bool:
    for no in ast.walk(tree):
        if isinstance(no, ast.Call):
            f = no.func
            nome = f.id if isinstance(f, ast.Name) else getattr(f, 'attr', '')
            if nome == 'adicionar_argumento_ciclo':
                return True
            if nome == 'add_argument' and any(
                isinstance(a, ast.Constant) and a.value == '--ciclo' for a in no.args
            ) and any(
                k.arg == 'required' and isinstance(k.value, ast.Constant) and k.value.value is True
                for k in no.keywords
            ):
                return True
    return False


def _todos_scripts():
    return [p for p in SCRIPTS.rglob('*.py') if p.name not in IGNORAR]


@pytest.mark.parametrize('rel', SCRIPTS_COM_CICLO)
def test_script_exige_ciclo(rel):
    assert _exige_ciclo(_arvore(rel)), f'{rel} precisa exigir --ciclo (use adicionar_argumento_ciclo)'


def _e_relogio(no) -> bool:
    """date.today() / datetime.now(...) — inclusive encadeado com .replace()/.astimezone()."""
    while isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) \
            and no.func.attr in ('replace', 'astimezone'):
        no = no.func.value
    return isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr in ('today', 'now')


@pytest.mark.parametrize('caminho', _todos_scripts(), ids=lambda p: str(p.relative_to(SCRIPTS)))
def test_nenhum_calculo_de_ciclo_pelo_relogio(caminho):
    tree = ast.parse(caminho.read_text(encoding='utf-8'))
    # variáveis que guardam a data do sistema (ex.: hoje = date.today())
    do_relogio = {
        alvo.id for no in ast.walk(tree) if isinstance(no, ast.Assign) and _e_relogio(no.value)
        for alvo in no.targets if isinstance(alvo, ast.Name)
    }
    for no in ast.walk(tree):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert no.name not in NOMES_PROIBIDOS, f'{caminho.name}: função proibida {no.name}()'
        # padrão proibido: <today()|now()>.strftime('%Y-%m')
        if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                and no.func.attr == 'strftime' and no.args
                and isinstance(no.args[0], ast.Constant) and no.args[0].value == '%Y-%m'):
            alvo = no.func.value
            via_variavel = isinstance(alvo, ast.Name) and alvo.id in do_relogio
            assert not (_e_relogio(alvo) or via_variavel), (
                f'{caminho.name}:{no.lineno} calcula ciclo a partir do relógio — '
                f'receba --ciclo da DAG (scripts/ciclo.py)'
            )


def test_dag_contrato():
    fonte = (RAIZ / 'dags' / 'ong_pipeline.py').read_text(encoding='utf-8')
    tree = ast.parse(fonte)
    assert "'30 11 3 * *'" in fonte, 'DAG deve rodar no dia 3 às 11:30 UTC'
    assert 'send_reports' not in fonte, 'O envio não pode estar na DAG — só depois da aprovação em /envio'
    assert 'days_ago' not in fonte, 'start_date deve ser fixo (days_ago recalcula a cada boot)'
    # Todo script com ciclo usado pela DAG passa por task_script (que injeta --ciclo)
    chamados = {
        a.value for no in ast.walk(tree) if isinstance(no, ast.Call)
        and getattr(no.func, 'id', '') == 'task_script'
        for a in no.args[:1] if isinstance(a, ast.Constant)
    }
    esperados = set(SCRIPTS_COM_CICLO) - {'send_reports.py'}
    assert esperados <= chamados, f'Scripts sem --ciclo na DAG: {esperados - chamados}'
    # E a primeira task é a validação de data
    assert 'validar_data_task >> extract_task' in fonte.replace('(', '').replace('\n', ' ')
