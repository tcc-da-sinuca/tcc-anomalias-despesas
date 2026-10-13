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
  Z-score e IQR usam como referência o grupo centro de custo × conta contábil; grupo com
  menos de 10 despesas usa a categoria e, se ela também for pequena, não é avaliado. O
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
| `metricas_por_gravidade.csv` | Para cada método e nível de gravidade (leve, moderada, alta, crítica): sinalizadas, anômalas, normais e precisão. As linhas `rejeicao_automatica` (base inteira de uma vez) e `rejeicao_automatica_no_lancamento` (descontando as originais de duplicatas, que no lançamento entram antes da cópia) estimam a rejeição automática por alerta crítico |
| `execucao.json` | Data, versões do Python e das bibliotecas, tempo de cada método e metadados da base. Muda a cada execução |

Os arquivos em `resultados/` são versionados, para que a equipe do artigo use
exatamente os números gerados. Para refazer a seed 7:
`python -m experimentos.avaliar_metodos --seed 7 --saida experimentos/resultados/seed_7`.

## Experimento ampliado (`avaliar_robustez.py`)

Responde à verificação do orientador de 08/10/2026 (robustez e ameaças à validade). Não
substitui o resultado principal (`avaliar_metodos.py`, sementes 42 e 7).

```bash
python -m experimentos.avaliar_robustez                  # 20 sementes (1 a 20), ~6 min
python -m experimentos.avaliar_robustez --sementes 5     # rápido, para testar
```

| Arquivo em `resultados/robustez/` | Conteúdo |
|---|---|
| `por_semente.csv` | Uma linha por semente e avaliação: VP, FP, FN, VN, precisão, recall, F1, taxa de FP, AP (área sob a curva precisão-revocação) e recall por tipo de anomalia |
| `resumo_sementes.csv` | Média e desvio padrão em 20 sementes: métodos, combinações, linhas de base (aleatório 5%, 5% maiores valores da categoria, Isolation Forest sobre atributos brutos), variantes (Z-score e IQR sobre log, z-score robusto com mediana e MAD) e ablação dos atributos do Isolation Forest |
| `random_state_if.csv` | Isolation Forest com 20 valores de `random_state` na base de semente 42 |
| `sensibilidade_limiar.csv` | `contamination` de 0,01 a 0,15; limiar do Z-score de 2 a 4; fator do IQR de 1,5 a 3 (média de 20 sementes) |
| `cenarios_estresse.csv` | Bases geradas com hipóteses diferentes das dos detectores (extremo sutil, duplicata tardia, fracionamento abaixo de 85%, fim de semana legítimo e todos juntos), 10 sementes |
| `execucao.json` | Sementes, parâmetros, cenários, duração e versões das bibliotecas |

As variantes e linhas de base existem só no script, para comparação; nenhum parâmetro da
aplicação muda.
