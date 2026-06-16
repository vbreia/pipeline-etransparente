#!/usr/bin/env python3
"""
Script para extração completa de dados de ONGs do site etransparente.org

Este script implementa uma solução orientada a objetos para extrair:
- Dados web via scraping (informações de contato, documentos, redes sociais)
- Dados de termos via API (contratos municipais, estaduais, federais, emendas)
"""

import requests
import json
import re
import glob
import html as html_module
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple, Any
from bs4 import BeautifulSoup
import logging
import os
from datetime import datetime
import time
from urllib.parse import urlsplit
from io import BytesIO

try:
    from PIL import Image
except Exception:
    Image = None


@dataclass
class RedesSociais:
    """Estrutura para redes sociais"""
    instagram: str = ""
    linkedin: str = ""
    youtube: str = ""
    outras: str = ""


@dataclass
class Documentos:
    """Estrutura para documentos categorizados"""
    cneas: str = ""
    cebas: str = ""
    utilidade_publica: str = ""
    relatorio_atividades: str = ""
    plano_acao: str = ""
    estatuto: str = ""
    ata_eleicao: str = ""
    balanco_2020: str = ""
    balanco_2021: str = ""
    balanco_2022: str = ""
    balanco_2023: str = ""
    balanco_2024: str = ""
    outros_documentos: str = ""


@dataclass
class TermosInfo:
    """Estrutura para informações de termos"""
    quantidade: int = 0
    termos: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.termos is None:
            self.termos = []


@dataclass
class EstatisticasTermos:
    """Estrutura para estatísticas de termos"""
    total_contratos_parcerias: int = 0
    tem_termos_municipio: bool = False
    tem_termos_estado: bool = False
    tem_termos_uniao: bool = False
    tem_emendas_parlamentares: bool = False
    distribuicao: Dict[str, int] = None
    
    def __post_init__(self):
        if self.distribuicao is None:
            self.distribuicao = {
                'municipio': 0,
                'estado': 0,
                'uniao': 0,
                'emendas_parlamentares': 0
            }


@dataclass
class ONGData:
    """Estrutura principal para dados de uma ONG"""
    nome: str = ""
    url: str = ""
    logo_url: str = ""
    logo_local_path: str = ""
    descricao_objeto_social: str = ""
    telefone: str = ""
    email: str = ""
    website: str = ""
    redes_sociais: RedesSociais = None
    horario_funcionamento: str = ""
    localizacao: str = ""
    cnpj: str = ""
    documentos: Documentos = None
    termos: Dict[str, TermosInfo] = None
    estatisticas_termos: EstatisticasTermos = None
    
    def __post_init__(self):
        if self.redes_sociais is None:
            self.redes_sociais = RedesSociais()
        if self.documentos is None:
            self.documentos = Documentos()
        if self.termos is None:
            self.termos = {
                'municipio': TermosInfo(),
                'estado': TermosInfo(),
                'uniao': TermosInfo(),
                'emendas_parlamentares': TermosInfo()
            }
        if self.estatisticas_termos is None:
            self.estatisticas_termos = EstatisticasTermos()


class WebScraper:
    """Classe responsável pelo scraping de dados web"""
    
    def __init__(self, headers: Dict[str, str]):
        self.headers = headers
        self.logger = logging.getLogger(__name__)
    
    def find_div_by_class(self, soup: BeautifulSoup, pattern: str):
        """Encontrar div por classe usando regex"""
        return soup.find('div', class_=re.compile(pattern))
    
    def extrair_redes_sociais_especificas(self, redes_list: List[str]) -> Tuple[str, str, str, List[str]]:
        """Separar redes sociais específicas"""
        instagram = ''
        linkedin = ''
        youtube = ''
        outras_redes = []
        
        for rede in redes_list:
            if 'instagram.com' in rede.lower():
                instagram = rede
            elif 'linkedin.com' in rede.lower():
                linkedin = rede
            elif 'youtube.com' in rede.lower() or 'youtu.be' in rede.lower():
                youtube = rede
            else:
                outras_redes.append(rede)
        
        return instagram, linkedin, youtube, outras_redes
    
    # Mapeia trechos da classe CSS `block-field-*` (slug do campo ACF) para a
    # categoria correspondente. O slug é a fonte confiável do tipo do
    # documento — o nome do arquivo na URL pode ser genérico (ex.: upload
    # reaproveitado) e não deve ser usado para identificar a categoria.
    _BLOCK_FIELD_CATEGORIAS = [
        ('cadastro-nacional-de-entidades', 'cneas'),
        ('cebas', 'cebas'),
        ('utilidade', 'utilidade_publica'),
        ('relat', 'relatorio_atividades'),
        ('plano-de', 'plano_acao'),
        ('estatuto', 'estatuto'),
        ('ata-de-eleio', 'ata_eleicao'),
        ('ata-de-eleicao', 'ata_eleicao'),
    ]

    def categorizar_documentos_por_bloco(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Categorizar documentos a partir do bloco HTML que os contém.

        Cada documento aparece dentro de um <div class="block-type-file
        block-field-<slug>">, onde o slug identifica o campo ACF de origem
        (ex.: `block-field-cebas`, `block-field-cadastro-nacional-de-...
        -cneas`). Usar esse slug em vez do nome do arquivo evita
        categorizar errado documentos com nomes de arquivo genéricos.
        """
        categorias = {
            'cneas': '',
            'cebas': '',
            'utilidade_publica': '',
            'relatorio_atividades': '',
            'plano_acao': '',
            'estatuto': '',
            'ata_eleicao': '',
            'balanco_2020': '',
            'balanco_2021': '',
            'balanco_2022': '',
            'balanco_2023': '',
            'balanco_2024': '',
            'outros_documentos': []
        }

        for bloco in soup.find_all('div', class_=re.compile(r'block-type-file')):
            classes = ' '.join(bloco.get('class', [])).lower()
            links = [a['href'] for a in bloco.find_all('a', href=True)
                     if a['href'].lower().endswith(('.pdf', '.doc', '.docx'))]
            if not links:
                continue
            doc = links[0]

            if 'balano' in classes or 'balanco' in classes or 'demonstr' in classes:
                for ano in ('2020', '2021', '2022', '2023', '2024'):
                    if ano in classes:
                        categorias[f'balanco_{ano}'] = doc
                        break
                else:
                    categorias['outros_documentos'].append(doc)
                continue

            for slug, categoria in self._BLOCK_FIELD_CATEGORIAS:
                if slug in classes:
                    categorias[categoria] = doc
                    break
            else:
                categorias['outros_documentos'].append(doc)

        return categorias

    def _baixar_logo(self, logo_url: str, ong_web_url: str) -> str:
        """Baixar logo, converter para JPG e salvar em assets/img/logos-ongs/<slug>.jpg (sobrescreve).
        
        Args:
            logo_url: URL da imagem da logo
            ong_web_url: URL completa da ONG (https://etransparente.org/oscs/{slug}/)
        
        Returns:
            Caminho relativo do arquivo salvo (assets/img/logos-ongs/<slug>.jpg)
        """
        if not logo_url:
            return ""

        try:
            base_dir = os.path.join(os.getcwd(), 'assets', 'img', 'logos-ongs')
            os.makedirs(base_dir, exist_ok=True)

            # Extrair slug único da URL (tudo depois de /oscs/ até a última /)
            slug = ''
            match = re.search(r'/oscs/([^/]+)/?$', ong_web_url)
            if match:
                slug = match.group(1)
            else:
                self.logger.warning(f"Não foi possível extrair slug de: {ong_web_url}")
                return ""
            
            destino = os.path.join(base_dir, f"{slug}.jpg")
            # Retornar caminho relativo para uso em dashboards
            destino_relativo = os.path.join('assets', 'img', 'logos-ongs', f"{slug}.jpg")

            # Limpar restos de extensões antigas do mesmo nome
            for f in glob.glob(os.path.join(base_dir, f"{slug}.*")):
                if f != destino:
                    try:
                        os.remove(f)
                    except Exception:
                        pass

            resp = requests.get(logo_url, headers=self.headers, timeout=30)
            if not (resp.status_code == 200 and resp.content):
                self.logger.warning(f"Falha ao baixar logo ({resp.status_code}) para {slug}: {logo_url}")
                return ""

            content = resp.content

            # Converter para JPG usando Pillow se disponível
            if Image is not None:
                try:
                    img = Image.open(BytesIO(content))
                    
                    # Converter para RGB se necessário, preservando transparência com fundo branco
                    if img.mode in ("RGBA", "LA"):
                        bg = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == "RGBA":
                            bg.paste(img, mask=img.split()[3])  # canal alpha
                        else:
                            bg.paste(img, mask=img.split()[1])  # canal LA
                        img = bg
                    elif img.mode == "P":
                        img = img.convert("RGB")
                    elif img.mode != "RGB":
                        img = img.convert("RGB")
                    
                    # Redimensionar para formato 1:1 (quadrado) com fundo branco
                    width, height = img.size
                    max_dim = max(width, height)
                    
                    # Criar imagem quadrada com fundo branco
                    square_img = Image.new('RGB', (max_dim, max_dim), (255, 255, 255))
                    
                    # Calcular posição para centralizar a imagem original
                    offset_x = (max_dim - width) // 2
                    offset_y = (max_dim - height) // 2
                    
                    # Colar imagem original centralizada
                    square_img.paste(img, (offset_x, offset_y))
                    
                    # Salvar como JPG
                    square_img.save(destino, format="JPEG", quality=90)
                    self.logger.info(f"Logo salva como JPG quadrado (1:1): {destino}")
                    return destino_relativo
                except Exception as conv_err:
                    self.logger.warning(f"Falha na conversão para JPG para {slug}: {conv_err}")

            # Fallback: se já for JPEG (magic bytes), salvar direto
            if content[:3] == b"\xff\xd8\xff":
                with open(destino, 'wb') as f:
                    f.write(content)
                return destino_relativo

            self.logger.warning(f"Logo não convertida (Pillow ausente ou formato desconhecido) para {slug}: {logo_url}")
            return ""

        except Exception as e:
            self.logger.error(f"Erro ao baixar logo de {slug}: {e}")
            return ""
    
    def extrair_dados_web(self, url: str, nome_ong: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Extrair dados completos de uma ONG específica via web scraping"""
        try:
            response = requests.get(url, headers=self.headers)
            
            if response.status_code != 200:
                return None, f"Erro HTTP {response.status_code}"
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Descrição do objeto social
            descricao = ''
            # Buscar primeiro pela estrutura específica da descrição do objeto social
            desc_bloco = soup.find('div', class_='pf-body')
            if not desc_bloco:
                # Fallback para outras possíveis classes
                desc_bloco = self.find_div_by_class(soup, r'job_description') or self.find_div_by_class(soup, r'description')
            
            if desc_bloco:
                # Extrair todo o texto da descrição, limitando a 1400 caracteres
                descricao = desc_bloco.get_text(strip=True)[:1400]
            
            # Telefone
            telefone = ''
            bloco_tel = self.find_div_by_class(soup, r'job_phone')
            if bloco_tel:
                ps = bloco_tel.find_all('p')
                for p in ps:
                    texto = p.get_text(strip=True)
                    if texto and not telefone:
                        telefone = texto
                        break

            # E-mail
            email = ''
            bloco_email = self.find_div_by_class(soup, r'job_email')
            if bloco_email:
                ps = bloco_email.find_all('p')
                for p in ps:
                    texto = p.get_text(strip=True)
                    if texto and not email:
                        email = texto
                        break

            # Website
            website = ''
            bloco_site = self.find_div_by_class(soup, r'job_website')
            if bloco_site:
                ps = bloco_site.find_all('p')
                for p in ps:
                    texto = p.get_text(strip=True)
                    if texto and not website:
                        website = texto
                        break

            # Redes sociais
            redes_list = []
            redes_set = set()
            bloco_redes = self.find_div_by_class(soup, r'social_networks')
            if bloco_redes:
                for a in bloco_redes.find_all('a', href=True):
                    if a['href'] not in redes_set:
                        redes_list.append(a['href'])
                        redes_set.add(a['href'])
            
            instagram, linkedin, youtube, outras_redes = self.extrair_redes_sociais_especificas(redes_list)

            # Horário de funcionamento
            horario = ''
            horario_bloco = (
                self.find_div_by_class(soup, r'timing-today') or
                self.find_div_by_class(soup, r'open-hours') or
                self.find_div_by_class(soup, r'horario') or
                self.find_div_by_class(soup, r'funcionamento')
            )
            if horario_bloco:
                horario = horario_bloco.get_text(strip=True)
            
            # Localização
            localizacao = ''
            endereco_bloco = self.find_div_by_class(soup, r'endereco') or self.find_div_by_class(soup, r'address') or self.find_div_by_class(soup, r'location')
            if endereco_bloco:
                localizacao = endereco_bloco.get_text(strip=True)

            # CNPJ
            cnpj = ''
            bloco_cnpj = self.find_div_by_class(soup, r'cnpj')
            if bloco_cnpj:
                ps = bloco_cnpj.find_all('p')
                for p in ps:
                    texto = p.get_text(strip=True)
                    if texto and not cnpj:
                        cnpj = texto
                        break

            # Logo
            logo_url = ''
            logo_local_path = ''
            anchor_logo = soup.find('a', class_=re.compile(r'profile-avatar'))
            if anchor_logo:
                href_logo = anchor_logo.get('href', '')
                style_attr = anchor_logo.get('style', '')
                if href_logo:
                    logo_url = href_logo
                elif style_attr:
                    match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style_attr)
                    if match:
                        logo_url = match.group(1)

                if logo_url:
                    logo_local_path = self._baixar_logo(logo_url, url)

            # Documentos
            docs_categorizados = self.categorizar_documentos_por_bloco(soup)

            # Decodificar entidades HTML em todos os campos de texto
            descricao = html_module.unescape(descricao)
            telefone = html_module.unescape(telefone)
            email = html_module.unescape(email)
            website = html_module.unescape(website)
            horario = html_module.unescape(horario)
            localizacao = html_module.unescape(localizacao)
            cnpj = html_module.unescape(cnpj)

            dados = {
                'nome': nome_ong,
                'url': url,
                'descricao_objeto_social': descricao,
                'telefone': telefone,
                'email': email,
                'website': website,
                'redes_sociais': {
                    'instagram': instagram,
                    'linkedin': linkedin,
                    'youtube': youtube,
                    'outras': ';'.join(outras_redes)
                },
                'horario_funcionamento': horario,
                'localizacao': localizacao,
                'cnpj': cnpj,
                'documentos': {
                    'cneas': docs_categorizados['cneas'],
                    'cebas': docs_categorizados['cebas'],
                    'utilidade_publica': docs_categorizados['utilidade_publica'],
                    'relatorio_atividades': docs_categorizados['relatorio_atividades'],
                    'plano_acao': docs_categorizados['plano_acao'],
                    'estatuto': docs_categorizados['estatuto'],
                    'ata_eleicao': docs_categorizados['ata_eleicao'],
                    'balanco_2020': docs_categorizados['balanco_2020'],
                    'balanco_2021': docs_categorizados['balanco_2021'],
                    'balanco_2022': docs_categorizados['balanco_2022'],
                    'balanco_2023': docs_categorizados['balanco_2023'],
                    'balanco_2024': docs_categorizados['balanco_2024'],
                    'outros_documentos': ';'.join(docs_categorizados['outros_documentos'])
                },
                'logo_url': logo_url,
                'logo_local_path': logo_local_path
            }
            
            return dados, None
            
        except Exception as e:
            self.logger.error(f"Erro ao extrair dados web para {nome_ong}: {str(e)}")
            return None, str(e)


class APIExtractor:
    """Classe responsável pela extração de dados via API"""
    
    def __init__(self, endpoint_base: str, headers: Dict[str, str]):
        self.endpoint_base = endpoint_base
        self.headers = headers
        self.logger = logging.getLogger(__name__)
    
    def obter_total_ongs(self) -> int:
        """Obter total de ONGs cadastradas"""
        try:
            url_count = f"{self.endpoint_base}?per_page=1"
            response = requests.get(url_count, headers=self.headers)
            
            if response.status_code == 200:
                total = int(response.headers.get('X-WP-Total', 0))
                self.logger.info(f"Total de ONGs encontradas: {total}")
                return total
            else:
                self.logger.error(f"Erro ao consultar total de ONGs: {response.status_code}")
                return 0
                
        except Exception as e:
            self.logger.error(f"Erro ao obter total de ONGs: {str(e)}")
            return 0
    
    def obter_dados_ongs(self, per_page: int = 10) -> List[Dict[str, Any]]:
        """Obter dados das ONGs via API"""
        try:
            url_list = f"{self.endpoint_base}?per_page={per_page}"
            response = requests.get(url_list, headers=self.headers)
            
            if response.status_code == 200:
                dados = response.json()
                self.logger.info(f"Coletados dados de {len(dados)} ONGs da API")
                return dados
            else:
                self.logger.error(f"Erro ao obter dados das ONGs: {response.status_code}")
                return []
                
        except Exception as e:
            self.logger.error(f"Erro ao obter dados das ONGs: {str(e)}")
            return []
    
    def extrair_termos_ong(self, ong_data: Dict[str, Any]) -> Dict[str, TermosInfo]:
        """Extrair todos os tipos de termos de uma ONG da API"""
        acf = ong_data.get('acf', {})
        
        tipos_termos = {
            'municipio': 'termos_com_municipio',
            'estado': 'termos_com_estado',
            'uniao': 'termo_uniao',
            'emendas_parlamentares': 'emendas_parlamentares'
        }
        
        termos_estruturados = {}
        
        for tipo_termo, campo_api in tipos_termos.items():
            dados_termo = acf.get(campo_api, [])
            
            if dados_termo and isinstance(dados_termo, list):
                termos_lista = []
                
                for termo in dados_termo:
                    if isinstance(termo, dict):
                        termo_limpo = {}
                        
                        for campo, valor in termo.items():
                            if valor:
                                # Limpar o nome do campo (remover sufixo do tipo)
                                nome_limpo = campo
                                sufixos = ['_municipio', '_estado', '_uniao', '_parlamentares']
                                if tipo_termo == 'emendas_parlamentares':
                                    sufixos = ['_emenda']
                                for sufixo in sufixos:
                                    if nome_limpo.endswith(sufixo):
                                        nome_limpo = nome_limpo.replace(sufixo, '')
                                        break
                                
                                termo_limpo[nome_limpo] = valor
                        
                        # Ignorar termos fantasma: criados acidentalmente na
                        # plataforma, ficam só com situacao_do_termo='Em aprovação'
                        # (valor padrão do WordPress) e nenhum campo real preenchido.
                        campos_reais = {k for k in termo_limpo if k != 'situacao_do_termo'}
                        if campos_reais:
                            termos_lista.append(termo_limpo)
                
                termos_estruturados[tipo_termo] = TermosInfo(
                    quantidade=len(termos_lista),
                    termos=termos_lista
                )
            else:
                termos_estruturados[tipo_termo] = TermosInfo()
        
        return termos_estruturados


class ONGExtractor:
    """Classe principal para extração completa de dados de ONGs"""
    
    def __init__(self, endpoint_base: str = "https://etransparente.org/wp-json/wp/v2/job_listing"):
        self.endpoint_base = endpoint_base
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36"
        }
        
        # Configurar logging (arquivo em ./logs/ong_extractor.log)
        log_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_ts = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        log_file = os.path.join(log_dir, f'ong_extractor_{log_ts}.log')

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Inicializar componentes
        self.api_extractor = APIExtractor(self.endpoint_base, self.headers)
        self.web_scraper = WebScraper(self.headers)
        
        # Estatísticas
        self.estatisticas = {
            'total_processadas': 0,
            'sucessos': 0,
            'erros': 0,
            'dados_web': {
                'telefone': 0,
                'email': 0,
                'website': 0,
                'cnpj': 0,
                'instagram': 0,
                'linkedin': 0,
                'youtube': 0
            },
            'termos': {
                'ongs_com_termos': 0,
                'total_contratos': 0,
                'por_tipo': {
                    'municipio': 0,
                    'estado': 0,
                    'uniao': 0,
                    'emendas_parlamentares': 0
                }
            }
        }
    
    def processar_ong_completa(self, ong_data: Dict[str, Any]) -> Tuple[Optional[ONGData], Optional[str]]:
        """Processar uma ONG com dados de informações + termos"""
        
        nome = ong_data.get('title', {}).get('rendered', 'Nome não encontrado')
        # Decodificar entidades HTML no nome (ex: &#8211; → -)
        nome = html_module.unescape(nome)
        url = ong_data.get('link', '')
        
        self.logger.info(f"Processando: {nome}")
        
        # Extrair dados de termos da API
        termos = self.api_extractor.extrair_termos_ong(ong_data)
        
        # Extrair dados da página web
        dados_web, erro_web = self.web_scraper.extrair_dados_web(url, nome)
        
        if dados_web:
            # Criar objeto ONGData
            ong = ONGData(
                nome=dados_web['nome'],
                url=dados_web['url'],
                logo_url=dados_web.get('logo_url', ''),
                logo_local_path=dados_web.get('logo_local_path', ''),
                descricao_objeto_social=dados_web['descricao_objeto_social'],
                telefone=dados_web['telefone'],
                email=dados_web['email'],
                website=dados_web['website'],
                redes_sociais=RedesSociais(**dados_web['redes_sociais']),
                horario_funcionamento=dados_web['horario_funcionamento'],
                localizacao=dados_web['localizacao'],
                cnpj=dados_web['cnpj'],
                documentos=Documentos(**dados_web['documentos']),
                termos=termos
            )
            
            # Calcular estatísticas dos termos
            total_termos = sum(info.quantidade for info in termos.values())
            ong.estatisticas_termos = EstatisticasTermos(
                total_contratos_parcerias=total_termos,
                tem_termos_municipio=termos['municipio'].quantidade > 0,
                tem_termos_estado=termos['estado'].quantidade > 0,
                tem_termos_uniao=termos['uniao'].quantidade > 0,
                tem_emendas_parlamentares=termos['emendas_parlamentares'].quantidade > 0,
                distribuicao={
                    'municipio': termos['municipio'].quantidade,
                    'estado': termos['estado'].quantidade,
                    'uniao': termos['uniao'].quantidade,
                    'emendas_parlamentares': termos['emendas_parlamentares'].quantidade
                }
            )
            
            # Atualizar estatísticas
            self._atualizar_estatisticas(ong)
            
            return ong, None
        else:
            # Se falhou extração web, criar ONG básica apenas com termos
            ong = ONGData(
                nome=nome,
                url=url,
                logo_url=dados_web['logo_url'] if dados_web else '',
                logo_local_path=dados_web['logo_local_path'] if dados_web else '',
                termos=termos
            )
            
            total_termos = sum(info.quantidade for info in termos.values())
            ong.estatisticas_termos = EstatisticasTermos(
                total_contratos_parcerias=total_termos,
                distribuicao={tipo: info.quantidade for tipo, info in termos.items()}
            )
            
            return ong, f"Dados web: {erro_web}"
    
    def _atualizar_estatisticas(self, ong: ONGData):
        """Atualizar estatísticas globais"""
        stats = self.estatisticas
        
        # Dados web
        if ong.telefone:
            stats['dados_web']['telefone'] += 1
        if ong.email:
            stats['dados_web']['email'] += 1
        if ong.website:
            stats['dados_web']['website'] += 1
        if ong.cnpj:
            stats['dados_web']['cnpj'] += 1
        if ong.redes_sociais.instagram:
            stats['dados_web']['instagram'] += 1
        if ong.redes_sociais.linkedin:
            stats['dados_web']['linkedin'] += 1
        if ong.redes_sociais.youtube:
            stats['dados_web']['youtube'] += 1
        
        # Termos
        total_termos_ong = sum(info.quantidade for info in ong.termos.values())
        if total_termos_ong > 0:
            stats['termos']['ongs_com_termos'] += 1
            stats['termos']['total_contratos'] += total_termos_ong
            
            for tipo, info in ong.termos.items():
                stats['termos']['por_tipo'][tipo] += info.quantidade
    
    def extrair_todas_ongs(self, max_ongs: Optional[int] = None) -> List[ONGData]:
        """Extrair dados de todas as ONGs ou um número limitado"""
        
        self.logger.info("Iniciando extração completa de dados das ONGs")
        
        # Obter total de ONGs
        total_disponivel = self.api_extractor.obter_total_ongs()
        
        if total_disponivel == 0:
            self.logger.error("Nenhuma ONG encontrada na API")
            return []
        
        # Determinar quantas processar
        if max_ongs is None:
            processar = total_disponivel
        else:
            processar = min(max_ongs, total_disponivel)
        
        self.logger.info(f"Processando {processar} ONGs de {total_disponivel} disponíveis")
        
        # Obter dados das ONGs
        dados_api = self.api_extractor.obter_dados_ongs(per_page=processar)
        
        if not dados_api:
            self.logger.error("Não foi possível obter dados das ONGs da API")
            return []
        
        # Processar cada ONG
        resultados = []
        
        for i, ong_data in enumerate(dados_api, 1):
            self.logger.info(f"Processando ONG {i}/{len(dados_api)}")
            
            ong, erro = self.processar_ong_completa(ong_data)
            
            if ong:
                resultados.append(ong)
                self.estatisticas['sucessos'] += 1
                self.logger.info(f"✅ Sucesso: {ong.nome}")
            else:
                self.estatisticas['erros'] += 1
                self.logger.error(f"❌ Erro: {erro}")
            
            self.estatisticas['total_processadas'] += 1
            
            # Pequena pausa para não sobrecarregar o servidor
            time.sleep(0.5)
        
        self.logger.info(f"Extração concluída: {len(resultados)} ONGs processadas com sucesso")
        return resultados
    
    def salvar_dados(self, dados: List[ONGData], arquivo: Optional[str] = None):
        """Salvar dados em arquivo JSON.

        Se `arquivo` for None, gera um nome com timestamp no diretório `output/`:
        `output/oscs_etransparente_YYYY-MM-DD-HH-MM-SS.json`.

        Observação: remover `estatisticas_termos` do dicionário de cada ONG antes
        de salvar para que o arquivo de saída não contenha estatísticas.
        Retorna o caminho do arquivo salvo em caso de sucesso, ou False em caso de erro.
        """

        try:
            # Determinar caminho destino se não fornecido
            if arquivo is None:
                timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                filename = f"oscs_etransparente_{timestamp}.json"
                dirpath = os.path.join(os.getcwd(), "output")
                os.makedirs(dirpath, exist_ok=True)
                arquivo = os.path.join(dirpath, filename)

            # Converter dataclasses para dicionários
            dados_dict = []
            for ong in dados:
                ong_dict = asdict(ong)

                # Remover estatísticas por ONG do output (campo opcional)
                ong_dict.pop('estatisticas_termos', None)

                dados_dict.append(ong_dict)

            # Salvar em JSON
            with open(arquivo, 'w', encoding='utf-8') as f:
                json.dump(dados_dict, f, ensure_ascii=False, indent=2)

            self.logger.info(f"Dados salvos em: {arquivo}")
            self.logger.info(f"Total de registros: {len(dados)}")

            return arquivo

        except Exception as e:
            self.logger.error(f"Erro ao salvar dados: {str(e)}")
            return False
    
    def gerar_relatorio_estatisticas(self):
        """Gerar relatório detalhado das estatísticas"""
        
        stats = self.estatisticas
        total = stats['total_processadas']
        
        if total == 0:
            self.logger.warning("Nenhuma ONG foi processada")
            return
        
        print("\n" + "="*60)
        print("📊 RELATÓRIO DE ESTATÍSTICAS - EXTRAÇÃO DE ONGs")
        print("="*60)
        
        print(f"\n🎯 RESUMO GERAL:")
        print(f"• Total processadas: {total}")
        print(f"• Sucessos: {stats['sucessos']} ({(stats['sucessos']/total*100):.1f}%)")
        print(f"• Erros: {stats['erros']} ({(stats['erros']/total*100):.1f}%)")
        
        print(f"\n🌐 DADOS WEB (Scraping):")
        for campo, count in stats['dados_web'].items():
            percentual = (count / stats['sucessos']) * 100 if stats['sucessos'] > 0 else 0
            print(f"• {campo.replace('_', ' ').title()}: {count}/{stats['sucessos']} ({percentual:.1f}%)")
        
        print(f"\n📋 TERMOS E CONTRATOS (API):")
        termos_stats = stats['termos']
        sucessos = stats['sucessos']
        print(f"• ONGs com contratos: {termos_stats['ongs_com_termos']}/{sucessos} ({(termos_stats['ongs_com_termos']/sucessos*100):.1f}%)")
        print(f"• Total de contratos: {termos_stats['total_contratos']}")
        
        if termos_stats['total_contratos'] > 0:
            print(f"\n📊 DISTRIBUIÇÃO POR TIPO:")
            for tipo, count in termos_stats['por_tipo'].items():
                if count > 0:
                    percentual = (count / termos_stats['total_contratos']) * 100
                    print(f"• {tipo.replace('_', ' ').title()}: {count} ({percentual:.1f}%)")
        
        print("\n" + "="*60)


def main():
    """Função principal"""
    
    print("🚀 Iniciando Extrator de Dados de ONGs - etransparente.org")
    print("="*60)
    
    # Criar instância do extrator
    extrator = ONGExtractor()
    
    # Extrair dados de todas as ONGs disponíveis
    dados = extrator.extrair_todas_ongs()
    
    if dados:
        # Salvar dados (retorna caminho do arquivo salvo ou False)
        caminho_salvo = extrator.salvar_dados(dados)

        if caminho_salvo:
            # Gerar relatório
            extrator.gerar_relatorio_estatisticas()

            print(f"\n✅ EXTRAÇÃO FINALIZADA COM SUCESSO!")
            print(f"💾 Arquivo gerado: {caminho_salvo}")
            print(f"📊 Total de ONGs extraídas: {len(dados)}")
        else:
            print(f"\n❌ Erro ao salvar dados")
    else:
        print(f"\n❌ Nenhuma ONG foi extraída")


if __name__ == "__main__":
    main()
