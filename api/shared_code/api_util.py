"""Utilitários HTTP da API de envio (só da API — não é copiado para a Function)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

import azure.functions as func

from shared_code import comum


def resposta(dados, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(dados, ensure_ascii=False), status_code=status,
                             mimetype='application/json', headers={'Cache-Control': 'no-store'})


def erro(mensagem: str, status: int, **extra) -> func.HttpResponse:
    return resposta({'ok': False, 'erro': mensagem, **extra}, status)


_SEGREDOS = re.compile(r'(AccountKey|SharedAccessSignature|sig|password|senha)=[^;&\s]+', re.I)


def detalhe_tecnico(exc: BaseException) -> str:
    """Tipo e mensagem curta da exceção, sem chaves/assinaturas — para diagnosticar sem abrir logs."""
    msg = _SEGREDOS.sub(r'\1=***', str(exc)).strip().splitlines()
    return f'{type(exc).__name__}: {msg[0][:200] if msg else ""}'.rstrip(': ')


def falha(contexto: str, mensagem: str, exc: BaseException) -> func.HttpResponse:
    """Erro interno: registra no log e devolve a mensagem + detalhe técnico sem segredos."""
    logging.exception('Erro em %s', contexto)
    return erro(mensagem, 500, detalhe=detalhe_tecnico(exc))


def corpo(req: func.HttpRequest) -> dict:
    try:
        return req.get_json() or {}
    except ValueError:
        return {}


def usuario(req: func.HttpRequest) -> dict | None:
    try:
        return comum.principal(req.headers)
    except Exception:
        logging.exception('Cabeçalho de identidade inválido')
        return None


def aprovadores() -> set[str]:
    """Contas que podem conferir e confirmar envios: configuração APROVADORES do Static Web App.

    Lista de e-mails separados por vírgula. Vazia/ausente = ninguém aprova (falha fechada).
    Não usamos o papel do SWA para isso: na prática os papéis personalizados chegavam à API
    de forma intermitente (06/10/2026) — a mesma sessão ora era aprovadora, ora não.
    O e-mail da conta vem do cabeçalho de identidade, que é estável.
    """
    import os
    return {e.strip().lower() for e in os.environ.get('APROVADORES', '').split(',') if e.strip()}


def e_aprovador(u: dict | None) -> bool:
    return bool(u) and bool(u.get('email')) and u['email'].lower() in aprovadores()


def negar_e_alertar(req: func.HttpRequest, u: dict | None, acao: str) -> func.HttpResponse:
    """Conta logada SEM o papel de aprovadora tentou uma ação restrita.

    Registra e avisa a gestão — no máximo um alerta por conta por hora, para
    não inundar caixas de entrada se alguém ficar clicando.
    """
    try:
        cont = comum.container()
        hora = datetime.now(timezone.utc).strftime('%Y%m%d%H')
        conta = (u or {}).get('email') or 'desconhecida'
        marcador = f'{comum.PREFIXO}_alertas/{hora}_{conta.replace("@", "_at_")}.json'
        acesso = comum.dados_de_acesso(req.headers)
        primeira_vez = comum.gravar_json(cont, marcador, {'conta': conta, 'acao': acao, **acesso},
                                         sobrescrever=False)
        if primeira_vez:
            comum.enviar_email(
                comum.destinatarios_gestao(),
                f'[etransparente] ALERTA: tentativa negada na página de envio — {conta}',
                comum.html_notificacao(
                    'Tentativa de ação restrita negada',
                    [('Conta', conta), ('Ação tentada', acao),
                     ('Data/hora', comum.formatar_brt(acesso['registrado_em'])),
                     ('IP', acesso['ip'] or 'indisponível'), ('Local aproximado', acesso['local_aproximado']),
                     ('Provedor', acesso['provedor']), ('Navegador', acesso['navegador'])],
                    rodape='Esta conta está logada no dashboard, mas não tem permissão de aprovar envios. '
                           'Se não reconhecer o acesso, verifique o Entra ID → Logs de entrada.',
                    cor='#b91c1c'))
    except Exception:
        logging.exception('Falha ao registrar/alertar tentativa negada')
    return erro('Sua conta não tem permissão para esta ação. A tentativa foi registrada.', 403)
