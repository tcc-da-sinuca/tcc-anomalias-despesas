# CLAUDE.md — Software de Detecção de Anomalias em Despesas Corporativas

> Contexto do projeto para o Claude Code. Idioma de trabalho: **português do Brasil**.
> Este repositório contém o **software** do TCC (Engenharia de Computação, 2026/2, Tema 49).

---

## 1. O que estamos construindo

Uma aplicação web que:
1. importa lançamentos de despesas corporativas;
2. detecta anomalias com Z-score, IQR, Isolation Forest e regras contextuais;
3. gera alertas com score, método e motivo legível;
4. permite que um auditor revise, classifique e registre um parecer sobre cada alerta.

**Problema:** a auditoria interna em PMEs é manual e amostral e deixa passar despesas incomuns ou fraudulentas.

**Princípio inegociável:** o alerta é um **indício estatístico, não uma acusação**. A
interface deve deixar isso claro e sempre exigir revisão humana.
**Exceção decidida pela equipe (08/10/2026):** na aprovação prévia, uma despesa com alerta
de gravidade crítica (Z-score ou IQR) é rejeitada automaticamente; quem lançou pode
encaminhar o pedido, que volta como prioritário para decisão humana (item 34 de
`docs/MUDANCAS_PARA_DOCUMENTACAO.md`).

**Prazo final:** software funcionando, com código e base de dados, até **02/11/2026**.

**Regra do orientador:** plágio de código é proibido. Não copie projetos prontos. Bibliotecas são permitidas.

---

## 2. Stack

- **Python 3.11+**
- **Detecção:** pandas, numpy, scikit-learn (`IsolationForest`)
- **Backend:** Flask (Blueprints) + SQLAlchemy 2 (via Flask-SQLAlchemy) + Alembic (via Flask-Migrate)
- **Banco:** PostgreSQL 16
- **Front-end:** Jinja2 + Bootstrap + Chart.js (manter simples)
- **Autenticação:** Flask-Login com senhas em hash; CSRF com Flask-WTF
- **Jobs:** APScheduler para reprocessar despesas novas, num container próprio (`agendador`, comando `flask agendador`)
- **Infra:** Docker Compose (app + agendador + postgres). O projeto precisa rodar localmente com um comando documentado no README.
- **Testes:** pytest. Por padrão em SQLite em memória; os testes marcados `postgres` usam `TEST_DATABASE_URL`.

---

## 3. Funcionalidades (requisitos já definidos na documentação)

| ID | Funcionalidade | Prioridade | Sprint |
|---|---|---|---|
| RF01 / US01 | Importar (CSV/XLSX) ou cadastrar despesas. Campos obrigatórios: valor, data, categoria, conta contábil, centro de custo, funcionário. Exibir erros de importação por linha. | Must | 1 |
| RF02 / US02 | Calcular estatísticas de referência (média, desvio, Q1, Q3, n) por categoria, conta e centro de custo. Recalcular após nova importação. | Must | 1 |
| RF03 / US03 | Z-score e IQR por grupo. Score numérico por despesa e sinalização acima do limiar. | Must | 2 |
| RF05 / US05 | Regras contextuais: combinação categoria × conta × centro de custo rara ou inexistente no histórico. | Must | 2 |
| RF04 / US04 | Isolation Forest multivariado, com score por despesa. | Should | 3 |
| RF04 / US06 | Lista de alertas com score, método e ao menos um motivo textual. | Must | 2 |
| RF06-07 / US07 | Classificar alerta: `aprovado`, `irregular`, `necessita_justificativa`. | Must | 3 |
| RF08 / US08 | Parecer obrigatório quando o status for `irregular` ou `necessita_justificativa`. | Should | 3 |
| RF09 / US09 | Dashboard: total de despesas, total sinalizado, % sinalizado, alertas por status. | Must | 4 |
| RF10 / US10 | Filtros combináveis: período, categoria, conta, centro de custo, funcionário, status, método. | Should | 4 |
| RF11 / US11 | Relatório mensal exportável: total analisado, anomalias e taxa de confirmação de irregularidade. | Could | 4 |
| RF12 | Histórico completo de análises e pareceres. | Must | 2–4 |
| RF13 / US12 | Administrador configura os parâmetros dos métodos, com validação dos valores. | Could | 4 |
| Novo (08/10) | Aprovação prévia: despesa lançada fora do padrão vira pedido para o administrador; crítica é rejeitada automaticamente e pode ser encaminhada com prioridade. Fora dos RFs entregues. | — | pós-S4 |

**Sprints:** S1 14/09–27/09 · S2 28/09–11/10 · S3 12/10–25/10 · S4 26/10–02/11.
A S4 tem só uma semana e muitas histórias. **Antecipe a tela de alertas e o fluxo de revisão sempre que possível.**
Decisão da equipe (23/09): US06 foi para a S2 e US07/US08 para a S3; se faltar tempo na S4, a US11 é a primeira a sair.

### Requisitos não funcionais (texto da documentação entregue)
- **RNF01 Desempenho:** o processamento deverá ser eficiente para o volume de dados definido no projeto.
- **RNF02 Auditabilidade:** pareceres imutáveis, com usuário e timestamp. Somente inserção, sem update nem delete.
- **RNF03 Segurança:** só usuários autenticados acessam o sistema. Controle por perfil.
- **RNF04 Confiabilidade:** aviso visível de que os alertas são indícios.
- **RNF05 Usabilidade:** motivos em linguagem simples (ex.: "valor 4,2x acima da média da categoria Viagens").
- **RNF06 Reprodutibilidade:** seeds fixas, parâmetros de cada execução registrados.
- **RNF07 Portabilidade:** execução local documentada via Docker Compose.

Não há metas numéricas de desempenho nem de taxa de falsos positivos (decisão da equipe,
ver `docs/MUDANCAS_PARA_DOCUMENTACAO.md`). As métricas do experimento são reportadas, não usadas como meta.

---

## 4. Atores e perfis

- `auditor`: importa, executa análises, revisa e classifica alertas, vê dashboard e relatórios.
- `administrador`: tudo o que o auditor faz, mais a configuração dos parâmetros dos métodos e o gerenciamento de usuários.

Não existe perfil `gestor` (decisão da equipe). Use `perfil_requerido(...)` de
`app/rotas/autorizacao.py` para restringir rotas; o administrador sempre passa.

---

## 5. Modelo de dados

Implementado em `app/models/` e refletido em `docs/diagramas/classes.puml`.

- `Usuario`: id, nome, email, senha_hash, perfil, ativo
- `LoteImportacao`: id, nome_arquivo, importado_por, importado_em, total_linhas, linhas_validas, erros (JSON)
- `Despesa`: id, valor (Numeric), data, categoria, conta_contabil, centro_custo, funcionario, descricao, lote_id (opcional: cadastro manual), situacao (`valida`|`pendente`|`rejeitada`; só válidas são histórico)
- `EstatisticaReferencia`: id, dimensao, chave, media, desvio, q1, q3, n, calculada_em (única por dimensao + chave)
- `ExecucaoAnalise`: id, iniciada_em, duracao_s, parametros (JSON), seed, total_despesas, total_alertas, executada_por (opcional: job agendado)
- `AlertaAnomalia`: id, despesa_id, execucao_id, metodo (`zscore`|`iqr`|`isolation_forest`|`contextual`), score, motivo, excesso, gravidade (`leve`|`moderada`|`alta`|`critica`), status_revisao (padrão `pendente`), criado_em
- `Parecer`: id, alerta_id, usuario_id, status, observacao, criado_em (**somente inserção**: eventos do SQLAlchemy + trigger no PostgreSQL)
- `ParametroMetodo`: metodo, chave (chave primária composta), valor, alterado_por, alterado_em
- `SolicitacaoAprovacao`: id, despesa_id (única), solicitada_por, criada_em, status (`pendente`|`aprovada`|`rejeitada`|`rejeitada_automaticamente`), gravidade, prioritaria, decidida_por, decidida_em, justificativa
- `EventoSolicitacao`: id, solicitacao_id, tipo, usuario_id (vazio = sistema), observacao, criado_em (**somente inserção**, como o parecer)

Valores de domínio (perfis, métodos, status, parâmetros padrão) ficam em `app/models/dominio.py`.

Parâmetros padrão: Z-score com |z| > 3; IQR com fator 1,5; Isolation Forest com
`contamination=0.05`, `random_state=42` e `limite_aprovacao=1000` (R$, para detectar fracionamento); contextual com frequência mínima da combinação < 1% ou combinação inexistente.

---

## 6. Arquitetura

Em camadas, seguindo o padrão *Coletor de eventos + Motor de regras/alertas*:

```
Apresentação (Jinja2)  →  Rotas Flask / API REST  →  Serviços  →  Motor de detecção
                                                         ↓
                                                  Repositórios (SQLAlchemy) → PostgreSQL
```

- O **motor fica desacoplado do Flask e do banco**. Cada detector é uma função ou classe pura
  que recebe um `DataFrame` e retorna `DataFrame[despesa_id, score, sinalizado, motivo]`.
- Um `consolidador` junta os resultados dos detectores e gera os `AlertaAnomalia`.
- Os serviços orquestram: carregar despesas → rodar o motor → persistir a execução e os alertas.
- **Referência dos métodos:** histórico do centro de custo × conta contábil, com recuo para a
  categoria quando o grupo tem menos de 10 despesas. A gravidade de cada alerta (`motor/gravidade.py`)
  mede quanto o score passou do limite do método.
- **Tipos de anomalia × métodos:** duplicidade, fracionamento e lançamento em fim de semana/feriado
  são cobertos pelo Isolation Forest com atributos derivados (dia da semana, feriado, repetições por
  funcionário). O método contextual trata só de categoria × conta × centro de custo.

### Endpoints
```
POST /api/despesas/importar      GET  /api/despesas
POST /api/analises               GET  /api/analises/{id}
GET  /api/alertas?filtros...     GET  /api/alertas/{id}
POST /api/alertas/{id}/parecer   GET  /api/dashboard
GET  /api/relatorios/mensal?ano=&mes=&formato=csv|pdf
GET  /api/parametros             PUT  /api/parametros   (admin)
GET  /api/solicitacoes           GET  /api/solicitacoes/{id}
POST /api/solicitacoes/{id}/aprovar|rejeitar (admin)    POST /api/solicitacoes/{id}/encaminhar
```
Já existem: `GET /api/saude` (verificação de saúde) e `GET /api/usuario-atual`.

### Estrutura de pastas
```
app/
  __init__.py          # create_app()
  config.py  extensoes.py  cli.py  formularios.py  filtros.py
  models/              # entidades SQLAlchemy + dominio.py
  repositorios/
  servicos/            # importacao, analise, revisao, relatorio, usuarios, parametros
  rotas/               # blueprints: api, web, auth (+ autorizacao.py)
  templates/  static/
motor/
  calendario.py  estatisticas.py  zscore.py  iqr.py  isolation_forest.py  contextual.py  consolidador.py
dados/
  gerar_base_sintetica.py   # base realista + anomalias injetadas e rotuladas
  seed_banco.py
experimentos/
  avaliar_metodos.py        # precisão, recall, F1, taxa de FP por método
migrations/
tests/
  test_models/  test_motor/  test_servicos/  test_api/
docs/
  ROTEIRO.md  MUDANCAS_PARA_DOCUMENTACAO.md  diagramas/
docker-compose.yml  Dockerfile  .env.example  README.md
```

---

## 7. Base de dados sintética e avaliação

O software precisa entregar uma **base de dados** junto com o código. Por isso:
- `dados/gerar_base_sintetica.py` gera despesas realistas: categorias como Viagens,
  Alimentação, Material de escritório, Software, Hospedagem, Combustível e Treinamentos;
  vários centros de custo e funcionários; sazonalidade; distribuições log-normais por categoria.
- O gerador **injeta anomalias rotuladas** com a coluna `anomalia_real` e o tipo da anomalia:
  valor extremo, combinação categoria/conta/CC incompatível, despesa duplicada, fracionamento
  logo abaixo de um limite e lançamento em fim de semana ou feriado.
- `experimentos/avaliar_metodos.py` compara os métodos e as combinações entre eles usando
  precisão, recall, F1 e taxa de falsos positivos. A seed deve ser fixa.

---

## 8. Entregáveis para a equipe de documentação e artigo

Outra parte da equipe escreve a documentação e o artigo. Eles dependem do que é produzido aqui.

| Data interna | O que entregar | Para quê |
|---|---|---|
| **25/09/2026** | Modelo de dados (seção 5) estável e refletido nos modelos SQLAlchemy ✅ | Diagrama de classes (entrega em 27/09) |
| **01/10/2026** | Arquitetura (seção 6) e o fluxo "executar análise → gerar alertas → registrar parecer" implementados ou, no mínimo, definidos | Diagrama de sequência e arquitetura (entrega em 03/10) |
| **18/10/2026** | `experimentos/avaliar_metodos.py` rodando e gerando `experimentos/resultados/metricas.csv` com precisão, recall, F1 e taxa de FP por método, além de seed e parâmetros usados | Resultados do artigo (entrega em 25/10) |

**Regras para o Claude Code:**
- Ao alterar uma entidade, um relacionamento, um endpoint ou o fluxo entre camadas, **avise
  explicitamente** que a mudança afeta os diagramas. Registre-a em `docs/MUDANCAS_PARA_DOCUMENTACAO.md`
  com data, o que mudou e qual diagrama ou seção é afetado. Atualize também `docs/diagramas/classes.puml`.
- Mudou um modelo? Gere a migration (`flask db migrate -m "..."`), revise e rode os testes: o teste
  `test_migrations_refletem_modelos` acusa modelos e migrations dessincronizados.
- Mantenha `docs/ROTEIRO.md` atualizado: ao concluir ou replanejar um item, marque-o, atualize
  a seção "Situação atual" e registre a mudança no histórico do arquivo.
- Os resultados de experimentos são sempre gerados por script, com seed fixa. Nunca informe
  números de desempenho que não tenham saído de uma execução real.

---

## 9. Convenções

- Nomes de domínio em **português sem acento** (`despesa`, `centro_custo`, `AlertaAnomalia`). Termos técnicos consagrados podem ficar em inglês (`score`, `seed`).
- Use `Decimal`/`Numeric` para valores monetários, nunca `float` na persistência.
- Cada detector gera um **motivo legível** para o auditor.
- Toda funcionalidade nova do motor vem acompanhada de testes pytest.
- Configurações via `.env`. Nunca faça commit de credenciais. Mantenha o `.env.example` atualizado.
- Commits em português, curtos e no imperativo (ex.: "Adiciona detector IQR por categoria").
- Para mudanças grandes, apresente o plano e espere confirmação antes de implementar.
- Se um pedido divergir dos RFs e das entidades acima, aponte a divergência antes de codar.
  Essa documentação já foi entregue ao orientador.
- Mantenha o README com a instrução para rodar tudo: `docker compose up`, as migrations e a carga da base sintética.
