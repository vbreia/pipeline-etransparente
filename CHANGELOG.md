# Changelog — etransparente.org

Todas as mudanças relevantes na metodologia, no cálculo de pontuação e no sistema de
transparência do etransparente.org são documentadas aqui.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).
Versionamento: `MAJOR.MINOR.PATCH` — ver `PLANO_DE_ACAO.md` (seção 4) para o critério de
cada tipo de mudança. Em resumo:

- **MAJOR**: mudança de metodologia — notas antes/depois não são diretamente comparáveis.
- **MINOR**: novo dado/funcionalidade sem alterar o cálculo existente — notas continuam comparáveis.
- **PATCH**: correção de bug — a metodologia estava correta, um dado estava sendo capturado/exibido errado.

---

## [1.3.0] - 2026-08-06

### Adicionado

- **Botão de report de erro nos relatórios.** Cada relatório em PDF, e-mail mensal e o perfil
  da OSC no painel de gestão agora trazem um link direto para reportar qualquer divergência
  percebida no documento. O link já vem preenchido com o nome da organização, o ciclo do
  relatório, o código de verificação (hash) e o link de autenticidade, para agilizar a
  investigação e a resposta.

### Corrigido

- **Números de visualização inventados quando o dado real não estava disponível.** Quando o
  sistema não tinha, para o ciclo em questão, dados reais de visualização da OSC na
  plataforma, o relatório em PDF preenchia o gráfico e os totais com valores aleatórios,
  apresentados visualmente como se fossem dados reais do Google Analytics — sem qualquer
  indicação de que eram provisórios. Corrigido: quando não há dado real disponível, o
  relatório agora exibe uma mensagem clara de indisponibilidade nesse ciclo, em vez de
  qualquer número.

### Dívida técnica registrada (não bloqueante)

O perfil da OSC no painel de gestão (`dashboard/osc.html`) recalcula, no navegador, o mesmo
hash de verificação que o sistema já calcula ao gerar o relatório — em vez de reutilizar o
valor já calculado. As duas implementações produzem o mesmo resultado hoje, mas por serem
independentes, uma mudança futura no cálculo do hash precisaria ser replicada manualmente nos
dois lugares. Estamos cientes e vamos unificar isso numa próxima iteração.

---

## [1.2.1] - 2026-08-06

### Corrigido

- **Endereço institucional incorreto exibido nos relatórios.** O campo de localização de
  cada OSC estava, em alguns casos, capturando o endereço institucional fixo do Instituto
  de Direito Coletivo (mantenedor da plataforma) em vez do endereço específico da própria
  organização. Causa: o seletor de extração casava com um bloco do cabeçalho global do site
  antes de alcançar o bloco de endereço específico da OSC. Corrigido para usar o campo
  específico da OSC como fonte primária.
  Validado contra 5 OSCs distintas, com endereços corretos e diferentes entre si.

- **Contagem de visualizações do site subestimada, em alguns casos zerada.** O painel de
  visualizações (Google Analytics) filtrava as páginas por correspondência exata de URL, sem
  normalizar diferenças de formatação (maiúsculas/minúsculas, barra final, acentuação
  codificada). Isso fazia com que visualizações reais deixassem de ser contabilizadas
  silenciosamente para algumas OSCs. Corrigido para normalizar a comparação antes de
  consultar o Google Analytics.
  Validado com o ciclo de junho/2026: a contagem do Instituto de Direito Coletivo, que
  aparecia como 0, passou a refletir corretamente o valor real (5 visualizações),
  confirmado de forma independente na interface do Google Analytics.

### Nota de transparência

A correção acima foi validada comparando o resultado do sistema com os dados reais do
Google Analytics para o ciclo de junho/2026, com total confirmado de forma independente.
Nenhum e-mail foi enviado nem PDF reemitido durante esse processo de validação.

---

## [1.2.0] - Não documentado retroativamente

Estado da metodologia antes deste changelog começar a ser mantido. Ver
`Metodologia_etransparente.docx` para a rubrica de pontuação vigente e os resumos de sessão
em `sessao_*.md` para o histórico de desenvolvimento até aqui.