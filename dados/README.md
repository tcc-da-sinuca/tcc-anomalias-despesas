# Dados

Scripts da base de dados entregue junto com o software (seção 7 do CLAUDE.md).

| Arquivo | Conteúdo | Sprint |
|---|---|---|
| `gerar_base_sintetica.py` | Gera despesas realistas (log-normal por categoria, sazonalidade) e injeta anomalias rotuladas (`anomalia_real`, `tipo_anomalia`). Seed fixa. | 1–2 |
| `seed_banco.py` | Carrega a base sintética no banco. | 1–2 |

Os arquivos gerados vão para `dados/gerados/`, que não é versionada. Qualquer
pessoa recria a mesma base rodando o script com a mesma seed.
