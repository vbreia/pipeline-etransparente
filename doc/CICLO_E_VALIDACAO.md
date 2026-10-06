# Ciclo, validação e preparação do envio

> Guia para quem mexe no pipeline. Contexto: entre ago e out/2026 três ciclos seguidos
> saíram com visualizações erradas. Este desenho existe para que um relatório errado
> não chegue a nenhuma OSC sem ser detectado.

## Regra de ouro: o ciclo vem da DAG

- O **ciclo** (`YYYY-MM`) é o mês que o relatório resume. Quem decide é **só a DAG**,
  a partir do `data_interval_start` do Airflow, e repassa como `--ciclo` a todos os scripts.
- **Nenhum script calcula o ciclo pela data do sistema** (`date.today()`, `datetime.now()`).
  Use `adicionar_argumento_ciclo(parser)` de `scripts/ciclo.py`.
- O teste `tests/test_contrato_ciclo.py` lê o código e falha no GitHub Actions se alguém
  quebrar essa regra. Ele foi verificado contra o código do incidente de 01/10/2026:
  reprova os 5 scripts que tinham o problema.

## Fluxo da DAG `ong_pipeline` (dia 3, 11:30 UTC)

| Task | Script | O que garante |
|---|---|---|
| `validar_data` | `ciclo.py` | ciclo já fechou há 48h+ e é o mês anterior (ou reprocessamento explícito) |
| `extract_ong_data` | `ong_extractor.py` | — |
| `generate_transparency_scores` | `generate_transparency_scores.py` | — |
| `fetch_ga4_views` | `ga4/oscs_monthly_views.py` | grava `oscs_views_{ciclo}.json` com cabeçalho (ciclo, período, data, hash) |
| `generate_dashboards` | `dash.py` | grava `dashboards/<ts>/relatorios.json`: o que cada PDF contém + hash do PDF |
| `upload_to_azure` | `upload_to_azure.py` | publica só os arquivos do ciclo |
| `generate_silver` | `generate_silver.py` | — |
| `detect_doc_changes` | `detect_doc_changes.py` | — |
| `validar_ciclo` | `validar_ciclo.py` | 12 verificações; qualquer bloqueante falhando para a DAG |
| `preparar_envios` | `preparar_envios.py` | e-mails prontos + amostra + código de validação. **Não envia.** |

O envio às OSCs não está na DAG: acontece depois da conferência e confirmação de uma pessoa
autorizada (configuração `APROVADORES`: Tatiana, Cinthia ou Victor) em `dashboard.etransparente.org/envio` (ver `doc/ENVIO_COM_APROVACAO.md`).

## As 12 verificações (`validar_ciclo.py`)

Bloqueantes (❌ param tudo): data do ciclo · arquivo de views (cabeçalho, período, gerado após o
fechamento + 48h, todos os dias, total > 0) · integridade por hash · número no PDF = dado ·
dashboard = PDF · **conferência cruzada com uma segunda consulta ao GA4** · mesma contagem de
OSCs em todas as etapas · nomes únicos · PDF publicado para toda OSC com e-mail.

Alertas (⚠️ aparecem com nome, não bloqueiam): OSCs que entraram/saíram · OSCs sem e-mail ·
total fora de 30–300% da mediana dos 3 meses anteriores.

Se algo não puder ser verificado (GA4 fora do ar, Azure inacessível), **conta como falha** —
o sistema nunca aprova o que não conseguiu conferir.

Resultado: `output/validacao_{ciclo}.json` e `gold/validacao/{ciclo}.json`.

## Comandos

```bash
# Rodar o ciclo manualmente (usa o ciclo do intervalo do Airflow)
docker exec airflow-webserver airflow dags trigger ong_pipeline

# Reprocessar um ciclo antigo de propósito
docker exec airflow-webserver airflow dags trigger ong_pipeline \
  --conf '{"ciclo": "2026-09", "reprocessar": true}'

# Só validar (depois de dash + upload)
docker exec -w /home/airflow airflow-scheduler python scripts/validar_ciclo.py --ciclo 2026-10

# Ensaio: preparar com todos os e-mails indo para um endereço interno
docker exec -w /home/airflow airflow-scheduler python scripts/preparar_envios.py \
  --ciclo 2026-10 --destino-teste comunicacao@direitocoletivo.org.br

# Testes (local)
python -m pytest tests
```

## Envio emergencial

`send_reports.py` continua existindo só para emergência: exige `--ciclo` e
`--confirmo-envio-emergencial`, e recusa enviar se a pasta de PDFs for de outro ciclo.
Use apenas com aprovação por escrito da gestão, e só se o fluxo de `doc/ENVIO_COM_APROVACAO.md` estiver indisponível.
