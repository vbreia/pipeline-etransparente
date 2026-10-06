"""GET /api/status[?ciclo=YYYY-MM] — tudo que a página /envio precisa mostrar.

Não devolve endereços de e-mail das OSCs nem o HTML dos e-mails.
"""
import azure.functions as func

from shared_code import api_util as u
from shared_code import comum


def main(req: func.HttpRequest) -> func.HttpResponse:
    usuario = u.usuario(req)
    if not usuario:
        return u.erro('Não autenticado.', 401)
    try:
        cont = comum.container()
        ciclo = req.params.get('ciclo') or (comum.ciclos_preparados(cont) or [None])[-1]
        if not ciclo:
            return u.resposta({'ciclo': None, 'usuario': _usuario(usuario)})
        estado = comum.estado_ciclo(cont, ciclo)
        m, v = estado['manifesto'] or {}, estado['validacao'] or {}
        codigo = m.get('codigo_validacao')

        abertos = {}
        if u.e_aprovador(usuario):
            prefixo = comum.caminho(ciclo, 'conferencia', usuario['id'] + '/')
            for b in cont.list_blobs(name_starts_with=prefixo):
                reg = comum.ler_json(cont, b.name) or {}
                if reg.get('codigo') == codigo:
                    abertos[reg['slug']] = comum.formatar_brt(reg['aberto_em'])

        amostra = []
        for a in (estado['amostra'] or {}).get('oscs', []):
            amostra.append({k: a.get(k) for k in ('slug', 'nome', 'fixa', 'views_total', 'media_diaria',
                                                  'nota_final', 'max_nota', 'nota_exibida', 'classificacao')}
                           | {'aberto_em': abertos.get(a['slug'])})

        aprov = estado['aprovacao']
        bloq = estado['bloqueio']
        nomes = sorted({e['nome'] for e in m.get('emails', [])} | set(m.get('sem_email', [])))
        return u.resposta({
            'ciclo': ciclo,
            'rotulo': m.get('rotulo', ciclo),
            'ciclos_disponiveis': comum.ciclos_preparados(cont),
            'usuario': _usuario(usuario),
            'validacao': {
                'status': v.get('status'),
                'validado_em': comum.formatar_brt(v['validado_em']) if v.get('validado_em') else None,
                'resumo': v.get('resumo', {}),
                'verificacoes': v.get('verificacoes', []),
            },
            'envio': {
                'preparado_em': comum.formatar_brt(m['preparado_em']) if m.get('preparado_em') else None,
                'codigo_validacao': codigo,
                'codigo_curto': m.get('codigo_curto'),
                'total_oscs': m.get('total_oscs'),
                'total_emails': m.get('total_emails'),
                'sem_email': m.get('sem_email', []),
                'modo_teste': m.get('modo_teste', False),
                'destino_teste': m.get('destino_teste'),
            },
            'amostra': amostra,
            'aprovacao': aprov and {
                'nome_declarado': aprov.get('nome_declarado'),
                'conta': aprov.get('conta'),
                'confirmado_em': comum.formatar_brt(aprov['confirmado_em']),
            },
            'bloqueio': bloq and {
                'reportes': [{'osc': r.get('osc'), 'campo': r.get('campo'), 'descricao': r.get('descricao'),
                              'conta': r.get('conta'), 'em': comum.formatar_brt(r['registrado_em'])}
                             for r in bloq.get('reportes', [])],
            },
            'andamento': comum.resumir_resultado(estado) | {'concluido': bool(estado['resultado'])},
            'pode_aprovar_motivos': comum.motivos_para_nao_aprovar(estado, codigo) if codigo else [],
            'oscs': nomes,
        })
    except Exception as e:
        return u.falha('/api/status', 'Erro ao carregar o estado do envio.', e)


def _usuario(p):
    return {'email': p['email'], 'nome_conta': p.get('nome_conta', ''), 'aprovador': u.e_aprovador(p)}
