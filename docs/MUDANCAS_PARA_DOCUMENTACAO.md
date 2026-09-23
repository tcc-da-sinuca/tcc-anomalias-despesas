# Mudanças para a documentação

Registro das decisões do desenvolvimento que afetam a Documentação de Software
(entregue em 13/09/2026), os diagramas ou o artigo. A equipe de documentação
deve incorporar cada item na próxima versão e marcar a coluna "Incorporado".

| # | Data | O que mudou | Onde afeta | Incorporado |
|---|---|---|---|---|
| 1 | 22/09/2026 | O termo **"gestor"** foi descartado. O sistema tem só os perfis **auditor** e **administrador**. | US09 ("Como auditor ou gestor…" → "Como auditor…"). O diagrama de casos de uso já está correto. | ☐ |
| 2 | 22/09/2026 | **Funcionário** passa a ser campo obrigatório na importação. A lista completa fica: valor, data, categoria, conta contábil, centro de custo e funcionário. Motivo: o filtro da RF10 e a identificação de duplicidade e fracionamento dependem desse campo. | Critério de aceite da US01. | ☐ |
| 3 | 22/09/2026 | Despesas **duplicadas**, **fracionamento** abaixo de limite e lançamentos em **fim de semana ou feriado** serão cobertos pelo **Isolation Forest** com atributos derivados (dia da semana, indicador de feriado, repetições por funcionário). Não foram criadas regras contextuais novas: o método contextual continua tratando só da combinação categoria × conta × centro de custo. | Artigo: discutir quais tipos de anomalia cada método captura. Sem impacto nos diagramas. | ☐ |
| 4 | 22/09/2026 | Os RNFs seguem **apenas o texto da documentação**, sem metas numéricas (nada de "5.000 despesas em 30 s" nem "FP ≤ 15%"). As métricas do experimento (precisão, recall, F1, taxa de FP) serão reportadas, mas não como metas. | Nenhuma alteração na documentação; o CLAUDE.md do repositório foi ajustado. | — |
| 5 | 22/09/2026 | Inconsistência de prioridade: o Quadro 1 marca RF11 e RF13 como "Importante", mas o Quadro 4 marca US11 e US12 como "Could". O desenvolvimento segue o plano de sprints (Sprint 4). | Quadros 1 e 4: alinhar as prioridades. | ☐ |
| 6 | 22/09/2026 | Modelo de dados implementado (`app/models/`). Detalhes que o diagrama de classes deve mostrar: `Despesa.lote_id` é opcional (despesa cadastrada à mão não tem lote); `ExecucaoAnalise.executada_por` é opcional (execução disparada por job agendado); `ParametroMetodo` tem chave composta (metodo, chave); `EstatisticaReferencia` é única por (dimensao, chave); `AlertaAnomalia.status_revisao` começa como `pendente`; `Parecer` não aceita `pendente` e exige observação para `irregular` e `necessita_justificativa`. | Diagrama de classes (entrega 27/09): usar `docs/diagramas/classes.puml`. | ☐ |
| 7 | 22/09/2026 | A imutabilidade do `Parecer` (RNF02) é garantida em duas camadas: eventos do SQLAlchemy na aplicação e trigger no PostgreSQL, que bloqueia UPDATE, DELETE e TRUNCATE. Uma nova revisão de um alerta gera um novo parecer, e o histórico completo fica preservado (RF12). | Diagrama de classes (estereótipo «somente inserção»). Diagrama de sequência (entrega 03/10): "registrar parecer" = INSERT de parecer + atualização de `status_revisao` do alerta. | ☐ |

## Como renderizar o diagrama de classes

`docs/diagramas/classes.puml` está em PlantUML. Há três opções:

- **VS Code / Codespace:** extensão *PlantUML* (jebbs.plantuml), já recomendada no devcontainer. Abra o arquivo e use `Alt+D` para a pré-visualização.
- **Navegador:** cole o conteúdo em <https://www.plantuml.com/plantuml>.
- **Linha de comando:** `java -jar plantuml.jar docs/diagramas/classes.puml` gera um PNG.
