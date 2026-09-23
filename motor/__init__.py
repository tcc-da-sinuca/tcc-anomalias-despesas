"""Motor de detecção de anomalias.

O motor não depende do Flask nem do banco. Cada detector é uma função (ou
classe) pura com o contrato:

    entrada: pandas.DataFrame com as despesas (colunas: despesa_id, valor, data,
             categoria, conta_contabil, centro_custo, funcionario, ...)
    saída:   pandas.DataFrame[despesa_id, score, sinalizado, motivo]

O ``consolidador`` junta os resultados dos detectores (zscore, iqr,
isolation_forest, contextual) e produz os dados dos ``AlertaAnomalia``.

Decisão registrada (docs/MUDANCAS_PARA_DOCUMENTACAO.md): duplicidade,
fracionamento e lançamento em fim de semana/feriado são cobertos pelo Isolation
Forest com atributos derivados (dia da semana, feriado, repetições por
funcionário). Não há regras contextuais extras.

Implementação: Sprint 2 (zscore, iqr, contextual) e Sprint 3 (isolation_forest).
"""
