# Roteiro de demonstração

Passo a passo para apresentar o software ao orientador ou à banca, em cerca de 15
minutos. Os números citados saíram de uma execução real desta sequência (27/09/2026),
com a base sintética de seed 42; se o código mudar, rode a sequência de novo e
atualize os números.

**Mensagem central:** o sistema aponta despesas incomuns e explica por quê, mas quem
decide é o auditor. O alerta é um **indício estatístico, não uma acusação** (a faixa
amarela no topo de todas as telas lembra isso o tempo todo).

---

## 1. Preparação (antes da apresentação, ~5 min)

Partir de um banco limpo, para os números baterem com este roteiro. Todos os números
e motivos abaixo foram conferidos numa execução real da sequência completa.

```bash
# No Codespace, depois de um reinício, rode antes o bloco "Problemas conhecidos" do README.
docker compose down -v                               # APAGA o banco de desenvolvimento
docker compose up --build -d
docker compose exec app flask seed-base              # 5.000 despesas (seed 42)
docker compose exec app flask executar-analise --email admin@exemplo.com
docker compose exec app flask criar-usuario --nome "Auditora Demo" \
  --email auditora@exemplo.com --perfil auditor --senha senha-da-demo
```

Resultado esperado da análise: **5.000 despesas, 596 alertas**.

Deixe abertos: o navegador em <http://localhost:5000>, uma janela anônima (para o
login da auditora) e o arquivo `dados/exemplos/importacao_demonstracao.csv`.

---

## 2. Apresentação

### 2.1 Login e dashboard (US09) — 1 min
- Entrar como administrador (`ADMIN_EMAIL` / `ADMIN_SENHA` do `.env`).
- Mostrar a **faixa amarela** (RNF04) e o dashboard: 5.000 despesas, 433 sinalizadas
  (8,66%), 596 alertas, todos pendentes, e os alertas por método.
- **Falar:** "uma despesa pode ter alertas de vários métodos, por isso há mais alertas
  que despesas sinalizadas".

### 2.2 Importação com erros por linha (US01) — 2 min
- Menu **Importar** → enviar `dados/exemplos/importacao_demonstracao.csv`.
- **Mostrar:** 11 linhas, **9 importadas, 2 com erro**, listadas por linha:
  - linha 11: "valor é obrigatório";
  - linha 12: "data inválida: '31/02/2026' (use AAAA-MM-DD ou DD/MM/AAAA)".
- **Falar:** o arquivo está no formato do Excel brasileiro (`;` e vírgula decimal); as
  linhas válidas entram mesmo com erros em outras; as estatísticas de referência (US02,
  menu **Estatísticas**) foram recalculadas.

### 2.3 Análise (US03, US04, US05) — 1 min
- Menu **Análises** → **Executar análise**.
- **Mostrar:** "5.009 despesa(s) analisada(s), 8 alerta(s) novo(s)" e, no detalhe,
  os alertas por método (Z-score 1, IQR 1, Isolation Forest 5, contextual 1) e os
  **parâmetros e a seed registrados** (RNF06).
- **Falar:** os 596 alertas anteriores não foram duplicados; só as despesas novas
  geraram alertas.

### 2.4 Alertas e filtros (US06, US10) — 2 min
- Menu **Alertas** → filtrar **Despesas de 24/08/2026 até 30/08/2026** (o filtro aplica
  sozinho) e depois **Funcionário F019**.
- **Mostrar os motivos em linguagem simples** (RNF05):

| Despesa do exemplo | Método | Motivo exibido |
|---|---|---|
| Passagem aérea internacional | Z-score | "Valor R$ 14.900,00 é 14,5x a média da categoria Viagens (R$ 1.030,39); z = 14,5, limiar 3." |
| | IQR | "Valor R$ 14.900,00 acima do limite superior da categoria Viagens (Q3 + 1,5 × IQR = R$ 2.187,50)." |
| | Isolation Forest | "Valor R$ 14.900,00 muito acima do habitual da categoria Viagens." |
| Licença de software (3 partes: R$ 955, 962 e 971) | Isolation Forest | "Valor R$ 955,00 entre 85% e 100% do limite de R$ 1.000,00, com mais 2 lançamentos do funcionário F019 na mesma faixa em até 5 dias (possível fracionamento)." |
| Abastecimento | Isolation Forest | "Lançada num domingo (30/08/2026)." |
| Diária de hotel | Contextual | "A combinação conta 3.1.06.001 × centro de custo CC-COM não aparece em nenhuma outra despesa da categoria Hospedagem (506 despesas)." |

- **Falar:** as três despesas "normais" do arquivo não geraram alerta.

### 2.5 Revisão e parecer (US07, US08, RF12) — 3 min
- Abrir o alerta da **Passagem aérea internacional** (Z-score).
- Tentar registrar **Irregular sem observação** → a tela recusa (observação obrigatória).
- Registrar **Necessita justificativa** com "Pedir a autorização da viagem ao gestor".
- Registrar um **novo parecer**: **Aprovado**, "Viagem autorizada pela diretoria".
- **Mostrar** o histórico com os dois pareceres, autor e horário.
- **Falar:** "aprovado" quer dizer que a **despesa** é regular (o alerta foi um falso
  positivo). Pareceres não podem ser alterados nem apagados, nem direto no banco
  (trigger no PostgreSQL, RNF02): uma nova decisão é um novo parecer.
- Abrir o alerta do **Abastecimento no domingo** e registrar **Irregular** com uma
  observação (será usado no relatório).

### 2.6 Relatório mensal (US11) — 2 min
- Menu **Relatório** → **agosto de 2026**.
- **Mostrar** a taxa de confirmação com a amostra, "50,00% (1 de 2)": a passagem foi
  aprovada e o abastecimento, irregular. Explicar a fórmula irregular ÷ (aprovado + irregular).
- **Baixar PDF** e abrir: mesmo conteúdo, com o aviso de indício no topo.
- **Baixar CSV** e abrir no Excel (formato brasileiro).

### 2.7 Perfis, parâmetros e usuários (US12, RNF03) — 2 min
- Na janela anônima, entrar como **auditora@exemplo.com**: o menu não tem
  **Usuários**, e **Parâmetros** aparece só para consulta.
- Como administrador, em **Parâmetros**, tentar o limiar do Z-score **0,5** → recusado
  ("use um valor de 1 a 10"). Não é preciso salvar um valor válido; se salvar, volte
  ao padrão (3) depois.
- Em **Usuários**, **desativar** a auditora e recarregar a janela anônima: ela perde o
  acesso na hora. Reativar em seguida.

### 2.8 Reprocessamento automático e experimento — 2 min
- `docker compose logs agendador`: o job verifica a cada 15 minutos se há despesas
  novas e, se houver, analisa sozinho ("job agendado" na tela **Análises**).
- Resultados do experimento (`experimentos/resultados/metricas.csv`, base seed 42):

| Avaliação | Precisão | Recall | F1 | Taxa de FP |
|---|---|---|---|---|
| Isolation Forest | 0,708 | 0,819 | 0,760 | 0,015 |
| Contextual + Isolation Forest | 0,738 | 0,954 | 0,832 | 0,015 |
| Z-score + contextual + Isolation Forest | 0,716 | 0,958 | 0,820 | 0,017 |

- **Falar:** cada método cobre um tipo de anomalia (valores extremos, combinações
  incompatíveis, duplicidade, fracionamento, fim de semana); combinados, pegam quase
  todas. Os resultados se repetem com outra base (seed 7, em `resultados/seed_7/`).

---

## 3. Perguntas prováveis

| Pergunta | Resposta |
|---|---|
| O sistema acusa funcionários? | Não. Todo alerta é um indício que exige revisão humana; a interface e o PDF deixam isso explícito (RNF04). |
| Por que o Isolation Forest sinaliza a despesa original de uma duplicata? | Porque as duas têm o mesmo valor repetido; o motivo aponta o par, e o auditor aprova a original. No experimento isso conta como falso positivo (30 dos 73 do método). |
| Fracionamento em só 2 parcelas é detectado? | Nem sempre: o sinal é fraco. Com 3 parcelas, como no exemplo, é detectado. É uma limitação a relatar. |
| A base sintética não favorece os métodos? | Os atributos vêm da definição das anomalias, e as janelas e faixas foram fixadas antes do experimento; o resultado se mantém com outra seed. Em dados reais, lançamentos legítimos em fim de semana existem e reduziriam o desempenho desse atributo. |
| Uma taxa de confirmação de 100% é confiável? | Depende da amostra, por isso ela aparece ao lado ("1 de 1"). |
| E se mudarem os parâmetros? | Vale para as próximas análises; cada análise registra os parâmetros e a seed que usou, então é possível reproduzi-la. |

## 4. Se algo der errado

- O app não sobe no Codespace: seção "Problemas conhecidos" do README.
- Os números não batem: o banco não estava limpo. Refaça a preparação (seção 1).
- Depois da demonstração, o banco fica com os pareceres de teste, que não podem ser
  apagados (RNF02). Para outra apresentação, refaça a seção 1.
