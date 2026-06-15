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
import random
import re
from datetime import datetime, timedelta

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

    cor_classificacao = _COR_CLASSIFICACAO.get(classificacao, '#6b7280')  # noqa: F841
    tag_texto = 'Com termos/emendas' if tag == 'com_termos_emendas' else 'Sem termos/emendas'

    badges_html_parts = []
    if badges.get('cebas'):
        badges_html_parts.append('<span class="pill pill-badge">CEBAS</span>')
    if badges.get('utilidade_publica'):
        badges_html_parts.append('<span class="pill pill-badge">Utilidade Pública</span>')
    badges_html = ''.join(badges_html_parts)

    data_emissao = datetime.now().strftime('%Y-%m')
    hash_hex = _gerar_hash(nome, data_emissao, nota_final, max_nota, classificacao)
    hash_curto = hash_hex[:12]
    qr_url = f'https://etransparente.org/verificar/{hash_hex}'
    qr_data_uri = _gerar_qr_data_uri(qr_url)

    descricao = osc.get('descricao_objeto_social', '') or ''
    descricao_obj = _html.escape(descricao[:400] + '...' if len(descricao) > 400 else descricao) if descricao else ''  # noqa: F841
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

    info_preenchida = contar_info_preenchida(osc)  # noqa: F841
    total_termos = contar_termos(osc)

    municipio_q = int(osc.get('termos', {}).get('municipio', {}).get('quantidade', 0) or 0)
    estado_q = int(osc.get('termos', {}).get('estado', {}).get('quantidade', 0) or 0)
    uniao_q = int(osc.get('termos', {}).get('uniao', {}).get('quantidade', 0) or 0)
    emendas_q = int(osc.get('termos', {}).get('emendas_parlamentares', {}).get('quantidade', 0) or 0)

    municipio_disp = municipio_q if municipio_q else 'Nenhum'
    estado_disp = estado_q if estado_q else 'Nenhum'
    uniao_disp = uniao_q if uniao_q else 'Nenhum'
    emendas_disp = emendas_q if emendas_q else 'Nenhuma'

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

    if outras_redes:
        parts = [p.strip() for p in re.split('[;,]', outras_redes) if p.strip()]
        for p in parts:
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

    socials_html = ''
    if social_items:
        items = []
        for idx, (label, href, kind) in enumerate(social_items, start=1):
            icon = icon_svg(kind)
            items.append(f'<li><span class="index">{idx}.</span> <a class="social" href="{_html.escape(href)}" target="_blank">{icon} {_html.escape(label)}</a></li>')
        socials_html = '<ol class="social-list">' + '\n'.join(items) + '</ol>'
    else:
        socials_html = '<div class="none">Nenhum</div>'

    if documentos_labels:
        docs_html_items = ''.join(f'<li>{_html.escape(lbl)}</li>' for lbl in documentos_labels)
        docs_html = f'<ul class="docs-list">{docs_html_items}</ul>'
    else:
        docs_html = '<div class="none">Nenhum</div>'

    # Identificar campos faltantes
    campos_faltantes = []
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
    if not instagram:
        campos_faltantes.append('Instagram')
    if not linkedin:
        campos_faltantes.append('LinkedIn')
    if not youtube:
        campos_faltantes.append('YouTube')
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
    for ano in ['2024', '2023', '2022']:
        if not documentos.get(f'balanco_{ano}'):
            campos_faltantes.append(f'Balanço {ano}')

    if campos_faltantes:
        faltantes_html = f'<div style="color:#dc2626;font-size:0.9rem;line-height:1.6;">{_html.escape(", ".join(campos_faltantes))}</div>'
    else:
        faltantes_html = '<div style="color:#16a34a;font-weight:500;font-size:0.95rem;">Todos os dados de transparência estão disponíveis.</div>'

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
    for fp in (regular_path, medium_path, bold_path):
        if not os.path.exists(fp):
            print(f"[dash.py] Aviso: fonte não encontrada em {fp}.")

    regular_url = f'file://{regular_path}'
    medium_url = f'file://{medium_path}'
    bold_url = f'file://{bold_path}'

    # Logo da ONG
    logo_url = ""
    if logo_local_path and os.path.exists(logo_local_path):
        logo_url = f'file://{os.path.abspath(logo_local_path)}'
    else:
        slug = ''
        match = re.search(r'/oscs/([^/]+)/?$', url)
        if match:
            slug = match.group(1)
            logo_path = os.path.join(repo_root, 'assets', 'img', 'logos-ongs', f'{slug}.jpg')
            if os.path.exists(logo_path):
                logo_url = f'file://{logo_path}'
        if not logo_url:
            safe_name = re.sub(r'[^A-Za-z0-9_-]+', '_', nome).strip('_') or 'logo'
            logo_path = os.path.join(repo_root, 'assets', 'img', 'logos-ongs', f'{safe_name}.jpg')
            if os.path.exists(logo_path):
                logo_url = f'file://{logo_path}'
        if not logo_url:
            default_logo = os.path.join(repo_root, 'assets', 'img', 'logo-default.png')
            if os.path.exists(default_logo):
                logo_url = f'file://{default_logo}'
            else:
                logo_url = "https://via.placeholder.com/80x80/1e3a8a/ffffff?text=Logo"

    if qr_data_uri:
        qr_img_tag = f'<img src="{qr_data_uri}" width="70" height="70" style="display:block;" alt="QR Code"/>'
    else:
        qr_img_tag = '<div style="width:70px;height:70px;background:#f1f5f9;border-radius:4px;"></div>'

    # ── variáveis para o novo layout ─────────────────────────────────────────
    sobre_card = ''
    if descricao.strip():
        sobre_card = (
            f'<div class="card about-card">'
            f'<div class="section-title">SOBRE A ORGANIZAÇÃO</div>'
            f'<p class="about-text">{_html.escape(descricao)}</p>'
            f'</div>'
        )

    _hoje = datetime.now()
    _chart_labels = [(_hoje - timedelta(days=29 - i)).strftime('%d/%m') for i in range(30)]
    _chart_data = [random.randint(10, 80) for _ in range(30)]
    chart_labels_js = json.dumps(_chart_labels)
    chart_data_js = str(_chart_data)

    idc_logo_path = os.path.join(repo_root, 'assets', 'img', 'LOGOIDC.png')
    idc_logo_tag = (
        f'<img src="file://{idc_logo_path}" alt="IDC" style="height:50px;display:block;margin-left:auto;">'
        if os.path.exists(idc_logo_path) else ''
    )

    _PILL_BG = {
        'Regular': 'background:#fee2e2;color:#dc2626',
        'Bom':     'background:#fef9c3;color:#ca8a04',
        'Ótimo':   'background:#dcfce7;color:#16a34a',
    }
    pill_style = _PILL_BG.get(classificacao, 'background:#f1f5f9;color:#374151')

    if campos_faltantes:
        _pc_style = 'background:#fff7ed;border-left:4px solid #f97316;border-radius:8px;padding:16px 20px;margin-bottom:12px;'
        _pt_style = 'color:#c2410c'
    else:
        _pc_style = 'background:#f0fdf4;border-left:4px solid #22c55e;border-radius:8px;padding:16px 20px;margin-bottom:12px;'
        _pt_style = 'color:#16a34a'

    tel_disp   = _html.escape(telefone)    if telefone    else '—'
    email_disp = _html.escape(email)       if email       else '—'
    website_link = (
        f'<a href="{_html.escape(website)}" style="color:#1e3a8a;word-break:break-all;">'
        f'{_html.escape(website)}</a>'
    ) if website else '—'
    loc_disp  = _html.escape(localizacao)  if localizacao else '—'
    cnpj_disp = _html.escape(cnpj)         if cnpj        else '—'
    n_docs = len(documentos_labels)
    # ─────────────────────────────────────────────────────────────────────────

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Dashboard - {_html.escape(nome)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
@font-face {{
    font-family:'MontserratLocal';
    src:url('{regular_url}') format('woff2');
    font-weight:400; font-style:normal;
}}
@font-face {{
    font-family:'MontserratLocal';
    src:url('{medium_url}') format('woff2');
    font-weight:500; font-style:normal;
}}
@font-face {{
    font-family:'MontserratLocal';
    src:url('{bold_url}') format('woff2');
    font-weight:700; font-style:normal;
}}
@page {{ size:210mm auto; margin:0; }}
* {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; box-sizing:border-box; }}
@media print {{ body {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }} }}
html,body {{
    margin:0; padding:0; background:#f1f5f9;
    font-family:'MontserratLocal','Montserrat','Segoe UI',Arial,sans-serif;
    font-size:13px; color:#1e293b;
}}
.header-strip {{ background:#1e3a8a; padding:16px 24px; }}
.header-strip-title {{
    color:#fff; font-weight:700; font-size:13px;
    letter-spacing:1px; text-transform:uppercase; margin-bottom:4px;
}}
.header-strip-sub {{ color:rgba(255,255,255,0.8); font-size:10px; }}
.page-content {{ padding:16px; }}
.card {{
    background:#fff; border-radius:8px;
    box-shadow:0 1px 4px rgba(0,0,0,0.08);
    padding:16px 20px; margin-bottom:12px;
}}
.about-card {{ background:#f8fafc; }}
.section-title {{
    text-transform:uppercase; font-size:10px; letter-spacing:1px;
    color:#64748b; margin-bottom:8px; font-weight:600;
}}
.ong-logo {{ width:60px; height:60px; border-radius:50%; object-fit:cover; display:block; }}
.ong-nome {{ font-size:20px; font-weight:700; color:#1e3a8a; margin-bottom:8px; word-break:break-word; }}
.ong-nome a {{ color:inherit; text-decoration:none; }}
.ong-meta {{ display:flex; flex-wrap:wrap; align-items:center; gap:6px; }}
.pill {{ display:inline-block; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600; }}
.pill-tag {{ background:#e0f2fe; color:#0369a1; }}
.pill-badge {{ background:#f3e8ff; color:#7c3aed; }}
.nota-text {{ font-size:12px; color:#374151; }}
.nota-text b {{ color:#1e3a8a; }}
.about-text {{ margin:0; font-size:12px; color:#374151; line-height:1.7; }}
.chart-note {{ font-size:10px; color:#94a3b8; margin-top:6px; }}
.row-2col {{ display:table; width:100%; margin-bottom:12px; }}
.col-half {{ display:table-cell; width:50%; vertical-align:top; }}
.col-half:first-child {{ padding-right:6px; }}
.col-half:last-child {{ padding-left:6px; }}
.col-half .card {{ margin-bottom:0; }}
.info-row {{ display:table; width:100%; padding:5px 0; border-bottom:1px solid #f1f5f9; font-size:12px; }}
.info-row:last-child {{ border-bottom:none; }}
.info-label {{ display:table-cell; color:#1e3a8a; font-weight:600; width:85px; padding-right:8px; vertical-align:top; }}
.info-val {{ display:table-cell; color:#374151; word-break:break-word; vertical-align:top; }}
.contracts-total {{ font-size:28px; font-weight:700; color:#1e3a8a; margin-bottom:8px; line-height:1; }}
.social-list {{ list-style:none; padding:0; margin:0; }}
.social-list li {{ padding:4px 0; border-bottom:1px solid #f1f5f9; font-size:12px; }}
.social-list li:last-child {{ border-bottom:none; }}
.social {{ color:#1e3a8a; text-decoration:none; display:inline-flex; align-items:center; gap:5px; }}
.social svg {{ flex-shrink:0; }}
.index {{ color:#9ca3af; margin-right:4px; font-size:11px; }}
.docs-list {{ list-style:none; padding:0; margin:0; }}
.docs-list li {{ font-size:11px; color:#374151; padding:4px 0; border-bottom:1px solid #f1f5f9; line-height:1.4; }}
.docs-list li:last-child {{ border-bottom:none; }}
.docs-list li::before {{ content:"✓ "; color:#16a34a; font-weight:700; }}
.none {{ font-size:12px; color:#9ca3af; }}
.footer {{ border-top:2px solid #e2e8f0; padding-top:14px; margin-top:4px; }}
.footer-table {{ width:100%; border-collapse:collapse; }}
.hash-code {{ font-family:monospace; font-size:11px; color:#374151; font-weight:600; margin-bottom:3px; }}
.verify-text {{ font-size:11px; color:#6b7280; line-height:1.4; }}
</style>
</head>
<body>

<div class="header-strip">
    <div class="header-strip-title">RELATÓRIO MENSAL DO ÍNDICE DE TRANSPARÊNCIA</div>
    <div class="header-strip-sub">Elaborado com dados da plataforma etransparente.org — Instituto de Direito Coletivo ©</div>
</div>

<div class="page-content">

    <div class="card">
        <table width="100%" cellpadding="0" cellspacing="0"><tr>
            <td width="76" style="vertical-align:middle;padding-right:16px;">
                <a href="{_html.escape(url)}" target="_blank" rel="noopener noreferrer">
                    <img src="{logo_url}" class="ong-logo" alt="Logo">
                </a>
            </td>
            <td style="vertical-align:middle;">
                <div class="ong-nome">
                    <a href="{_html.escape(url)}" target="_blank" rel="noopener noreferrer">{_html.escape(nome)}</a>
                </div>
                <div class="ong-meta">
                    <span class="pill" style="{pill_style}">{_html.escape(classificacao)}</span>
                    <span class="nota-text"><b>Nota:</b> {nota_final}/{max_nota}</span>
                    <span class="pill pill-tag">{_html.escape(tag_texto)}</span>
                    {badges_html}
                </div>
            </td>
        </tr></table>
    </div>

    {sobre_card}

    <div class="card">
        <div class="section-title">VISUALIZAÇÕES NO SITE — ÚLTIMO MÊS</div>
        <canvas id="viewsChart" height="120"></canvas>
        <div class="chart-note">* Dados de visualização do etransparente.org via Google Analytics</div>
    </div>

    <div class="row-2col">
        <div class="col-half"><div class="card">
            <div class="section-title">INFORMAÇÕES</div>
            <div class="info-row"><span class="info-label">Telefone</span><span class="info-val">{tel_disp}</span></div>
            <div class="info-row"><span class="info-label">E-mail</span><span class="info-val">{email_disp}</span></div>
            <div class="info-row"><span class="info-label">Website</span><span class="info-val">{website_link}</span></div>
            <div class="info-row"><span class="info-label">Localização</span><span class="info-val">{loc_disp}</span></div>
            <div class="info-row"><span class="info-label">CNPJ</span><span class="info-val">{cnpj_disp}</span></div>
        </div></div>
        <div class="col-half"><div class="card">
            <div class="section-title">CONTRATOS E PARCERIAS</div>
            <div class="contracts-total">{total_termos}</div>
            <div class="info-row"><span class="info-label">Município</span><span class="info-val">{municipio_disp}</span></div>
            <div class="info-row"><span class="info-label">Estado</span><span class="info-val">{estado_disp}</span></div>
            <div class="info-row"><span class="info-label">União</span><span class="info-val">{uniao_disp}</span></div>
            <div class="info-row"><span class="info-label">Emendas parl.</span><span class="info-val">{emendas_disp}</span></div>
        </div></div>
    </div>

    <div class="row-2col">
        <div class="col-half"><div class="card">
            <div class="section-title">REDES SOCIAIS</div>
            {socials_html}
        </div></div>
        <div class="col-half"><div class="card">
            <div class="section-title">DOCUMENTOS ({n_docs})</div>
            {docs_html}
        </div></div>
    </div>

    <div style="{_pc_style}">
        <div class="section-title" style="{_pt_style}">DADOS OU DOCUMENTOS PENDENTES</div>
        {faltantes_html}
    </div>

    <div class="footer">
        <table class="footer-table"><tr>
            <td style="vertical-align:middle;width:80px;">{qr_img_tag}</td>
            <td style="vertical-align:middle;padding-left:12px;">
                <div class="hash-code">Código: {hash_curto}</div>
                <div class="verify-text">Documento oficial emitido pelo IDC. Verifique em <b>etransparente.org/verificar</b></div>
            </td>
            <td style="vertical-align:middle;text-align:right;">
                {idc_logo_tag}
                <div style="color:#64748b;font-size:11px;margin-top:4px;">etransparente.org</div>
            </td>
        </tr></table>
    </div>

</div>

<script>
const ctx = document.getElementById('viewsChart').getContext('2d');
new Chart(ctx, {{
    type: 'line',
    data: {{
        labels: {chart_labels_js},
        datasets: [{{
            data: {chart_data_js},
            borderColor: '#1e3a8a',
            backgroundColor: 'rgba(30,58,138,0.1)',
            fill: true,
            tension: 0.4,
            pointRadius: 0,
            borderWidth: 2
        }}]
    }},
    options: {{
        responsive: true,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 9 }} }} }},
            y: {{ grid: {{ color: '#f1f5f9' }}, ticks: {{ font: {{ size: 9 }} }} }}
        }}
    }}
}});
</script>

</body>
</html>"""

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

    mes_nome = datetime.now().strftime('%B').lower()
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

        slug = ''
        match = re.search(r'/oscs/([^/]+)/?$', url)
        if match:
            slug = match.group(1)
        else:
            slug = ''.join(c if c.isalnum() or c in ('-', '_') else '-' for c in nome).lower()
            slug = re.sub(r'-+', '-', slug).strip('-')[:50]

        nome_arquivo = f"Relatório-etransparente-{mes_nome}-de-{ano}-{slug}"

        html_file = os.path.join(html_dir, f"{nome_arquivo}.html")
        pdf_file = os.path.join(pdf_dir, f"{nome_arquivo}.pdf")

        try:
            try:
                html_content, hash_hex = gerar_dashboard_html(osc, score)
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
<html><head><meta charset="utf-8"><title>Erro - {_html.escape(nome)}</title></head>
<body>
<h1>Erro ao gerar dashboard para {_html.escape(nome)}</h1>
<pre>{_html.escape(str(e))}</pre>
</body></html>"""

            try:
                with open(html_file, 'w', encoding='utf-8') as fh:
                    fh.write(html_content)
            except Exception as e:
                print(f"✗ Erro ao salvar HTML para {nome}: {e}")
                continue

            if PLAYWRIGHT_AVAILABLE:
                try:
                    with sync_playwright() as p:
                        browser = p.chromium.launch()
                        page = browser.new_page()
                        page.goto(f"file://{os.path.abspath(html_file)}")
                        page.wait_for_timeout(1500)
                        page.pdf(
                            path=pdf_file,
                            width="210mm",
                            print_background=True,
                            prefer_css_page_size=False,
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
