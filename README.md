# Detecção Automática de Anomalias em Despesas Corporativas

Software do TCC de Engenharia de Computação (2026/2, Tema 49):
**Detecção automática de anomalias em despesas corporativas por métodos estatísticos e análise de dados.**

A aplicação importa lançamentos de despesas, detecta anomalias com Z-score, IQR,
Isolation Forest e regras contextuais, gera alertas com score, método e motivo, e
permite que um auditor revise, classifique e registre um parecer sobre cada alerta.

> Os alertas são **indícios estatísticos, não acusações**. Toda despesa sinalizada
> precisa de revisão humana.

**Equipe:** Caio Ramos Castilho, Guilherme Rocha Barreto, Levi Silva Cardozo,
Melcksedeck Teyllor Rocha de Sousa, Omar Darbas Mustafa Filho e Vinicius Girotto Pereira.
**Orientador:** Prof. Nelson Aguiar.

---

## Como rodar (Docker Compose)

Pré-requisitos: Docker com Docker Compose v2.24 ou mais recente. No GitHub
Codespaces isso já vem pronto pelo devcontainer.

```bash
cp .env.example .env          # ajuste SECRET_KEY, ADMIN_EMAIL e ADMIN_SENHA
docker compose up --build
```

Na subida, o container da aplicação:

1. aplica as migrations (`flask db upgrade`);
2. cria o administrador inicial com os dados `ADMIN_*` do `.env` e os parâmetros padrão dos métodos (`flask seed-admin`);
3. carrega a base sintética, se `SEED_BASE_SINTETICA=1` (`flask seed-base`);
4. inicia o servidor em <http://localhost:5000>.

Entre com o `ADMIN_EMAIL` e a `ADMIN_SENHA` definidos no `.env`.

### Carga da base sintética

A base sintética tem 5.000 despesas de 12 meses (set/2025 a ago/2026), com anomalias
injetadas e rotuladas. Ela é gerada com seed fixa, então todos obtêm a mesma base.

```bash
docker compose exec app flask seed-base            # gera (seed 42) e carrega no banco
```

Para carregar automaticamente na subida, defina `SEED_BASE_SINTETICA=1` no `.env`.
O comando pode ser repetido: se a base já estiver carregada, não faz nada
(`--forcar` substitui o lote, desde que as despesas ainda não tenham alertas).

Para só gerar os arquivos, sem banco:

```bash
python -m dados.gerar_base_sintetica               # CSV, XLSX e metadados em dados/gerados/
python -m dados.gerar_base_sintetica --help        # seed, volume, período, taxa, limite
```

Os rótulos (`anomalia_real`, `tipo_anomalia`) ficam só no arquivo e não vão para o
banco. Detalhes em [`dados/README.md`](dados/README.md).

### Importar despesas

Pela tela **Importar** (menu superior) ou pela API (`POST /api/despesas/importar`,
campo `arquivo`). Aceita CSV separado por `,` ou `;` e XLSX. A primeira linha precisa
ter as colunas valor, data, categoria, conta contábil, centro de custo e funcionário;
descrição é opcional. Linhas com erro não entram e aparecem listadas por número de
linha; as demais são importadas. Após cada importação, as estatísticas de referência
(tela **Estatísticas**) são recalculadas.

### Comandos úteis

```bash
docker compose exec app flask recalcular-estatisticas          # recalcula as estatísticas de referência
docker compose exec app flask criar-usuario --perfil auditor   # cria um auditor
docker compose exec app flask db migrate -m "Descreve a mudança"   # nova migration após alterar modelos
docker compose exec app flask db upgrade
docker compose down            # para os serviços (os dados continuam no volume)
docker compose down -v         # para e APAGA o banco
```

---

## Testes

```bash
docker compose exec app pytest          # todos os testes, inclusive os de PostgreSQL
```

Fora do Docker (por exemplo, no terminal do Codespace):

```bash
pip install -r requirements-dev.txt
pytest                                  # testes em SQLite em memória
docker compose up -d db && pytest       # inclui os testes de PostgreSQL (trigger e migrations)
```

Os testes marcados `postgres` usam `TEST_DATABASE_URL` e são pulados quando o
banco não está disponível. O banco `despesas_teste` é criado automaticamente na
primeira subida do container `db`.

> **Validação (23/09/2026):** os testes passaram com PostgreSQL 16, incluindo
> o trigger de imutabilidade e a sincronia entre modelos e migrations. O fluxo do
> entrypoint (`flask db upgrade`, `flask seed-admin` e `flask run`) foi executado
> fora do Docker. A subida completa com `docker compose up` ainda precisa ser
> conferida num ambiente com Docker, como o Codespace.

---

## Estrutura

```
app/            aplicação Flask (models, servicos, rotas, templates)
motor/          detectores de anomalia, sem dependência de Flask ou banco
dados/          base sintética e carga no banco
experimentos/   avaliação dos métodos (precisão, recall, F1, taxa de FP)
migrations/     migrations do Alembic (Flask-Migrate)
tests/          testes pytest
docs/           registro de mudanças para a documentação e diagramas (PlantUML)
```

O contexto completo do projeto (requisitos, modelo de dados, arquitetura e
convenções) está em [`CLAUDE.md`](CLAUDE.md). Decisões que afetam a documentação
entregue ficam em [`docs/MUDANCAS_PARA_DOCUMENTACAO.md`](docs/MUDANCAS_PARA_DOCUMENTACAO.md).
O diagrama de classes está em [`docs/diagramas/classes.puml`](docs/diagramas/classes.puml).
O caminho até a entrega final, com o que já foi feito e o que falta, está em
[`docs/ROTEIRO.md`](docs/ROTEIRO.md).

## Situação por sprint

| Sprint | Período | Conteúdo | Situação |
|---|---|---|---|
| S1 | 14/09–27/09 | Modelo de dados, autenticação, infraestrutura; importação (US01) e estatísticas (US02) | Modelo de dados, autenticação, infraestrutura, base sintética, importação (US01) e estatísticas (US02) prontos |
| S2 | 28/09–11/10 | Z-score, IQR (US03), regras contextuais (US05), lista de alertas (US06) | — |
| S3 | 12/10–25/10 | Isolation Forest (US04), experimento comparativo, revisão e parecer (US07, US08) | — |
| S4 | 26/10–02/11 | Dashboard, filtros, parâmetros, usuários, job, relatório | — |
