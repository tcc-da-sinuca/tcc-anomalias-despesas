# Isolation Forest (RF04 / US04)

> **Situação:** aprovado pela equipe em 25/09/2026, com as decisões D5 a D8 como
> recomendadas, e implementado em `motor/isolation_forest.py`. Os números das
> seções 2 e 5 vêm da checagem exploratória feita **antes** da correção do gerador
> (D7) e serviram só para escolher os atributos. **Não são resultados para o
> artigo**: esses estão em `experimentos/resultados/`.

## 1. Papel do método

Pela decisão registrada no item 3 de `MUDANCAS_PARA_DOCUMENTACAO.md`, o Isolation
Forest cobre as três anomalias que os outros métodos não pegam: **despesa duplicada**,
**fracionamento logo abaixo de um limite** e **lançamento em fim de semana ou
feriado**. No experimento atual, Z-score, IQR e contextual pegam no máximo 2 das 30
duplicadas e 2 dos 30 lançamentos em fim de semana ou feriado. Os fracionamentos que o
Z-score pega (25 de 96) são pegos por acaso: são valores altos para Material de
escritório.

O Isolation Forest não olha a despesa isolada, e sim **atributos derivados** de
cada despesa em relação às outras. A escolha desses atributos é o que define o que
o método consegue detectar.

## 2. Atributos propostos (conjunto A)

Todos são calculados no motor, a partir das próprias despesas, sem banco.

| Atributo | Cálculo | Anomalia que mira |
|---|---|---|
| `desvio_valor` | \|z\| do **logaritmo** do valor dentro do grupo centro de custo × conta (recuo para a categoria se o grupo tiver menos de 10 despesas; mudança de 08/10/2026) | valor extremo (em log, porque os valores são assimétricos e as categorias têm escalas diferentes) |
| `fim_semana_feriado` | 1 se sábado, domingo ou feriado nacional (`motor/calendario.py`), 0 se não | lançamento em dia não útil |
| `repeticoes_valor` | outras despesas do **mesmo funcionário, categoria e valor** em até 7 dias corridos, para antes ou para depois | duplicidade |
| `fracionamento` | se o valor está entre 85% e 100% do limite de aprovação: outras despesas do mesmo funcionário, também nessa faixa, em até 5 dias corridos; senão, 0 | fracionamento |

Parâmetros do modelo: `contamination=0.05`, `random_state=42` (já previstos) e
`n_estimators=100` (padrão do scikit-learn, registrado na execução).

Na checagem exploratória, as despesas normais quase nunca ativam os atributos de
contagem:

| Atributo ativo (> 0) | Normais | Duplicadas | Fracionamentos | Fim de semana/feriado |
|---|---|---|---|---|
| `repeticoes_valor` | 1,4% | 100% | 0% | 40%* |
| `fracionamento` | 0,3% | 7% | 100% | 0% |
| `fim_semana_feriado` | 0% | 0% | 0% | 100% |

\* artefato do gerador; ver a decisão D7.

### Alternativas testadas e descartadas

| Conjunto | O que muda em relação ao A | Resultado (sinalizadas de cada tipo) |
|---|---|---|
| **A** (proposto) | — | duplicadas 30/30, fracionamento 88/96, fim de semana 13/30, extremos 22/30; 72 normais |
| B | + nº de despesas do funcionário na categoria em 5 dias | fim de semana sobe para 21/30, extremos caem para 17/30; o atributo é ativo em 57% das normais, então é ruído |
| C | + indicador "perto do limite" sozinho | fracionamento 96/96, mas duplicadas caem para 27/30 e fim de semana para 12/30 |

O conjunto A é o mais equilibrado e o mais fácil de explicar no motivo.

## 3. Score e sinalização

- `score` = `-score_samples(...)` do scikit-learn: quanto maior, mais isolada a despesa.
- `sinalizado` = `predict(...) == -1`, ou seja, as ~5% mais isoladas (`contamination`).
- Mesmo contrato dos outros detectores: `detectar(despesas, contamination=0.05,
  random_state=42, limite_aprovacao=1000.0)` → `DataFrame[despesa_id, score, sinalizado, motivo]`.
- Uma função pública `atributos(despesas, limite_aprovacao)` devolve a tabela de
  atributos, para os testes e para o experimento poderem analisá-la.

## 4. Motivo legível (RNF05)

O Isolation Forest não diz por que isolou uma despesa. A proposta é montar o motivo
a partir dos atributos ativos da despesa sinalizada, uma frase por atributo:

- "Lançada num domingo (14/06/2026)." / "Lançada em feriado nacional (21/04/2026)."
- "O funcionário F012 lançou o mesmo valor (R$ 350,00) na categoria Software mais 1 vez em até 7 dias."
- "Valor R$ 950,00 entre 85% e 100% do limite de R$ 1.000,00, com mais 2 lançamentos do funcionário F007 na mesma faixa em até 5 dias (possível fracionamento)."
- "Valor R$ 4.800,00 muito acima do habitual do centro de custo CC-COM na conta contábil 3.1.01.001." (quando `desvio_valor` > 2,5)

Se nenhum atributo estiver ativo, o motivo diz isso com honestidade: "Combinação
incomum de valor, data e frequência de lançamentos, sem um fator isolado que
explique; revise o contexto da despesa." As frases entram na ordem da tabela da seção 2.

Consequência para o auditor: numa duplicidade, **a original e a cópia** são
sinalizadas, porque as duas têm o mesmo valor repetido. O motivo aponta o par. No
experimento, a original conta como falso positivo, porque o rótulo dela é 0.

## 5. Decisões (aprovadas em 25/09/2026)

**D5. Atributos: conjunto A (recomendado)?** Ver seção 2. Os atributos vêm da
definição das anomalias na documentação (duplicidade, fracionamento, dia não útil),
não do código do gerador. As janelas (7 e 5 dias) e a faixa (85%) foram fixadas a
partir dessas definições e não serão ajustadas olhando o resultado do experimento.
Para reforçar, o experimento também será rodado com outra seed (7) e o artigo
reporta as duas.

**D6. Limite de aprovação como parâmetro novo (recomendado) ou constante?**
Fracionamento só existe em relação a um limite, que é uma política de cada empresa.
Proposta: novo parâmetro `isolation_forest.limite_aprovacao = 1000` em
`PARAMETROS_PADRAO`. `ParametroMetodo` guarda chave e valor, então **não há mudança
de tabela nem migration**: o `flask seed-admin` insere o parâmetro que falta. Mas a
seção 5 do CLAUDE.md e a lista de parâmetros da documentação ganham um item, e isso
vai para `MUDANCAS_PARA_DOCUMENTACAO.md`. As janelas (7 e 5 dias) e a faixa (85%)
ficam como constantes do motor, registradas na execução.

**D7. Corrigir um artefato do gerador (recomendado)?** O gerador cria a combinação
incompatível e o lançamento em fim de semana **copiando uma despesa normal, que
continua na base**, e mantém o valor exato dela. Resultado: 80% das combinações
incompatíveis e 40% dos lançamentos em fim de semana têm um "gêmeo" de mesmo valor
e mesmo funcionário, e o Isolation Forest os pega pelo motivo errado (como
duplicidade). Isso inflaria o resultado do método no artigo. Proposta: nesses dois
tipos, sortear um valor novo da distribuição da categoria, em vez de copiar o da
despesa modelo. Efeitos:
- a base muda (mesma seed, outros valores nesses 60 eventos), então o item 8 de
  `MUDANCAS_PARA_DOCUMENTACAO.md` ganha uma correção;
- `metricas.csv` precisa ser gerado de novo;
- quem já carregou a base no banco roda `flask seed-base --forcar`, o que só funciona
  se ainda não houver alertas. No banco de desenvolvimento, o caminho é `docker compose down -v`.

A alternativa é manter a base e só relatar a limitação no artigo.

**D8. Motivo montado pelos atributos ativos (recomendado)?** Ver seção 4. A
alternativa, explicar com SHAP ou com a profundidade por atributo, traz uma
dependência nova e um texto menos direto para o auditor.

## 6. Limitações a relatar no artigo

- Na base sintética, as despesas normais nunca caem em fim de semana; numa empresa
  real, há despesas legítimas nesses dias (viagens, por exemplo). Por isso, o
  atributo `fim_semana_feriado` tende a render menos em dados reais.
- O feriado considerado é só o nacional; os estaduais e municipais ficam de fora.
- `contamination=0.05` fixa a proporção de sinalizados. Se a base tiver mais ou menos
  anomalias que isso, a precisão ou o recall caem por construção.

## 7. Impacto e plano

- **Entidades e diagramas:** nenhuma mudança de tabela. Só o parâmetro novo (D6).
- **Código:** `motor/isolation_forest.py` (atributos + detector + motivo), entrada em
  `DETECTORES`, parâmetro em `PARAMETROS_PADRAO`, correção do gerador (D7).
- **Testes:** cada atributo com dados pequenos e controlados, reprodutibilidade (mesma
  seed dá o mesmo resultado), motivos, e o teste de sanidade com a base sintética.
- **Experimento:** gerar de novo `metricas.csv` com os quatro métodos, com a seed 42 e
  também a 7.
- **Documentação:** registrar D5 a D8 em `MUDANCAS_PARA_DOCUMENTACAO.md` e atualizar o roteiro.
