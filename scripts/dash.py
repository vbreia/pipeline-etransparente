"""
Small utility to render one HTML dashboard per ONG (from the latest
`oscs_etransparente_*.json` in `output/`). Saves HTML files under
`output/dashboards/<timestamp>/html` and PDFs under
`output/dashboards/<timestamp>/pdf` using Playwright/Chromium.

Usage: run `python scripts/dash.py` from repository root. The script will
locate the newest `output/oscs_etransparente_*.json` automatically.
"""

import base64
import glob
import hashlib
import html as _html
import io
import json
import os
import re
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

try:
    import qrcode as _qrcode  # optional
    QRCODE_AVAILABLE = True
except Exception:
    QRCODE_AVAILABLE = False


_SCORE_DEFAULTS = {
    'nota_final': 0,
    'max_nota': 30,
    'classificacao': 'Regular',
    'tag': 'sem_termos_emendas',
    'badges': {'cebas': False, 'utilidade_publica': False},
}

_COR_CLASSIFICACAO = {
    'Regular': '#dc2626',
    'Bom': '#d97706',
    'Ótimo': '#16a34a',
}


def find_latest_input():
    files = glob.glob(os.path.join('output', 'oscs_etransparente_*.json'))
    if not files:
        raise FileNotFoundError('Nenhum arquivo oscs_etransparente_*.json em output/')
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def find_latest_scores():
    files = glob.glob(os.path.join('output', 'scores', 'transparency_scores_*.json'))
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def _gerar_hash(nome: str, data_emissao: str, nota_final, max_nota, classificacao: str) -> str:
    raw = f"{nome}{data_emissao}{nota_final}{max_nota}{classificacao}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _gerar_qr_data_uri(url: str) -> str:
    """Gera QR code em memória e retorna data URI base64 (ou '' se falhar)."""
    if not QRCODE_AVAILABLE:
        return ''
    try:
        buf = io.BytesIO()
        _qrcode.make(url).save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        return f'data:image/png;base64,{b64}'
    except Exception:
        return ''


# fields to show in the "Informações principais" box
INFO_CAMPOS = [
    "nome",
    "url",
    "descricao_objeto_social",
    "telefone",
    "email",
    "website",
    "horario_funcionamento",
    "localizacao",
    "cnpj",
]
TOTAL_INFO = len(INFO_CAMPOS)


def contar_info_preenchida(osc):
    preenchidos = 0
    for campo in INFO_CAMPOS:
        valor = osc.get(campo)
        if isinstance(valor, str) and valor.strip():
            preenchidos += 1
    return preenchidos


def contar_termos(osc):
    termos = osc.get('termos', {}) or {}
    total = 0
    for chave in ['municipio', 'estado', 'uniao', 'emendas_parlamentares']:
        bloco = termos.get(chave, {}) or {}
        total += int(bloco.get('quantidade', 0) or 0)
    return total


def gerar_dashboard_html(osc, score=None):
    nome = osc.get('nome', 'Sem nome')
    url = osc.get('url', '#')

    # Score data — use defaults when score is absent
    s = score or {}
    nota_final = s.get('nota_final', _SCORE_DEFAULTS['nota_final'])
    max_nota = s.get('max_nota', _SCORE_DEFAULTS['max_nota'])
    classificacao = s.get('classificacao', _SCORE_DEFAULTS['classificacao'])
    tag = s.get('tag', _SCORE_DEFAULTS['tag'])
    badges = s.get('badges') or _SCORE_DEFAULTS['badges']

    cor_classificacao = _COR_CLASSIFICACAO.get(classificacao, '#6b7280')
    tag_texto = 'Com termos/emendas' if tag == 'com_termos_emendas' else 'Sem termos/emendas'

    badges_html_parts = []
    if badges.get('cebas'):
        badges_html_parts.append('<span class="badge badge-cebas">CEBAS</span>')
    if badges.get('utilidade_publica'):
        badges_html_parts.append('<span class="badge badge-utilidade">Utilidade Pública</span>')
    badges_html = ''.join(badges_html_parts)

    data_emissao = datetime.now().strftime('%Y-%m')
    hash_hex = _gerar_hash(nome, data_emissao, nota_final, max_nota, classificacao)
    hash_curto = hash_hex[:12]
    qr_url = f'https://etransparente.org/verificar/{hash_hex}'
    qr_data_uri = _gerar_qr_data_uri(qr_url)

    descricao = osc.get('descricao_objeto_social', '') or ''
    descricao_obj = _html.escape(descricao[:400] + '...' if len(descricao) > 400 else descricao) if descricao else ''
    telefone = osc.get('telefone', '') or ''
    email = osc.get('email', '') or ''
    website = osc.get('website', '') or ''
    localizacao = osc.get('localizacao', '') or ''
    cnpj = osc.get('cnpj', '') or ''

    # Buscar logo local da ONG
    logo_local_path = osc.get('logo_local_path', '') or ''

    redes = osc.get('redes_sociais', {}) or {}
    instagram = redes.get('instagram', '') or ''
    linkedin = redes.get('linkedin', '') or ''
    youtube = redes.get('youtube', '') or ''
    outras_redes = redes.get('outras', '') or ''

    documentos = osc.get('documentos', {}) or {}

    def doc_label(key):
        # Map keys to human-friendly labels per user request
        if key.startswith('balanco_'):
            ano = key.split('_', 1)[1]
            return f'Balanço contábil (Lei estadual 5981/11) – {ano}'
        mapping = {
            'plano_acao': 'Plano de Ação',
            'cneas': 'CNEAS',
            'cebas': 'CEBAS',
            'relatorio_atividades': 'Relatório de Atividades',
            'estatuto': 'Estatuto (último registrado no RCPJ)',
            'ata_eleicao': 'Ata de eleição administração e do conselho fiscal (Lei estadual 5981/11)'
        }
        return mapping.get(key, key.replace('_', ' ').title())

    documentos_presentes = [k for k, v in documentos.items() if v]
    documentos_labels = [doc_label(k) for k in documentos_presentes]

    info_preenchida = contar_info_preenchida(osc)
    total_termos = contar_termos(osc)

    municipio_q = int(osc.get('termos', {}).get('municipio', {}).get('quantidade', 0) or 0)
    estado_q = int(osc.get('termos', {}).get('estado', {}).get('quantidade', 0) or 0)
    uniao_q = int(osc.get('termos', {}).get('uniao', {}).get('quantidade', 0) or 0)
    emendas_q = int(osc.get('termos', {}).get('emendas_parlamentares', {}).get('quantidade', 0) or 0)

    # Display strings: when zero, show 'Nenhum' (and for emendas 'Nenhuma')
    municipio_disp = municipio_q if municipio_q else 'Nenhum'
    estado_disp = estado_q if estado_q else 'Nenhum'
    uniao_disp = uniao_q if uniao_q else 'Nenhum'
    emendas_disp = emendas_q if emendas_q else 'Nenhuma'

    # Build an enumerated social links list. Each item shows the network name only
    # (no raw URL visible). We include a minimalist inline SVG icon per known network.
    def icon_svg(kind):
        if kind == 'instagram':
            return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="3" width="18" height="18" rx="5" stroke="#1e293b" stroke-width="1.2" fill="none"/><circle cx="12" cy="12" r="3" stroke="#1e293b" stroke-width="1.2" fill="none"/><circle cx="17.5" cy="6.5" r="0.8" fill="#1e293b"/></svg>'
        if kind == 'linkedin':
            return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="3" width="18" height="18" rx="2" stroke="#1e293b" stroke-width="1.2" fill="none"/><path d="M8 11v6" stroke="#1e293b" stroke-width="1.2"/><rect x="8" y="7" width="3" height="2" stroke="#1e293b" stroke-width="1.2" fill="none"/><path d="M14 11v6" stroke="#1e293b" stroke-width="1.2"/><path d="M14 11c1.5 0 2-1 2-1.8V11z" stroke="#1e293b" stroke-width="1.2" fill="none"/></svg>'
        if kind == 'youtube':
            return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="6" width="18" height="12" rx="3" stroke="#1e293b" stroke-width="1.2" fill="none"/><path d="M10 9l5 3-5 3V9z" fill="#1e293b"/></svg>'
        return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="9" stroke="#1e293b" stroke-width="1.2" fill="none"/></svg>'

    social_items = []
    if instagram:
        social_items.append(('Instagram', instagram, 'instagram'))
    if linkedin:
        social_items.append(('LinkedIn', linkedin, 'linkedin'))
    if youtube:
        social_items.append(('YouTube', youtube, 'youtube'))

    # 'outras_redes' may contain multiple URLs separated by ';' or ','; try to split and map domains to names
    if outras_redes:
        parts = [p.strip() for p in re.split('[;,]', outras_redes) if p.strip()]
        for p in parts:
            # try to identify the service by domain
            name = 'Site'
            try:
                host = p.split('://')[-1].split('/')[0].lower()
                if 'facebook' in host:
                    name = 'Facebook'
                elif 'tiktok' in host:
                    name = 'TikTok'
                elif 'x.com' in host or 'twitter' in host:
                    name = 'X'
                elif 'instagram' in host:
                    name = 'Instagram'
                elif 'linkedin' in host:
                    name = 'LinkedIn'
                elif 'youtube' in host or 'youtu.be' in host:
                    name = 'YouTube'
            except Exception:
                name = 'Site'
            social_items.append((name, p, 'other'))

    # Build HTML for enumerated social list (only the network name is visible and linked)
    socials_html = ''
    if social_items:
        items = []
        for idx, (label, href, kind) in enumerate(social_items, start=1):
            icon = icon_svg(kind)
            # visible text is the label (no raw URL)
            items.append(f'<li><span class="index">{idx}.</span> <a class="social" href="{_html.escape(href)}" target="_blank">{icon} {_html.escape(label)}</a></li>')
        socials_html = '<ol class="social-list">' + '\n'.join(items) + '</ol>'
    else:
        socials_html = '<div class="none">Nenhum</div>'

    # Documents list HTML (minimalist)
    if documentos_labels:
        docs_html_items = ''.join(f'<li>{_html.escape(lbl)}</li>' for lbl in documentos_labels)
        docs_html = f'<ul class="docs-list">{docs_html_items}</ul>'
    else:
        docs_html = '<div class="none">Nenhum</div>'

    descricao_block = (
        f'<div class="desc-box"><strong>Sobre a organização</strong>'
        f'<p>{_html.escape(descricao)}</p></div>'
    ) if descricao.strip() else ''

    # Identificar campos faltantes
    campos_faltantes = []

    # Verificar informações básicas
    if not telefone:
        campos_faltantes.append('Telefone')
    if not email:
        campos_faltantes.append('E-mail')
    if not website:
        campos_faltantes.append('Website')
    if not localizacao:
        campos_faltantes.append('Localização')
    if not cnpj:
        campos_faltantes.append('CNPJ')

    # Verificar redes sociais
    if not instagram:
        campos_faltantes.append('Instagram')
    if not linkedin:
        campos_faltantes.append('LinkedIn')
    if not youtube:
        campos_faltantes.append('YouTube')

    # Verificar documentos importantes
    if not documentos.get('cneas'):
        campos_faltantes.append('CNEAS')
    if not documentos.get('cebas'):
        campos_faltantes.append('CEBAS')
    if not documentos.get('estatuto'):
        campos_faltantes.append('Estatuto')
    if not documentos.get('relatorio_atividades'):
        campos_faltantes.append('Relatório de Atividades')
    if not documentos.get('plano_acao'):
        campos_faltantes.append('Plano de Ação')

    # Verificar balanços (últimos 3 anos)
    for ano in ['2024', '2023', '2022']:
        if not documentos.get(f'balanco_{ano}'):
            campos_faltantes.append(f'Balanço {ano}')

    # Construir HTML de campos faltantes
    if campos_faltantes:
        faltantes_texto = ', '.join(campos_faltantes)
        faltantes_html = f'<div style="color:#dc2626; font-size:0.9rem; line-height:1.6;">{_html.escape(faltantes_texto)}</div>'
    else:
        faltantes_html = '<div style="color:#16a34a; font-weight:500; font-size:0.95rem;">🎉 Parabéns! Todos os dados de transparência estão disponíveis.</div>'

    # Tentar /home/airflow primeiro (volume Docker), fallback para cwd
    _home_airflow = '/home/airflow'
    if os.path.exists(os.path.join(_home_airflow, 'assets')):
        repo_root = _home_airflow
    else:
        repo_root = os.path.abspath(os.getcwd())
    font_dir = os.path.join(repo_root, 'assets', 'fonts')
    regular_path = os.path.join(font_dir, 'Montserrat-Regular.woff2')
    medium_path = os.path.join(font_dir, 'Montserrat-Medium.woff2')
    bold_path = os.path.join(font_dir, 'Montserrat-Bold.woff2')
    # Background images absolute paths (prefer JPG)
    bg_jpg_path = os.path.join(repo_root, 'assets', 'img', 'bg-dash-e.jpg')
    bg_svg_path = os.path.join(repo_root, 'assets', 'img', 'bg-dash-e.svg')
    # Fonts existence checks (optional warnings)
    for fp in (regular_path, medium_path, bold_path):
        if not os.path.exists(fp):
            print(f"[dash.py] Aviso: fonte não encontrada em {fp}. Pode afetar a renderização.")
    if not os.path.exists(bg_jpg_path) and not os.path.exists(bg_svg_path):
        print(f"[dash.py] Aviso: nenhum background encontrado em {bg_jpg_path} ou {bg_svg_path}.")

    # Use file:// URLs so wkhtmltopdf (called from a different working dir) can access the files
    regular_url = f'file://{regular_path}'
    medium_url = f'file://{medium_path}'
    bold_url = f'file://{bold_path}'

    # Prefer JPG (more robust with wkhtmltopdf). Fallback to SVG if JPG missing.
    if os.path.exists(bg_jpg_path):
        bg_url = f'file://{bg_jpg_path}'
    else:
        bg_url = f'file://{bg_svg_path}'

    # Determinar logo da ONG
    # 1. Tentar usar logo_local_path se existir
    # 2. Se não existir, tentar buscar na pasta de logos usando slug da URL
    # 3. Fallback: logo padrão ou placeholder
    logo_url = ""

    if logo_local_path and os.path.exists(logo_local_path):
        # Usar caminho absoluto do logo local
        logo_url = f'file://{os.path.abspath(logo_local_path)}'
    else:
        # Tentar encontrar logo pelo slug extraído da URL
        slug = ''
        match = re.search(r'/oscs/([^/]+)/?$', url)
        if match:
            slug = match.group(1)
            logo_path = os.path.join(repo_root, 'assets', 'img', 'logos-ongs', f'{slug}.jpg')

            if os.path.exists(logo_path):
                logo_url = f'file://{logo_path}'

        # Se ainda não encontrou, tentar fallback com nome seguro
        if not logo_url:
            safe_name = re.sub(r'[^A-Za-z0-9_-]+', '_', nome).strip('_') or 'logo'
            logo_path = os.path.join(repo_root, 'assets', 'img', 'logos-ongs', f'{safe_name}.jpg')

            if os.path.exists(logo_path):
                logo_url = f'file://{logo_path}'

        # Fallback: usar logo padrão se existir
        if not logo_url:
            default_logo = os.path.join(repo_root, 'assets', 'img', 'logo-default.png')
            if os.path.exists(default_logo):
                logo_url = f'file://{default_logo}'
            else:
                # Última opção: usar placeholder de teste (pode ser removido depois)
                logo_url = "https://via.placeholder.com/80x80/1e3a8a/ffffff?text=Logo"

    if qr_data_uri:
        qr_img_tag = f'<img src="{qr_data_uri}" width="80" height="80" style="display:block;" alt="QR Code de verificação"/>'
    else:
        qr_img_tag = '<div style="width:80px;height:80px;background:#f1f5f9;border-radius:4px;"></div>'

    html = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
                <meta charset="utf-8">
                <title>Dashboard - {_html.escape(nome)}</title>
                <style>
                        @font-face {{
                            font-family: 'MontserratLocal';
                            src: url('{regular_url}') format('woff2');
                            font-weight: 400;
                            font-style: normal;
                            font-display: swap;
                        }}
                        @font-face {{
                            font-family: 'MontserratLocal';
                            src: url('{medium_url}') format('woff2');
                            font-weight: 500;
                            font-style: normal;
                            font-display: swap;
                        }}
                        @font-face {{
                            font-family: 'MontserratLocal';
                            src: url('{bold_url}') format('woff2');
                            font-weight: 700;
                            font-style: normal;
                            font-display: swap;
                        }}

            /* Forçar impressão de cores */
            * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; box-sizing: border-box; }}
            @media print {{
                body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
                .container {{ box-shadow: none; }}
            }}
            html, body {{ width: 1414px; height: 2000px; margin: 0; padding: 0; font-family: 'MontserratLocal', 'Montserrat', sans-serif; }}
            .page-wrapper {{ position: relative; width: 1414px; height: 2000px; }}
            .bg-header {{
                width: 1414px;
                height: 2000px;
                position: absolute;
                top: 0; left: 0;
                z-index: 0; display: block;
            }}
            .container {{
                position: relative; z-index: 1;
                margin: 85px 18px 20px;
                background: rgba(255, 255, 255, 0.97);
                padding: 24px 28px 28px;
                border-radius: 8px;
                box-shadow: 0 4px 16px rgba(0,0,0,0.18);
            }}
            .content-main {{ display: block; }}
            .header {{ margin-bottom: 18px; border-bottom: 2px solid #1e3a8a; padding-bottom: 16px; }}
            .header-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
            .header-table td {{ vertical-align: middle; padding: 0; }}
            .logo-cell {{ width: 96px; padding-right: 16px; }}
            .text-cell {{ width: auto; }}
            .logo {{ width: 80px; height: 80px; border-radius: 50%; object-fit: cover; display: block; }}
            .logo-link {{ display: inline-block; text-decoration: none; }}
            .title-area {{ display: block; }}
            .title-area .nome-ong {{ margin-bottom: 8px; }}
            .nome-ong {{ font-size: 1.35rem; font-weight: 700; color: #1e3a8a; word-break: break-word; }}
            .nome-ong a {{ color: inherit; text-decoration: none; }}
            .meta {{ display: -webkit-box; display: -ms-flexbox; display: flex; -ms-flex-wrap: wrap; flex-wrap: wrap; font-size: 0.9rem; color: #374151; -webkit-box-align: center; -ms-flex-align: center; align-items: center; }}
            .meta span {{ display: inline-block; margin-right: 10px; margin-bottom: 4px; }}
            .classificacao-badge {{ font-weight: 700; font-size: 0.95rem; }}
            .tag-pill {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; background: #e0f2fe; color: #0369a1; font-weight: 500; }}
            .badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }}
            .badge-cebas {{ background: #fef3c7; color: #92400e; }}
            .badge-utilidade {{ background: #dcfce7; color: #166534; }}
            .desc-box {{ background: #f8fafc; border-left: 4px solid #64748b; border-radius: 6px; padding: 12px 16px; margin-bottom: 14px; }}
            .desc-box strong {{ display: block; color: #475569; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }}
            .desc-box p {{ margin: 0; font-size: 0.9rem; color: #374151; line-height: 1.6; }}
            .body {{ display: -webkit-box; display: -ms-flexbox; display: flex; -ms-flex-wrap: wrap; flex-wrap: wrap; gap: 12px; }}
            .info-box {{ background: linear-gradient(135deg, #f0f4ff 0%, #f9fafb 100%); padding: 16px 18px; border-radius: 8px; border-left: 4px solid #1e3a8a; -webkit-box-flex: 1; -ms-flex: 1 1 calc(50% - 6px); flex: 1 1 calc(50% - 6px); min-width: 220px; }}
            .info-box > strong {{ display: block; margin-bottom: 10px; color: #1e3a8a; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; }}
            .info-box .valor {{ font-size: 1.5rem; color: #1e3a8a; font-weight: 700; margin-bottom: 10px; }}
            .info-row {{ font-size: 0.87rem; color: #374151; padding: 4px 0; border-bottom: 1px solid #e2e8f0; line-height: 1.4; }}
            .info-row:last-child {{ border-bottom: none; }}
            .info-row b {{ color: #1e3a8a; margin-right: 4px; }}
            .link-area {{ margin-top: 12px; padding: 14px 16px; border-radius: 8px; background: #fff7ed; border-left: 4px solid #f59e0b; }}
            .link-area > p {{ margin: 0 0 8px 0; color: #92400e; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; }}
            .social-list {{ list-style: none; padding: 0; margin: 0; }}
            .social-list li {{ display: -webkit-box; display: -ms-flexbox; display: flex; -webkit-box-align: center; -ms-flex-align: center; align-items: center; padding: 4px 0; border-bottom: 1px solid #e2e8f0; font-size: 0.87rem; }}
            .social-list li:last-child {{ border-bottom: none; }}
            .social-list .index {{ color: #9ca3af; margin-right: 8px; font-size: 0.78rem; }}
            .social {{ display:-webkit-inline-box; display:-ms-inline-flexbox; display:inline-flex; -webkit-box-align:center; -ms-flex-align:center; align-items:center; gap:5px; color:#1e3a8a; text-decoration:none; }}
            .social svg {{ flex-shrink:0; }}
            .docs-list {{ list-style: none; padding: 0; margin: 0; }}
            .docs-list li {{ font-size: 0.85rem; color: #374151; padding: 4px 0; border-bottom: 1px solid #e2e8f0; line-height: 1.4; }}
            .docs-list li:last-child {{ border-bottom: none; }}
            .docs-list li::before {{ content: "✓ "; color: #16a34a; font-weight: 700; }}
            .none {{ font-size: 0.87rem; color: #9ca3af; }}
            .institutional-footer {{ margin-top: 28px; }}
            .institutional-divider {{ border-top: 2px solid #1e3a8a; margin-bottom: 20px; }}
            .institutional-content {{ display: table; width: 100%; border-collapse: collapse; }}
            .institutional-left {{ display: table-cell; width: 50%; padding-right: 20px; vertical-align: top; font-size: 0.88rem; color: #374151; }}
            .institutional-right {{ display: table-cell; width: 50%; padding-left: 20px; border-left: 1px solid #e5e7eb; vertical-align: top; font-size: 0.88rem; color: #374151; }}
            .institutional-left strong, .institutional-right strong {{ display: block; color: #1e3a8a; margin-bottom: 8px; font-size: 0.9rem; }}
            .institutional-left p, .institutional-right p {{ margin: 0; line-height: 1.6; }}
            .footer-verificacao {{ margin-top: 30px; padding-top: 14px; border-top: 2px solid #e5e7eb; display: -webkit-box; display: -ms-flexbox; display: flex; -webkit-box-align: center; -ms-flex-align: center; align-items: center; gap: 16px; font-size: 0.8rem; color: #6b7280; }}
            .footer-text {{ -webkit-box-flex: 1; -ms-flex: 1; flex: 1; }}
            .hash-curto {{ font-family: monospace; font-size: 0.82rem; color: #374151; font-weight: 600; margin-bottom: 4px; }}
        </style>
    </head>
    <body>
        <div class="page-wrapper">
        <img class="bg-header" src="{bg_url}" alt=""/>
        <div class="container">

            <div class="header">
                <table class="header-table">
                    <tr>
                        <td class="logo-cell">
                            <a class="logo-link" href="{_html.escape(url)}" target="_blank" rel="noopener noreferrer"><img class="logo" src="{logo_url}" alt="Logo"/></a>
                        </td>
                        <td class="text-cell">
                            <div class="title-area">
                                <div class="nome-ong"><a href="{_html.escape(url)}" target="_blank" rel="noopener noreferrer">{_html.escape(nome)}</a></div>
                                <div class="meta">
                                    <span class="classificacao-badge" style="color:{cor_classificacao};">{_html.escape(classificacao)}</span>
                                    <span><strong>Nota:</strong> {nota_final}/{max_nota}</span>
                                    <span class="tag-pill">{_html.escape(tag_texto)}</span>
                                    {badges_html}
                                </div>
                            </div>
                        </td>
                    </tr>
                </table>
            </div>

            <div class="content-main">
                {descricao_block}
                <div class="body">
                    <div class="info-box">
                        <strong>Informações</strong>
                        <div class="info-row"><b>Telefone</b> {_html.escape(telefone) or '—'}</div>
                        <div class="info-row"><b>E-mail</b> {_html.escape(email) or '—'}</div>
                        <div class="info-row"><b>Website</b> <a href="{_html.escape(website)}">{_html.escape(website) or '—'}</a></div>
                        <div class="info-row"><b>Localização</b> {_html.escape(localizacao) or '—'}</div>
                        <div class="info-row"><b>CNPJ</b> {_html.escape(cnpj) or '—'}</div>
                    </div>
                    <div class="info-box">
                        <strong>Contratos e Parcerias</strong>
                        <div class="valor">{total_termos}</div>
                        <div class="info-row"><b>Município</b> {municipio_disp}</div>
                        <div class="info-row"><b>Estado</b> {estado_disp}</div>
                        <div class="info-row"><b>União</b> {uniao_disp}</div>
                        <div class="info-row"><b>Emendas parl.</b> {emendas_disp}</div>
                    </div>
                    <div class="info-box">
                        <strong>Redes Sociais</strong>
                        {socials_html}
                    </div>
                    <div class="info-box">
                        <strong>Documentos ({len(documentos_labels)})</strong>
                        {docs_html}
                    </div>
                </div>

                <div class="link-area">
                    <p>Dados ou documentos pendentes</p>
                    {faltantes_html}
                </div>
            </div>

            <div class="institutional-footer">
                <div class="institutional-divider"></div>
                <div class="institutional-content">
                    <div class="institutional-left">
                        <strong>Sobre a instituição</strong>
                        <p>{descricao_obj}</p>
                    </div>
                    <div class="institutional-right">
                        <strong>O Índice de Transparência</strong>
                        <p>O Índice de Transparência do etransparente.org avalia o nível de prestação de contas e abertura institucional das organizações da sociedade civil cadastradas na plataforma. A pontuação é calculada com base no preenchimento de informações públicas, documentos institucionais e contratos com o poder público.</p>
                        <p style="margin-top:8px;">Acesse <strong>etransparente.org</strong> para mais informações.</p>
                    </div>
                </div>
            </div>

            <div class="footer-verificacao">
                {qr_img_tag}
                <div class="footer-text">
                    <div class="hash-curto">Código: {hash_curto}</div>
                    <div>Documento oficial emitido pelo IDC. Verifique em <strong>etransparente.org/verificar</strong></div>
                </div>
            </div>

        </div>
        </div>
    </body>
    </html>
    """

    return html, hash_hex


def main():
    input_file = find_latest_input()
    with open(input_file, 'r', encoding='utf-8') as f:
        oscs = json.load(f)

    # Load scores and build lookup by ONG name
    scores_file = find_latest_scores()
    scores_by_nome = {}
    if scores_file:
        try:
            with open(scores_file, 'r', encoding='utf-8') as f:
                scores_data = json.load(f)
            for r in scores_data.get('resultados', []):
                nome_score = r.get('nome', '')
                if nome_score:
                    scores_by_nome[nome_score] = r
            print(f"Scores carregados: {scores_file} ({len(scores_by_nome)} ONGs)")
        except Exception as e:
            print(f"Aviso: erro ao carregar scores: {e}. Usando valores padrão.")
    else:
        print("Aviso: nenhum arquivo de scores encontrado. Usando valores padrão.")

    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    data_emissao = datetime.now().strftime('%Y-%m')
    # Usar /home/airflow como base se existir (volume Docker), fallback para cwd
    _base = '/home/airflow' if os.path.exists('/home/airflow/output') else os.getcwd()
    base_out = os.path.join(_base, 'output', 'dashboards', ts)
    html_dir = os.path.join(base_out, 'html')
    pdf_dir = os.path.join(base_out, 'pdf')
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    # Obter data para nome do arquivo: Relatório-etransparente-{mês}-de-{ano}-{slug}
    mes_nome = datetime.now().strftime('%B').lower()  # january, february, etc
    # Mapear para português
    meses_pt = {
        'january': 'janeiro', 'february': 'fevereiro', 'march': 'março', 'april': 'abril',
        'may': 'maio', 'june': 'junho', 'july': 'julho', 'august': 'agosto',
        'september': 'setembro', 'october': 'outubro', 'november': 'novembro', 'december': 'dezembro'
    }
    mes_nome = meses_pt.get(mes_nome, datetime.now().strftime('%B').lower())
    ano = datetime.now().strftime('%Y')
    ciclo = f"{mes_nome}-{ano}"

    verificacoes = []
    pdf_count = 0
    for idx, osc in enumerate(oscs, 1):
        nome = osc.get('nome', 'Sem nome')
        url = osc.get('url', '')
        score = scores_by_nome.get(nome)

        # Extrair slug da URL
        slug = ''
        match = re.search(r'/oscs/([^/]+)/?$', url)
        if match:
            slug = match.group(1)
        else:
            # Fallback: usar nome sanitizado se não conseguir extrair slug
            slug = ''.join(c if c.isalnum() or c in ('-', '_') else '-' for c in nome).lower()
            slug = re.sub(r'-+', '-', slug).strip('-')[:50]

        # Nome do arquivo: Relatório-etransparente-{mês}-de-{ano}-{slug}
        nome_arquivo = f"Relatório-etransparente-{mes_nome}-de-{ano}-{slug}"

        html_file = os.path.join(html_dir, f"{nome_arquivo}.html")
        pdf_file = os.path.join(pdf_dir, f"{nome_arquivo}.pdf")

        try:
            try:
                html_content, hash_hex = gerar_dashboard_html(osc, score)
                # Registrar verificação apenas quando o HTML foi gerado com sucesso
                s = score or {}
                verificacoes.append({
                    'hash': hash_hex,
                    'nome': nome,
                    'nota_final': s.get('nota_final', _SCORE_DEFAULTS['nota_final']),
                    'max_nota': s.get('max_nota', _SCORE_DEFAULTS['max_nota']),
                    'classificacao': s.get('classificacao', _SCORE_DEFAULTS['classificacao']),
                    'data_emissao': data_emissao,
                    'ciclo': ciclo,
                })
            except Exception as e:
                print(f"✗ Erro ao gerar HTML para {nome}: {e}")
                html_content = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>Erro - {_html.escape(nome)}</title></head>
<body>
<h1>Erro ao gerar dashboard para {_html.escape(nome)}</h1>
<pre>{_html.escape(str(e))}</pre>
</body></html>"""

            try:
                with open(html_file, 'w', encoding='utf-8') as fh:
                    fh.write(html_content)
            except Exception as e:
                print(f"✗ Erro ao salvar HTML para {nome}: {e}")
                # If we can't save HTML, skip PDF generation for this ONG
                continue

            if PLAYWRIGHT_AVAILABLE:
                try:
                    with sync_playwright() as p:
                        browser = p.chromium.launch()
                        page = browser.new_page()
                        page.goto(f"file://{os.path.abspath(html_file)}")
                        page.wait_for_timeout(500)
                        page.pdf(
                            path=pdf_file,
                            width="1414px",
                            height="2000px",
                            print_background=True,
                        )
                        browser.close()
                    pdf_count += 1
                    print(f"✓ PDF criado: {pdf_file}")
                except Exception as e:
                    print(f"✗ Erro ao gerar PDF para {nome}: {e}")
            else:
                print(f"⚠️  playwright não disponível: pulando conversão para {nome}. HTML salvo em {html_file}")
        except Exception as e:
            print(f"✗ Erro inesperado processando {nome}: {e}")
            continue

    # Salvar registros de verificação (acumula entradas do mesmo mês)
    verificacoes_path = os.path.join(_base, 'output', f'verificacoes_{data_emissao}.json')
    try:
        existing = []
        if os.path.exists(verificacoes_path):
            with open(verificacoes_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        existing.extend(verificacoes)
        with open(verificacoes_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f"Verificações salvas: {verificacoes_path} ({len(verificacoes)} registros)")
    except Exception as e:
        print(f"Aviso: erro ao salvar verificações: {e}")

    print('\n' + '=' * 60)
    print(f"Total de PDFs gerados: {pdf_count}/{len(oscs)}")
    print(f"Pasta de saída: {base_out}")


if __name__ == '__main__':
    main()
