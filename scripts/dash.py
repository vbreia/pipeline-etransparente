"""
Small utility to render one HTML dashboard per ONG (from the latest
`oscs_etransparente_*.json` in `output/`). Saves HTML files under
`output/dashboards/<timestamp>/html` and (optionally) PDFs under
`output/dashboards/<timestamp>/pdf` when `pdfkit` + `wkhtmltopdf` are available.

Usage: run `python scripts/dash.py` from repository root. The script will
locate the newest `output/oscs_etransparente_*.json` automatically.
"""

import json
import os
import glob
import random
import re
import shutil
import html as _html
from datetime import datetime

try:
    import pdfkit  # optional
    PDFKIT_AVAILABLE = True
except Exception:
    PDFKIT_AVAILABLE = False


def find_latest_input():
    files = glob.glob(os.path.join('output', 'oscs_etransparente_*.json'))
    if not files:
        raise FileNotFoundError('Nenhum arquivo oscs_etransparente_*.json em output/')
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


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


def gerar_dashboard_html(osc):
    nome = osc.get('nome', 'Sem nome')
    url = osc.get('url', '#')

    descricao = osc.get('descricao_objeto_social', '') or ''
    telefone = osc.get('telefone', '') or ''
    email = osc.get('email', '') or ''
    website = osc.get('website', '') or ''
    localizacao = osc.get('localizacao', '') or ''
    cnpj = osc.get('cnpj', '') or ''

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

    nivel = random.choice(['Bronze', 'Prata', 'Ouro', 'Platina'])
    nota_geral = round(random.uniform(6.0, 10.0), 1)

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
        docs_html = f'<ul class="docs">{docs_html_items}</ul>'
    else:
        docs_html = '<div class="none">Nenhum</div>'
    # Resolve absolute paths for local fonts so wkhtmltopdf can load them
    repo_root = os.path.abspath(os.getcwd())
    font_dir = os.path.join(repo_root, 'assets', 'fonts')
    regular_path = os.path.join(font_dir, 'Montserrat-Regular.woff2')
    medium_path = os.path.join(font_dir, 'Montserrat-Medium.woff2')
    bold_path = os.path.join(font_dir, 'Montserrat-Bold.woff2')

    # Use file:// URLs so wkhtmltopdf (called from a different working dir) can access the files
    regular_url = f'file://{regular_path}'
    medium_url = f'file://{medium_path}'
    bold_url = f'file://{bold_path}'

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

            /* Forçar impressão de cores e ajustes de impressão */
            * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            @media print {{
              body {{ background: #f5f5f5; -webkit-print-color-adjust: exact; }}
              .container {{ box-shadow: none; }}
              /* Ajustes de margens, tamanhos se necessário */
            }}
            body {{ font-family: 'MontserratLocal', 'Montserrat', sans-serif; }}
            body {{ font-family: 'MontserratLocal', 'Montserrat', sans-serif; }}
            .container {{ max-width: 900px; margin: 0 auto; background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
            .header {{ display: flex; align-items: center; gap: 20px; margin-bottom: 30px; border-bottom: 2px solid #1e3a8a; padding-bottom: 20px; }}
            .logo {{ width: 80px; height: 80px; border-radius: 50%; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); flex-shrink: 0; }}
            .logo-link {{ display: inline-block; margin-right: 18px; text-decoration: none; }}
            .title-area {{ display: flex; flex-direction: column; gap: 8px; }}
            .nome-ong {{ font-size: 1.4rem; font-weight: bold; color: #1e3a8a; word-break: break-word; }}
            .nome-ong a {{ color: inherit; text-decoration: none; }}
            .meta {{ display: flex; gap: 20px; font-size: 0.95rem; color: #374151; }}
            /* wkhtmltopdf may not support flex gap reliably; add explicit margins for PDF */
            .meta span {{ display: inline-block; margin-right: 18px; }}
            /* Use flexbox instead of CSS grid for better wkhtmltopdf compatibility */
            .body {{ display: -webkit-box; display: -ms-flexbox; display: flex; -ms-flex-wrap: wrap; flex-wrap: wrap; gap: 20px; margin-top: 20px; }}
            .info-box {{ background: linear-gradient(135deg, #f0f4ff 0%, #f9fafb 100%); padding: 16px; border-radius: 8px; border-left: 4px solid #1e3a8a; flex: 1 1 calc(50% - 10px); box-sizing: border-box; min-width: 260px; }}
            .info-box strong {{ display: block; margin-bottom: 8px; color: #1e3a8a; font-size: 0.95rem; }}
            .info-box .valor {{ font-size: 1.3rem; color: #374151; font-weight: bold; }}
            .link-area {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #e5e7eb; }}
            .link-area p {{ margin: 0 0 8px 0; color: #6b7280; font-size: 0.9rem; }}
            .link-area a {{ color: #1e3a8a; text-decoration: none; word-break: break-all; }}
            .link-area a:hover {{ text-decoration: underline; }}
            .social-list {{ list-style: none; padding-left: 0; margin: 6px 0 0 0; }}
            .social-list li {{ display: flex; align-items: center; gap: 8px; margin: 6px 0; }}
            .social-list .index {{ color: #6b7280; margin-right: 6px; font-weight: 600; }}
            .social {{ display:inline-flex; align-items:center; gap:6px; color:#1e3a8a; text-decoration:none; }}
            .social svg {{ flex-shrink:0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <a class="logo-link" href="{_html.escape(url)}" target="_blank" rel="noopener noreferrer"><div class="logo" aria-hidden="true"></div></a>
                <div class="title-area">
                    <div class="nome-ong"><a href="{_html.escape(url)}" target="_blank" rel="noopener noreferrer">{_html.escape(nome)}</a></div>
                    <div class="meta">
                        <span><strong>Nível:</strong> { _html.escape(nivel) }</span>
                        <span><strong>Nota:</strong> { nota_geral }</span>
                    </div>
                </div>
            </div>

            <div class="body">
                <div class="info-box">
                    <strong>Informações Principais</strong>
                    <div class="valor">{info_preenchida}/{TOTAL_INFO}</div>
                    <div style="margin-top:10px; font-size:0.95rem; color:#374151;">
                        <div><strong>Telefone:</strong> {_html.escape(telefone)}</div>
                        <div><strong>Email:</strong> {_html.escape(email)}</div>
                        <div><strong>Website:</strong> <a href="{_html.escape(website)}">{_html.escape(website)}</a></div>
                        <div><strong>Localização:</strong> {_html.escape(localizacao)}</div>
                        <div><strong>CNPJ:</strong> {_html.escape(cnpj)}</div>
                    </div>
                </div>
                <div class="info-box">
                    <strong>Termos</strong>
                    <div class="valor">{total_termos}</div>
                    <div style="margin-top:10px; font-size:0.95rem; color:#374151;">
                        <div><strong>Município:</strong> {municipio_disp}</div>
                        <div><strong>Estado:</strong> {estado_disp}</div>
                        <div><strong>União:</strong> {uniao_disp}</div>
                        <div><strong>Emendas:</strong> {emendas_disp}</div>
                    </div>
                </div>
            </div>

            <div class="link-area">
                <p><strong>Redes Sociais:</strong></p>
                <div class="social-row">{socials_html}</div>
                <p style="margin-top:12px;"><strong>Documentos disponíveis:</strong></p>
                <div class="docs-area">{docs_html}</div>
                
            </div>
        </div>
    </body>
    </html>
    """

    return html


def main():
    input_file = find_latest_input()
    with open(input_file, 'r', encoding='utf-8') as f:
        oscs = json.load(f)

    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    base_out = os.path.join('output', 'dashboards', ts)
    html_dir = os.path.join(base_out, 'html')
    pdf_dir = os.path.join(base_out, 'pdf')
    os.makedirs(html_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    pdf_count = 0
    for idx, osc in enumerate(oscs, 1):
        nome = osc.get('nome', 'Sem nome')
        nome_arquivo = ''.join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in nome)
        nome_arquivo = nome_arquivo.strip().replace(' ', '_')[:50]

        html_file = os.path.join(html_dir, f"{idx:03d}_{nome_arquivo}.html")
        pdf_file = os.path.join(pdf_dir, f"{idx:03d}_{nome_arquivo}.pdf")

        try:
            try:
                html_content = gerar_dashboard_html(osc)
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

            if PDFKIT_AVAILABLE:
                try:
                    options = {
                        'page-size': 'A4',
                        'margin-top': '15mm',
                        'margin-right': '15mm',
                        'margin-bottom': '15mm',
                        'margin-left': '15mm',
                        'encoding': 'UTF-8',
                        'enable-local-file-access': None,   # permite carregar assets locais
                        'background': None,                 # renderiza fundos
                        'zoom': '1.0',
                        'javascript-delay': '200',
                        'load-error-handling': 'ignore',
                        'load-media-error-handling': 'ignore'
                    }

                    # Tentar localizar automaticamente o executável wkhtmltopdf
                    wk_path = shutil.which('wkhtmltopdf')
                    if not wk_path:
                        common = ['/usr/local/bin/wkhtmltopdf', '/usr/bin/wkhtmltopdf', '/snap/bin/wkhtmltopdf', '/opt/bin/wkhtmltopdf']
                        for p in common:
                            if os.path.exists(p) and os.access(p, os.X_OK):
                                wk_path = p
                                break

                    config = None
                    if wk_path:
                        try:
                            config = pdfkit.configuration(wkhtmltopdf=wk_path)
                            print(f"Usando wkhtmltopdf: {wk_path}")
                        except Exception:
                            config = None
                    else:
                        print("Aviso: wkhtmltopdf não encontrado no PATH ou em locais comuns. Tentarei sem configuração explícita (pode falhar).")

                    pdfkit.from_file(html_file, pdf_file, options=options, configuration=config)
                    pdf_count += 1
                    print(f"✓ PDF criado: {pdf_file}")
                except Exception as e:
                    # Mensagem mais amigável quando o binário não existe
                    msg = str(e)
                    if 'No wkhtmltopdf executable found' in msg or 'No wkhtmltopdf' in msg:
                        print(f"✗ Erro ao gerar PDF para {nome}: wkhtmltopdf não encontrado. Instale-o e certifique-se de que está no PATH. Veja https://wkhtmltopdf.org/downloads.html")
                    else:
                        print(f"✗ Erro ao gerar PDF para {nome}: {e}")
            else:
                print(f"⚠️  pdfkit não disponível: pulando conversão para {nome}. HTML salvo em {html_file}")
        except Exception as e:
            print(f"✗ Erro inesperado processando {nome}: {e}")
            continue

    print('\n' + '=' * 60)
    print(f"Total de PDFs gerados: {pdf_count}/{len(oscs)}")
    print(f"Pasta de saída: {base_out}")


if __name__ == '__main__':
    main()

