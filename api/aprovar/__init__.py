"""POST /api/aprovar — a presidência confirma o envio do ciclo.

Corpo: {ciclo, codigo, nome_declarado, conferencia: {slug: true, ...}}

Só aceita se:
  - a conta está na configuração APROVADORES (senão: 403 + alerta à gestão);
  - o código é o do envio preparado AGORA, a validação está aprovada, não há
    bloqueio e o ciclo ainda não foi confirmado nem começou a ser enviado;
  - TODOS os PDFs da amostra foram abertos por esta conta (registro no servidor)
    e marcados como "confere";
  - há um nome declarado.

Grava aprovacao.json (uma única vez — gravação concorrente perde), enfileira
um e-mail por OSC e avisa presidência, transparência e comunicação.
"""
import json
import azure.functions as func

from shared_code import api_util as u
from shared_code import comum


def main(req: func.HttpRequest) -> func.HttpResponse:
    usuario = u.usuario(req)
    if not usuario:
        return u.erro('Não autenticado.', 401)
    if not u.e_aprovador(usuario):
        return u.negar_e_alertar(req, usuario, 'confirmar envio do ciclo')

    b = u.corpo(req)
    ciclo, codigo = b.get('ciclo'), b.get('codigo')
    nome = ' '.join(str(b.get('nome_declarado') or '').split())
    conferencia = b.get('conferencia') or {}
    if len(nome) < 5:
        return u.erro('Digite seu nome completo na declaração.', 400)

    try:
        cont = comum.container()
        estado = comum.estado_ciclo(cont, ciclo)
        motivos = comum.motivos_para_nao_aprovar(estado, codigo)
        if motivos:
            return u.erro('Não é possível confirmar.', 409, motivos=motivos)

        amostra = (estado['amostra'] or {}).get('oscs', [])
        pendentes = []
        for a in amostra:
            reg = comum.ler_json(cont, comum.caminho(ciclo, 'conferencia', usuario['id'], f'{a["slug"]}.json'))
            if conferencia.get(a['slug']) is not True or not reg or reg.get('codigo') != codigo:
                pendentes.append(a['nome'])
        if not amostra or pendentes:
            return u.erro('Abra e confira todos os PDFs da amostra antes de confirmar.', 409,
                          motivos=[f'Pendente: {n}' for n in pendentes] or ['Amostra ausente.'])

        acesso = comum.dados_de_acesso(req.headers)
        compat = comum.nomes_compativeis(nome, usuario.get('nome_conta', ''))
        aprovacao = {
            'ciclo': ciclo,
            'codigo_validacao': codigo,
            'nome_declarado': nome,
            'conta': usuario['email'],
            'conta_id': usuario['id'],
            'nome_titular_conta': usuario.get('nome_conta', ''),
            'nome_confere_com_titular': compat,
            'confirmado_em': acesso['registrado_em'],
            'acesso': acesso,
            'conferencia': [
                {'slug': a['slug'], 'nome': a['nome'], 'fixa': a.get('fixa', False),
                 'aberto_em': (comum.ler_json(cont, comum.caminho(ciclo, 'conferencia', usuario['id'],
                                                                   f'{a["slug"]}.json')) or {}).get('aberto_em')}
                for a in amostra],
            'total_emails': estado['manifesto']['total_emails'],
        }
        if not comum.gravar_json(cont, comum.caminho(ciclo, 'aprovacao.json'), aprovacao, sobrescrever=False):
            return u.erro('Este ciclo já foi confirmado.', 409)

        # Enfileira um e-mail por OSC
        q = comum.fila('envios')
        n = 0
        for e in estado['manifesto']['emails']:
            q.send_message(json.dumps({'ciclo': ciclo, 'slug': e['slug'], 'codigo': codigo}))
            n += 1

        _notificar(ciclo, estado['manifesto'], aprovacao, n)
        return u.resposta({'ok': True, 'enfileirados': n})
    except Exception as e:
        return u.falha('/api/aprovar', 'Erro ao confirmar o envio. Nada foi enviado se a confirmação não aparecer na página.', e)


def _notificar(ciclo, manifesto, a, n):
    acesso = a['acesso']
    if a['nome_confere_com_titular'] is False:
        aviso_nome = f'⚠️ DIFERE do titular da conta ({a["nome_titular_conta"]})'
    elif a['nome_confere_com_titular'] is None:
        aviso_nome = 'não verificável (a conta não informa o nome do titular)'
    else:
        aviso_nome = 'compatível com o titular da conta'
    conferencias = [f'{c["nome"]}{" (fixa)" if c["fixa"] else ""} — PDF aberto em '
                    f'{comum.formatar_brt(c["aberto_em"]) if c["aberto_em"] else "?"}' for c in a['conferencia']]
    teste = ' [ENSAIO]' if manifesto.get('modo_teste') else ''
    comum.enviar_email(
        comum.destinatarios_gestao(),
        f'[etransparente]{teste} Envio do ciclo {manifesto.get("rotulo", ciclo)} CONFIRMADO por {a["nome_declarado"]}',
        comum.html_notificacao(
            f'Envio do ciclo {manifesto.get("rotulo", ciclo)} confirmado',
            [('Nome declarado', a['nome_declarado']),
             ('Nome × titular da conta', aviso_nome),
             ('Conta usada', a['conta']),
             ('Data/hora', comum.formatar_brt(a['confirmado_em'])),
             ('IP', acesso['ip'] or 'indisponível'),
             ('Local aproximado', acesso['local_aproximado']),
             ('Provedor', acesso['provedor']),
             ('Navegador', acesso['navegador']),
             ('Código de validação', manifesto.get('codigo_curto', '')),
             ('E-mails enfileirados', n)],
            rodape='O envio às OSCs começou. Se você não reconhece esta confirmação, reporte um erro '
                   'em /envio imediatamente: o bloqueio interrompe os e-mails ainda não enviados.',
            itens=['Conferência por amostra:'] + conferencias))
