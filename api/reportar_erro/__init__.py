"""POST /api/reportar-erro {ciclo, osc, campo, descricao} — BLOQUEIA o envio do ciclo.

Qualquer pessoa com acesso ao dashboard pode bloquear (bloquear é sempre o
lado seguro). O desbloqueio é só técnico: regerar o ciclo (novo código, nova
conferência) ou `scripts/desbloquear_envio.py` com justificativa registrada.

Se o envio já tiver começado, a Function para de enviar os e-mails restantes.
"""
import logging

import azure.functions as func

from shared_code import api_util as u
from shared_code import comum

CAMPOS = {'views': 'Visualizações', 'nota': 'Nota', 'classificacao': 'Classificação',
          'cadastro': 'Dados cadastrais', 'pdf': 'PDF não abre / ilegível', 'outro': 'Outro'}


def main(req: func.HttpRequest) -> func.HttpResponse:
    usuario = u.usuario(req)
    if not usuario:
        return u.erro('Não autenticado.', 401)
    b = u.corpo(req)
    ciclo = b.get('ciclo')
    osc = str(b.get('osc') or '').strip()[:200]
    campo = b.get('campo') if b.get('campo') in CAMPOS else 'outro'
    descricao = str(b.get('descricao') or '').strip()[:2000]
    if not ciclo or not osc or len(descricao) < 5:
        return u.erro('Informe a OSC e descreva o problema.', 400)

    try:
        cont = comum.container()
        caminho = comum.caminho(ciclo, 'bloqueio.json')
        acesso = comum.dados_de_acesso(req.headers)
        reporte = {'osc': osc, 'campo': CAMPOS[campo], 'descricao': descricao,
                   'conta': usuario['email'], 'registrado_em': acesso['registrado_em'], 'acesso': acesso}
        bloqueio = comum.ler_json(cont, caminho) or {'ciclo': ciclo, 'bloqueado_em': acesso['registrado_em'],
                                                     'reportes': []}
        bloqueio['reportes'].append(reporte)
        comum.gravar_json(cont, caminho, bloqueio)

        estado = comum.estado_ciclo(cont, ciclo)
        rotulo = (estado['manifesto'] or {}).get('rotulo', ciclo)
        ja_enviados = comum.resumir_resultado(estado)['enviados']
        _notificar_tecnico(cont, ciclo, rotulo, reporte, estado, ja_enviados)
        comum.enviar_email(
            comum.destinatarios_gestao(),
            f'[etransparente] Envio do ciclo {rotulo} BLOQUEADO — erro reportado em {osc}',
            comum.html_notificacao(
                f'Envio do ciclo {rotulo} bloqueado',
                [('OSC', osc), ('Campo', reporte['campo']), ('Reportado por', usuario['email']),
                 ('Data/hora', comum.formatar_brt(reporte['registrado_em'])),
                 ('E-mails já enviados antes do bloqueio', ja_enviados)],
                rodape='Nenhum novo e-mail será enviado até a equipe técnica analisar. '
                       'A equipe técnica foi notificada.', cor='#b45309'))
        return u.resposta({'ok': True})
    except Exception:
        logging.exception('Erro em /api/reportar-erro')
        return u.erro('Não foi possível registrar o erro. Avise a equipe técnica diretamente.', 500)


def _notificar_tecnico(cont, ciclo, rotulo, r, estado, ja_enviados):
    # Valores que o sistema tinha para a OSC, para a investigação
    rel = comum.ler_json(cont, f'gold/{ciclo}/relatorios.json') or {}
    dados = next((x for x in rel.get('relatorios', []) if x.get('nome') == r['osc']), {})
    linhas = [('OSC', r['osc']), ('Campo', r['campo']), ('Descrição', r['descricao']),
              ('Reportado por', r['conta']), ('Data/hora', comum.formatar_brt(r['registrado_em'])),
              ('IP / local', f'{r["acesso"]["ip"]} — {r["acesso"]["local_aproximado"]}'),
              ('Código de validação', (estado['manifesto'] or {}).get('codigo_curto', '')),
              ('Envio confirmado?', 'sim' if estado['aprovacao'] else 'não'),
              ('E-mails já enviados', ja_enviados)]
    if dados:
        linhas += [('Sistema: visualizações', dados.get('views_total')),
                   ('Sistema: nota', f'{dados.get("nota_final")}/{dados.get("max_nota")} ({dados.get("classificacao")})'),
                   ('Sistema: PDF', dados.get('pdf')), ('Sistema: hash do PDF', dados.get('pdf_sha256', '')[:16])]
    comum.enviar_email(
        comum.destinatario_tecnico(),
        f'[etransparente][TÉCNICO] Erro reportado no ciclo {rotulo} — {r["osc"]}',
        comum.html_notificacao(
            'Erro reportado — investigação técnica', linhas,
            rodape='Para liberar: corrigir e regerar o ciclo (preparar_envios.py — novo código e nova conferência) '
                   'ou, se for falso alarme, scripts/desbloquear_envio.py --ciclo ... --motivo "...".',
            cor='#b91c1c'))
