## Guia didático — `ong_extractor.py`

Este documento explica, passo a passo, o que faz o script `ong_extractor.py` presente neste repositório. O objetivo é ajudar qualquer pessoa (mesmo sem muita experiência em Python) a entender a responsabilidade de cada bloco de código, o formato dos dados, como executar e como estender/depurar.

---

## Visão geral

`ong_extractor.py` é um *pipeline* (pequeno ETL) que combina duas fontes de dados sobre Organizações da Sociedade Civil (ONGs) do site `etransparente.org`:

- scraping da própria página da ONG (para contatos, documentos, redes sociais, descrição etc.)
- consulta à REST API (para termos e contratos cadastrados via ACF)

O script estrutura os dados usando `dataclasses` (estruturas leves e tipadas), agrega estatísticas internas durante a execução e salva os dados finais em JSON.

Principais componentes (arquitetura):

- Dataclasses: definem o 'modelo' em memória (como `ONGData`, `Documentos`, `RedesSociais`)
- `WebScraper`: faz requests + parsing HTML com BeautifulSoup
- `APIExtractor`: consulta a REST API e organiza os termos por tipo
- `ONGExtractor`: orquestra o processo (usa `APIExtractor` + `WebScraper`), calcula estatísticas e salva o resultado
- `main()`: função de entrada que instancia `ONGExtractor` e dispara a extração completa

---

## Dataclasses (modelos de dados)

Por que usar `dataclass`?

- simplifica criação de objetos com campos nomeados
- fácil conversão para dicionário com `asdict()` antes de salvar JSON

Principais dataclasses explicadas:

- `RedesSociais` — campos: `instagram`, `linkedin`, `youtube`, `outras` (strings). Normaliza links encontrados.
- `Documentos` — campos categorizados para os diferentes tipos de documento (estatuto, balancetes por ano etc.). Cada campo armazena o link/URL ou string vazia.
- `TermosInfo` — usado para armazenar uma lista de termos/contratos de um tipo (ex.: município). Campos: `quantidade` e `termos` (lista de dicionários com informações do termo).
- `EstatisticasTermos` — resumo booleano e contagens por tipo (municipio/estado/união/emendas) — usado internamente.
- `ONGData` — objeto principal que reúne: `nome`, `url`, `descricao_objeto_social`, `telefone`, `email`, `website`, `redes_sociais`, `horario_funcionamento`, `localizacao`, `cnpj`, `documentos`, `termos`, `estatisticas_termos`.

Observação: o script atualmente remove o campo `estatisticas_termos` antes de salvar o JSON final (opção solicitada), então o arquivo salvo não contém essas estatísticas por ONG — elas existem apenas durante a execução para relatórios no terminal/logs.

---

## `WebScraper` — scraping da página da ONG

Responsabilidade: visitar a URL público da ONG e extrair informações estruturadas do HTML.

Principais pontos do `WebScraper`:

- `find_div_by_class(soup, pattern)` — utilitário que busca uma `div` usando regex para a classe. Evita depender de uma única classe exata.
- `extrair_redes_sociais_especificas(redes_list)` — separa links de redes sociais por plataforma (instagram, linkedin, youtube) e agrupa o resto em `outras`.
- `categorizar_documentos(documentos_list)` — percorre links de documentos (PDF/DOC) e tenta categorizar por palavra-chave (estatuto, plano, balanco). Documentos sem categoria vão para `outros_documentos`.
- `extrair_dados_web(url, nome_ong)` — faz o request, cria o `soup`, e extrai:
  - Descrição do objeto social: primeiro tenta `div.pf-body`; se não encontrar, tenta classes que costumam conter a descrição
  - Telefone, e-mail, website (procura blocos específicos por classe)
  - Redes sociais: percorre âncoras dentro de `social_networks`
  - Horário de funcionamento, localização, CNPJ
  - Documentos: encontra todos os links que terminam em `.pdf`, `.doc`, `.docx` e passa por `categorizar_documentos`

Erros: a função retorna `(dados, None)` em sucesso ou `(None, erro_message)` em caso de exceção ou erro HTTP. O método loga o erro para ajudar a depuração.

Dica prática: se alguma ONG não devolver informação esperada, abra o HTML (no navegador) e procure pelas classes mencionadas — o site pode ter variações por template.

---

## `APIExtractor` — consulta à REST API

Responsabilidade: obter dados estruturados (principalmente ACF — campos personalizados) para cada ONG via endpoint WordPress.

Principais métodos:

- `obter_total_ongs()` — faz uma request com `per_page=1` e lê o header `X-WP-Total` para descobrir quantos posts (ONGs) existem.
- `obter_dados_ongs(per_page)` — busca uma página de ONGs (usado para obter os objetos que serão iterados). Por simplicidade o código pede `per_page=processar` para obter tudo em uma requisição — se houver muitas ONGs, será melhor paginar.
- `extrair_termos_ong(ong_data)` — dentro do `ong_data` obtido pela API, procura em `acf` os campos relacionados a termos (contratos com município/estado/união e emendas). Para cada tipo:
  - normaliza nomes de campos (remove sufixos `_municipio`, `_estado` etc.)
  - monta `TermosInfo(quantidade, termos=[...])`

Retorno: um dicionário com chaves `municipio`, `estado`, `uniao`, `emendas_parlamentares` onde cada uma é um `TermosInfo`.

---

## `ONGExtractor` — orquestração e estatísticas

Responsabilidade: juntar as duas fontes (API + web), montar objetos `ONGData`, acumular estatísticas globais e salvar o resultado final.

Fluxo resumido de `processar_ong_completa(ong_data)`:

1. obter `nome` e `url` do objeto vindo da API
2. chamar `APIExtractor.extrair_termos_ong()` para obter os termos
3. chamar `WebScraper.extrair_dados_web(url, nome)` para obter dados de contato e documentos
4. montar `ONGData(...)` preenchendo os campos a partir do scraping + termos
5. calcular `EstatisticasTermos` por ONG (somente em memória)
6. atualizar estatísticas globais (`_atualizar_estatisticas`) — contagens de quantas ONGs têm telefone/email/cnpj, e distribuição de termos

Observações sobre estatísticas:

- As estatísticas são mantidas no dicionário `self.estatisticas` dentro de `ONGExtractor`; servem para gerar um relatório no terminal (método `gerar_relatorio_estatisticas`).
- Conforme solicitado, elas não são gravadas por ONG no JSON final — o campo `estatisticas_termos` é removido antes do `salvar_dados()`.

---

## Salvando os dados: `salvar_dados()`

Comportamento atual (após alterações feitas neste repositório):

1. Se `arquivo` for None, gera um nome timestamped no diretório `output/` com o padrão: `oscs_etransparente_YYYY-MM-DD-HH-MM-SS.json`.
2. Cria a pasta `output/` se não existir.
3. Converte cada `ONGData` em dicionário com `asdict()`.
4. Remove a chave `estatisticas_termos` (se presente) de cada dicionário, para manter o JSON final 'limpo'.
5. Salva o arquivo e retorna o caminho completo do arquivo salvo (ou `False` em caso de erro).

Formato de saída (cada elemento é um dicionário):

```json
{
  "nome": "Nome da ONG",
  "url": "https://etransparente.org/oscs/exemplo/",
  "descricao_objeto_social": "Texto...",
  "telefone": "...",
  "email": "...",
  "website": "...",
  "redes_sociais": {"instagram":"...","linkedin":"","youtube":"","outras":"..."},
  "horario_funcionamento": "...",
  "localizacao": "...",
  "cnpj": "...",
  "documentos": {"estatuto":"...","balanco_2020":"...","outros_documentos":"link1;link2"},
  "termos": {"municipio": {"quantidade": 1, "termos": [...]}, "estado": {...}, "uniao": {...}, "emendas_parlamentares": {...}}
}
```

---

## Logging

- O logger é configurado para escrever em `./logs/ong_extractor_{TIMESTAMP}.log` e também imprimir no console (StreamHandler).
- Cada execução gera um arquivo novo com sufixo timestamp (ex.: `ong_extractor_2025-11-04-13-45-12.log`).

Sugestões de melhoria: usar `TimedRotatingFileHandler` ou `RotatingFileHandler` para limitar número de arquivos/uso de disco, ou criar um symlink `logs/ong_extractor.log` apontando para o mais recente.

---

## Função principal (`main()`)

O `main()` faz:

1. cria `extrator = ONGExtractor()`;
2. chama `extrator.extrair_todas_ongs()` (por padrão busca o total e tenta processar tudo de uma vez);
3. chama `extrator.salvar_dados(dados)` — que salva em `output/` com nome timestamped se nenhum nome for passado;
4. chama `extrator.gerar_relatorio_estatisticas()` para imprimir resultado no terminal.

Observação prática: o método `obter_dados_ongs(per_page=processar)` atualmente pede todos os registros em uma única requisição, o que pode falhar se houver limite no per_page do servidor. Para maior robustez, paginar seria indicado (loop com `page=1..N`).

---

## Como rodar (passo a passo)

1. Garanta que você tem o ambiente Python adequado (ver `requirements.txt`). Instale as dependências em um venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Execute o extrator (diretório raiz `pipeline`):

```bash
python3 ong_extractor.py
```

3. Ao final, verifique:

- arquivo salvo em `output/` (nome `oscs_etransparente_YYYY-MM-DD-HH-MM-SS.json`)
- logs em `logs/` com o arquivo `ong_extractor_YYYY-MM-DD-HH-MM-SS.log`

---

## Casos comuns de erro e como debugar

- Erros HTTP (4xx/5xx): o `WebScraper` retorna erro específico `Erro HTTP {codigo}`; cheque o log e o `response.status_code`.
- Mudanças no template HTML: se a descrição ou contato não aparecer, abra a página no navegador, inspecione as classes e ajuste os padrões usados em `find_div_by_class` ou adicione novos fallbacks.
- Limites de API / `per_page`: se a API limitar `per_page`, pagine os resultados em `obter_dados_ongs()`.
- Exceções não tratadas: logs em `logs/` devem apresentar tracebacks; use-os para localizar a linha com problema.

---

## Sugestões de melhorias e próximos passos

- Gerar `requirements.txt` pinado com `pip freeze > requirements.txt` para reprodutibilidade.
- Implementar paginação robusta na chamada à API (usar `page` e `per_page` em loop até consumir `X-WP-Total`).
- Adicionar testes unitários para:
  - `categorizar_documentos()` (vários exemplos de nomes de arquivos)
  - `extrair_redes_sociais_especificas()`
  - parsing de termos (mockando a resposta da API)
- Adicionar um CLI mínimo com `argparse` para permitir `--max-ongs`, `--output-dir` e `--no-logs`.
- Considerar politeness: aumentar pausa entre requests, usar cache local ou re-execução incremental.

---

## Recapitulação (em 3 linhas)

- `ong_extractor.py` coleta dados de ONGs via API + scraping, organiza em dataclasses e salva um JSON final.
- Estatísticas são calculadas em memória e mostradas no terminal; não são salvas por registro no JSON final (campo removido antes de salvar).
- Logs e arquivos resultantes são gerados com timestamp em `logs/` e `output/`.

Se quiser, posso:

- gerar uma versão do README com instruções de deploy em um servidor (systemd, cron),
- adicionar pequenos testes unitários e um script `scripts/generate_report.py` para produzir relatórios por ONG (txt/csv),
- ou transformar isto em um pacote pip instalável.

----

Arquivo gerado automaticamente para documentação explicativa por ferramenta assistente em projeto.
