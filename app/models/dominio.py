"""Valores de domínio compartilhados pelos modelos, serviços e motor.

Os valores são guardados como texto no banco e validados por CHECK constraints.
Não usamos ENUM nativo do PostgreSQL para facilitar as migrations.
"""


def _sql_in(valores: tuple[str, ...]) -> str:
    """Monta a lista usada nas CHECK constraints: ('a', 'b', 'c')."""
    return "(" + ", ".join(f"'{v}'" for v in valores) + ")"


# --- Perfis de usuário (seção 4 do CLAUDE.md; o perfil "gestor" foi descartado) ---
PERFIL_AUDITOR = "auditor"
PERFIL_ADMINISTRADOR = "administrador"
PERFIS = (PERFIL_AUDITOR, PERFIL_ADMINISTRADOR)

# --- Métodos de detecção ---
METODO_ZSCORE = "zscore"
METODO_IQR = "iqr"
METODO_ISOLATION_FOREST = "isolation_forest"
METODO_CONTEXTUAL = "contextual"
METODOS = (METODO_ZSCORE, METODO_IQR, METODO_ISOLATION_FOREST, METODO_CONTEXTUAL)

# --- Gravidade de um alerta (quanto o score passou do limite do método) ---
# Os níveis e as faixas ficam no motor (motor/gravidade.py).
from motor.gravidade import NIVEIS as GRAVIDADES  # noqa: E402

# --- Status de revisão de um alerta (RF06/RF07) ---
STATUS_PENDENTE = "pendente"
STATUS_APROVADO = "aprovado"
STATUS_IRREGULAR = "irregular"
STATUS_NECESSITA_JUSTIFICATIVA = "necessita_justificativa"

# Status que um parecer pode registrar (o auditor não "volta" um alerta para pendente).
STATUS_PARECER = (STATUS_APROVADO, STATUS_IRREGULAR, STATUS_NECESSITA_JUSTIFICATIVA)
# Status possíveis de um alerta.
STATUS_REVISAO = (STATUS_PENDENTE,) + STATUS_PARECER
# Status que exigem observação no parecer (RF08 / US08).
STATUS_EXIGEM_OBSERVACAO = (STATUS_IRREGULAR, STATUS_NECESSITA_JUSTIFICATIVA)

# --- Aprovação prévia de despesas (item 34 de MUDANCAS_PARA_DOCUMENTACAO.md) ---
# Situação da despesa: só as válidas contam como histórico, análise, dashboard e relatório.
SITUACAO_VALIDA = "valida"
SITUACAO_PENDENTE = "pendente"  # fora do padrão, aguardando decisão
SITUACAO_REJEITADA = "rejeitada"
SITUACOES_DESPESA = (SITUACAO_VALIDA, SITUACAO_PENDENTE, SITUACAO_REJEITADA)

# Status do pedido de aprovação ("ticket").
SOLICITACAO_PENDENTE = "pendente"
SOLICITACAO_APROVADA = "aprovada"
SOLICITACAO_REJEITADA = "rejeitada"
SOLICITACAO_REJEITADA_AUTOMATICAMENTE = "rejeitada_automaticamente"
STATUS_SOLICITACAO = (
    SOLICITACAO_PENDENTE,
    SOLICITACAO_APROVADA,
    SOLICITACAO_REJEITADA,
    SOLICITACAO_REJEITADA_AUTOMATICAMENTE,
)

# Eventos do histórico de um pedido (somente inserção).
EVENTO_CRIADA = "criada"
EVENTO_REJEITADA_AUTOMATICAMENTE = "rejeitada_automaticamente"
EVENTO_ENCAMINHADA = "encaminhada"
EVENTO_APROVADA = "aprovada"
EVENTO_REJEITADA = "rejeitada"
TIPOS_EVENTO = (
    EVENTO_CRIADA,
    EVENTO_REJEITADA_AUTOMATICAMENTE,
    EVENTO_ENCAMINHADA,
    EVENTO_APROVADA,
    EVENTO_REJEITADA,
)

# --- Dimensões das estatísticas de referência (RF02) ---
DIMENSAO_CATEGORIA = "categoria"
DIMENSAO_CONTA = "conta_contabil"
DIMENSAO_CENTRO_CUSTO = "centro_custo"
DIMENSOES = (DIMENSAO_CATEGORIA, DIMENSAO_CONTA, DIMENSAO_CENTRO_CUSTO)

# --- Parâmetros padrão dos métodos (seção 5 do CLAUDE.md) ---
# Formato: {metodo: {chave: valor}}. Os valores ficam como texto em ParametroMetodo.
PARAMETROS_PADRAO = {
    METODO_ZSCORE: {"limiar": "3"},
    METODO_IQR: {"fator": "1.5"},
    # limite_aprovacao: valor (R$) abaixo do qual se procura fracionamento (decisão D6).
    METODO_ISOLATION_FOREST: {
        "contamination": "0.05",
        "random_state": "42",
        "limite_aprovacao": "1000",
    },
    METODO_CONTEXTUAL: {"frequencia_minima": "0.01"},
}

SQL_PERFIS = _sql_in(PERFIS)
SQL_METODOS = _sql_in(METODOS)
SQL_STATUS_REVISAO = _sql_in(STATUS_REVISAO)
SQL_GRAVIDADES = _sql_in(GRAVIDADES)
SQL_SITUACOES_DESPESA = _sql_in(SITUACOES_DESPESA)
SQL_STATUS_SOLICITACAO = _sql_in(STATUS_SOLICITACAO)
SQL_TIPOS_EVENTO = _sql_in(TIPOS_EVENTO)
SQL_STATUS_PARECER = _sql_in(STATUS_PARECER)
SQL_STATUS_EXIGEM_OBSERVACAO = _sql_in(STATUS_EXIGEM_OBSERVACAO)
