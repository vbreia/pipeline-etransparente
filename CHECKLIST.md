# Checklist pré-push

Execute os três comandos abaixo (a partir da raiz do repo) antes de qualquer `git push`.
Todos devem terminar com exit 0.

---

## 1. Smoke test estrutural (validate_pipeline_output.py)

Valida campos obrigatórios, faixas de nota e enums nos JSONs de saída
(`oscs_etransparente_*.json`, `scores/transparency_scores_*.json`, `oscs_views_*.json`).

```bash
python3 scripts/tests/validate_pipeline_output.py --output-dir output
```

Flags úteis:
- `--strict` — trata warnings como falha (recomendado antes de merge em main)
- `--output-dir /home/airflow/output` — aponta para output de produção/Docker

---

## 2. Detecção de vazamento de dados (detect_data_leak.py)

Detecta campos como `localizacao` ou `cnpj` com o mesmo valor em OSCs diferentes
e verifica se o endereço da sentinela aparece nos HTMLs de outras OSCs.

```bash
python3 scripts/tests/detect_data_leak.py --output-dir output
```

Flags úteis:
- `--sentinela "Nome da OSC"` — troca a OSC usada como sentinela (default: IDC)
- `--pular-html` — pula a checagem de HTMLs renderizados (mais rápido, se os HTMLs ainda não foram gerados)

---

## 3. Testes unitários de normalize_path (Bug 2 — GA4)

Testa a normalização de paths antes da query ao GA4.

```bash
python3 scripts/tests/test_normalize_path.py
```

> **Nota:** A correção de normalização de paths em `oscs_monthly_views.py` ainda
> requer validação com credencial GA4 real (produção/staging) antes de ser
> considerada pronta para merge. Ver comentário `NOTE` na docstring de `normalize_path()`.

---

## Quando rodar

| Situação | validate | detect_leak | test_normalize |
|----------|----------|-------------|----------------|
| Mudança em `ong_extractor.py` | ✅ | ✅ | — |
| Mudança em `generate_transparency_scores.py` | ✅ | — | — |
| Mudança em `oscs_monthly_views.py` | — | — | ✅ |
| Mudança em `dash.py` | ✅ | ✅ | — |
| Qualquer push para `main` | ✅ | ✅ | ✅ |
