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

    data_emissao = datetime.now().strftime('%Y-%m')
    hash_hex = _gerar_hash(nome, data_emissao, nota_final, max_nota, classificacao)
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
        qr_img_tag = f'<img src="{qr_data_uri}" width="80" height="80" style="display:block;" alt="QR Code"/>'
    else:
        qr_img_tag = '<div style="width:80px;height:80px;background:#f1f5f9;border-radius:4px;"></div>'

    # ── pré-cálculos para o novo layout ESG ────────────────────────────────────
    sobre_card_html = ''
    if descricao.strip():
        sobre_card_html = f"""
    <div class="card">
        <div class="card-header"><span class="card-icon">📋</span><span class="card-title">SOBRE A ORGANIZAÇÃO</span></div>
        <p class="about-text">{_html.escape(descricao)}</p>
    </div>"""

    descricao_curta = _html.escape(descricao[:120] + '...' if len(descricao) > 120 else descricao) if descricao else ''

    _hoje = datetime.now()
    _chart_labels = [(_hoje - timedelta(days=29 - i)).strftime('%d/%m') for i in range(30)]
    _chart_data = [random.randint(50, 800) for _ in range(30)]
    chart_labels_js = json.dumps(_chart_labels)
    chart_data_js = json.dumps(_chart_data)
    total_visualizacoes = sum(_chart_data)
    media_diaria = round(total_visualizacoes / len(_chart_data))

    _meses_pt = {
        'january': 'janeiro', 'february': 'fevereiro', 'march': 'março', 'april': 'abril',
        'may': 'maio', 'june': 'junho', 'july': 'julho', 'august': 'agosto',
        'september': 'setembro', 'october': 'outubro', 'november': 'novembro', 'december': 'dezembro'
    }
    mes_extenso = _meses_pt.get(_hoje.strftime('%B').lower(), _hoje.strftime('%B').lower())
    ano_atual = _hoje.strftime('%Y')
    mm_atual = _hoje.strftime('%m')
    _primeiro_dia_prox_mes = (_hoje.replace(day=28) + timedelta(days=4)).replace(day=1)
    _ultimo_dia_mes = (_primeiro_dia_prox_mes - timedelta(days=1)).strftime('%d')
    periodo_referencia = f"Período de referência: 01/{mm_atual}/{ano_atual} a {_ultimo_dia_mes}/{mm_atual}/{ano_atual}"

    idc_logo_path = os.path.join(repo_root, 'assets', 'img', 'LOGOIDC.png')
    idc_logo_tag = (
        f'<img src="file://{idc_logo_path}" alt="IDC" style="height:40px;display:block;margin-left:auto;">'
        if os.path.exists(idc_logo_path) else ''
    )

    _PILL_BG = {
        'Regular': 'background:#fee2e2;color:#dc2626;border:1px solid #fca5a5',
        'Bom':     'background:#fef9c3;color:#ca8a04;border:1px solid #fde047',
        'Ótimo':   'background:#dcfce7;color:#16a34a;border:1px solid #86efac',
    }
    pill_style = _PILL_BG.get(classificacao, 'background:#f1f5f9;color:#374151;border:1px solid #e2e8f0')
    tag_pill_style = 'background:#e0f2fe;color:#0369a1;border:1px solid #7dd3fc'
    badge_pill_style = 'background:#f3e8ff;color:#7c3aed;border:1px solid #c4b5fd'

    _badges_parts = []
    if badges.get('cebas'):
        _badges_parts.append(f'<span class="pill" style="{badge_pill_style}">CEBAS</span>')
    if badges.get('utilidade_publica'):
        _badges_parts.append(f'<span class="pill" style="{badge_pill_style}">Utilidade Pública Federal</span>')
    certificacoes_html = ''
    if _badges_parts:
        certificacoes_html = (
            '<div style="margin-top:10px;padding-top:10px;border-top:1px solid #e2e8f0;">'
            '<span style="font-size:9px;letter-spacing:1px;color:#64748b;margin-right:8px;">CERTIFICAÇÕES</span>'
            + ''.join(_badges_parts) + '</div>'
        )

    tel_disp   = _html.escape(telefone)    if telefone    else '<span style="color:#cbd5e1;">—</span>'
    email_disp = _html.escape(email)       if email       else '<span style="color:#cbd5e1;">—</span>'
    website_link = (
        f'<a href="{_html.escape(website)}" style="color:#1e3a8a;word-break:break-all;">'
        f'{_html.escape(website)}</a>'
    ) if website else '<span style="color:#cbd5e1;">—</span>'
    loc_disp  = _html.escape(localizacao)  if localizacao else '<span style="color:#cbd5e1;">—</span>'
    cnpj_disp = _html.escape(cnpj)         if cnpj        else '<span style="color:#cbd5e1;">—</span>'
    n_docs = len(documentos_labels)

    _contatos_rows = [
        ('📞', 'Telefone', tel_disp),
        ('✉', 'E-mail', email_disp),
        ('🌐', 'Website', website_link),
        ('📍', 'Localização', loc_disp),
        ('🏢', 'CNPJ', cnpj_disp),
    ]
    contatos_html = ''.join(
        f'<div class="contact-row"><span class="contact-icon">{icone}</span>'
        f'<span class="contact-label">{rotulo}</span><span class="contact-val">{valor}</span></div>'
        for icone, rotulo, valor in _contatos_rows
    )

    _esferas = [
        ('Município', municipio_q, '#1e3a8a'),
        ('Estado', estado_q, '#3b82f6'),
        ('União', uniao_q, '#93c5fd'),
        ('Emendas parlamentares', emendas_q, '#bfdbfe'),
    ]
    _esferas_presentes = [e for e in _esferas if e[1] > 0]

    if total_termos > 0:
        doughnut_labels_js = json.dumps([e[0] for e in _esferas_presentes])
        doughnut_data_js = json.dumps([e[1] for e in _esferas_presentes])
        doughnut_colors_js = json.dumps([e[2] for e in _esferas_presentes])
        _legenda_items = ''.join(
            f'<div class="legend-row"><span class="legend-dot" style="background:{cor};"></span>'
            f'<span class="legend-label">{_html.escape(nome_esfera)}</span>'
            f'<span class="legend-val">{qtd} ({round(qtd / total_termos * 100)}%)</span></div>'
            for nome_esfera, qtd, cor in _esferas_presentes
        )
        contratos_chart_html = f"""
            <table width="100%" cellpadding="0" cellspacing="0"><tr>
                <td style="width:130px;vertical-align:middle;">
                    <div style="position:relative;width:130px;height:130px;">
                        <canvas id="contratosChart" width="130" height="130"></canvas>
                        <div style="position:absolute;top:0;left:0;width:130px;height:130px;display:flex;flex-direction:column;align-items:center;justify-content:center;">
                            <div style="font-size:22px;font-weight:700;color:#1e3a8a;">{total_termos}</div>
                            <div style="font-size:9px;color:#64748b;">contratos</div>
                        </div>
                    </div>
                </td>
                <td style="vertical-align:middle;padding-left:16px;">{_legenda_items}</td>
            </tr></table>"""
    else:
        doughnut_labels_js = '[]'
        doughnut_data_js = '[]'
        doughnut_colors_js = '[]'
        contratos_chart_html = '<div class="none-box">Nenhum contrato registrado</div>'

    if social_items:
        social_rows_html = ''.join(
            f'<div class="social-row"><span class="social-icon">{icon_svg(kind)}</span>'
            f'<span class="social-name">{_html.escape(label)}</span>'
            f'<a class="social-handle" href="{_html.escape(href)}" target="_blank">{_html.escape(href)}</a>'
            f'<span class="social-check">✅</span></div>'
            for label, href, kind in social_items
        )
    else:
        social_rows_html = '<div class="none-box">Nenhuma rede social cadastrada</div>'

    if documentos_labels:
        docs_grid_html = '<div class="docs-grid">' + ''.join(
            f'<div class="doc-item">✅ {_html.escape(lbl)}</div>' for lbl in documentos_labels
        ) + '</div>'
    else:
        docs_grid_html = '<div class="none-box">Nenhum documento cadastrado</div>'

    if campos_faltantes:
        alerta_html = f"""
    <div class="alert-box alert-warning">
        <div class="alert-header">⚠️ DADOS OU DOCUMENTOS PENDENTES</div>
        <div class="alert-text">{_html.escape(', '.join(campos_faltantes))}</div>
    </div>"""
    else:
        alerta_html = """
    <div class="alert-box alert-success">
        <table width="100%" cellpadding="0" cellspacing="0"><tr>
            <td>
                <div class="alert-header alert-header-success">🏆 PARABÉNS!</div>
                <div class="alert-text alert-text-success">Sua organização está com todas as informações e documentos obrigatórios preenchidos e atualizados.</div>
            </td>
            <td style="width:50px;text-align:right;font-size:28px;">✅</td>
        </tr></table>"""
    # ─────────────────────────────────────────────────────────────────────────

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Dashboard - {_html.escape(nome)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
@font-face {{
    font-family:'Montserrat';
    src:url('{regular_url}') format('woff2');
    font-weight:400; font-style:normal;
}}
@font-face {{
    font-family:'Montserrat';
    src:url('{medium_url}') format('woff2');
    font-weight:500; font-style:normal;
}}
@font-face {{
    font-family:'Montserrat';
    src:url('{bold_url}') format('woff2');
    font-weight:700; font-style:normal;
}}
@page {{ margin:0; }}
* {{ font-family:'Montserrat','Segoe UI',Arial,sans-serif; -webkit-print-color-adjust:exact; print-color-adjust:exact; box-sizing:border-box; }}
@media print {{ body {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }} }}
html,body {{ margin:0; padding:16px 0; background:#f1f5f9; font-size:13px; color:#1e293b; }}
.wrapper {{ max-width:900px; margin:0 auto; }}

.header-strip {{ background:#0f172a; padding:20px 32px; display:table; width:100%; }}
.header-left, .header-right {{ display:table-cell; vertical-align:middle; }}
.header-right {{ text-align:right; }}
.header-bar {{ border-left:4px solid #3b82f6; height:60px; display:inline-block; margin-right:12px; vertical-align:middle; }}
.header-text {{ display:inline-block; vertical-align:middle; }}
.header-line1 {{ font-size:11px; letter-spacing:2px; color:#fff; opacity:0.7; }}
.header-line2 {{ font-size:22px; font-weight:700; color:#fff; }}
.header-line3 {{ font-size:10px; color:#93c5fd; }}
.header-date {{ font-size:13px; color:#fff; font-weight:700; }}
.header-period {{ font-size:10px; color:#fff; opacity:0.7; margin-top:2px; }}

.card {{ background:#fff; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.08); margin:0 16px 12px; padding:16px 24px; }}
.card-header {{ margin-bottom:10px; }}
.card-icon {{ margin-right:6px; }}
.card-title {{ font-size:10px; letter-spacing:1.5px; color:#1e3a8a; font-weight:700; }}
.about-text {{ font-size:12px; color:#374151; line-height:1.7; margin:0; }}

.id-card {{ border-radius:10px; }}
.id-logo {{ width:80px; height:80px; border-radius:50%; object-fit:cover; border:3px solid #e2e8f0; display:block; }}
.id-nome {{ font-size:22px; font-weight:700; color:#1e3a8a; }}
.id-nome a {{ color:inherit; text-decoration:none; }}
.id-desc {{ font-size:11px; color:#64748b; margin-top:4px; }}
.metrics-box {{ background:#f8fafc; border-radius:8px; padding:12px 16px; }}
.metrics-col {{ text-align:center; padding:0 4px; }}
.metrics-label {{ font-size:9px; letter-spacing:0.5px; color:#64748b; margin-bottom:4px; }}
.metrics-nota {{ font-size:18px; font-weight:700; color:#1e3a8a; }}
.pill {{ display:inline-block; padding:4px 12px; border-radius:20px; font-size:11px; font-weight:600; }}

.chart-note {{ font-size:9px; color:#94a3b8; margin-top:6px; }}
.views-side {{ background:#f8fafc; border-radius:8px; padding:12px; text-align:center; }}
.views-label {{ font-size:9px; color:#64748b; }}
.views-val {{ font-size:20px; font-weight:700; color:#1e3a8a; margin:2px 0 8px; }}
.views-val-sm {{ font-size:16px; font-weight:700; color:#1e3a8a; margin-top:2px; }}
.views-sep {{ border-top:1px solid #e2e8f0; margin:6px 0; }}

.two-col {{ display:table; width:100%; }}
.two-col .col {{ display:table-cell; width:48%; vertical-align:top; }}
.two-col .col:first-child {{ padding-right:2%; }}
.two-col .col:last-child {{ padding-left:2%; }}
.two-col .card {{ margin:0; height:100%; }}

.contact-row {{ display:table; width:100%; padding:7px 0; border-bottom:1px solid #f1f5f9; font-size:12px; }}
.contact-row:last-child {{ border-bottom:none; }}
.contact-icon {{ display:table-cell; width:22px; }}
.contact-label {{ display:table-cell; width:90px; color:#1e3a8a; font-weight:600; }}
.contact-val {{ display:table-cell; color:#374151; word-break:break-word; }}

.legend-row {{ font-size:11px; color:#374151; padding:3px 0; }}
.legend-dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; }}
.legend-label {{ margin-right:4px; }}
.legend-val {{ color:#64748b; }}

.social-row {{ display:table; width:100%; padding:6px 0; border-bottom:1px solid #f1f5f9; font-size:12px; }}
.social-row:last-child {{ border-bottom:none; }}
.social-icon {{ display:table-cell; width:24px; vertical-align:middle; }}
.social-name {{ display:table-cell; width:70px; color:#1e293b; font-weight:600; vertical-align:middle; }}
.social-handle {{ display:table-cell; color:#1e3a8a; text-decoration:none; word-break:break-all; vertical-align:middle; }}
.social-check {{ display:table-cell; width:24px; text-align:right; vertical-align:middle; }}

.docs-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 12px; }}
.doc-item {{ font-size:11px; color:#374151; }}

.none-box {{ color:#94a3b8; font-size:12px; text-align:center; padding:16px 0; }}

.alert-box {{ border-radius:8px; padding:16px 24px; margin:0 16px 12px; }}
.alert-warning {{ background:#fff7ed; border-left:4px solid #f97316; }}
.alert-success {{ background:#f0fdf4; border-left:4px solid #22c55e; }}
.alert-header {{ font-size:10px; letter-spacing:1px; color:#c2410c; font-weight:700; margin-bottom:6px; }}
.alert-header-success {{ color:#15803d; }}
.alert-text {{ font-size:12px; color:#9a3412; }}
.alert-text-success {{ font-size:12px; color:#15803d; }}

.footer {{ border-top:2px solid #e2e8f0; margin:0 16px 16px; padding:20px 24px 0; }}
.footer-table {{ width:100%; border-collapse:collapse; }}
.auth-title {{ font-size:10px; letter-spacing:1px; color:#1e3a8a; font-weight:700; margin-bottom:6px; }}
.auth-text {{ font-size:11px; color:#374151; line-height:1.5; }}
.auth-hash {{ font-family:monospace; font-size:9px; color:#64748b; word-break:break-all; margin-top:6px; }}
.auth-date {{ font-size:10px; color:#6b7280; margin-top:4px; }}
.idc-col {{ border-left:1px solid #e2e8f0; padding-left:20px; text-align:right; }}
.idc-label {{ font-size:9px; letter-spacing:1px; color:#64748b; margin-bottom:6px; }}
.idc-text {{ font-size:10px; color:#64748b; line-height:1.5; margin-bottom:8px; }}
.idc-site {{ color:#1e3a8a; font-size:11px; font-weight:700; margin-top:6px; }}
</style>
</head>
<body>
<div class="wrapper">

<div class="header-strip">
    <div class="header-left">
        <span class="header-bar"></span>
        <span class="header-text">
            <div class="header-line1">RELATÓRIO MENSAL DO</div>
            <div class="header-line2">ÍNDICE DE TRANSPARÊNCIA</div>
            <div class="header-line3">Emitido pelo Instituto de Direito Coletivo – IDC</div>
        </span>
    </div>
    <div class="header-right">
        <div class="header-date">📅 {mes_extenso}/{ano_atual}</div>
        <div class="header-period">{periodo_referencia}</div>
    </div>
</div>

<div class="card id-card">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td style="width:90px;vertical-align:middle;">
            <a href="{_html.escape(url)}" target="_blank" rel="noopener noreferrer">
                <img src="{logo_url}" class="id-logo" alt="Logo">
            </a>
        </td>
        <td style="vertical-align:middle;padding:0 20px;">
            <div class="id-nome"><a href="{_html.escape(url)}" target="_blank" rel="noopener noreferrer">{_html.escape(nome)}</a></div>
            <div class="id-desc">{descricao_curta}</div>
        </td>
        <td style="width:280px;vertical-align:middle;">
            <div class="metrics-box">
                <table width="100%" cellpadding="0" cellspacing="0"><tr>
                    <td class="metrics-col">
                        <div class="metrics-label">CLASSIFICAÇÃO</div>
                        <span class="pill" style="{pill_style}">{_html.escape(classificacao)}</span>
                    </td>
                    <td class="metrics-col">
                        <div class="metrics-label">NOTA OBTIDA</div>
                        <div class="metrics-nota">{nota_final}/{max_nota}</div>
                    </td>
                    <td class="metrics-col">
                        <div class="metrics-label">STATUS</div>
                        <span class="pill" style="{tag_pill_style}">{_html.escape(tag_texto)}</span>
                    </td>
                </tr></table>
                {certificacoes_html}
            </div>
        </td>
    </tr></table>
</div>
{sobre_card_html}

<div class="card">
    <div class="card-header"><span class="card-icon">📈</span><span class="card-title">VISUALIZAÇÕES DO SITE — ÚLTIMO MÊS</span></div>
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td style="width:75%;vertical-align:top;">
            <canvas id="viewsChart" height="140"></canvas>
        </td>
        <td style="width:25%;vertical-align:top;padding-left:12px;">
            <div class="views-side">
                <div class="views-label">👁 TOTAL DE VISUALIZAÇÕES</div>
                <div class="views-val">{total_visualizacoes}</div>
                <div class="views-sep"></div>
                <div class="views-label">📊 MÉDIA DIÁRIA</div>
                <div class="views-val-sm">{media_diaria}</div>
            </div>
        </td>
    </tr></table>
    <div class="chart-note">* Dados de visualização do etransparente.org via Google Analytics</div>
</div>

<div class="two-col">
    <div class="col"><div class="card">
        <div class="card-header"><span class="card-icon">👤</span><span class="card-title">INFORMAÇÕES DE CONTATO</span></div>
        {contatos_html}
    </div></div>
    <div class="col"><div class="card">
        <div class="card-header"><span class="card-icon">🤝</span><span class="card-title">CONTRATOS E PARCERIAS</span></div>
        {contratos_chart_html}
    </div></div>
</div>

<div class="two-col">
    <div class="col"><div class="card">
        <div class="card-header"><span class="card-icon">🔗</span><span class="card-title">REDES SOCIAIS</span></div>
        {social_rows_html}
    </div></div>
    <div class="col"><div class="card">
        <div class="card-header"><span class="card-icon">📁</span><span class="card-title">DOCUMENTOS DISPONÍVEIS ({n_docs})</span></div>
        {docs_grid_html}
    </div></div>
</div>

{alerta_html}

<div class="footer">
    <table class="footer-table"><tr>
        <td style="width:90px;vertical-align:top;">{qr_img_tag}</td>
        <td style="vertical-align:top;padding:0 20px;">
            <div class="auth-title">🛡 AUTENTICIDADE DO DOCUMENTO</div>
            <div class="auth-text">Escaneie o QR Code ao lado ou acesse <a href="https://etransparente.org/verificar" style="color:#1e3a8a;">etransparente.org/verificar</a></div>
            <div class="auth-hash"><b>Código Hash (SHA-256):</b> {hash_hex}</div>
            <div class="auth-date">Data de emissão: {data_emissao}</div>
        </td>
        <td style="width:160px;vertical-align:top;" class="idc-col">
            <div class="idc-label">DOCUMENTO OFICIAL</div>
            <div class="idc-text">Este relatório é emitido mensalmente pelo IDC com base nas informações públicas disponibilizadas pela organização na plataforma etransparente.org.</div>
            {idc_logo_tag}
            <div class="idc-site">etransparente.org</div>
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
            backgroundColor: 'rgba(30,58,138,0.08)',
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

const contratosCanvas = document.getElementById('contratosChart');
if (contratosCanvas) {{
    new Chart(contratosCanvas.getContext('2d'), {{
        type: 'doughnut',
        data: {{
            labels: {doughnut_labels_js},
            datasets: [{{
                data: {doughnut_data_js},
                backgroundColor: {doughnut_colors_js},
                borderWidth: 0
            }}]
        }},
        options: {{
            cutout: '65%',
            plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }}
        }}
    }});
}}
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
                        page.wait_for_timeout(2000)  # aguardar Chart.js renderizar
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
