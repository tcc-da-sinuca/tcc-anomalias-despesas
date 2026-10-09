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

Resultado esperado da análise: **5.000 despesas, 599 alertas**.

Para os números não mudarem durante a apresentação, deixe o job de reprocessamento
parado (`REPROCESSAMENTO_INTERVALO_MIN=0` no `.env` antes de subir); depois da importação ele
analisaria a base de novo sozinho.

Deixe abertos: o navegador em <http://localhost:5000>, uma janela anônima (para o
login da auditora) e o arquivo `dados/exemplos/importacao_demonstracao.csv`.

---

## 2. Apresentação

### 2.1 Login e dashboard (US09) — 1 min
- Mostrar a tela de login (o que o sistema faz e o aviso de indício). Entrar como
  administrador (`ADMIN_EMAIL` / `ADMIN_SENHA` do `.env`).
- Mostrar a **faixa amarela** (RNF04) e o dashboard: 5.000 despesas, 431 sinalizadas
  (8,62%), 599 alertas, todos pendentes (a barra **Andamento da revisão** começa em 0%).
- **Falar:** a referência de cada despesa é o histórico do mesmo **centro de custo e conta**;
  uma despesa pode ter alertas de vários métodos, por isso há mais alertas que despesas
  sinalizadas.

### 2.2 Lançamento com aprovação prévia (US01 + aprovação prévia) — 3 min
- Na janela anônima, entrar como **auditora@exemplo.com**. Menu **Dados → Importar** →
  enviar `dados/exemplos/importacao_demonstracao.csv` (também sai do botão **Baixar arquivo
  de exemplo (CSV)**).
- **Mostrar** o resultado do lote: 11 linhas, **9 importadas, 2 com erro** (linha 11: "valor é
  obrigatório"; linha 12: "data inválida: '31/02/2026'"), e a **verificação no lançamento**:
  **3 dentro do padrão**, **5 aguardando aprovação**, **1 rejeitada automaticamente**.
- **Falar:** os quatro métodos rodaram na hora contra o histórico; o que está fora do padrão
  não entra como válido e vira pedido para o administrador. O selo amarelo no menu
  **Pedidos** mostra 5 pendentes.

### 2.3 Rejeição automática e encaminhamento — 2 min
- Ainda como auditora: **Pedidos → Rejeitados automaticamente** → pedido da **Passagem aérea
  internacional** (R$ 14.900,00).
- **Mostrar** os motivos com o score colorido pela gravidade:

| Método | Score | Motivo exibido |
|---|---|---|
| IQR | 21,67 · **14,45x o limite** (crítica) | "Valor R$ 14.900,00 acima do limite superior do centro de custo CC-COM na conta contábil 3.1.01.001 (Q3 + 1,5 × IQR = R$ 2.153,90)." |
| Z-score | 13,17 · **4,39x o limite** (crítica) | "Valor R$ 14.900,00 é 14,4x a média do centro de custo CC-COM na conta contábil 3.1.01.001 (R$ 1.036,32); z = 13,2, limiar 3." |
| Isolation Forest | 0,74 · 1,27x o limite (alta) | "Valor R$ 14.900,00 muito acima do habitual do centro de custo CC-COM na conta contábil 3.1.01.001." |

- Encaminhar com a justificativa "Viagem internacional autorizada pela diretoria; anexo a
  autorização." → o pedido volta como **pendente prioritário**.
- **Falar:** só o Z-score e o IQR chegam a "crítica"; no experimento, toda rejeição automática
  foi de uma anomalia de verdade (13 de 13 e 8 de 8, seeds 42 e 7). O encaminhamento garante
  que uma despesa legítima chegue a um humano.

### 2.4 Decisão do administrador — 2 min
- Na janela do administrador: o selo do menu fica **vermelho** (há prioritário) e o
  dashboard mostra "6 pedido(s) de aprovação pendente(s), 1 prioritário(s)".
- **Pedidos**: o #1 (passagem) aparece **no topo, em destaque**, seguido por gravidade
  (diária de hotel "alta", abastecimento "moderada", três parcelas de software "leve").
- Abrir o #1 → **Aprovar** com "Autorização da diretoria conferida." → mostrar o histórico do
  pedido (aberto, rejeitado pelo sistema, encaminhado, aprovado) e a despesa **Válida**.
- Abrir o **Abastecimento** (domingo) → **Rejeitar** sem justificativa (recusado) e depois com
  "Abastecimento em domingo sem viagem registrada."
- **Falar:** só o administrador decide, e nunca uma despesa que ele mesmo lançou
  (segregação de funções); o histórico dos pedidos não pode ser alterado nem no banco.

### 2.5 Alertas: gravidade e decisão rápida (US06, US07, US10) — 2 min
- Menu **Alertas** → filtrar **Despesas de 01/08/2026 até 31/08/2026** (aplica sozinho).
- **Mostrar** o score colorido: o primeiro alerta (IQR, R$ 2.167,52, Treinamentos) está em
  vermelho, **27,37x o limite**; os de Z-score logo abaixo, em laranja (alta).
- No primeiro, botão de **decisão rápida** → **Rejeitar** com "Valor sem comprovante." → volta
  para a lista com os filtros e a mensagem "Alerta #… rejeitado (irregular)".
- Botão **"i"** de outro alerta → detalhe com o **contexto do grupo** e o histórico de pareceres.
- **Falar:** "aprovado" quer dizer que a **despesa** é regular; os pareceres não podem ser
  alterados nem apagados (RNF02).

### 2.6 Relatório mensal (US11) — 2 min
- Menu **Relatório** → **agosto de 2026**.
- **Mostrar** a taxa de confirmação com a amostra, **"25,00% (1 de 4)"**: os 3 alertas da
  passagem aprovada contam como "aprovado" e o alerta rejeitado na decisão rápida, como
  "irregular". Despesas pendentes e rejeitadas não entram no relatório.
- **Baixar PDF** (com o aviso de indício no topo) e **Baixar CSV** (formato do Excel brasileiro).

### 2.7 Perfis, parâmetros e usuários (US12, RNF03) — 2 min
- Na janela anônima, entrar como **auditora@exemplo.com**: o menu não tem
  **Configuração → Usuários**, e **Configuração → Parâmetros** aparece só para consulta.
- Como administrador, em **Configuração → Parâmetros**, tentar o limiar do Z-score **0,5** → recusado
  ("use um valor de 1 a 10"). Não é preciso salvar um valor válido; se salvar, volte
  ao padrão (3) depois.
- Em **Configuração → Usuários**, **desativar** a auditora e recarregar a janela anônima: ela perde o
  acesso na hora. Reativar em seguida.

### 2.8 Reprocessamento automático e experimento — 2 min
- `docker compose logs agendador`: o job verifica a cada 15 minutos se há despesas
  novas e, se houver, analisa sozinho ("job agendado" na tela **Análises**).
- Resultados do experimento (`experimentos/resultados/metricas.csv`, base seed 42):

| Avaliação | Precisão | Recall | F1 | Taxa de FP |
|---|---|---|---|---|
| Isolation Forest | 0,756 | 0,875 | 0,811 | 0,013 |
| Contextual + Isolation Forest | 0,774 | 0,968 | 0,860 | 0,013 |
| Z-score + contextual + Isolation Forest | 0,715 | 0,977 | 0,826 | 0,018 |

- **Falar:** cada método cobre um tipo de anomalia (valores extremos, combinações
  incompatíveis, duplicidade, fracionamento, fim de semana); combinados, pegam quase
  todas. Os resultados se repetem com outra base (seed 7, em `resultados/seed_7/`).

---

## 3. Perguntas prováveis

| Pergunta | Resposta |
|---|---|
| O sistema acusa funcionários? | Não. Todo alerta é um indício; a interface e o PDF deixam isso explícito (RNF04). A única decisão automática é a rejeição de lançamentos com gravidade crítica, e quem lançou pode encaminhar o pedido para um humano decidir, com prioridade. |
| A rejeição automática não contradiz "sempre exige revisão humana"? | É uma exceção decidida pela equipe e registrada (item 34). Ela só vale para gravidade crítica no Z-score ou no IQR, que no experimento acertou em 13 de 13 e 8 de 8 casos (seeds 42 e 7), e o encaminhamento devolve o caso a um humano. |
| Por que o administrador não aprova a própria despesa? | Segregação de funções: quem lança não decide sobre o próprio lançamento. |
| Por que o Isolation Forest sinaliza a despesa original de uma duplicata? | Na análise da base inteira, as duas têm o mesmo valor repetido; o motivo aponta o par, e o auditor aprova a original. No experimento, isso conta como falso positivo. No lançamento isso não acontece: a original entra antes de a cópia existir. |
| Por que o Isolation Forest nunca chega a "crítica"? | A escala dele depende do tamanho de cada base, e no experimento os alertas mais extremos dele acertavam só metade das vezes. Por isso, ele gera pedidos para revisão, mas não rejeita sozinho. |
| A base sintética não favorece os métodos? | Os atributos vêm da definição das anomalias, e as janelas e faixas foram fixadas antes do experimento; o resultado se mantém com outra seed. Em dados reais, lançamentos legítimos em fim de semana existem e reduziriam o desempenho desse atributo. |
| Uma taxa de confirmação de 100% é confiável? | Depende da amostra, por isso ela aparece ao lado ("1 de 1"). |
| E se mudarem os parâmetros? | Vale para as próximas análises; cada análise registra os parâmetros e a seed que usou, então é possível reproduzi-la. |

## 4. Se algo der errado

- O app não sobe no Codespace: seção "Problemas conhecidos" do README.
- Os números não batem: o banco não estava limpo. Refaça a preparação (seção 1).
- Depois da demonstração, o banco fica com os pareceres de teste, que não podem ser
  apagados (RNF02). Para outra apresentação, refaça a seção 1.
