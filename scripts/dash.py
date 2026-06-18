"""
Small utility to render one HTML dashboard per ONG (from the latest
`oscs_etransparente_*.json` in `output/`). Saves HTML files under
`output/dashboards/<timestamp>/html` and PDFs under
`output/dashboards/<timestamp>/pdf` using Playwright/Chromium.

Usage: run `python scripts/dash.py` from repository root. The script will
locate the newest `output/oscs_etransparente_*.json` automatically.
"""

import base64
import calendar
import glob
import hashlib
import html as _html
import io
import json
import os
import random
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


def gerar_qr_png(hash_hex: str, url: str) -> str:
    """Gera QR Code como PNG em /tmp e retorna caminho file://"""
    if not QRCODE_AVAILABLE:
        return ''
    try:
        path = f'/tmp/qrcode_{hash_hex[:16]}.png'
        qr = _qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        img.save(path)
        return f'file://{path}'
    except Exception:
        return ''


def imagem_para_base64(caminho: str) -> str:
    """Converte imagem local para data URI base64."""
    if not caminho or not os.path.exists(caminho):
        return ''
    ext = os.path.splitext(caminho)[1].lower().replace('.', '')
    mime = 'jpeg' if ext in ('jpg', 'jpeg') else ext
    with open(caminho, 'rb') as f:
        dados = base64.b64encode(f.read()).decode()
    return f'data:image/{mime};base64,{dados}'


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


_CAMPOS_PADRAO_TERMO = {'situacao_do_termo', 'resultado_da_prestacao_de_contas', 'prestacao_de_contas_da_parceria'}


def _termo_e_real(termo):
    return bool({k for k, v in termo.items() if k not in _CAMPOS_PADRAO_TERMO and v})


def _contar_termos_reais(bloco):
    lista = bloco.get('termos', []) or [] if isinstance(bloco, dict) else []
    return sum(1 for t in lista if isinstance(t, dict) and _termo_e_real(t))


def contar_termos(osc):
    termos = osc.get('termos', {}) or {}
    return sum(_contar_termos_reais(termos.get(c, {}) or {})
               for c in ['municipio', 'estado', 'uniao', 'emendas_parlamentares'])


def gerar_dashboard_html(osc, score=None, views_by_url=None):
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

    data_emissao = datetime.now().strftime('%Y-%m')
    data_emissao_formatada = datetime.now().strftime('%d/%m/%Y')
    hash_hex = _gerar_hash(nome, data_emissao, nota_final, max_nota, classificacao)
    url_verificacao = f'https://etransparente.org/verificar/{hash_hex}'
    qr_path = gerar_qr_png(hash_hex, url_verificacao)

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

    _termos_raw = osc.get('termos', {}) or {}
    municipio_q = _contar_termos_reais(_termos_raw.get('municipio', {}) or {})
    estado_q = _contar_termos_reais(_termos_raw.get('estado', {}) or {})
    uniao_q = _contar_termos_reais(_termos_raw.get('uniao', {}) or {})
    emendas_q = _contar_termos_reais(_termos_raw.get('emendas_parlamentares', {}) or {})

    _PH_SOCIAL_ICONS = {
        'instagram': 'ph-instagram-logo',
        'linkedin': 'ph-linkedin-logo',
        'youtube': 'ph-youtube-logo',
        'facebook': 'ph-facebook-logo',
        'x': 'ph-x-logo',
        'whatsapp': 'ph-whatsapp-logo',
    }

    def phosphor_icon(kind):
        return f'<i class="ph {_PH_SOCIAL_ICONS.get(kind, "ph-globe")}"></i>'

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
            name, kind = 'Site', 'site'
            try:
                host = p.split('://')[-1].split('/')[0].lower()
                if 'facebook' in host:
                    name, kind = 'Facebook', 'facebook'
                elif 'tiktok' in host:
                    name, kind = 'TikTok', 'site'
                elif 'whatsapp' in host or 'wa.me' in host:
                    name, kind = 'WhatsApp', 'whatsapp'
                elif 'x.com' in host or 'twitter' in host:
                    name, kind = 'X', 'x'
                elif 'instagram' in host:
                    name, kind = 'Instagram', 'instagram'
                elif 'linkedin' in host:
                    name, kind = 'LinkedIn', 'linkedin'
                elif 'youtube' in host or 'youtu.be' in host:
                    name, kind = 'YouTube', 'youtube'
            except Exception:
                name, kind = 'Site', 'site'
            social_items.append((name, p, kind))

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

    # Logo da ONG — embutido em base64 para funcionar fora da VM
    logo_url = ""
    logo_path = None
    if logo_local_path and os.path.exists(logo_local_path):
        logo_path = logo_local_path
    else:
        slug = ''
        match = re.search(r'/oscs/([^/]+)/?$', url)
        if match:
            slug = match.group(1)
            candidate = os.path.join(repo_root, 'assets', 'img', 'logos-ongs', f'{slug}.jpg')
            if os.path.exists(candidate):
                logo_path = candidate
        if not logo_path:
            safe_name = re.sub(r'[^A-Za-z0-9_-]+', '_', nome).strip('_') or 'logo'
            candidate = os.path.join(repo_root, 'assets', 'img', 'logos-ongs', f'{safe_name}.jpg')
            if os.path.exists(candidate):
                logo_path = candidate
        if not logo_path:
            default_logo = os.path.join(repo_root, 'assets', 'img', 'logo-default.png')
            if os.path.exists(default_logo):
                logo_path = default_logo
    if logo_path:
        logo_url = imagem_para_base64(logo_path)
    if not logo_url:
        logo_url = "https://via.placeholder.com/80x80/1e3a8a/ffffff?text=Logo"

    if qr_path:
        qr_img_tag = f'<img src="{qr_path}" width="80" height="80" style="display:block;margin:0 auto;" alt="QR Code"/>'
    else:
        qr_img_tag = '<div style="width:80px;height:80px;background:#f1f5f9;border-radius:4px;margin:0 auto;"></div>'

    # ── pré-cálculos para o novo layout ESG ────────────────────────────────────
    sobre_card_html = ''
    if descricao.strip():
        sobre_card_html = f"""
    <div class="card">
        <div class="card-header"><span class="icon-circle"><i class="ph ph-file-text"></i></span><span class="card-title">SOBRE A ORGANIZAÇÃO</span></div>
        <p class="about-text">{_html.escape(descricao)}</p>
    </div>"""

    descricao_curta = _html.escape(descricao[:120] + '...' if len(descricao) > 120 else descricao) if descricao else ''

    _hoje = datetime.now()
    _ano_chart = _hoje.year
    _mes_chart = _hoje.month
    _dias_no_mes = calendar.monthrange(_ano_chart, _mes_chart)[1]
    _chart_labels = [
        datetime(_ano_chart, _mes_chart, d).strftime('%d/%m')
        for d in range(1, _dias_no_mes + 1)
    ]
    views_list = (views_by_url or {}).get(url)
    if views_list and len(views_list) == _dias_no_mes:
        _chart_data = views_list
    else:
        _chart_data = [random.randint(50, 800) for _ in range(_dias_no_mes)]
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
    periodo_referencia = f"Período de referência: 01/{mm_atual}/{ano_atual} a {_dias_no_mes:02d}/{mm_atual}/{ano_atual}"

    idc_logo_path = os.path.join(repo_root, 'assets', 'img', 'LOGOIDC.png')
    idc_logo_b64 = imagem_para_base64(idc_logo_path)
    idc_logo_tag = (
        f'<img src="{idc_logo_b64}" alt="IDC" style="height:32px;display:block;">'
        if idc_logo_b64 else ''
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
        ('<i class="ph ph-phone"></i>', 'Telefone', tel_disp),
        ('<i class="ph ph-envelope-simple"></i>', 'E-mail', email_disp),
        ('<i class="ph ph-globe"></i>', 'Website', website_link),
        ('<i class="ph ph-map-pin"></i>', 'Localização', loc_disp),
        ('<i class="ph ph-buildings"></i>', 'CNPJ', cnpj_disp),
    ]
    contatos_html = ''.join(
        f'<div class="contact-row"><span class="contact-icon"><span class="icon-circle-sm">{icone}</span></span>'
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
            f'<div class="social-row"><span class="social-icon"><span class="icon-circle-sm">{phosphor_icon(kind)}</span></span>'
            f'<span class="social-name">{_html.escape(label)}</span>'
            f'<a class="social-handle" href="{_html.escape(href)}" target="_blank">{_html.escape(href)}</a>'
            f'<span class="social-check"><i class="ph ph-check-circle" style="color:#16a34a;"></i></span></div>'
            for label, href, kind in social_items
        )
    else:
        social_rows_html = '<div class="none-box">Nenhuma rede social cadastrada</div>'

    if documentos_labels:
        docs_grid_html = '<div class="docs-grid">' + ''.join(
            f'<div class="doc-item"><i class="ph ph-check-circle" style="color:#16a34a;"></i> {_html.escape(lbl)}</div>' for lbl in documentos_labels
        ) + '</div>'
    else:
        docs_grid_html = '<div class="none-box">Nenhum documento cadastrado</div>'

    if campos_faltantes:
        alerta_html = f"""
    <div class="alert-box alert-warning">
        <div class="alert-header"><i class="ph ph-warning"></i> DADOS OU DOCUMENTOS PENDENTES</div>
        <div class="alert-text">{_html.escape(', '.join(campos_faltantes))}</div>
    </div>"""
    else:
        alerta_html = """
    <div class="alert-box alert-success">
        <table width="100%" cellpadding="0" cellspacing="0"><tr>
            <td>
                <div class="alert-header alert-header-success"><i class="ph ph-trophy"></i> PARABÉNS!</div>
                <div class="alert-text alert-text-success">Sua organização está com todas as informações e documentos obrigatórios preenchidos e atualizados.</div>
            </td>
            <td style="width:50px;text-align:right;font-size:28px;"><i class="ph ph-check-circle" style="color:#16a34a;"></i></td>
        </tr></table>
    </div>"""
    # ─────────────────────────────────────────────────────────────────────────

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Dashboard - {_html.escape(nome)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://unpkg.com/@phosphor-icons/web"></script>
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
@page {{ size:auto; }}
* {{ font-family:'Montserrat','Segoe UI',Arial,sans-serif; -webkit-print-color-adjust:exact; print-color-adjust:exact; box-sizing:border-box; }}
@media print {{ body {{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }} }}
html,body {{ margin:0; padding:0; background:#f1f5f9; font-size:13px; color:#1e293b; }}
.wrapper {{ max-width:900px; margin:0 auto; }}
.content-wrapper {{ padding-bottom:80px; }}

.header-strip {{
    background:#0f172a;
    padding:20px 32px;
    width:100%;
    box-sizing:border-box;
    display:table;
}}
.header-left, .header-right {{ display:table-cell; vertical-align:middle; }}
.header-right {{ text-align:right; }}
.header-bar {{ border-left:4px solid #3b82f6; height:60px; display:inline-block; margin-right:12px; vertical-align:middle; }}
.header-text {{ display:inline-block; vertical-align:middle; }}
.header-line1 {{ font-size:11px; letter-spacing:2px; color:#fff; opacity:0.7; }}
.header-line2 {{ font-size:22px; font-weight:700; color:#fff; }}
.header-line3 {{ font-size:10px; color:#93c5fd; }}
.header-date {{ font-size:13px; color:#fff; font-weight:700; }}
.header-period {{ font-size:10px; color:#fff; opacity:0.7; margin-top:2px; }}

.card {{ background:#fff; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.08); margin:0 24px 8px; padding:16px 24px; break-inside:avoid; page-break-inside:avoid; }}
.card-header {{ margin-bottom:10px; display:flex; align-items:center; gap:8px; }}
.ph {{ font-size:16px; color:#1e3a8a; vertical-align:middle; }}
.icon-circle {{
    display:inline-flex; align-items:center; justify-content:center;
    width:32px; height:32px; border-radius:50%; background:#e0e7ff; flex-shrink:0;
}}
.icon-circle .ph {{ font-size:16px; color:#1e3a8a; }}
.icon-circle-sm {{
    display:inline-flex; align-items:center; justify-content:center;
    width:24px; height:24px; border-radius:50%; background:#e0e7ff; flex-shrink:0;
}}
.icon-circle-sm .ph {{ font-size:13px; color:#1e3a8a; }}
.card-title {{ font-size:10px; letter-spacing:1.5px; color:#1e3a8a; font-weight:700; }}
.about-text {{ font-size:12px; color:#374151; line-height:1.7; margin:0; }}

.id-card {{ border-radius:10px; }}
.id-logo {{ width:80px; height:80px; border-radius:50%; object-fit:cover; border:3px solid #e2e8f0; display:block; }}
.id-nome {{ font-size:22px; font-weight:700; color:#1e3a8a; }}
.id-nome a {{ color:inherit; text-decoration:none; }}
.id-desc {{ font-size:11px; color:#64748b; margin-top:4px; }}
.metrics-box {{ background:#f8fafc; border-radius:8px; padding:14px 16px; }}
.metrics-row {{ display:table; width:100%; }}
.metrics-item {{ display:table-cell; vertical-align:middle; padding:0 8px; }}
.metrics-item-center {{ text-align:center; border-left:1px solid #e2e8f0; border-right:1px solid #e2e8f0; }}
.metrics-divider {{ display:table-cell; width:1px; background:#e2e8f0; }}
.metrics-label {{ font-size:8px; letter-spacing:1.5px; color:#64748b; font-weight:600; margin-bottom:6px; }}
.metrics-value {{ display:flex; align-items:center; gap:6px; }}
.metrics-nota {{ font-size:28px; font-weight:700; color:#1e3a8a; line-height:1; }}
.metrics-max {{ font-size:14px; font-weight:400; color:#94a3b8; }}
.pill {{ display:inline-block; padding:4px 12px; border-radius:20px; font-size:11px; font-weight:600; }}

.chart-note {{ font-size:9px; color:#94a3b8; margin-top:6px; }}
#viewsChart {{ max-height:100px; }}
.views-side {{ background:#f8fafc; border-radius:8px; padding:10px; text-align:left; }}
.views-label {{ font-size:9px; color:#64748b; }}
.views-val {{ font-size:18px; font-weight:700; color:#1e3a8a; margin:2px 0 5px; padding-left:30px; }}
.views-val-sm {{ font-size:14px; font-weight:700; color:#1e3a8a; margin-top:1px; padding-left:30px; }}
.views-sep {{ border-top:1px solid #e2e8f0; margin:4px 0; }}

.two-col {{
    display:table; width:100%; table-layout:fixed; margin-bottom:8px;
    break-inside:avoid; page-break-inside:avoid;
}}
.two-col .col {{ display:table-cell; width:50%; vertical-align:top; padding:0 4px; box-sizing:border-box; }}
.two-col .col:first-child {{ padding-left:0; }}
.two-col .col:last-child {{ padding-right:0; }}
.two-col .card {{ margin:0; height:100%; }}

.contact-row {{ display:table; width:100%; padding:7px 0; border-bottom:1px solid #f1f5f9; font-size:12px; }}
.contact-row:last-child {{ border-bottom:none; }}
.contact-icon {{ display:table-cell; width:32px; vertical-align:middle; }}
.contact-label {{ display:table-cell; width:90px; color:#1e3a8a; font-weight:600; }}
.contact-val {{ display:table-cell; color:#374151; word-break:break-word; }}

.legend-row {{ font-size:11px; color:#374151; padding:3px 0; }}
.legend-dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; }}
.legend-label {{ margin-right:4px; }}
.legend-val {{ color:#64748b; }}

.social-row {{ display:table; width:100%; padding:6px 0; border-bottom:1px solid #f1f5f9; font-size:12px; }}
.social-row:last-child {{ border-bottom:none; }}
.social-icon {{ display:table-cell; width:32px; vertical-align:middle; }}
.social-name {{ display:table-cell; width:70px; color:#1e293b; font-weight:600; vertical-align:middle; }}
.social-handle {{
    display:table-cell;
    color:#1e3a8a;
    text-decoration:none;
    max-width:200px;
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
    vertical-align:middle;
}}
.social-check {{ display:table-cell; width:24px; text-align:right; vertical-align:middle; }}

.docs-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:6px 12px; }}
.doc-item {{ font-size:11px; color:#374151; }}

.none-box {{ color:#94a3b8; font-size:12px; text-align:center; padding:16px 0; }}

.alert-box {{ border-radius:8px; padding:16px 24px; margin:0 24px 8px; }}
.alert-warning {{ background:#fff7ed; border-left:4px solid #f97316; }}
.alert-success {{ background:#f0fdf4; border-left:4px solid #22c55e; }}
.alert-header {{ font-size:10px; letter-spacing:1px; color:#c2410c; font-weight:700; margin-bottom:6px; }}
.alert-header-success {{ color:#15803d; }}
.alert-text {{ font-size:12px; color:#9a3412; }}
.alert-text-success {{ font-size:12px; color:#15803d; }}

.final-page {{
    break-before:page;
    min-height:100vh;
    display:flex;
    flex-direction:column;
    background:#ffffff;
    padding:0;
}}
.final-hero {{
    background:#0f172a;
    background-image:linear-gradient(135deg, #0f172a 60%, #1e3a8a 100%);
    padding:28px 40px 22px;
    text-align:center;
    color:#fff;
}}
.final-hero-icon {{
    width:48px; height:48px;
    border:2px solid #bfa76a;
    border-radius:50%;
    display:flex; align-items:center; justify-content:center;
    margin:0 auto 12px;
}}
.final-hero-icon .ph {{ font-size:24px; color:#bfa76a; }}
.final-title-light {{ font-size:20px; font-weight:400; color:#fff; margin:0; letter-spacing:1px; }}
.final-title-gold {{ font-size:22px; font-weight:700; color:#bfa76a; margin:4px 0 10px; letter-spacing:1px; }}
.final-subtitle {{ font-size:10px; color:rgba(255,255,255,0.75); line-height:1.5; max-width:500px; margin:0 auto; }}
.final-divider {{ height:3px; background:linear-gradient(90deg, #bfa76a, #1e3a8a, #bfa76a); }}

.final-three-cols {{ display:table; width:100%; padding:18px 40px; box-sizing:border-box; }}
.final-col {{ display:table-cell; width:33%; vertical-align:top; padding:0 16px; text-align:center; }}
.final-col:first-child {{ padding-left:0; }}
.final-col:last-child {{ padding-right:0; }}
.final-col-icon {{
    width:44px; height:44px;
    border:1.5px solid #bfa76a;
    border-radius:50%;
    display:flex; align-items:center; justify-content:center;
    margin:0 auto 8px;
}}
.final-col-icon .ph {{ font-size:20px; color:#1e3a8a; }}
.final-col-title {{ font-size:11px; font-weight:700; color:#1e3a8a; letter-spacing:1px; margin-bottom:6px; }}
.final-col-text {{ font-size:10px; color:#374151; line-height:1.5; margin:0; }}

.final-who-box {{
    background:#f8fafc;
    margin:0 40px;
    border-radius:10px;
    padding:16px 32px;
    text-align:center;
}}
.final-who-title {{ font-size:11px; font-weight:700; color:#1e3a8a; letter-spacing:1.5px; margin-bottom:6px; }}
.final-who-divider {{ width:40px; height:2px; background:#bfa76a; margin:0 auto 12px; }}
.final-who-cols {{ display:table; width:100%; }}
.final-who-item {{ display:table-cell; vertical-align:top; text-align:center; padding:0 8px; }}
.final-who-icon {{
    width:44px; height:44px;
    border:1.5px solid #cbd5e1;
    border-radius:12px;
    display:flex; align-items:center; justify-content:center;
    margin:0 auto 6px;
}}
.final-who-icon .ph {{ font-size:20px; color:#1e3a8a; }}
.final-who-label {{ font-size:9px; font-weight:700; color:#374151; letter-spacing:0.5px; line-height:1.4; }}

.final-auth-box {{
    margin:14px 40px;
    background:#0f172a;
    border-radius:10px;
    padding:18px 28px;
    color:#fff;
}}
.final-auth-title {{ font-size:11px; font-weight:700; letter-spacing:1.5px; color:#fff; margin-bottom:12px; text-align:center; }}
.final-auth-grid {{ display:table; width:100%; }}
.final-auth-shield {{ display:table-cell; width:80px; vertical-align:middle; text-align:center; }}
.final-auth-items {{ display:table-cell; vertical-align:top; padding:0 20px; }}
.final-auth-item {{ display:flex; align-items:flex-start; gap:10px; margin-bottom:8px; }}
.final-auth-item:last-child {{ margin-bottom:0; }}
.final-auth-item-icon {{
    width:26px; height:26px;
    background:rgba(255,255,255,0.1);
    border-radius:6px;
    display:flex; align-items:center; justify-content:center;
    flex-shrink:0;
}}
.final-auth-item-icon .ph {{ font-size:13px; color:#bfa76a; }}
.final-auth-item-title {{ font-size:9px; font-weight:700; letter-spacing:1px; color:#bfa76a; margin-bottom:2px; }}
.final-auth-item-text {{ font-size:9px; color:rgba(255,255,255,0.7); line-height:1.35; }}
.final-auth-qr {{ display:table-cell; width:120px; vertical-align:middle; text-align:center; }}
.final-auth-qr img {{ border-radius:6px; background:#fff; padding:4px; }}
.final-auth-qr-text {{ font-size:9px; color:rgba(255,255,255,0.7); margin-top:6px; line-height:1.35; }}
.final-auth-qr-url {{ font-size:9px; font-weight:700; color:#bfa76a; margin-top:4px; }}
.final-auth-qr-hash {{ font-family:monospace; font-size:7px; color:rgba(255,255,255,0.5); margin-top:4px; word-break:break-all; }}
.final-auth-note {{ font-size:9px; color:rgba(255,255,255,0.5); margin-top:10px; margin-bottom:0; line-height:1.4; border-top:1px solid rgba(255,255,255,0.1); padding-top:8px; }}

.final-footer {{
    border-top: 2px solid #1e3a8a;
    padding: 20px 40px;
    background: #ffffff;
    margin-top: auto;
}}
</style>
</head>
<body>
<div class="wrapper">
<div class="content-wrapper">

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
        <div class="header-date"><i class="ph ph-calendar"></i> {mes_extenso}/{ano_atual}</div>
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
                <div class="metrics-row">
                    <div class="metrics-item">
                        <div class="metrics-label">CLASSIFICAÇÃO</div>
                        <div class="metrics-value">
                            <i class="ph ph-seal-check" style="font-size:18px;color:{cor_classificacao};"></i>
                            <span class="pill" style="{pill_style}">{_html.escape(classificacao)}</span>
                        </div>
                    </div>
                    <div class="metrics-divider"></div>
                    <div class="metrics-item metrics-item-center">
                        <div class="metrics-label">NOTA OBTIDA</div>
                        <div class="metrics-nota">{nota_final}<span class="metrics-max">/{max_nota}</span></div>
                    </div>
                    <div class="metrics-divider"></div>
                    <div class="metrics-item">
                        <div class="metrics-label">STATUS</div>
                        <div class="metrics-value">
                            <span class="pill" style="{tag_pill_style}">{_html.escape(tag_texto)}</span>
                        </div>
                    </div>
                </div>
                {certificacoes_html}
            </div>
        </td>
    </tr></table>
</div>
{sobre_card_html}

<div class="card">
    <div class="card-header"><span class="icon-circle"><i class="ph ph-chart-line-up"></i></span><span class="card-title">VISUALIZAÇÕES DA SUA OSC NA PLATAFORMA — ÚLTIMO MÊS</span></div>
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td style="width:65%;vertical-align:top;">
            <canvas id="viewsChart" style="height:100px;"></canvas>
        </td>
        <td style="width:35%;vertical-align:top;padding-left:12px;">
            <div class="views-side">
                <div style="display:flex;align-items:center;justify-content:flex-start;gap:6px;margin-bottom:3px;">
                    <div class="icon-circle-sm"><i class="ph ph-eye"></i></div>
                    <span class="views-label">TOTAL DE VISUALIZAÇÕES</span>
                </div>
                <div class="views-val">{total_visualizacoes}</div>
                <div class="views-sep"></div>
                <div style="display:flex;align-items:center;justify-content:flex-start;gap:6px;margin-bottom:3px;">
                    <div class="icon-circle-sm"><i class="ph ph-chart-bar"></i></div>
                    <span class="views-label">MÉDIA DIÁRIA</span>
                </div>
                <div class="views-val-sm">{media_diaria}</div>
            </div>
        </td>
    </tr></table>
    <div class="chart-note">* Dados de visualização do etransparente.org via Google Analytics</div>
</div>

<div class="two-col">
    <div class="col"><div class="card">
        <div class="card-header"><span class="icon-circle"><i class="ph ph-user"></i></span><span class="card-title">INFORMAÇÕES DE CONTATO</span></div>
        {contatos_html}
    </div></div>
    <div class="col"><div class="card">
        <div class="card-header"><span class="icon-circle"><i class="ph ph-handshake"></i></span><span class="card-title">CONTRATOS E PARCERIAS</span></div>
        {contratos_chart_html}
    </div></div>
</div>

<div class="two-col">
    <div class="col"><div class="card">
        <div class="card-header"><span class="icon-circle"><i class="ph ph-share-network"></i></span><span class="card-title">REDES SOCIAIS</span></div>
        {social_rows_html}
    </div></div>
    <div class="col"><div class="card">
        <div class="card-header"><span class="icon-circle"><i class="ph ph-folder-open"></i></span><span class="card-title">DOCUMENTOS DISPONÍVEIS ({n_docs})</span></div>
        {docs_grid_html}
    </div></div>
</div>

{alerta_html}

</div>

<div class="final-page">

  <!-- Seção hero -->
  <div class="final-hero">
    <div class="final-hero-icon">
      <i class="ph ph-shield-check"></i>
    </div>
    <h1 class="final-title-light">TRANSPARÊNCIA QUE FORTALECE.</h1>
    <h1 class="final-title-gold">CONFIANÇA QUE TRANSFORMA.</h1>
    <p class="final-subtitle">Esta é a última página do seu Relatório Mensal do Índice de Transparência.<br>Conheça mais sobre o eTransparente e a autenticidade deste documento.</p>
  </div>

  <!-- Linha dourada separadora -->
  <div class="final-divider"></div>

  <!-- Três colunas: Sobre / Emendas / Finalidade -->
  <div class="final-three-cols">
    <div class="final-col">
      <div class="final-col-icon"><i class="ph ph-users-three"></i></div>
      <div class="final-col-title">SOBRE O<br>ETRANSPARENTE.ORG</div>
      <p class="final-col-text">Iniciativa do Instituto de Direito Coletivo que apoia organizações da sociedade civil na promoção da transparência, da boa gestão e da prestação de contas, em conformidade com o MROSC.</p>
    </div>
    <div class="final-col">
      <div class="final-col-icon"><i class="ph ph-magnifying-glass"></i></div>
      <div class="final-col-title">EMENDAS<br>PARLAMENTARES</div>
      <p class="final-col-text">Módulo dedicado ao acompanhamento das emendas recebidas, registro da aplicação dos recursos e organização da prestação de contas, alinhado às exigências de transparência e às decisões do STF.</p>
    </div>
    <div class="final-col">
      <div class="final-col-icon"><i class="ph ph-target"></i></div>
      <div class="final-col-title">FINALIDADE<br>DESTE RELATÓRIO</div>
      <p class="final-col-text">Consolida de forma objetiva as informações públicas da organização disponíveis na plataforma, podendo ser utilizado como instrumento de prestação de contas perante parceiros, financiadores e órgãos públicos.</p>
    </div>
  </div>

  <!-- Quem utiliza este relatório -->
  <div class="final-who-box">
    <div class="final-who-title">QUEM UTILIZA ESTE RELATÓRIO?</div>
    <div class="final-who-divider"></div>
    <div class="final-who-cols">
      <div class="final-who-item">
        <div class="final-who-icon"><i class="ph ph-bank"></i></div>
        <div class="final-who-label">ÓRGÃOS<br>PÚBLICOS</div>
      </div>
      <div class="final-who-item">
        <div class="final-who-icon"><i class="ph ph-handshake"></i></div>
        <div class="final-who-label">FINANCIADORES E<br>DOADORES</div>
      </div>
      <div class="final-who-item">
        <div class="final-who-icon"><i class="ph ph-microphone-stage"></i></div>
        <div class="final-who-label">PARLAMENTARES</div>
      </div>
      <div class="final-who-item">
        <div class="final-who-icon"><i class="ph ph-magnifying-glass"></i></div>
        <div class="final-who-label">ÓRGÃOS DE<br>CONTROLE</div>
      </div>
      <div class="final-who-item">
        <div class="final-who-icon"><i class="ph ph-users"></i></div>
        <div class="final-who-label">SOCIEDADE E<br>PARCEIROS</div>
      </div>
    </div>
  </div>

  <!-- Autenticidade e validação -->
  <div class="final-auth-box">
    <div class="final-auth-title">AUTENTICIDADE E VALIDAÇÃO</div>
    <div class="final-auth-grid">
      <div class="final-auth-shield">
        <i class="ph ph-shield-check" style="font-size:60px;color:#bfa76a;"></i>
      </div>
      <div class="final-auth-items">
        <div class="final-auth-item">
          <div class="final-auth-item-icon"><i class="ph ph-lock-key"></i></div>
          <div>
            <div class="final-auth-item-title">CÓDIGO ÚNICO</div>
            <div class="final-auth-item-text">Identifica o relatório de forma exclusiva na plataforma.</div>
          </div>
        </div>
        <div class="final-auth-item">
          <div class="final-auth-item-icon"><i class="ph ph-fingerprint"></i></div>
          <div>
            <div class="final-auth-item-title">INTEGRIDADE</div>
            <div class="final-auth-item-text">Hash criptográfico garante que o conteúdo não foi alterado após a emissão.</div>
          </div>
        </div>
        <div class="final-auth-item">
          <div class="final-auth-item-icon"><i class="ph ph-qr-code"></i></div>
          <div>
            <div class="final-auth-item-title">QR CODE</div>
            <div class="final-auth-item-text">Permite a consulta da versão digital e a verificação da autenticidade.</div>
          </div>
        </div>
        <div class="final-auth-item">
          <div class="final-auth-item-icon"><i class="ph ph-calendar-check"></i></div>
          <div>
            <div class="final-auth-item-title">DATA E HORA</div>
            <div class="final-auth-item-text">Registro automático do momento exato da geração do relatório.</div>
          </div>
        </div>
      </div>
      <div class="final-auth-qr">
        {qr_img_tag}
        <div class="final-auth-qr-text">Escaneie para validar<br>este documento</div>
        <div class="final-auth-qr-url">etransparente.org/validar</div>
        <div class="final-auth-qr-hash">Hash: {hash_hex}</div>
      </div>
    </div>
    <p class="final-auth-note">Qualquer alteração posterior nos dados da organização não modifica retroativamente este relatório, preservando sua integridade documental.</p>
  </div>

  <!-- Rodapé institucional -->
  <div class="final-footer">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>

        <!-- Coluna 1: Logo IDC + nome + descrição + contatos -->
        <td style="width:32%;vertical-align:top;padding-right:24px;border-right:1px solid #e2e8f0;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
            <img src="{idc_logo_b64}" style="height:40px;flex-shrink:0;" alt="IDC">
            <div>
              <div style="font-size:11px;font-weight:700;color:#1e3a8a;line-height:1.3;">Instituto de Direito Coletivo</div>
              <div style="font-size:8px;color:#64748b;line-height:1.4;margin-top:2px;">Organização da sociedade civil que atua pelo fortalecimento da democracia, da justiça e dos direitos coletivos.</div>
            </div>
          </div>
          <div style="font-size:9px;color:#64748b;margin-bottom:4px;display:flex;align-items:center;gap:6px;">
            <i class="ph ph-envelope" style="color:#1e3a8a;font-size:11px;"></i>
            contato@direitocoletivo.org.br
          </div>
          <div style="font-size:9px;color:#64748b;display:flex;align-items:center;gap:6px;">
            <i class="ph ph-globe" style="color:#1e3a8a;font-size:11px;"></i>
            www.direitocoletivo.org.br
          </div>
        </td>

        <!-- Coluna 2: Documento oficial + data -->
        <td style="width:36%;vertical-align:top;padding:0 24px;border-right:1px solid #e2e8f0;">
          <div style="font-size:10px;font-weight:700;letter-spacing:0.5px;color:#1e3a8a;margin-bottom:8px;">DOCUMENTO OFICIAL EMITIDO PELO IDC</div>
          <p style="font-size:9px;color:#64748b;line-height:1.6;margin:0 0 10px;">Relatório gerado automaticamente pela plataforma eTransparente.org com base nas informações públicas da organização.</p>
          <div style="font-size:10px;color:#374151;"><strong>Data de emissão:</strong> {data_emissao_formatada}</div>
        </td>

        <!-- Coluna 3: etransparente.org + slogan -->
        <td style="width:32%;vertical-align:middle;text-align:right;padding-left:24px;">
          <div style="font-size:18px;font-weight:700;color:#1e3a8a;margin-bottom:6px;">etransparente.org</div>
          <div style="font-size:9px;color:#64748b;line-height:1.6;">Organizações mais transparentes.<br>Sociedade mais forte.</div>
        </td>

      </tr>
    </table>
  </div>

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
        maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 9 }}, maxTicksLimit: 5, maxRotation: 0 }} }},
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

    # ── rodapé mini, repetido em todas as páginas do PDF via footerTemplate ──
    # Chromium não repete elementos position:fixed em todas as páginas do PDF
    # (só renderiza onde calham no fluxo normal). A única forma suportada de
    # ter algo fixo em TODA página é o footerTemplate nativo do Playwright.
    # O QR Code é gerado como PNG em /tmp e referenciado via file://.
    _mini_qr_tag = (
        f'<img src="{qr_path}" width="34" height="34" style="display:block;">'
        if qr_path else
        '<div style="width:34px;height:34px;background:#f1f5f9;border-radius:4px;"></div>'
    )
    mini_footer_template_html = f"""
<div style="width:100%;font-family:Arial,sans-serif;font-size:8px;color:#64748b;border-top:1px solid #e2e8f0;margin:0 24px;padding:6px 0 0;box-sizing:border-box;">
    <table style="width:100%;border-collapse:collapse;">
        <tr>
            <td style="width:34px;vertical-align:middle;">{_mini_qr_tag}</td>
            <td style="vertical-align:middle;padding-left:10px;">
                <div style="font-family:monospace;font-size:7px;color:#64748b;word-break:break-all;">Hash: {hash_hex}</div>
            </td>
        </tr>
    </table>
</div>"""

    return html, hash_hex, mini_footer_template_html


def main():
    input_file = find_latest_input()
    with open(input_file, 'r', encoding='utf-8') as f:
        oscs = json.load(f)

    if os.environ.get('PIPELINE_TEST_MODE', '').lower() == 'true':
        oscs = [o for o in oscs if 'direito coletivo' in o.get('nome', '').lower() or 'idc' in o.get('nome', '').lower()]
        print(f'PIPELINE_TEST_MODE: filtrando apenas IDC ({len(oscs)} ONG)')

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

    # Load GA4 views data
    views_by_url = {}
    views_file = os.path.join(_base, 'output', f'oscs_views_{data_emissao}.json')
    if os.path.exists(views_file):
        try:
            with open(views_file, 'r', encoding='utf-8') as f:
                views_data = json.load(f)
            for entry in views_data:
                url = entry.get('url', '')
                if url:
                    views_by_url[url] = entry.get('views', [])
            print(f"GA4 views carregados: {views_file} ({len(views_by_url)} ONGs)")
        except Exception as e:
            print(f"Aviso: erro ao carregar GA4 views: {e}")
    else:
        print(f"Aviso: arquivo GA4 views não encontrado em {views_file}. Usando dados aleatórios como fallback.")

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
            mini_footer_template_html = ''
            try:
                html_content, hash_hex, mini_footer_template_html = gerar_dashboard_html(osc, score, views_by_url)
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
                        page.set_content(html_content, wait_until='domcontentloaded')
                        page.wait_for_load_state('networkidle')
                        page.wait_for_timeout(3000)
                        # Força carregamento de todas as imagens file://
                        page.evaluate("""
                            () => new Promise(resolve => {
                                const imgs = document.querySelectorAll('img');
                                let pending = imgs.length;
                                if (!pending) return resolve();
                                imgs.forEach(img => {
                                    if (img.complete) { if (!--pending) resolve(); }
                                    else {
                                        img.onload = img.onerror = () => { if (!--pending) resolve(); };
                                    }
                                });
                            })
                        """)
                        page.pdf(
                            path=pdf_file,
                            format='A4',
                            print_background=True,
                            margin={'top': '28px', 'bottom': '50px', 'left': '0px', 'right': '0px'},
                            display_header_footer=bool(mini_footer_template_html),
                            header_template='<div></div>',
                            footer_template=mini_footer_template_html or '<div></div>',
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

    # Limpeza dos QR Codes temporários
    for f in glob.glob('/tmp/qrcode_*.png'):
        try:
            os.remove(f)
        except Exception:
            pass

    print('\n' + '=' * 60)
    print(f"Total de PDFs gerados: {pdf_count}/{len(oscs)}")
    print(f"Pasta de saída: {base_out}")


if __name__ == '__main__':
    main()
