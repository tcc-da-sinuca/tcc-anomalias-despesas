"""Consultas de alertas e execuções de análise."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload, selectinload

from app.extensoes import db
from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise
from app.models.dominio import METODOS, SITUACAO_VALIDA, STATUS_PENDENTE, STATUS_REVISAO

POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 200

# Filtros de texto da US10: comparação exata com o campo da despesa.
CAMPOS_DESPESA = ("categoria", "conta_contabil", "centro_custo", "funcionario")

# Ordenações da lista de alertas: chave do parâmetro "ordem" → rótulo na tela.
ORDEM_PADRAO = "padrao"
ORDENACOES = {
    ORDEM_PADRAO: "Pendentes primeiro, maior score",
    "data_desc": "Data da despesa (mais recente primeiro)",
    "data_asc": "Data da despesa (mais antiga primeiro)",
    "valor_desc": "Valor (maior primeiro)",
    "valor_asc": "Valor (menor primeiro)",
}


class FiltroInvalidoError(ValueError):
    """Valor de filtro inválido. ``campo`` indica o parâmetro com problema."""

    def __init__(self, campo: str, mensagem: str):
        super().__init__(mensagem)
        self.campo = campo


@dataclass(frozen=True)
class FiltrosAlertas:
    """Filtros combináveis da lista de alertas (RF10 / US10). Campo vazio = sem filtro.

    O período (``data_inicio`` e ``data_fim``, inclusive) se refere à **data da
    despesa**, não à data de criação do alerta.
    """

    data_inicio: date | None = None
    data_fim: date | None = None
    categoria: str | None = None
    conta_contabil: str | None = None
    centro_custo: str | None = None
    funcionario: str | None = None
    status: str | None = None
    metodo: str | None = None
    execucao_id: int | None = None

    @classmethod
    def de_parametros(cls, parametros: Mapping[str, str]) -> "FiltrosAlertas":
        """Lê os filtros da query string. Levanta ``FiltroInvalidoError``."""

        def texto(nome):
            valor = (parametros.get(nome) or "").strip()
            return valor or None

        def data(nome):
            valor = texto(nome)
            if valor is None:
                return None
            try:
                return date.fromisoformat(valor)
            except ValueError:
                raise FiltroInvalidoError(
                    nome, f"{nome}: use uma data no formato AAAA-MM-DD."
                ) from None

        status, metodo = texto("status"), texto("metodo")
        if status is not None and status not in STATUS_REVISAO:
            raise FiltroInvalidoError(
                "status", f"status inválido. Use um de: {', '.join(STATUS_REVISAO)}."
            )
        if metodo is not None and metodo not in METODOS:
            raise FiltroInvalidoError(
                "metodo", f"método inválido. Use um de: {', '.join(METODOS)}."
            )
        execucao = texto("execucao_id")
        if execucao is not None and not execucao.isdigit():
            raise FiltroInvalidoError("execucao_id", "execucao_id deve ser um número.")

        filtros = cls(
            data_inicio=data("data_inicio"),
            data_fim=data("data_fim"),
            **{campo: texto(campo) for campo in CAMPOS_DESPESA},
            status=status,
            metodo=metodo,
            execucao_id=int(execucao) if execucao is not None else None,
        )
        if filtros.data_inicio and filtros.data_fim and filtros.data_inicio > filtros.data_fim:
            raise FiltroInvalidoError("data_fim", "A data final não pode ser anterior à inicial.")
        return filtros

    def como_parametros(self) -> dict[str, str]:
        """Só os filtros preenchidos, como texto, para montar links (paginação etc.)."""
        return {
            nome: valor.isoformat() if isinstance(valor, date) else str(valor)
            for nome, valor in asdict(self).items()
            if valor is not None
        }

    @property
    def ativos(self) -> int:
        return len(self.como_parametros())


def ler_ordem(valor: str | None) -> str:
    """Valida o parâmetro ``ordem``. Vazio = ordem padrão. Levanta ``FiltroInvalidoError``."""
    ordem = (valor or "").strip() or ORDEM_PADRAO
    if ordem not in ORDENACOES:
        raise FiltroInvalidoError("ordem", f"ordem inválida. Use uma de: {', '.join(ORDENACOES)}.")
    return ordem


def _criterios_de_ordem(ordem: str) -> list:
    """Colunas de ORDER BY. O id no fim desempata, para a paginação não pular nem repetir."""
    if ordem == "data_desc":
        return [Despesa.data.desc(), AlertaAnomalia.id.desc()]
    if ordem == "data_asc":
        return [Despesa.data.asc(), AlertaAnomalia.id.asc()]
    if ordem == "valor_desc":
        return [Despesa.valor.desc(), AlertaAnomalia.id.desc()]
    if ordem == "valor_asc":
        return [Despesa.valor.asc(), AlertaAnomalia.id.asc()]
    pendente_primeiro = case((AlertaAnomalia.status_revisao == STATUS_PENDENTE, 0), else_=1)
    return [pendente_primeiro, AlertaAnomalia.score.desc(), AlertaAnomalia.id]


def paginar_alertas(
    pagina: int = 1,
    por_pagina: int = POR_PAGINA_PADRAO,
    filtros: FiltrosAlertas | None = None,
    ordem: str = ORDEM_PADRAO,
):
    """Alertas que atendem a todos os filtros ao mesmo tempo. Retorna um ``Pagination``.

    ``ordem`` é uma das chaves de ``ORDENACOES``; a padrão põe os pendentes primeiro e,
    dentro de cada status, o maior score primeiro.
    """
    filtros = filtros or FiltrosAlertas()
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAXIMO))
    # Alertas de despesas pendentes ou rejeitadas são tratados nos pedidos de aprovação.
    consulta = (
        select(AlertaAnomalia)
        .join(AlertaAnomalia.despesa)
        .where(Despesa.situacao == SITUACAO_VALIDA)
        .options(joinedload(AlertaAnomalia.despesa))
    )
    if filtros.status:
        consulta = consulta.where(AlertaAnomalia.status_revisao == filtros.status)
    if filtros.metodo:
        consulta = consulta.where(AlertaAnomalia.metodo == filtros.metodo)
    if filtros.execucao_id is not None:
        consulta = consulta.where(AlertaAnomalia.execucao_id == filtros.execucao_id)
    if filtros.data_inicio:
        consulta = consulta.where(Despesa.data >= filtros.data_inicio)
    if filtros.data_fim:
        consulta = consulta.where(Despesa.data <= filtros.data_fim)
    for campo in CAMPOS_DESPESA:
        valor = getattr(filtros, campo)
        if valor:
            consulta = consulta.where(getattr(Despesa, campo) == valor)
    consulta = consulta.order_by(*_criterios_de_ordem(ordem))
    return db.paginate(consulta, page=max(pagina, 1), per_page=por_pagina, error_out=False)


def obter_alerta(alerta_id: int) -> AlertaAnomalia | None:
    """Alerta com a despesa, a execução e os pareceres já carregados."""
    consulta = (
        select(AlertaAnomalia)
        .where(AlertaAnomalia.id == alerta_id)
        .options(
            joinedload(AlertaAnomalia.despesa),
            joinedload(AlertaAnomalia.execucao),
            selectinload(AlertaAnomalia.pareceres),
        )
    )
    return db.session.scalar(consulta)


def outros_alertas_da_despesa(alerta: AlertaAnomalia) -> list[AlertaAnomalia]:
    """Alertas de outros métodos para a mesma despesa."""
    consulta = (
        select(AlertaAnomalia)
        .where(AlertaAnomalia.despesa_id == alerta.despesa_id, AlertaAnomalia.id != alerta.id)
        .order_by(AlertaAnomalia.criado_em, AlertaAnomalia.metodo)
    )
    return list(db.session.scalars(consulta))


def paginar_execucoes(pagina: int = 1, por_pagina: int = 20):
    consulta = select(ExecucaoAnalise).order_by(
        ExecucaoAnalise.iniciada_em.desc(), ExecucaoAnalise.id.desc()
    )
    return db.paginate(consulta, page=max(pagina, 1), per_page=por_pagina, error_out=False)


def alertas_por_metodo(execucao_id: int) -> dict[str, int]:
    """Quantos alertas a execução criou em cada método."""
    consulta = (
        select(AlertaAnomalia.metodo, func.count(AlertaAnomalia.id))
        .where(AlertaAnomalia.execucao_id == execucao_id)
        .group_by(AlertaAnomalia.metodo)
        .order_by(AlertaAnomalia.metodo)
    )
    return dict(db.session.execute(consulta).all())
