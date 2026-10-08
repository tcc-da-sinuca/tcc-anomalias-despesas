# Roteiro até a entrega final (02/11/2026)

Caminho do software do TCC, do estado atual até a entrega. Cada item aponta o
requisito (RF/US) e o critério para considerá-lo pronto.

**Como usar:** marque `[x]` quando o item estiver no `main` com testes passando.
Ao concluir ou replanejar algo, atualize a seção "Situação atual" e registre a
mudança no histórico, no fim do arquivo. Decisões que afetam a documentação
entregue continuam indo para [`MUDANCAS_PARA_DOCUMENTACAO.md`](MUDANCAS_PARA_DOCUMENTACAO.md).

---

## Situação atual (atualizado em 27/09/2026)

**Sprint 1 (14/09–27/09): concluída.** Importação (US01), estatísticas de referência
(US02), base do sistema e base sintética prontas. A subida completa com `docker compose up`
foi testada no Codespace (é preciso um contorno de firewall, descrito no README).

**Sprint 2 (28/09–11/10): adiantada e concluída em 23/09.** Fluxo de análise definido
([`FLUXO_ANALISE.md`](FLUXO_ANALISE.md)); Z-score, IQR e regra contextual implementados;
análise pela tela, pela API e por comando; lista e detalhe de alertas (US06).

**Sprint 3 (12/10–25/10): em andamento, adiantada.** Revisão e parecer (US07/US08)
concluídos em 25/09. Isolation Forest (US04) e experimento com os quatro métodos
concluídos em 25/09 (seeds 42 e 7). **A S3 está concluída.**

**Sprint 4 (26/10–02/11): adiantada, em andamento.** Dashboard (US09) concluído em 26/09; filtros (US10), parâmetros (US12), gerenciamento de usuários e job de reprocessamento em 27/09; relatório mensal (US11) em CSV também em 27/09. **Todas as histórias do backlog estão implementadas**, incluindo o PDF do relatório.

| Área | Situação |
|---|---|
| Modelo de dados e migrations | ✅ Pronto, com imutabilidade do parecer (eventos + trigger) |
| Autenticação e perfis | ✅ Login, logout, `perfil_requerido`, CSRF, gerenciamento de usuários pelo administrador |
| Infraestrutura | ✅ `docker compose up` testado no Codespace (db, app e agendador): migrations, admin, login, `seed-base`, job e testes no container |
| Base sintética | ✅ Gerador, carga no banco (`flask seed-base`) e calendário de feriados |
| Importação e estatísticas (US01, US02) | ✅ CSV/XLSX com erros por linha, cadastro manual, API, telas e estatísticas recalculadas a cada importação |
| Motor de detecção | ✅ Z-score, IQR, contextual, Isolation Forest e consolidador |
| Telas de alertas, revisão e dashboard | ✅ Análises, lista de alertas com filtros combináveis, detalhe, parecer com histórico, dashboard |
| Experimento | ✅ `metricas.csv` com os quatro métodos, seeds 42 e 7 |
| Testes | 409 passando (SQLite + PostgreSQL) |

**Próximo passo:** recriar o banco limpo antes da apresentação e testar com Docker Desktop. O restante do Fechamento está pronto.

---

## Marcos e prazos

| Data | Marco | Quem depende | Situação |
|---|---|---|---|
| 25/09 | Modelo de dados estável, refletido em `classes.puml` | Documentação: diagrama de classes (27/09) | ✅ |
| 27/09 | **Fim da S1:** US01, US02 e subida com Docker Compose | — | ✅ (23/09) |
| 01/10 | Fluxo "executar análise → gerar alertas → registrar parecer" implementado ou, no mínimo, definido | Documentação: diagramas de sequência e arquitetura (03/10) | ✅ definido; análise e alertas implementados (23/09) |
| 11/10 | **Fim da S2:** Z-score, IQR, contextual e lista de alertas com motivo | — | ✅ (23/09) |
| 18/10 | `experimentos/resultados/metricas.csv` gerado por script, com seed e parâmetros | Artigo: resultados (25/10) | ✅ (25/09) |
| 25/10 | **Fim da S3:** Isolation Forest, experimento, revisão e parecer | — | ✅ (25/09) |
| 02/11 | **Entrega final:** software funcionando, com código e base de dados | Orientador | ⬜ (todas as histórias implementadas em 27/09; falta o Fechamento) |

---

## Sprint 1 — 14/09 a 27/09

### Feito
- [x] Modelo de dados completo (8 entidades) com migration inicial e teste de sincronia modelo × migration
- [x] Imutabilidade do `Parecer` em duas camadas: eventos do SQLAlchemy e trigger no PostgreSQL (RNF02)
- [x] Login com senha em hash, perfis `auditor` e `administrador` e decorador `perfil_requerido` (RNF03)
- [x] Aviso de que alertas são indícios, visível em todas as páginas (RNF04)
- [x] Docker Compose, entrypoint (migrations + admin inicial) (RNF07)
- [x] Diagrama de classes (`docs/diagramas/classes.puml`)
- [x] Base sintética: 5.000 despesas, 5 tipos de anomalia rotulados, seed fixa (RNF06)
- [x] Carga da base no banco: `flask seed-base`, opcional na subida
- [x] Calendário de feriados nacionais (`motor/calendario.py`)

- [x] **US01: importação de CSV/XLSX** (`app/servicos/importacao.py`)
  - valida os 6 campos obrigatórios e registra os erros por linha em `LoteImportacao.erros`
  - aceita CSV com `,` e `.` e também o formato do Excel brasileiro (`;` e `,`)
  - importa as linhas válidas e informa as inválidas, sem abortar o lote inteiro
  - `POST /api/despesas/importar` e `GET /api/despesas`
  - tela de upload com o resumo de erros por linha
  - `flask seed-base` passa a usar esse serviço
- [x] **US01: cadastro manual de despesa** (formulário web, despesa sem lote)
- [x] **US02: estatísticas de referência** (`motor/estatisticas.py` + `app/servicos/estatisticas.py`)
  - média, desvio, Q1, Q3 e n por categoria, conta contábil e centro de custo
  - recalculadas automaticamente após cada importação e cadastro (substituem as anteriores)
  - tela de estatísticas e comando `flask recalcular-estatisticas`

- [x] **`docker compose up` testado no Codespace**: migrations, admin inicial, login, `GET /api/saude`,
  `flask seed-base` e os 157 testes dentro do container. O tráfego entre containers precisou de um
  contorno de firewall do Codespace (seção "Problema conhecido" do README)

---

## Sprint 2 — 28/09 a 11/10

- [x] **Até 01/10: definir o fluxo de análise** para a equipe de documentação: feito em 23/09
  em [`FLUXO_ANALISE.md`](FLUXO_ANALISE.md), registrado nos itens 11 e 12 de `MUDANCAS_PARA_DOCUMENTACAO.md`
- [x] **US03: Z-score por categoria** (`motor/zscore.py`): score = |z|, sinaliza acima do limiar (padrão 3), motivo do tipo "valor 4,2x acima da média da categoria Viagens"
- [x] **US03: IQR por categoria** (`motor/iqr.py`): fator 1,5, score em IQRs além do quartil, motivo com os limites do grupo
- [x] **US05: regra contextual** (`motor/contextual.py`): combinação categoria × conta × centro de custo inexistente ou com frequência < 1% dentro da categoria
- [x] **Consolidador** (`motor/consolidador.py`): `executar_detectores` (resultado completo, para o experimento) e `consolidar` (só os sinalizados)
- [x] **Serviço de análise** (`servicos/analise.py`): carrega despesas → roda o motor → grava `ExecucaoAnalise` (parâmetros e seed) e os `AlertaAnomalia` (RF12, RNF06), sem repetir alerta de despesa + método
- [x] `POST /api/analises`, `GET /api/analises/{id}`, botão "Executar análise" na tela e `flask executar-analise`
- [x] **US06: lista de alertas** (tela e `GET /api/alertas`, `GET /api/alertas/{id}`) com score, método e motivo, filtro por status e método, e tela de detalhe. Adiantada da S4 (decisão de 23/09)
- [x] Testes do motor com dados pequenos e controlados, mais um teste com a base sintética

## Sprint 3 — 12/10 a 25/10

- [x] **US04: Isolation Forest** (`motor/isolation_forest.py`), conforme [`ISOLATION_FOREST.md`](ISOLATION_FOREST.md)
  - atributos derivados: valor, dia da semana, feriado (`motor/calendario.py`), repetições por funcionário e valor, proximidade de um limite
  - `contamination=0.05` e `random_state=42`
- [x] **Experimento** (`experimentos/avaliar_metodos.py`), **até 18/10**
  - [x] gera a base (seed 42) ou lê o CSV e roda o motor direto, sem banco
  - [x] precisão, recall, F1 e taxa de FP por método, por combinação (união e votação) e por tipo de anomalia
  - [x] grava `experimentos/resultados/metricas.csv` com seed e parâmetros (25/09)
  - [x] incluir o Isolation Forest e gerar os resultados com as seeds 42 e 7 (25/09)
  - entregar à equipe do artigo só números gerados pelo script
- [x] **US07/US08: revisão e parecer**, adiantada da S4 (decisão de 23/09); concluída em 25/09
  - `servicos/revisao.py`: insere o `Parecer` e atualiza `status_revisao`
  - observação obrigatória para `irregular` e `necessita_justificativa`
  - `POST /api/alertas/{id}/parecer` e tela de detalhe do alerta com o histórico de pareceres (RF12)

## Sprint 4 — 26/10 a 02/11 (uma semana só)

- [x] **US09: dashboard**: total de despesas, total sinalizado, % sinalizado, alertas por status (Chart.js); `GET /api/dashboard` (26/09)
- [x] **US10: filtros combináveis** na lista de alertas: período, categoria, conta, centro de custo, funcionário, status e método (27/09; período = data da despesa)
- [x] **US12: parâmetros dos métodos** (admin): `GET`/`PUT /api/parametros`, tela com validação (27/09; auditor vê, administrador altera)
- [x] **Gerenciamento de usuários** (admin): criar, desativar, trocar perfil (seção 4 do CLAUDE.md) (27/09)
- [x] **Job do APScheduler**: reprocessa despesas novas (`executada_por` vazio), no container `agendador` (27/09)
- [x] **US11: relatório mensal** (Could): total analisado, anomalias e taxa de confirmação = irregular ÷ (aprovado + irregular) (item 18 de `MUDANCAS_PARA_DOCUMENTACAO.md`); `GET /api/relatorios/mensal` em CSV (27/09)
  - [x] PDF (27/09, com `reportlab`)

## Fechamento (até 02/11)

- [x] `docker compose up` do zero, num clone limpo, sobe tudo e carrega a base (27/09). Revelou e corrigiu: o `agendador` rodava antes das migrations (agora espera o `app` saudável); documentado o erro com `umask` restritiva no Linux
- [x] README revisado: início rápido em 4 comandos, testes e experimento pelo Docker, situação das sprints, validação atualizada (27/09)
- [x] `.env.example` atualizado; nenhuma credencial no repositório nem no histórico (27/09)
- [x] `MUDANCAS_PARA_DOCUMENTACAO.md` e `classes.puml` alinhados com o código final: atributos, associações (as 8 chaves estrangeiras) e enums conferidos automaticamente (27/09)
- [x] Roteiro de demonstração em [`ROTEIRO_DEMONSTRACAO.md`](ROTEIRO_DEMONSTRACAO.md), com arquivo de exemplo `dados/exemplos/importacao_demonstracao.csv` e números conferidos numa execução real (27/09)
- [ ] Recriar o banco de desenvolvimento limpo antes da apresentação (seção 1 do roteiro de demonstração)
- [ ] Testar `docker compose up` com Docker Desktop (Windows ou Mac) de alguém da equipe

---

## Riscos e pontos de atenção

| Risco | Mitigação |
|---|---|
| S4 tem uma semana e muitas histórias | Lista de alertas adiantada para a S2 e revisão/parecer para a S3. US11 (Could) é a primeira a sair se faltar tempo |
| Prazo de 01/10 para o fluxo de análise cai no começo da S2 | Definir as assinaturas dos serviços antes de implementar os detectores |
| `docker compose up` só foi testado no Codespace | Repetir num clone limpo e, se possível, com Docker Desktop no Fechamento |
| Isolation Forest pode detectar mal duplicidade e fracionamento | O experimento mostra isso por tipo de anomalia; o resultado é reportado, não é meta |

---

## Histórico

| Data | Mudança |
|---|---|
| 23/09/2026 | Roteiro criado. S1: base do sistema e base sintética prontas; US01 e US02 abertas. Proposta de adiantar a lista de alertas (S2) e a revisão/parecer (S3). |
| 23/09/2026 | Equipe aprovou o novo plano: US06 na S2, US07/US08 na S3; US11 é a primeira a sair se faltar tempo. |
| 23/09/2026 | US01 e US02 concluídas (importação CSV/XLSX, cadastro manual, API, telas, estatísticas). Base sintética passou para 01/09/2025–31/08/2026, porque a importação recusa datas futuras. 157 testes. |
| 23/09/2026 | `docker compose up` testado no Codespace; S1 concluída. Documentado no README o contorno do firewall (`iptables-legacy`) que bloqueava o tráfego entre os containers. |
| 23/09/2026 | Fluxo de análise definido e aprovado (`FLUXO_ANALISE.md`): Z-score e IQR por categoria, frequência contextual dentro da categoria, sem alerta repetido por despesa + método, grupo mínimo de 10. Item de 01/10 concluído. |
| 23/09/2026 | S2 concluída antes do início: Z-score, IQR, contextual, consolidador, serviço de análise, API, comando e telas de análises e alertas (US03, US05, US06). Validado no Docker com a base sintética. 226 testes. |
| 25/09/2026 | US07/US08 concluídas: `servicos/revisao.py`, `POST /api/alertas/{id}/parecer` e formulário de parecer no detalhe do alerta, com histórico. Próximo: experimento antes do Isolation Forest. 250 testes. |
| 25/09/2026 | Experimento rodando com Z-score, IQR e contextual: `metricas.csv`, `metricas_por_tipo.csv` e `execucao.json` versionados em `experimentos/resultados/`. Metodologia registrada no item 13 de `MUDANCAS_PARA_DOCUMENTACAO.md`. 258 testes. |
| 25/09/2026 | Isolation Forest implementado (atributos derivados, parâmetro `limite_aprovacao`, motivo pelos atributos ativos) e gerador corrigido (valor novo nas combinações incompatíveis e fins de semana). Experimento gerado de novo com os quatro métodos, seeds 42 e 7. S3 concluída. 272 testes. |
| 26/09/2026 | Definidos o significado dos status de revisão e a fórmula da taxa de confirmação (irregular ÷ (aprovado + irregular)); itens 17 e 18 de `MUDANCAS_PARA_DOCUMENTACAO.md` e seção 4 de `FLUXO_ANALISE.md`. |
| 26/09/2026 | US09 concluída: dashboard na página inicial e `GET /api/dashboard` (item 19 de `MUDANCAS_PARA_DOCUMENTACAO.md`). 281 testes. |
| 27/09/2026 | US10 concluída: filtros combináveis na tela de alertas e em `GET /api/alertas` (item 20 de `MUDANCAS_PARA_DOCUMENTACAO.md`). 302 testes. |
| 27/09/2026 | US12 concluída: tela e API de parâmetros com validação de faixa (item 21 de `MUDANCAS_PARA_DOCUMENTACAO.md`). 329 testes. |
| 27/09/2026 | Gerenciamento de usuários concluído: tela do administrador para criar, trocar perfil, desativar e reativar (item 22 de `MUDANCAS_PARA_DOCUMENTACAO.md`). 346 testes. |
| 27/09/2026 | Job de reprocessamento concluído, em container próprio `agendador` (item 23 de `MUDANCAS_PARA_DOCUMENTACAO.md`: muda os diagramas de arquitetura e implantação). 355 testes. |
| 27/09/2026 | US11 concluída em CSV: tela e `GET /api/relatorios/mensal` (item 24 de `MUDANCAS_PARA_DOCUMENTACAO.md`). Todas as histórias implementadas. 375 testes. |
| 27/09/2026 | Filtros da tela de alertas e escolha do mês do relatório passam a ser aplicados ao mudar o campo, sem botão (o botão fica só para quem estiver sem JavaScript). 378 testes. |
| 27/09/2026 | Relatório mensal também em PDF (item 25 de `MUDANCAS_PARA_DOCUMENTACAO.md`), com o aviso de indício. 382 testes. |
| 27/09/2026 | Taxa de confirmação passa a mostrar a amostra, ex.: "66,67% (2 de 3)" (item 26 de `MUDANCAS_PARA_DOCUMENTACAO.md`). 383 testes. |
| 27/09/2026 | Fechamento: clone limpo validado (e corrigida a ordem de subida do `agendador`), README revisado, credenciais e diagrama de classes conferidos, roteiro de demonstração escrito. Pendentes: banco limpo e teste com Docker Desktop. 384 testes. |
| 28/09/2026 | Nova aparência da interface (identidade visual, login, menu agrupado, dashboard, alertas no celular, detalhe em duas colunas com contexto da categoria), conferida com capturas de tela; item 29 de `MUDANCAS_PARA_DOCUMENTACAO.md`. 386 testes. |
| 07/10/2026 | Configuração de produção para VPS (Nginx + HTTPS + gunicorn) e guia `docs/IMPLANTACAO.md`, testados no Docker com proxy simulado; item 30 de `MUDANCAS_PARA_DOCUMENTACAO.md`. Corrigida uma corrida entre o job e a análise manual (o job criava uma análise vazia). 398 testes. |
| 08/10/2026 | Ordenação da lista de alertas por data e valor, crescente e decrescente (item 31 de `MUDANCAS_PARA_DOCUMENTACAO.md`). 409 testes. |
