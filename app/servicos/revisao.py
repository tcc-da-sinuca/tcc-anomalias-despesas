"""Revisão de alertas: classificação e parecer do auditor (RF06–RF08 / US07, US08).

Fluxo descrito em docs/FLUXO_ANALISE.md, seção 4. Registrar um parecer é:

1. validar o status e a observação (obrigatória para ``irregular`` e
   ``necessita_justificativa``);
2. inserir o ``Parecer``, que é somente inserção (RNF02);
3. atualizar ``AlertaAnomalia.status_revisao`` com o status do parecer.

Um alerta pode receber vários pareceres (reavaliação); o ``status_revisao``
reflete o mais recente e o histórico completo continua disponível (RF12). O CHECK
do banco repete a regra da observação como segunda barreira.

Não faz commit; quem chama (rota) decide.
"""

from app.extensoes import db
from app.models import AlertaAnomalia, Parecer, Usuario
from app.models.dominio import STATUS_EXIGEM_OBSERVACAO, STATUS_PARECER

NOMES_STATUS = {
    "aprovado": "aprovado",
    "irregular": "irregular",
    "necessita_justificativa": "necessita justificativa",
}


class ParecerInvalidoError(ValueError):
    """Dados do parecer inválidos. ``campo`` indica o campo do formulário com erro."""

    def __init__(self, campo: str, mensagem: str):
        super().__init__(mensagem)
        self.campo = campo


def registrar_parecer(
    alerta: AlertaAnomalia, usuario: Usuario, status: str | None, observacao: str | None
) -> Parecer:
    """Insere um parecer e atualiza o ``status_revisao`` do alerta.

    Levanta ``ParecerInvalidoError`` para status inválido ou observação ausente
    quando ela é obrigatória.
    """
    if status not in STATUS_PARECER:
        raise ParecerInvalidoError(
            "status", "Escolha a classificação: aprovado, irregular ou necessita justificativa."
        )
    observacao = (observacao or "").strip() or None
    if status in STATUS_EXIGEM_OBSERVACAO and observacao is None:
        raise ParecerInvalidoError(
            "observacao", f"A observação é obrigatória para o status {NOMES_STATUS[status]}."
        )

    parecer = Parecer(alerta=alerta, usuario_id=usuario.id, status=status, observacao=observacao)
    db.session.add(parecer)
    alerta.status_revisao = status
    return parecer
