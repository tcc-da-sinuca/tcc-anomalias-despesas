# Roteiro até a entrega final (02/11/2026)

Caminho do software do TCC, do estado atual até a entrega. Cada item aponta o
requisito (RF/US) e o critério para considerá-lo pronto.

**Como usar:** marque `[x]` quando o item estiver no `main` com testes passando.
Ao concluir ou replanejar algo, atualize a seção "Situação atual" e registre a
mudança no histórico, no fim do arquivo. Decisões que afetam a documentação
entregue continuam indo para [`MUDANCAS_PARA_DOCUMENTACAO.md`](MUDANCAS_PARA_DOCUMENTACAO.md).

---

## Situação atual (atualizado em 23/09/2026)

**Sprint 1 (14/09–27/09): histórias concluídas.** Importação (US01) e estatísticas de
referência (US02) prontas, além da base do sistema e da base sintética. Na S1 só falta
testar o `docker compose up` num ambiente com Docker.

| Área | Situação |
|---|---|
| Modelo de dados e migrations | ✅ Pronto, com imutabilidade do parecer (eventos + trigger) |
| Autenticação e perfis | ✅ Login, logout, `perfil_requerido`, CSRF |
| Infraestrutura | ✅ Docker Compose e entrypoint escritos · ⚠️ `docker compose up` ainda não testado num ambiente com Docker |
| Base sintética | ✅ Gerador, carga no banco (`flask seed-base`) e calendário de feriados |
| Importação e estatísticas (US01, US02) | ✅ CSV/XLSX com erros por linha, cadastro manual, API, telas e estatísticas recalculadas a cada importação |
| Motor de detecção | ⬜ Contrato, calendário e estatísticas por grupo (base para Z-score e IQR) |
| Telas de alertas, revisão e dashboard | ⬜ Existem as telas de despesas, importação e estatísticas; alertas ainda não |
| Experimento | ⬜ Não iniciado |
| Testes | 157 passando (SQLite + PostgreSQL) |

**Próximo passo:** definir o fluxo de análise até 01/10 (prazo da documentação) e começar Z-score e IQR (S2).

---

## Marcos e prazos

| Data | Marco | Quem depende | Situação |
|---|---|---|---|
| 25/09 | Modelo de dados estável, refletido em `classes.puml` | Documentação: diagrama de classes (27/09) | ✅ |
| 27/09 | **Fim da S1:** US01 e US02 | — | ✅ (23/09) |
| 01/10 | Fluxo "executar análise → gerar alertas → registrar parecer" implementado ou, no mínimo, definido | Documentação: diagramas de sequência e arquitetura (03/10) | ⬜ |
| 11/10 | **Fim da S2:** Z-score, IQR, contextual e lista de alertas com motivo | — | ⬜ |
| 18/10 | `experimentos/resultados/metricas.csv` gerado por script, com seed e parâmetros | Artigo: resultados (25/10) | ⬜ |
| 25/10 | **Fim da S3:** Isolation Forest, experimento, revisão e parecer | — | ⬜ |
| 02/11 | **Entrega final:** software funcionando, com código e base de dados | Orientador | ⬜ |

---

## Sprint 1 — 14/09 a 27/09

### Feito
- [x] Modelo de dados completo (8 entidades) com migration inicial e teste de sincronia modelo × migration
- [x] Imutabilidade do `Parecer` em duas camadas: eventos do SQLAlchemy e trigger no PostgreSQL (RNF02)
- [x] Login com senha em hash, perfis `auditor` e `administrador` e decorador `perfil_requerido` (RNF03)
- [x] Aviso de que alertas são indícios, visível em todas as páginas (RNF04)
- [x] Docker Compose, entrypoint (migrations + admin inicial) e devcontainer (RNF07)
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

### Falta
- [ ] Rodar `docker compose up` no Codespace e corrigir o que falhar

---

## Sprint 2 — 28/09 a 11/10

- [ ] **Até 01/10: definir o fluxo de análise** para a equipe de documentação
  - assinaturas de `servicos/analise.py` e `servicos/revisao.py` e do `motor/consolidador.py`
  - avisar a documentação e registrar em `MUDANCAS_PARA_DOCUMENTACAO.md`
- [ ] **US03: Z-score por grupo** (`motor/zscore.py`): score = |z|, sinaliza acima do limiar (padrão 3), motivo do tipo "valor 4,2x acima da média da categoria Viagens"
- [ ] **US03: IQR por grupo** (`motor/iqr.py`): fator 1,5, motivo com os limites do grupo
- [ ] **US05: regra contextual** (`motor/contextual.py`): combinação categoria × conta × centro de custo inexistente ou com frequência < 1%
- [ ] **Consolidador** (`motor/consolidador.py`): junta os detectores e gera os dados dos alertas
- [ ] **Serviço de análise** (`servicos/analise.py`): carrega despesas → roda o motor → grava `ExecucaoAnalise` (parâmetros e seed) e os `AlertaAnomalia` (RF12, RNF06)
- [ ] `POST /api/analises`, `GET /api/analises/{id}` e botão "Executar análise" na tela
- [ ] **US06: lista de alertas** (tela e `GET /api/alertas`, `GET /api/alertas/{id}`) com score, método e motivo. Adiantada da S4 (decisão de 23/09)
- [ ] Testes do motor com dados pequenos e controlados, mais um teste com a base sintética

## Sprint 3 — 12/10 a 25/10

- [ ] **US04: Isolation Forest** (`motor/isolation_forest.py`)
  - atributos derivados: valor, dia da semana, feriado (`motor/calendario.py`), repetições por funcionário e valor, proximidade de um limite
  - `contamination=0.05` e `random_state=42`
- [ ] **Experimento** (`experimentos/avaliar_metodos.py`), **até 18/10**
  - lê o CSV da base sintética e roda o motor direto, sem banco
  - precisão, recall, F1 e taxa de FP por método, por combinação de métodos e por tipo de anomalia
  - grava `experimentos/resultados/metricas.csv` com seed e parâmetros
  - entregar à equipe do artigo só números gerados pelo script
- [ ] **US07/US08: revisão e parecer**, adiantada da S4 (decisão de 23/09)
  - `servicos/revisao.py`: insere o `Parecer` e atualiza `status_revisao`
  - observação obrigatória para `irregular` e `necessita_justificativa`
  - `POST /api/alertas/{id}/parecer` e tela de detalhe do alerta com o histórico de pareceres (RF12)

## Sprint 4 — 26/10 a 02/11 (uma semana só)

- [ ] **US09: dashboard**: total de despesas, total sinalizado, % sinalizado, alertas por status (Chart.js); `GET /api/dashboard`
- [ ] **US10: filtros combináveis** na lista de alertas: período, categoria, conta, centro de custo, funcionário, status e método
- [ ] **US12: parâmetros dos métodos** (admin): `GET`/`PUT /api/parametros`, tela com validação
- [ ] **Gerenciamento de usuários** (admin): criar, desativar, trocar perfil (seção 4 do CLAUDE.md)
- [ ] **Job do APScheduler**: reprocessa despesas novas (`executada_por` vazio)
- [ ] **US11: relatório mensal** (Could): total analisado, anomalias e taxa de confirmação; `GET /api/relatorios/mensal` em CSV (PDF se der tempo)

## Fechamento (até 02/11)

- [ ] `docker compose up` do zero, num clone limpo, sobe tudo e carrega a base
- [ ] README revisado: subir, rodar migrations, carregar a base, rodar testes e o experimento
- [ ] `.env.example` atualizado; nenhuma credencial no repositório
- [ ] `MUDANCAS_PARA_DOCUMENTACAO.md` e `classes.puml` alinhados com o código final
- [ ] Roteiro de demonstração: importar → analisar → revisar → dashboard → relatório

---

## Riscos e pontos de atenção

| Risco | Mitigação |
|---|---|
| S4 tem uma semana e muitas histórias | Lista de alertas adiantada para a S2 e revisão/parecer para a S3. US11 (Could) é a primeira a sair se faltar tempo |
| Prazo de 01/10 para o fluxo de análise cai no começo da S2 | Definir as assinaturas dos serviços antes de implementar os detectores |
| `docker compose up` nunca foi executado | Testar no Codespace ainda na S1 |
| Isolation Forest pode detectar mal duplicidade e fracionamento | O experimento mostra isso por tipo de anomalia; o resultado é reportado, não é meta |

---

## Histórico

| Data | Mudança |
|---|---|
| 23/09/2026 | Roteiro criado. S1: base do sistema e base sintética prontas; US01 e US02 abertas. Proposta de adiantar a lista de alertas (S2) e a revisão/parecer (S3). |
| 23/09/2026 | Equipe aprovou o novo plano: US06 na S2, US07/US08 na S3; US11 é a primeira a sair se faltar tempo. |
| 23/09/2026 | US01 e US02 concluídas (importação CSV/XLSX, cadastro manual, API, telas, estatísticas). Base sintética passou para 01/09/2025–31/08/2026, porque a importação recusa datas futuras. 157 testes. |
