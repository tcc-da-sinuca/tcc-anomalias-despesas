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
Codespaces isso já vem pronto na imagem padrão.

```bash
cp .env.example .env          # ajuste SECRET_KEY, ADMIN_EMAIL e ADMIN_SENHA
docker compose up --build
```

O Compose sobe três serviços: `db` (PostgreSQL), `app` (a aplicação web) e
`agendador` (o job que analisa automaticamente as despesas novas).

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

### Dashboard

A página inicial mostra o total de despesas, quantas foram sinalizadas (despesas
distintas com pelo menos um alerta), o percentual sinalizado e os alertas por status
e por método. Clicar num status abre a lista de alertas filtrada. Pela API:
`GET /api/dashboard`.

### Executar a análise e ver os alertas

Na tela **Análises**, o botão **Executar análise** aplica Z-score, IQR, a regra
contextual e o Isolation Forest a todas as despesas e grava os alertas. A tela **Alertas** lista cada
alerta com score, método e motivo. No detalhe do alerta, o auditor classifica a
despesa (aprovado, irregular ou necessita justificativa) e registra um parecer; a
observação é obrigatória nos dois últimos casos. Pareceres não podem ser alterados:
uma nova revisão gera um novo parecer e o histórico fica visível. Uma despesa que já tem alerta de um método não recebe outro do mesmo
método, então a análise pode ser repetida após cada importação. A lista de alertas
tem filtros combináveis: período (data da despesa), categoria, conta contábil, centro
de custo, funcionário, status e método. Pela API:
`POST /api/analises`, `GET /api/alertas`, `POST /api/alertas/{id}/parecer`. Detalhes em
[`docs/FLUXO_ANALISE.md`](docs/FLUXO_ANALISE.md).

### Relatório mensal

A tela **Relatório** mostra, para o mês escolhido (pela data da despesa), o total de
despesas, as sinalizadas, os alertas por status e método e a taxa de confirmação de
irregularidade = irregular ÷ (aprovado + irregular). Os botões **Baixar CSV** (padrão
do Excel brasileiro) e **Baixar PDF** exportam o relatório. Pela API:
`GET /api/relatorios/mensal?ano=2026&mes=3&formato=pdf` (ou `csv`, ou `json`).

### Parâmetros dos métodos

A tela **Parâmetros** mostra os critérios de cada método (limiar do Z-score, fator do
IQR, frequência mínima da regra contextual, proporção, seed e limite de aprovação do
Isolation Forest), com a faixa válida e o valor padrão. O auditor só consulta; o
administrador altera. A mudança vale para as próximas análises. Pela API:
`GET /api/parametros` e `PUT /api/parametros` (administrador).

### Usuários

O administrador gerencia os usuários na tela **Usuários**: cria (com senha inicial),
troca o perfil (`auditor` ou `administrador`), desativa e reativa. Usuários não são
excluídos, porque os pareceres guardam quem os registrou; desativar tira o acesso na
hora. Pela linha de comando também é possível criar: `flask criar-usuario`.

### Reprocessamento automático

O container `agendador` verifica a cada `REPROCESSAMENTO_INTERVALO_MIN` minutos
(padrão 15, definido no `.env`; 0 desliga) se há despesas novas desde a última
análise completa. Se houver, executa a análise, que aparece na tela **Análises** como
"job agendado". Duas análises nunca rodam ao mesmo tempo. Para acompanhar:
`docker compose logs -f agendador`. Para rodar o job uma vez, na hora:
`docker compose exec app flask agendador --uma-vez`.

### Comandos úteis

```bash
docker compose exec app flask executar-analise                # executa a análise de anomalias
docker compose exec app flask recalcular-estatisticas          # recalcula as estatísticas de referência
docker compose exec app flask criar-usuario --perfil auditor   # cria um auditor
docker compose exec app flask db migrate -m "Descreve a mudança"   # nova migration após alterar modelos
docker compose exec app flask db upgrade
docker compose down            # para os serviços (os dados continuam no volume)
docker compose down -v         # para e APAGA o banco
```

### Problemas conhecidos no Codespace: depois de reiniciar

Depois que o Codespace reinicia, o Docker da VM costuma ficar num estado ruim. O
roteiro abaixo resolve os três sintomas já vistos. Nenhum passo apaga o banco: os
dados ficam no volume `pgdata`.

```bash
# 1. Libera o tráfego entre os containers (as regras se perdem a cada reinício)
sudo iptables-legacy -I DOCKER-USER -i br-+ -j ACCEPT
sudo iptables-legacy -I DOCKER-USER -o br-+ -j ACCEPT

# 2. Descarta o cache de build e os containers antigos (o Docker recria tudo)
docker builder prune -af
docker compose rm -f db app agendador

# 3. Sobe de novo
docker compose up --build
```

| Sintoma | Causa | Passo que resolve |
|---|---|---|
| O app para em `>> Aplicando migrations...` com `connection timeout expired` | A imagem do Codespace deixa uma tabela `iptables-legacy` com `FORWARD DROP`, que só libera a rede padrão `docker0`, não a rede do Compose | 1 |
| O build falha no `COPY . .` com `parent snapshot ... does not exist` | O cache de build aponta para camadas que o Docker perdeu no reinício | 2 (`builder prune`) |
| A subida falha com `RWLayer of container ... is unexpectedly nil` | O container aponta para uma camada de arquivos que o Docker perdeu | 2 (`compose rm`) |

O problema é do ambiente do Codespace, não do projeto. Com Docker Desktop (Windows e
Mac) ele não deve aparecer, mas isso ainda não foi testado.

---

## Testes

```bash
docker compose exec app pytest          # todos os testes, inclusive os de PostgreSQL
```

### Experimento

```bash
python -m experimentos.avaliar_metodos   # métricas por método em experimentos/resultados/
```

Detalhes da metodologia e dos arquivos em [`experimentos/README.md`](experimentos/README.md).

Fora do Docker (por exemplo, no terminal do Codespace):

```bash
pip install -r requirements-dev.txt && cp -n .env.example .env   # uma vez por Codespace
pytest                                  # testes em SQLite em memória
docker compose up -d db && pytest       # inclui os testes de PostgreSQL (trigger e migrations)
```

Os testes marcados `postgres` usam `TEST_DATABASE_URL` e são pulados quando o
banco não está disponível. O banco `despesas_teste` é criado automaticamente na
primeira subida do container `db`.

> **Validação (23/09/2026):** `docker compose up --build` testado no Codespace.
> As migrations, o administrador inicial, o login, `GET /api/saude`, `flask seed-base`
> (5.000 despesas) e os 157 testes rodaram dentro do container, contra o PostgreSQL 16.

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
