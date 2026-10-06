"""
Function de envio (Azure Functions, Python, modelo v2) — `etransparente-envio`.

Roda FORA da VM. Envia exatamente os e-mails que a DAG preparou e a
presidência confirmou. Não gera nem recalcula nada.

Gatilhos:
  envios         uma mensagem = um e-mail {ciclo, slug, codigo}
  envios-poison  mensagens que falharam 5 vezes (criada automaticamente pela plataforma)

Antes de CADA e-mail, confere:
  - aprovação existe e é para o mesmo código de validação do manifesto
    (senão a mensagem é ignorada, sem alterar o estado do ciclo);
  - não há bloqueio (erro reportado) — se houver, não envia;
  - o e-mail preparado e o PDF não foram alterados (hash igual ao do manifesto);
  - este e-mail ainda não foi enviado (não duplica em reprocessamentos).

Ao terminar o último e-mail do ciclo, grava resultado.json e avisa a gestão.
"""
import json
import logging

import azure.functions as func

import comum

app = func.FunctionApp()


@app.queue_trigger(arg_name='msg', queue_name='envios', connection='DADOS_STORAGE')
def enviar(msg: func.QueueMessage) -> None:
    pedido = json.loads(msg.get_body().decode('utf-8'))
    processar(pedido, tentativa=msg.dequeue_count or 1)


@app.queue_trigger(arg_name='msg', queue_name='envios-poison', connection='DADOS_STORAGE')
def desistir(msg: func.QueueMessage) -> None:
    """Esgotadas as tentativas: marca a falha definitiva e fecha o ciclo se for o último."""
    pedido = json.loads(msg.get_body().decode('utf-8'))
    cont = comum.container()
    st = comum.ler_json(cont, _status_path(pedido)) or {}
    if st.get('estado') == 'enviado':
        return
    _gravar_status(cont, pedido, 'falhou_definitivo', nome=st.get('nome', ''),
                   erro=st.get('erro', 'tentativas esgotadas'))
    concluir_se_terminou(cont, pedido['ciclo'])


def processar(pedido: dict, tentativa: int = 1, cont=None, enviar_email=None) -> str:
    """Retorna o estado final gravado. Exceção = erro temporário (a fila tenta de novo)."""
    cont = cont or comum.container()
    enviar_email = enviar_email or comum.enviar_email
    ciclo, slug, codigo = pedido['ciclo'], pedido['slug'], pedido['codigo']

    atual = comum.ler_json(cont, _status_path(pedido)) or {}
    if atual.get('estado') == 'enviado':
        logging.info('%s/%s já enviado — ignorando mensagem repetida', ciclo, slug)
        return 'enviado'

    manifesto = comum.ler_json(cont, comum.caminho(ciclo, 'manifesto.json')) or {}
    aprovacao = comum.ler_json(cont, comum.caminho(ciclo, 'aprovacao.json')) or {}
    item = next((e for e in manifesto.get('emails', []) if e['slug'] == slug), None)
    nome = (item or {}).get('nome', slug)

    def final(estado, erro=''):
        _gravar_status(cont, pedido, estado, nome=nome, erro=erro, tentativa=tentativa)
        concluir_se_terminou(cont, ciclo)
        return estado

    if not item or not aprovacao or manifesto.get('codigo_validacao') != codigo \
            or aprovacao.get('codigo_validacao') != codigo:
        # Mensagem sem aprovação válida (avulsa, forjada ou de uma preparação antiga):
        # não envia e NÃO altera o estado do ciclo — senão travaria a aprovação legítima.
        logging.warning('Mensagem ignorada %s/%s: sem aprovação válida para o código %s', ciclo, slug, codigo[:8])
        return 'ignorado'
    if comum.ler_json(cont, comum.caminho(ciclo, 'bloqueio.json')):
        return final('suspenso_por_bloqueio', 'erro reportado — envio bloqueado')

    email = comum.ler_json(cont, comum.caminho(ciclo, 'emails', f'{slug}.json'))
    if not email:
        return final('falhou_definitivo', 'e-mail preparado não encontrado')
    sem_hash = {k: v for k, v in email.items() if k != 'email_sha256'}
    if comum.sha256_json(sem_hash) != item['email_sha256']:
        return final('falhou_definitivo', 'e-mail preparado foi alterado depois da aprovação')
    pdf = cont.get_blob_client(item['pdf_blob']).download_blob().readall()
    if comum.sha256_bytes(pdf) != item['pdf_sha256']:
        return final('falhou_definitivo', 'PDF foi alterado depois da aprovação')

    _gravar_status(cont, pedido, 'enviando', nome=nome, tentativa=tentativa)
    try:
        enviar_email(email['destinatario'], email['assunto'], email['html'], anexo=pdf, nome_anexo=email['pdf_nome'])
    except Exception as ex:
        _gravar_status(cont, pedido, 'erro_temporario', nome=nome, erro=repr(ex)[:500], tentativa=tentativa)
        raise  # a fila tenta de novo; após 5 tentativas vai para envios-poison
    return final('enviado')


def concluir_se_terminou(cont, ciclo: str) -> bool:
    estado = comum.estado_ciclo(cont, ciclo)
    if not comum.envio_concluido(estado):
        return False
    res = comum.resumir_resultado(estado)
    res['concluido_em'] = comum.agora_utc().isoformat(timespec='seconds')
    # Só quem gravar primeiro avisa (evita e-mail duplicado de conclusão)
    if not comum.gravar_json(cont, comum.caminho(ciclo, 'resultado.json'), res, sobrescrever=False):
        return True
    m = estado['manifesto'] or {}
    teste = ' [ENSAIO]' if m.get('modo_teste') else ''
    itens = ([f'Falhou: {n}' for n in res['falhas']] + [f'Suspenso (bloqueio): {n}' for n in res['suspensos']]
             + [f'Sem e-mail cadastrado: {n}' for n in res['sem_email']])
    try:
        comum.enviar_email(
            comum.destinatarios_gestao(),
            f'[etransparente]{teste} Envio do ciclo {m.get("rotulo", ciclo)} concluído — '
            f'{res["enviados"]}/{res["total"]} entregues',
            comum.html_notificacao(
                f'Envio do ciclo {m.get("rotulo", ciclo)} concluído',
                [('Entregues', f'{res["enviados"]} de {res["total"]}'), ('Falhas', len(res['falhas'])),
                 ('Suspensos por bloqueio', len(res['suspensos'])), ('Sem e-mail', len(res['sem_email'])),
                 ('Concluído em', comum.formatar_brt(res['concluido_em']))],
                itens=itens or None,
                cor='#15803d' if res['enviados'] == res['total'] else '#b45309'))
    except Exception:
        logging.exception('Falha ao avisar conclusão do ciclo %s', ciclo)
    return True


def _status_path(pedido):
    return comum.caminho(pedido['ciclo'], 'status', f'{pedido["slug"]}.json')


def _gravar_status(cont, pedido, estado, nome='', erro='', tentativa=None):
    comum.gravar_json(cont, _status_path(pedido), {
        'slug': pedido['slug'], 'nome': nome, 'estado': estado, 'erro': erro, 'tentativa': tentativa,
        'atualizado_em': comum.agora_utc().isoformat(timespec='seconds'),
    })
