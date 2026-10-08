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
SQL_STATUS_PARECER = _sql_in(STATUS_PARECER)
SQL_STATUS_EXIGEM_OBSERVACAO = _sql_in(STATUS_EXIGEM_OBSERVACAO)
