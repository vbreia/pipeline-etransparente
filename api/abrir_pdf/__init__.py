"""POST /api/abrir-pdf {ciclo, slug, codigo} — registra que a aprovadora abriu o PDF
da amostra e devolve um link de leitura válido por 15 minutos.

A conferência só é aceita na aprovação se o PDF tiver sido aberto por AQUI —
o registro fica no servidor, não depende do navegador.
"""
import azure.functions as func

from shared_code import api_util as u
from shared_code import comum


def main(req: func.HttpRequest) -> func.HttpResponse:
    usuario = u.usuario(req)
    if not usuario:
        return u.erro('Não autenticado.', 401)
    if not u.e_aprovador(usuario):
        return u.negar_e_alertar(req, usuario, 'abrir PDF da amostra de conferência')
    b = u.corpo(req)
    ciclo, slug, codigo = b.get('ciclo'), b.get('slug'), b.get('codigo')
    try:
        cont = comum.container()
        manifesto = comum.ler_json(cont, comum.caminho(ciclo, 'manifesto.json')) or {}
        amostra = comum.ler_json(cont, comum.caminho(ciclo, 'amostra.json')) or {}
        if manifesto.get('codigo_validacao') != codigo:
            return u.erro('O envio foi preparado de novo — recarregue a página.', 409)
        item = next((a for a in amostra.get('oscs', []) if a['slug'] == slug), None)
        if not item:
            return u.erro('Esta OSC não faz parte da amostra de conferência.', 400)
        comum.gravar_json(cont, comum.caminho(ciclo, 'conferencia', usuario['id'], f'{slug}.json'), {
            'slug': slug, 'codigo': codigo, 'conta': usuario['email'],
            'aberto_em': comum.agora_utc().isoformat(timespec='seconds'),
            'ip': comum.ip_cliente(req.headers),
        })
        return u.resposta({'ok': True, 'url': comum.url_leitura_temporaria(item['pdf_blob'])})
    except Exception as e:
        return u.falha('/api/abrir-pdf', 'Não foi possível abrir o PDF.', e)
