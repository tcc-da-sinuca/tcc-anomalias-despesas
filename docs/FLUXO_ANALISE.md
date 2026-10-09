# Fluxo "executar análise → gerar alertas → registrar parecer"

> **Situação:** aprovado pela equipe em 23/09/2026, com as decisões D1 a D4 como
> recomendadas. É a referência para os diagramas de sequência e de arquitetura
> (entrega da documentação em 03/10). Registrado nos itens 11 e 12 de
> `MUDANCAS_PARA_DOCUMENTACAO.md`.

**Resumo:** nenhuma entidade muda. A proposta define as assinaturas do motor
(`motor/`), dos serviços `analise` e `revisao`, das rotas e o que é gravado em
cada passo. As decisões tomadas estão na seção 6.

---

## 1. Visão geral

```
Auditor ── POST /api/analises ──► rotas/api.py
                                     │
                                     ▼
                         servicos/analise.executar_analise(usuario)
                           1. parametros.obter_parametros()          ◄── ParametroMetodo
                           2. carrega todas as despesas → DataFrame  ◄── Despesa
                           3. motor.consolidador.executar_detectores(df, parametros)
                                 ├─ motor.zscore.detectar(df, limiar)
                                 ├─ motor.iqr.detectar(df, fator)
                                 ├─ motor.contextual.detectar(df, frequencia_minima)
                                 └─ motor.isolation_forest.detectar(...)   (S3)
                           4. motor.consolidador.consolidar(resultados) → alertas
                           5. descarta alertas já existentes (mesma despesa + método)
                           6. grava ExecucaoAnalise + AlertaAnomalia (pendente)
                                     │
                                     ▼
                                  commit (rota)

Auditor ── POST /api/alertas/{id}/parecer ──► servicos/revisao.registrar_parecer(...)
                           1. valida status e observação (RF08)
                           2. INSERT Parecer (somente inserção, RNF02)
                           3. UPDATE AlertaAnomalia.status_revisao = status
                                     │
                                     ▼
                                  commit (rota)
```

Princípios mantidos: o motor não importa Flask nem SQLAlchemy (o experimento o
chama direto com o CSV); os serviços não fazem commit (a rota ou o comando
decide, como já acontece na importação); o alerta nasce `pendente` e só muda com
um parecer humano.

---

## 2. Motor (`motor/`), sem Flask e sem banco

### 2.1 Contrato comum dos detectores

```python
# Entrada: DataFrame com despesa_id, valor (float), data (datetime64), categoria,
#          conta_contabil, centro_custo, funcionario
# Saída:   DataFrame[despesa_id, score, sinalizado, motivo], uma linha por despesa
COLUNAS_RESULTADO = ("despesa_id", "score", "sinalizado", "motivo")
```

- **Uma linha por despesa**, sinalizada ou não. O experimento precisa das
  não sinalizadas para calcular FP e FN; o consolidador filtra depois.
- `score`: quanto maior, mais anômala. A escala é própria de cada método (tabela
  abaixo) e não é comparável entre métodos.
- `motivo`: texto para o auditor, preenchido só quando `sinalizado` é verdadeiro
  (vazio nos demais).
- Os detectores calculam as estatísticas do grupo a partir do próprio DataFrame
  recebido, com as mesmas regras de `motor/estatisticas.py` (desvio amostral,
  quartis por interpolação linear). Eles **não** leem `EstatisticaReferencia`:
  assim o experimento roda sem banco e o resultado não depende da última
  gravação de estatísticas.

### 2.2 Detectores

| Arquivo | Assinatura | Score | Sinaliza quando | Exemplo de motivo |
|---|---|---|---|---|
| `zscore.py` (S2) | `detectar(despesas, limiar=3.0, dimensao="categoria")` | \|z\| no grupo | \|z\| > limiar | "Valor R$ 9.850,00 é 4,2x a média da categoria Viagens (R$ 2.340,00); z = 5,1, limiar 3." |
| `iqr.py` (S2) | `detectar(despesas, fator=1.5, dimensao="categoria")` | distância além do quartil, em IQRs (0 dentro da caixa) | score > fator | "Valor R$ 9.850,00 acima do limite do grupo categoria Viagens (Q3 + 1,5 × IQR = R$ 2.100,00)." |
| `contextual.py` (S2) | `detectar(despesas, frequencia_minima=0.01)` | 1 − frequência da combinação | frequência < mínimo | "A combinação conta 3.1.07 × centro de custo CC-TI aparece em 0,4% das despesas de Viagens (2 de 538)." |
| `isolation_forest.py` (S3) | `detectar(despesas, contamination=0.05, random_state=42, limite_aprovacao=1000.0)` | `-score_samples` do scikit-learn | `predict == -1` | Uma frase por atributo ativo, por exemplo "Lançada num domingo (14/06/2026)." (ver [`ISOLATION_FOREST.md`](ISOLATION_FOREST.md)) |

Regras comuns do Z-score e do IQR:
- grupo com menos de **10** despesas, ou com desvio/IQR zero, não é avaliado
  (score 0, não sinaliza), porque a estatística não é confiável. Constante
  `N_MINIMO_GRUPO = 10` no motor, não configurável (decisão D4);
- o Z-score é bilateral (\|z\|); o motivo diz "acima" ou "abaixo" da média.

### 2.3 Consolidador (`motor/consolidador.py`)

```python
DETECTORES = {"zscore": zscore.detectar, "iqr": iqr.detectar,
              "contextual": contextual.detectar,
              "isolation_forest": isolation_forest.detectar}

def executar_detectores(
    despesas: pd.DataFrame,
    parametros: dict[str, dict[str, float | int]],
    metodos: Iterable[str] | None = None,           # None = todos os de DETECTORES
) -> dict[str, pd.DataFrame]:
    """Roda cada detector e devolve {metodo: DataFrame[despesa_id, score, sinalizado, motivo]}."""

def consolidar(resultados: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Só as linhas sinalizadas, empilhadas: DataFrame[despesa_id, metodo, score, motivo]."""
```

- **Um alerta por despesa e método**, como já prevê o modelo
  (`AlertaAnomalia.metodo` é um só). Se o Z-score e o IQR sinalizam a mesma
  despesa, surgem dois alertas; a tela agrupa por despesa se for preciso.
- O experimento usa `executar_detectores` (precisa das linhas não sinalizadas) e
  calcula as combinações de métodos, como "sinalizada por pelo menos um" ou "por
  pelo menos dois", a partir desses resultados. Isso não entra no consolidador.

---

## 3. Serviço de análise (`app/servicos/analise.py`)

```python
def executar_analise(
    usuario: Usuario | None,                 # None = job agendado (executada_por vazio)
    metodos: Iterable[str] | None = None,
) -> ExecucaoAnalise:
    """Roda o motor sobre todas as despesas e grava a execução e os alertas novos.

    Não faz commit.
    """
```

Passos:
1. `parametros.obter_parametros()`, uma função nova em `servicos/parametros.py`,
   lê `ParametroMetodo` e converte o texto em número:
   `{"zscore": {"limiar": 3.0}, ..., "isolation_forest": {"contamination": 0.05, "random_state": 42}}`.
   A validação e a edição pelo administrador continuam na S4 (US12).
2. Carrega **todas** as despesas num DataFrame (id, valor como float só para o
   cálculo, data e campos de agrupamento).
3. `executar_detectores` e depois `consolidar`.
4. **Não repete alerta:** descarta as linhas cuja despesa já tem alerta do mesmo
   método, de qualquer execução anterior (decisão D3).
5. Grava a `ExecucaoAnalise`:
   - `parametros`: os métodos executados, os parâmetros de cada um e as
     constantes do motor (RNF06). Exemplo:
     `{"metodos": ["zscore", "iqr", "contextual"], "zscore": {"limiar": 3.0}, "iqr": {"fator": 1.5}, "contextual": {"frequencia_minima": 0.01}, "dimensao_valor": "categoria", "n_minimo_grupo": 10}`;
   - `seed`: o `random_state` do Isolation Forest (42 por padrão);
   - `total_despesas`: quantas foram analisadas;
   - `total_alertas`: quantos alertas **novos** foram criados;
   - `duracao_s` e `executada_por`.
6. Grava os `AlertaAnomalia` com `status_revisao = "pendente"` e `score` como
   float.

Por que analisar sempre todas: as estatísticas de grupo dependem da base toda, e
a regra do passo 4 faz a reexecução só gerar alertas para o que é novo. O job do
APScheduler (S4) passa a ser apenas `executar_analise(None)`, sem precisar
controlar quais despesas são "novas". Para o volume do projeto (5.000 despesas),
isso roda em poucos segundos dentro da requisição, sem fila.

### Consultas (`app/repositorios/alertas.py`)

```python
def paginar_alertas(pagina=1, por_pagina=50, *, status=None, metodo=None,
                    execucao_id=None) -> Pagination     # os filtros da US10 entram na S4
def obter_alerta(alerta_id: int) -> AlertaAnomalia | None  # com despesa e pareceres
def paginar_execucoes(pagina=1, por_pagina=20) -> Pagination
```

A lista é ordenada por status (pendentes primeiro) e depois por score decrescente.

---

## 4. Serviço de revisão (`app/servicos/revisao.py`), S3

```python
class ParecerInvalidoError(ValueError): ...

def registrar_parecer(
    alerta: AlertaAnomalia,
    usuario: Usuario,
    status: str,                 # aprovado | irregular | necessita_justificativa
    observacao: str | None,
) -> Parecer:
    """Insere um parecer e atualiza o status_revisao do alerta. Não faz commit."""
```

- `status` fora de `STATUS_PARECER` ou observação vazia (depois de `strip`) para
  `irregular` e `necessita_justificativa`: levanta `ParecerInvalidoError` com uma
  mensagem para o formulário. O CHECK do banco continua como segunda barreira.
- Um alerta pode receber **vários pareceres** (reavaliação). Cada um é um INSERT
  novo, e o `status_revisao` passa a refletir o mais recente. O histórico
  completo aparece no detalhe do alerta (RF12). Isso segue o que já está
  registrado no item 7 de `MUDANCAS_PARA_DOCUMENTACAO.md`.
- Qualquer usuário autenticado (auditor ou administrador) pode dar parecer.

### Significado dos status (definido em 26/09/2026)

Os status descrevem a decisão do auditor sobre a **despesa** que gerou o alerta.

| Status | Significado | Quando usar | Observação |
|---|---|---|---|
| `pendente` | Ninguém revisou ainda | Automático na criação do alerta; nenhum parecer registra este status | — |
| `aprovado` | A despesa é regular (o alerta foi um falso positivo). Refere-se à despesa, não ao alerta | Despesa incomum, mas correta e autorizada | Opcional (recomendado dizer por quê) |
| `irregular` | A despesa não se justifica (o indício foi confirmado) | Duplicidade, fracionamento, lançamento indevido, erro de classificação etc. | Obrigatória |
| `necessita_justificativa` | Ainda não dá para concluir; falta explicação ou documento do responsável | Quando é preciso pedir recibo, nota fiscal ou autorização | Obrigatória, dizendo o que foi pedido |

Fluxo normal: `pendente` → `aprovado` ou `irregular`, ou `pendente` →
`necessita_justificativa` → novo parecer com `aprovado` ou `irregular`.

**Taxa de confirmação de irregularidade** (US11): `irregular ÷ (aprovado + irregular)`,
contando o status atual dos alertas. Só entram os alertas com conclusão; `pendente` e
`necessita_justificativa` ficam fora.

---

## 5. Rotas

| Rota | Sprint | Perfil | Resposta |
|---|---|---|---|
| `POST /api/analises` | S2 | auditor | 201 com a execução (`id`, totais, parâmetros, duração) |
| `GET /api/analises/{id}` | S2 | auditor | execução + contagem de alertas por método |
| `GET /api/alertas?status=&metodo=&execucao_id=&pagina=` | S2 | auditor | lista paginada |
| `GET /api/alertas/{id}` | S2 | auditor | alerta + despesa + pareceres |
| `POST /api/alertas/{id}/parecer` | S3 | auditor | 201 com o parecer · 400 com a mensagem de validação |

Linha de comando: `flask executar-analise [--metodo zscore] [--email usuario]`. Sem
`--email`, a execução fica sem autor, como a do job agendado.

Na web: botão **Executar análise** (formulário POST com CSRF), com uma tela de
resultado que leva à lista de alertas (S2); tela **Alertas** com score, método e
motivo (US06, S2); detalhe do alerta com o formulário de parecer e o histórico
(S3). O aviso de que o alerta é um indício continua em todas as páginas.

---

## 6. Decisões (aprovadas em 23/09/2026)

> **Atualização (08/10/2026):** a equipe trocou a referência para o grupo **centro de custo ×
> conta contábil**, com recuo para a categoria quando o grupo tem menos de 10 despesas
> (item 32 de `MUDANCAS_PARA_DOCUMENTACAO.md`). O texto abaixo registra a decisão original.

**D1. Grupo do Z-score e do IQR: categoria (recomendado) ou as três dimensões?**
O RF02 calcula estatísticas por categoria, conta e centro de custo, mas as
categorias têm escalas muito diferentes: a mediana vai de R$ 55 (Alimentação) a
R$ 1.183 (Treinamentos). Agrupar por centro de custo mistura essas escalas.
Numa checagem exploratória na base sintética (Z-score com limiar 3; não é
resultado do experimento):

| Grupo | Valores extremos pegos (de 30) | Despesas normais sinalizadas |
|---|---|---|
| categoria | 29 | 24 |
| conta contábil | 28 | 19 |
| centro de custo | 11 | 68 |

Proposta: `dimensao="categoria"` por padrão, como no exemplo do RNF05; a
dimensão fica como argumento do detector para o experimento comparar as três.
Não vira parâmetro configurável pelo administrador.

**D2. Base da frequência na regra contextual: dentro da categoria (recomendado) ou sobre o total?**
"Frequência < 1%" sobre o total de despesas sinaliza qualquer categoria pequena.
Na mesma checagem exploratória:

| Base da frequência | Combinações incompatíveis pegas (de 30) | Despesas normais sinalizadas |
|---|---|---|
| total de despesas | 30 | 216 |
| despesas da mesma categoria | 30 | 0 |

Proposta: frequência = despesas com a mesma categoria × conta × centro de custo ÷
despesas da categoria. "Combinação inexistente no histórico" fica coberta: é a
combinação que só aparece na própria despesa, com frequência mínima.
**Isso ajusta o texto do RF05, então precisa ir para `MUDANCAS_PARA_DOCUMENTACAO.md`.**

**D3. Reexecução: não repetir alerta da mesma despesa e método (recomendado)?**
Sem essa regra, cada execução duplicaria todos os alertas e os pareceres já dados
ficariam espalhados. A consequência é que, se o administrador mudar um
parâmetro, as despesas já alertadas pelo método não ganham um alerta novo. As
que passarem a ser sinalizadas ganham. Os alertas antigos nunca são apagados
(RF12).

**D4. Tamanho mínimo do grupo (10) fixo no código (recomendado) ou configurável?**
Torná-lo configurável acrescenta uma chave em `PARAMETROS_PADRAO` e na tela da
US12. Proposta: deixar fixo e documentado; na base sintética todos os grupos têm
centenas de despesas, então isso só afeta importações reais pequenas.

---

## 7. Impacto na documentação

- **Entidades:** nenhuma mudança. `classes.puml` e migrations continuam iguais.
- **Diagrama de sequência:** as seções 1, 3 e 4 deste arquivo.
- **Diagrama de arquitetura:** motor (detectores + consolidador) → serviço de
  análise → repositórios, como na seção 6 do CLAUDE.md, sem camadas novas.
- **Texto do RF05:** decisão D2.
- **`ExecucaoAnalise.parametros`:** passa a ter formato definido (seção 3, passo 5).

---

## 8. Verificação no lançamento e pedidos de aprovação (08/10/2026)

Item 34 de `MUDANCAS_PARA_DOCUMENTACAO.md`. Além da análise sob demanda e do job, os
métodos rodam **no lançamento** (cadastro manual e importação, linha a linha):

```
Usuário ── cadastra/importa ──► servicos/lancamento.lancar_despesas(dados, usuario)
              1. trava de análise (a mesma da seção 3)
              2. histórico = despesas válidas + as novas (ids provisórios)
              3. motor: executar_detectores → consolidar (com gravidade)
              4. por despesa nova:
                   sem alerta ............ Despesa(situacao=valida)
                   alerta não crítico .... Despesa(pendente) + SolicitacaoAprovacao(pendente)
                   alerta crítico ........ Despesa(rejeitada) + SolicitacaoAprovacao(rejeitada_automaticamente)
              5. ExecucaoAnalise(tipo=verificacao_lancamento) + AlertaAnomalia + EventoSolicitacao
                                     │
Administrador ── aprova ──► Despesa(valida) + parecer "aprovado" nos alertas + evento
              ── rejeita (justificativa) ──► Despesa(rejeitada) + parecer "irregular" + evento
Quem lançou ── encaminha (justificativa) ──► pedido pendente e prioritário + evento
```

- Só o administrador decide, e nunca um pedido de despesa que ele mesmo lançou.
- Só despesas **válidas** contam como histórico, estatísticas, análises, dashboard,
  lista de alertas e relatório. Pendentes e rejeitadas ficam na tela **Pedidos**.
- A carga do histórico (`flask seed-base`) entra sem verificação.
