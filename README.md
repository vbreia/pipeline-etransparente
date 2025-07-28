# 🏢 Extrator de Dados de ONGs - etransparente.org

Script Python orientado a objetos para extração completa de dados de ONGs do site **etransparente.org**, combinando web scraping e API REST.

## 🎯 Funcionalidades

### 📊 **Dados Extraídos**

**🌐 Informações Web (Scraping)**
- **Contato**: Telefone, Email, Website
- **Identificação**: CNPJ, Localização, Descrição do objeto social
- **Redes Sociais**: Instagram, LinkedIn, YouTube (separados automaticamente)
- **Documentos**: CNEAS, CEBAS, Estatuto, Balanços contábeis (categorizados por ano)

**📋 Termos e Contratos (API)**
- **Termos com Município**: Contratos e colaborações municipais
- **Termos com Estado**: Parcerias estaduais
- **Termos com União**: Convênios federais
- **Emendas Parlamentares**: Recursos de emendas parlamentares

### 🔧 **Características Técnicas**

- **Orientação a Objetos**: Código modular e reutilizável
- **Logging Completo**: Registros detalhados de execução
- **Tratamento de Erros**: Robustez na extração de dados
- **Dataclasses**: Estruturas de dados tipadas e organizadas
- **Proteção contra Sobrecarga**: Pausas entre requisições
- **Estatísticas Integradas**: Relatórios de completude automáticos

## 📦 Dependências

```bash
pip install beautifulsoup4 requests
```

## 🚀 Como Usar

### **Execução Básica**

```bash
python3 ong_extractor.py
```

### **Personalização**

```python
from ong_extractor import ONGExtractor

# Criar instância
extrator = ONGExtractor()

# Extrair dados (padrão: 10 ONGs para teste)
dados = extrator.extrair_todas_ongs(max_ongs=10)

# Processar todas as ONGs disponíveis
# dados = extrator.extrair_todas_ongs()

# Salvar dados
extrator.salvar_dados(dados, "meus_dados.json")

# Gerar relatório
extrator.gerar_relatorio_estatisticas()
```

## 📁 Arquivos Gerados

### **`dados_pre_tratados.json`**
Arquivo principal com todos os dados extraídos em formato JSON estruturado.

### **`ong_extractor.log`**
Log detalhado da execução com timestamps e níveis de log.

## 📊 Estrutura dos Dados

```json
{
  "nome": "Nome da ONG",
  "url": "URL da página",
  "descricao_objeto_social": "Descrição das atividades",
  "telefone": "Telefone de contato",
  "email": "Email de contato",
  "website": "Site oficial",
  "redes_sociais": {
    "instagram": "URL do Instagram",
    "linkedin": "URL do LinkedIn", 
    "youtube": "URL do YouTube",
    "outras": "Outras redes sociais"
  },
  "localizacao": "Endereço físico",
  "cnpj": "CNPJ da organização",
  "documentos": {
    "cneas": "URL do certificado CNEAS",
    "cebas": "URL do certificado CEBAS",
    "estatuto": "URL do estatuto",
    "balanco_2023": "URL do balanço 2023",
    "balanco_2024": "URL do balanço 2024",
    "outros_documentos": "Outros documentos"
  },
  "termos": {
    "municipio": {
      "quantidade": 2,
      "termos": [
        {
          "identificacao_do_instrumento_de_parceria": "TERMO DE COLABORAÇÃO Nº 026/2022",
          "valor_total_do_termo": "R$960.900,00",
          "data_da_assinatura": "2022-05-15",
          "situacao_do_termo": "Ativo"
        }
      ]
    },
    "estado": { "quantidade": 0, "termos": [] },
    "uniao": { "quantidade": 1, "termos": [...] },
    "emendas_parlamentares": { "quantidade": 0, "termos": [] }
  },
  "estatisticas_termos": {
    "total_contratos_parcerias": 3,
    "tem_termos_municipio": true,
    "tem_termos_estado": false,
    "tem_termos_uniao": true,
    "tem_emendas_parlamentares": false,
    "distribuicao": {
      "municipio": 2,
      "estado": 0,
      "uniao": 1,
      "emendas_parlamentares": 0
    }
  }
}
```

## 🏗️ Arquitetura do Sistema

### **Classes Principais**

#### **`ONGExtractor`**
- Classe principal que orquestra todo o processo
- Gerencia estatísticas e logging
- Coordena extração web e API

#### **`WebScraper`**
- Responsável pelo scraping das páginas web
- Extrai informações de contato, documentos e redes sociais
- Categoriza documentos automaticamente

#### **`APIExtractor`**
- Gerencia comunicação com a API REST
- Extrai dados de termos e contratos
- Processa campos ACF (Advanced Custom Fields)

#### **`Dataclasses`**
- **`ONGData`**: Estrutura principal dos dados
- **`RedesSociais`**: Organização das redes sociais
- **`Documentos`**: Categorização de documentos
- **`TermosInfo`**: Informações de contratos
- **`EstatisticasTermos`**: Métricas de contratos

## 📈 Relatório de Estatísticas

O script gera automaticamente um relatório detalhado:

```
📊 RELATÓRIO DE ESTATÍSTICAS - EXTRAÇÃO DE ONGs
============================================================

🎯 RESUMO GERAL:
• Total processadas: 10
• Sucessos: 10 (100.0%)
• Erros: 0 (0.0%)

🌐 DADOS WEB (Scraping):
• Telefone: 8/10 (80.0%)
• Email: 8/10 (80.0%)
• Website: 6/10 (60.0%)
• Cnpj: 10/10 (100.0%)
• Instagram: 6/10 (60.0%)
• Linkedin: 2/10 (20.0%)
• Youtube: 3/10 (30.0%)

📋 TERMOS E CONTRATOS (API):
• ONGs com contratos: 6/10 (60.0%)
• Total de contratos: 15

📊 DISTRIBUIÇÃO POR TIPO:
• Municipio: 10 (66.7%)
• Estado: 2 (13.3%)
• Uniao: 3 (20.0%)
```

## ⚙️ Configurações

### **Endpoint da API**
```python
endpoint_base = "https://etransparente.org/wp-json/wp/v2/job_listing"
```

### **Headers HTTP**
```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
```

### **Logging**
- Arquivo: `ong_extractor.log`
- Níveis: INFO, ERROR, WARNING
- Formato: `timestamp - level - message`

## 🚦 Limitações e Boas Práticas

### **Rate Limiting**
- Pausa de 0.5s entre requisições para não sobrecarregar o servidor
- Tratamento de erros HTTP

### **Robustez**
- Tratamento de exceções em todas as operações
- Logging detalhado para debug
- Validação de dados antes do processamento

### **Escalabilidade**
- Código modular permite fácil extensão
- Dataclasses facilitam manutenção
- Arquitetura orientada a objetos permite reutilização

## 🔍 Troubleshooting

### **Erro de Módulos**
```bash
pip install beautifulsoup4 requests
```

### **Erro de Timeout**
- Verificar conexão com internet
- Ajustar timeout nas requisições

### **Dados Incompletos**
- Verificar logs para identificar problemas específicos
- Algumas ONGs podem não ter todos os campos preenchidos

## 📝 Exemplo de Uso Avançado

```python
import logging
from ong_extractor import ONGExtractor

# Configurar logging personalizado
logging.basicConfig(level=logging.DEBUG)

# Criar extrator
extrator = ONGExtractor()

# Processar apenas ONGs com contratos
dados = extrator.extrair_todas_ongs(max_ongs=50)

# Filtrar ONGs com contratos ativos
ongs_com_contratos = [
    ong for ong in dados 
    if ong.estatisticas_termos.total_contratos_parcerias > 0
]

# Salvar apenas ONGs com contratos
extrator.salvar_dados(ongs_com_contratos, "ongs_com_contratos.json")

print(f"Encontradas {len(ongs_com_contratos)} ONGs com contratos ativos")
```

## 👥 Contribuição

Para contribuir com melhorias:

1. **Fork** o projeto
2. **Crie** uma branch para sua feature
3. **Commit** suas mudanças
4. **Push** para a branch
5. **Abra** um Pull Request

## 📄 Licença

Este projeto está sob licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

---

**Desenvolvido para facilitar a análise de transparência de ONGs brasileiras** 🇧🇷
