"""
Envio com aprovação — API do dashboard (/api/*) e Function de envio, de ponta a
ponta, com Azure Blob/Queue e SMTP simulados em memória.

Cada teste corresponde a uma regra combinada com a gestão:
  - só a presidência confirma; tentativa de outra conta é negada e avisada;
  - a confirmação exige abrir e conferir os 3 PDFs da amostra (registro no servidor);
  - nome declarado + conta + IP + local vão para presidência, transparência e comunicação;
  - "reportar erro" bloqueia na hora, inclusive no meio do envio;
  - a Function envia exatamente o que foi preparado (hash) e nunca duplica.
"""
import base64
import copy
import importlib
import json
import pathlib
import sys
import types

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'api'))
sys.path.insert(0, str(RAIZ / 'functions'))

import azure.functions as func  # noqa: E402
from azure.core.exceptions import ResourceExistsError  # noqa: E402

from artefatos import sha256_json  # noqa: E402

CICLO = '2026-10'
CODIGO = 'c0d1g0' * 10


# ── Azure / SMTP em memória ─────────────────────────────────────────────────

class Blob:
    def __init__(self, store, nome):
        self.store, self.name = store, nome

    def exists(self):
        return self.name in self.store

    def download_blob(self):
        dados = self.store[self.name]
        return types.SimpleNamespace(readall=lambda: dados)

    def upload_blob(self, dados, overwrite=True):
        if not overwrite and self.name in self.store:
            raise ResourceExistsError('existe')
        self.store[self.name] = dados if isinstance(dados, bytes) else dados.encode()


class Cont:
    def __init__(self):
        self.store = {}

    def get_blob_client(self, nome):
        return Blob(self.store, nome)

    def list_blobs(self, name_starts_with=''):
        return [types.SimpleNamespace(name=n) for n in sorted(self.store) if n.startswith(name_starts_with)]

    def delete_blob(self, nome):
        self.store.pop(nome)

    def json(self, nome):
        return json.loads(self.store[nome]) if nome in self.store else None

    def put(self, nome, obj):
        self.store[nome] = json.dumps(obj).encode() if not isinstance(obj, bytes) else obj


class Fila:
    def __init__(self):
        self.msgs = []

    def send_message(self, m):
        self.msgs.append(json.loads(m))


@pytest.fixture
def mundo(monkeypatch):
    """Ciclo 2026-10 preparado e validado, como a DAG deixa no Azure."""
    cont, fila, emails = Cont(), Fila(), []
    oscs = [('instituto-de-direito-coletivo-idc', 'INSTITUTO DE DIREITO COLETIVO – IDC', True),
            ('lar-de-daniel', 'LAR DE DANIEL', False), ('severa-romana', 'INSTITUTO SEVERA ROMANA', False),
            ('outra-osc', 'OUTRA OSC', False)]
    itens = []
    for slug, nome, _ in oscs:
        pdf = f'PDF-{slug}'.encode()
        cont.put(f'gold/{CICLO}/pdf/{slug}.pdf', pdf)
        email = {'ciclo': CICLO, 'slug': slug, 'nome': nome, 'destinatario': f'{slug}@osc.org',
                 'destinatario_original': f'{slug}@osc.org', 'assunto': f'{nome} — Relatório',
                 'html': '<p>relatório</p>', 'pdf_blob': f'gold/{CICLO}/pdf/{slug}.pdf',
                 'pdf_nome': f'{slug}.pdf', 'pdf_sha256': __import__('hashlib').sha256(pdf).hexdigest()}
        email['email_sha256'] = sha256_json(email)
        cont.put(f'envios/{CICLO}/emails/{slug}.json', email)
        itens.append({k: email[k] for k in ('slug', 'nome', 'destinatario', 'assunto', 'pdf_blob',
                                            'pdf_sha256', 'email_sha256')})
    cont.put(f'envios/{CICLO}/manifesto.json', {
        'ciclo': CICLO, 'rotulo': 'outubro/2026', 'preparado_em': '2026-11-03T11:50:00+00:00',
        'modo_teste': False, 'codigo_validacao': CODIGO, 'codigo_curto': CODIGO[:8].upper(),
        'total_oscs': 5, 'total_emails': 4, 'sem_email': ['OSC SEM EMAIL'], 'emails': itens,
        'amostra': [s for s, _, _ in oscs[:3]]})
    cont.put(f'envios/{CICLO}/amostra.json', {'ciclo': CICLO, 'codigo_validacao': CODIGO, 'oscs': [
        {'slug': s, 'nome': n, 'fixa': f, 'views_total': 12, 'media_diaria': '0,4', 'nota_final': 30.0,
         'max_nota': 30, 'classificacao': 'Ótimo', 'pdf_blob': f'gold/{CICLO}/pdf/{s}.pdf'}
        for s, n, f in oscs[:3]]})
    cont.put(f'gold/validacao/{CICLO}.json', {'status': 'aprovado', 'validado_em': '2026-11-03T11:45:00+00:00',
                                              'resumo': {'total_views': 357}, 'verificacoes': []})

    def enviar_email(para, assunto, corpo, anexo=None, nome_anexo=''):
        emails.append({'para': para, 'assunto': assunto, 'corpo': corpo, 'anexo': anexo})

    modulos = []
    for nome in ('shared_code.comum', 'comum'):
        m = importlib.import_module(nome)
        monkeypatch.setattr(m, 'container', lambda: cont)
        monkeypatch.setattr(m, 'fila', lambda nome='envios': fila)
        monkeypatch.setattr(m, 'enviar_email', enviar_email)
        monkeypatch.setattr(m, 'geolocalizar', lambda ip: {'city': 'Rio de Janeiro', 'region': 'RJ',
                                                           'country': 'BR', 'org': 'AS28573 Claro'})
        monkeypatch.setattr(m, 'url_leitura_temporaria', lambda blob, minutos=15: f'https://sas/{blob}')
        modulos.append(m)
    return types.SimpleNamespace(cont=cont, fila=fila, emails=emails, amostra=[s for s, _, _ in oscs[:3]])


def req(rota, corpo=None, papeis=('etransparente_acesso',), email='presidencia@direitocoletivo.org.br',
        nome='Maria da Silva', params=None):
    principal = {'identityProvider': 'aad', 'userId': 'uid-' + email.split('@')[0], 'userDetails': email,
                 'userRoles': ['anonymous', 'authenticated', *papeis],
                 'claims': [{'typ': 'name', 'val': nome}]}
    headers = {'x-ms-client-principal': base64.b64encode(json.dumps(principal).encode()).decode(),
               'x-forwarded-for': '177.10.20.30:51234', 'user-agent': 'Mozilla/5.0 Chrome/129 Windows NT 10.0'}
    return func.HttpRequest(method='POST' if corpo is not None else 'GET', url=f'/api/{rota}', headers=headers,
                            params=params or {}, body=json.dumps(corpo or {}).encode())


APROVADORA = ('etransparente_acesso', 'aprovador_envio')


def chamar(modulo, r):
    m = importlib.import_module(modulo)
    resp = m.main(r)
    return resp.status_code, json.loads(resp.get_body() or b'{}')


def abrir_todos(mundo):
    for s in mundo.amostra:
        st, b = chamar('abrir_pdf', req('abrir-pdf', {'ciclo': CICLO, 'slug': s, 'codigo': CODIGO}, papeis=APROVADORA))
        assert st == 200 and b['url'].startswith('https://sas/')


def aprovar(nome='Maria da Silva', papeis=APROVADORA, codigo=CODIGO, conferencia=None, **kw):
    conf = conferencia if conferencia is not None else {s: True for s in
                                                        ('instituto-de-direito-coletivo-idc', 'lar-de-daniel', 'severa-romana')}
    return chamar('aprovar', req('aprovar', {'ciclo': CICLO, 'codigo': codigo, 'nome_declarado': nome,
                                             'conferencia': conf}, papeis=papeis, **kw))


# ── API: quem pode o quê ────────────────────────────────────────────────────

def test_status_nao_vaza_emails_das_oscs(mundo):
    st, b = chamar('status', req('status'))
    assert st == 200 and b['ciclo'] == CICLO and b['envio']['total_emails'] == 4
    assert '@osc.org' not in json.dumps(b)
    assert b['usuario']['aprovador'] is False


def test_conta_sem_papel_nao_aprova_e_gestao_e_avisada_uma_vez_por_hora(mundo):
    for _ in range(3):
        st, b = aprovar(papeis=('etransparente_acesso',), email='voluntario@direitocoletivo.org.br')
        assert st == 403
    alertas = [e for e in mundo.emails if 'ALERTA' in e['assunto']]
    assert len(alertas) == 1
    assert 'voluntario@direitocoletivo.org.br' in alertas[0]['corpo'] and '177.10.20.30' in alertas[0]['corpo']
    assert not mundo.fila.msgs and f'envios/{CICLO}/aprovacao.json' not in mundo.cont.store


def test_nao_aprova_sem_abrir_os_pdfs(mundo):
    st, b = aprovar()
    assert st == 409 and len(b['motivos']) == 3
    assert not mundo.fila.msgs


def test_nao_aprova_com_uma_osc_marcada_como_nao_confere(mundo):
    abrir_todos(mundo)
    st, _ = aprovar(conferencia={'instituto-de-direito-coletivo-idc': True, 'lar-de-daniel': False,
                                 'severa-romana': True})
    assert st == 409


def test_nao_aprova_com_codigo_antigo(mundo):
    abrir_todos(mundo)
    st, b = aprovar(codigo='outro-codigo')
    assert st == 409 and any('código' in m for m in b['motivos'])


def test_nome_obrigatorio(mundo):
    abrir_todos(mundo)
    assert aprovar(nome='  ')[0] == 400


def test_aprovacao_completa(mundo):
    abrir_todos(mundo)
    st, b = aprovar()
    assert st == 200 and b['enfileirados'] == 4
    assert {m['slug'] for m in mundo.fila.msgs} == {'instituto-de-direito-coletivo-idc', 'lar-de-daniel',
                                                    'severa-romana', 'outra-osc'}
    a = mundo.cont.json(f'envios/{CICLO}/aprovacao.json')
    assert a['nome_declarado'] == 'Maria da Silva' and a['conta'] == 'presidencia@direitocoletivo.org.br'
    assert a['acesso']['ip'] == '177.10.20.30' and a['nome_confere_com_titular'] is True
    assert all(c['aberto_em'] for c in a['conferencia'])
    aviso = next(e for e in mundo.emails if 'CONFIRMADO' in e['assunto'])
    assert set(aviso['para']) == {'presidencia@direitocoletivo.org.br', 'transparencia@direitocoletivo.org.br',
                                  'comunicacao@direitocoletivo.org.br'}
    for trecho in ('Maria da Silva', 'presidencia@direitocoletivo.org.br', '177.10.20.30',
                   'Rio de Janeiro, RJ, BR', 'Claro', 'Chrome/129'):
        assert trecho in aviso['corpo']
    # segunda confirmação é recusada
    assert aprovar()[0] == 409


def test_nome_diferente_do_titular_e_destacado_sem_bloquear(mundo):
    abrir_todos(mundo)
    st, _ = aprovar(nome='Fulano de Tal')
    assert st == 200
    aviso = next(e for e in mundo.emails if 'CONFIRMADO' in e['assunto'])
    assert 'DIFERE do titular' in aviso['corpo']


def test_nome_declarado_e_escapado_no_email(mundo):
    abrir_todos(mundo)
    aprovar(nome='<script>alert(1)</script> Maria')
    aviso = next(e for e in mundo.emails if 'CONFIRMADO' in e['assunto'])
    assert '<script>' not in aviso['corpo'] and '&lt;script&gt;' in aviso['corpo']


def test_reportar_erro_bloqueia_e_avisa_tecnico_e_gestao(mundo):
    st, _ = chamar('reportar_erro', req('reportar-erro', {'ciclo': CICLO, 'osc': 'LAR DE DANIEL', 'campo': 'views',
                                                          'descricao': 'PDF mostra 0, tabela mostra 29'}))
    assert st == 200
    assert mundo.cont.json(f'envios/{CICLO}/bloqueio.json')['reportes'][0]['osc'] == 'LAR DE DANIEL'
    assuntos = [e['assunto'] for e in mundo.emails]
    assert any('[TÉCNICO]' in a for a in assuntos) and any('BLOQUEADO' in a for a in assuntos)
    tecnico = next(e for e in mundo.emails if '[TÉCNICO]' in e['assunto'])
    assert tecnico['para'] in ('comunicacao@direitocoletivo.org.br', ['comunicacao@direitocoletivo.org.br'])
    # com bloqueio, não aprova
    abrir_todos(mundo)
    st, b = aprovar()
    assert st == 409 and any('bloqueado' in m for m in b['motivos'])


# ── Function de envio ───────────────────────────────────────────────────────

def _function():
    return importlib.import_module('function_app')


def _aprovado(mundo):
    abrir_todos(mundo)
    assert aprovar()[0] == 200


def test_function_envia_exatamente_o_preparado_com_pdf(mundo):
    _aprovado(mundo)
    fa = _function()
    for m in list(mundo.fila.msgs):
        assert fa.processar(m) == 'enviado'
    entregues = [e for e in mundo.emails if e['para'] and '@osc.org' in e['para']]
    assert len(entregues) == 4
    assert all(e['anexo'].startswith(b'PDF-') for e in entregues)
    res = mundo.cont.json(f'envios/{CICLO}/resultado.json')
    assert res['enviados'] == 4 and res['total'] == 4 and res['sem_email'] == ['OSC SEM EMAIL']
    conclusao = [e for e in mundo.emails if 'concluído' in e['assunto']]
    assert len(conclusao) == 1 and '4/4' in conclusao[0]['assunto']


def test_function_nao_duplica(mundo):
    _aprovado(mundo)
    fa = _function()
    m = mundo.fila.msgs[0]
    fa.processar(m)
    fa.processar(m)  # mensagem repetida
    assert len([e for e in mundo.emails if e['para'] == m['slug'] + '@osc.org']) == 1


def test_function_respeita_bloqueio_no_meio_do_envio(mundo):
    _aprovado(mundo)
    fa = _function()
    fa.processar(mundo.fila.msgs[0])
    chamar('reportar_erro', req('reportar-erro', {'ciclo': CICLO, 'osc': 'OUTRA OSC', 'campo': 'nota',
                                                  'descricao': 'nota errada no PDF'}))
    estados = [fa.processar(m) for m in mundo.fila.msgs[1:]]
    assert estados == ['suspenso_por_bloqueio'] * 3
    assert len([e for e in mundo.emails if '@osc.org' in str(e['para'])]) == 1


def test_function_recusa_email_adulterado(mundo):
    _aprovado(mundo)
    caminho = f'envios/{CICLO}/emails/lar-de-daniel.json'
    e = mundo.cont.json(caminho)
    e['destinatario'] = 'atacante@exemplo.com'
    mundo.cont.put(caminho, e)
    m = next(x for x in mundo.fila.msgs if x['slug'] == 'lar-de-daniel')
    assert _function().processar(m) == 'falhou_definitivo'
    assert not any(x['para'] == 'atacante@exemplo.com' for x in mundo.emails)


def test_function_recusa_pdf_adulterado(mundo):
    _aprovado(mundo)
    mundo.cont.put(f'gold/{CICLO}/pdf/severa-romana.pdf', b'PDF-trocado')
    m = next(x for x in mundo.fila.msgs if x['slug'] == 'severa-romana')
    assert _function().processar(m) == 'falhou_definitivo'


def test_function_ignora_mensagem_sem_aprovacao_sem_travar_o_ciclo(mundo):
    fa = _function()
    m = {'ciclo': CICLO, 'slug': 'lar-de-daniel', 'codigo': CODIGO}
    assert fa.processar(m) == 'ignorado'                   # nenhuma aprovação: nada sai
    assert not [e for e in mundo.emails if '@osc.org' in str(e['para'])]
    assert not mundo.cont.list_blobs(f'envios/{CICLO}/status/')
    _aprovado(mundo)                                       # aprovação legítima continua possível
    assert fa.processar(dict(m, slug='severa-romana', codigo='forjado')) == 'ignorado'
    assert fa.processar(m) == 'enviado'


def test_function_erro_smtp_vira_nova_tentativa(mundo, monkeypatch):
    _aprovado(mundo)
    fa = _function()

    def smtp_fora(*a, **k):
        raise OSError('SMTP indisponível')
    m = mundo.fila.msgs[0]
    with pytest.raises(OSError):
        fa.processar(m, enviar_email=smtp_fora)
    assert mundo.cont.json(f'envios/{CICLO}/status/{m["slug"]}.json')['estado'] == 'erro_temporario'
    assert fa.processar(m, tentativa=2) == 'enviado'


# ── as duas cópias do código comum são idênticas à canônica ─────────────────

def test_copias_do_comum_identicas():
    canon = (RAIZ / 'envio' / 'comum.py').read_text(encoding='utf-8')
    for copia in (RAIZ / 'api' / 'shared_code' / 'comum.py', RAIZ / 'functions' / 'comum.py'):
        texto = copia.read_text(encoding='utf-8')
        assert texto.split('\n', 1)[1] == canon, f'{copia} desatualizada — rode envio/sincronizar_copias.py'
