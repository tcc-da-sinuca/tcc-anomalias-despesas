# Experimentos

`avaliar_metodos.py` compara os métodos de detecção e as combinações entre eles na
base sintética rotulada. Roda o motor direto, sem banco nem Flask.

```bash
python -m experimentos.avaliar_metodos                               # base gerada com seed 42
python -m experimentos.avaliar_metodos --param zscore.limiar=2.5     # outro parâmetro
python -m experimentos.avaliar_metodos --seed 7 --saida /tmp/seed7    # outra base
python -m experimentos.avaliar_metodos --arquivo dados/gerados/despesas_sinteticas.csv
docker compose exec app python -m experimentos.avaliar_metodos       # dentro do Docker
```

Regra: nenhum número de desempenho vai para o artigo sem ter saído de uma execução
real deste script. Com o mesmo código, a mesma seed e os mesmos parâmetros, os CSVs
saem idênticos.

## Como a avaliação é feita

- **Unidade:** cada linha da base, comparada com o rótulo `anomalia_real`. A despesa
  original de uma duplicada tem rótulo 0; se for sinalizada, conta como falso positivo.
- **Avaliações:**
  - `metodo`: cada método sozinho;
  - `uniao`: sinaliza se qualquer método do conjunto sinalizar (todas as combinações);
  - `votacao`: sinaliza se pelo menos 2 métodos sinalizarem.
- **Métricas** (positivo = anomalia): precisão = VP / (VP + FP); recall = VP / (VP + FN);
  F1 = 2·VP / (2·VP + FP + FN); taxa de FP = FP / (FP + VN). Métrica sem denominador
  fica vazia.
- **Parâmetros:** os padrões do motor (os mesmos da aplicação), salvo `--param`.
  Z-score e IQR agrupam por categoria e ignoram grupos com menos de 10 despesas. O
  Isolation Forest usa `contamination=0.05`, `random_state=42` e limite de aprovação de
  R$ 1.000 (atributos em [`docs/ISOLATION_FOREST.md`](../docs/ISOLATION_FOREST.md)).
- **Seeds:** o resultado principal usa a base com seed 42 (`resultados/`); a seed 7
  (`resultados/seed_7/`) mostra se o resultado se mantém com outra base.
- **Atenção ao ler o Isolation Forest:** numa duplicidade ele sinaliza a original e a
  cópia; a original tem rótulo 0 e conta como falso positivo.

## Arquivos em `resultados/`

| Arquivo | Conteúdo |
|---|---|
| `metricas.csv` | Uma linha por avaliação: VP, FP, FN, VN, precisão, recall, F1, taxa de FP, total sinalizado, seed da base e parâmetros (JSON) |
| `metricas_por_tipo.csv` | Para cada avaliação e tipo de anomalia (e para as linhas normais): linhas, sinalizadas e taxa. Na linha `normal`, a taxa é a de falsos positivos |
| `execucao.json` | Data, versões do Python e das bibliotecas, tempo de cada método e metadados da base. Muda a cada execução |

Os arquivos em `resultados/` são versionados, para que a equipe do artigo use
exatamente os números gerados. Para refazer a seed 7:
`python -m experimentos.avaliar_metodos --seed 7 --saida experimentos/resultados/seed_7`.
