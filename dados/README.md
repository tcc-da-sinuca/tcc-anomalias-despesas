# Dados

Scripts da base de dados entregue junto com o software (seção 7 do CLAUDE.md).

| Arquivo | Conteúdo |
|---|---|
| `gerar_base_sintetica.py` | Gera despesas realistas e injeta anomalias rotuladas. Seed fixa. |
| `seed_banco.py` | Carrega a base no banco como um lote de importação (usado por `flask seed-base`). |

Os arquivos gerados vão para `dados/gerados/`, que não é versionada. Qualquer
pessoa recria a mesma base rodando o script com a mesma seed.

```bash
python -m dados.gerar_base_sintetica                        # padrão: seed 42, 5.000 linhas
python -m dados.gerar_base_sintetica --seed 7 --n 10000     # outra seed e outro volume
flask seed-base                                             # gera e carrega no banco
```

## Arquivos gerados

| Arquivo | Conteúdo |
|---|---|
| `despesas_sinteticas.csv` | Separador `,`, decimal `.`, datas ISO (`AAAA-MM-DD`), UTF-8 |
| `despesas_sinteticas.xlsx` | O mesmo conteúdo, para testar a importação de XLSX |
| `metadados.json` | Seed, parâmetros e contagens por tipo de anomalia (RNF06) |

Colunas: `id_sintetico`, os campos da `Despesa` (`data`, `valor`, `categoria`,
`conta_contabil`, `centro_custo`, `funcionario`, `descricao`) e os rótulos
`anomalia_real` (0/1), `tipo_anomalia` e `grupo_anomalia`. O `id_sintetico` e os
rótulos **não vão para o banco**: o experimento lê o CSV e roda o motor direto.

## Despesas normais

- 12 meses (01/09/2025 a 31/08/2026, todo no passado, porque a importação recusa datas futuras), só em dias úteis (segunda a sexta, sem feriados nacionais; ver `motor/calendario.py`).
- 7 categorias, cada uma com valor log-normal (mediana e dispersão próprias), 1 ou 2 contas contábeis exclusivas e os centros de custo em que costuma aparecer.
- 5 centros de custo (`CC-ADM`, `CC-COM`, `CC-TI`, `CC-OPS`, `CC-RH`) e 40 funcionários (`F001` a `F040`), cada um ligado a um único centro de custo.
- Sazonalidade: volume menor em dezembro e janeiro; Viagens e Hospedagem caem nas férias; Treinamentos se concentram em mar–mai e ago–out; Material de escritório sobe no início do ano.

Os parâmetros de cada categoria estão em `CATEGORIAS`, no início do script.

## Anomalias injetadas

Por padrão, 3% de `n` em eventos (150), divididos igualmente entre os 5 tipos.
Cada anomalia é uma **linha nova**; a despesa normal usada como modelo continua na base.

| `tipo_anomalia` | Como é gerada | Método que deve capturá-la |
|---|---|---|
| `valor_extremo` | Valor de 5 a 15 vezes a mediana da categoria | Z-score, IQR |
| `combinacao_incompativel` | Troca o centro de custo ou a conta por um que a categoria nunca usa nas despesas normais | Contextual |
| `duplicada` | Cópia de uma despesa (mesmo funcionário, valor, categoria, conta, centro de custo e descrição), de 0 a 3 dias úteis depois | Isolation Forest (atributos derivados) |
| `fracionamento` | Compra dividida em 2 a 4 lançamentos entre 88% e 99,9% do limite (R$ 1.000), mesmo funcionário, em até 3 dias úteis. Categorias: Material de escritório, Software, Hospedagem | Isolation Forest (atributos derivados) |
| `fim_semana_feriado` | Despesa movida para um sábado, domingo ou feriado do mesmo mês | Isolation Forest (atributos derivados) |

`grupo_anomalia` liga linhas relacionadas: as partes de um fracionamento
(`FRAC-001`, ...) e a duplicada com a sua original (`DUP-001`, ...). A original
fica com `anomalia_real = 0`.

Com os padrões, a base tem 5.000 linhas, das quais 216 são anômalas: os 30
fracionamentos geram 96 linhas.
