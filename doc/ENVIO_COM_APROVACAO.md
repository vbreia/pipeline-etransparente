# Envio com aprovação — operação e implantação

> O envio dos relatórios às OSCs não acontece mais na VM. A DAG prepara; a
> presidência confere uma amostra e confirma em `dashboard.etransparente.org/envio`;
> uma Azure Function envia exatamente o que foi preparado.

## Peças

| Peça | Onde | O que faz |
|---|---|---|
| `scripts/preparar_envios.py` | VM (última task da DAG) | Monta e-mails, sorteia amostra, calcula código, avisa "ciclo pronto" |
| `dashboard/envio.html` | Static Web App | Página de conferência e confirmação |
| `api/` | Static Web App (funções gerenciadas, Python 3.11) | `status`, `abrir-pdf`, `aprovar`, `reportar-erro` |
| `functions/` | Function App `etransparente-envio` (Consumo Flexível, Brazil South) | Envia 1 e-mail por mensagem da fila `envios` |
| `envio/comum.py` | canônico | Regras comuns; copiado para `api/shared_code/` e `functions/` por `envio/sincronizar_copias.py` |
| `scripts/desbloquear_envio.py` | VM | Libera bloqueio por **falso alarme**, com justificativa registrada |

Dados no Azure (conta `etransparentedata`, container `etransparente`), em `envios/{ciclo}/` —
**fora de `gold/`**, porque `gold/` é legível pelo token de leitura do dashboard e aqui há
e-mails de OSCs e dados de acesso. Fila: `envios` (e `envios-poison`, criada pela plataforma).

## Regras garantidas pelo código (e testadas em `tests/test_envio.py`)

- Só contas com o papel `aprovador_envio` confirmam. Outra conta logada que tentar: 403 +
  e-mail de alerta (no máximo 1 por conta por hora) para presidência, transparência e comunicação.
- A confirmação exige que **a própria conta** tenha aberto os 3 PDFs da amostra pela página
  (registro no servidor) e marcado "confere" em todos, mais um nome declarado.
- A confirmação vale para um **código de validação**. Se o ciclo for preparado de novo, o código muda.
- E-mail "envio confirmado" com nome declarado, conta, data/hora, IP, local aproximado, provedor,
  navegador e horário de abertura de cada PDF. Nome diferente do titular da conta é destacado.
- "Reportar erro" (qualquer conta do dashboard) bloqueia na hora. A Function confere o bloqueio
  **antes de cada e-mail**: um bloqueio no meio do envio impede os restantes.
- A Function confere o hash do e-mail preparado e do PDF antes de enviar: qualquer alteração
  depois da aprovação faz aquele e-mail falhar em vez de sair adulterado.
- Mensagem sem aprovação válida é ignorada sem alterar o ciclo. E-mail já enviado nunca é reenviado.
- Ao fim, `resultado.json` e e-mail "envio concluído" (uma única vez).

## Implantação

### 1. Configurações do Static Web App (`etransparente-dashboard` → Variáveis de ambiente)

| Nome | Valor |
|---|---|
| `DADOS_STORAGE` | Cadeia de conexão da conta `etransparentedata` (Conta de armazenamento → Chaves de acesso) |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `transparencia@direitocoletivo.org.br` |
| `SMTP_PASSWORD` | senha de app do transparencia@ |
| `SMTP_FROM` | `transparencia@direitocoletivo.org.br` |
| `NOTIFICAR_GESTAO` | `presidencia@direitocoletivo.org.br,transparencia@direitocoletivo.org.br,comunicacao@direitocoletivo.org.br` |
| `EMAIL_TECNICO` | `comunicacao@direitocoletivo.org.br` |

As mesmas 8 configurações vão na **Function App** `etransparente-envio` (Configurações → Variáveis de ambiente).

### 2. Publicar o dashboard + API

```bash
# token novo: portal → etransparente-dashboard → Gerenciar token de implantação → Redefinir
swa deploy ./dashboard --api-location ./api --api-language python --api-version 3.11 \
  --deployment-token "<token>" --env production
```

### 3. Publicar a Function

```bash
npm i -g azure-functions-core-tools@4      # uma vez
az login                                   # uma vez
cd functions && func azure functionapp publish etransparente-envio
```

## Operação

- **Dia 3:** a DAG roda; se a validação aprovar, chega o e-mail "Ciclo pronto para conferência".
- **Presidência:** abre `/envio`, abre os 3 PDFs, marca "Sim", digita o nome, confirma.
- **Acompanhamento:** a página atualiza sozinha durante o envio; ao fim chega "envio concluído".
- **Erro reportado:** chega e-mail técnico para comunicacao@. Duas saídas:
  - erro real → corrigir e rodar a DAG de novo (nova preparação = novo código, nova amostra,
    nova conferência; o bloqueio é arquivado);
  - falso alarme → `scripts/desbloquear_envio.py --ciclo ... --responsavel "..." --motivo "..."`.
- **Bloqueio no meio do envio, com e-mails já enviados:** retomada é manual (o sistema se recusa
  a re-preparar para não duplicar). Analisar `envios/{ciclo}/status/` e tratar caso a caso.

## Ensaio (antes do primeiro ciclo real)

```bash
# na VM: prepara um ciclo com TODOS os e-mails indo para um endereço interno
docker exec -w /home/airflow airflow-scheduler python scripts/preparar_envios.py \
  --ciclo 2026-09 --destino-teste comunicacao@direitocoletivo.org.br
```
A página mostra a faixa "ENSAIO". Confirmar por ela envia tudo só para o endereço de teste.
