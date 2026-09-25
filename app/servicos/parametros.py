"""Serviço de parâmetros dos métodos de detecção (RF13 / US12).

Garante os parâmetros padrão, lê os valores já convertidos em número para o motor
e permite que o administrador os altere, com validação de faixa (``REGRAS``).

Uma alteração vale para as próximas análises; os alertas já gerados não mudam, e
cada ``ExecucaoAnalise`` guarda os parâmetros que usou (RNF06).
"""

import math
from dataclasses import dataclass

from sqlalchemy import select

from app.extensoes import db
from app.models import ParametroMetodo, Usuario
from app.models.base import agora_utc
from app.models.dominio import PARAMETROS_PADRAO


@dataclass(frozen=True)
class RegraParametro:
    """Tipo, faixa válida e textos de ajuda de um parâmetro."""

    metodo: str
    chave: str
    rotulo: str
    ajuda: str
    tipo: type  # int ou float
    minimo: float
    maximo: float
    minimo_exclusivo: bool = False  # True: o valor precisa ser maior que o mínimo

    @property
    def nome(self) -> str:
        return f"{self.metodo}.{self.chave}"

    @property
    def faixa(self) -> str:
        abre = "maior que" if self.minimo_exclusivo else "de"
        ate = "e até" if self.minimo_exclusivo else "a"
        return f"{abre} {exibir(self.minimo)} {ate} {exibir(self.maximo)}"


# Ordem de exibição. Faixas registradas no item 21 de MUDANCAS_PARA_DOCUMENTACAO.md.
REGRAS = (
    RegraParametro(
        "zscore",
        "limiar",
        "Limiar do |z|",
        "Sinaliza a despesa cujo valor fica a mais que este número de desvios padrão "
        "da média da categoria. Menor = mais alertas.",
        float,
        1,
        10,
    ),
    RegraParametro(
        "iqr",
        "fator",
        "Fator do IQR",
        "Sinaliza valores além de Q3 + fator × IQR (ou abaixo de Q1 − fator × IQR) na "
        "categoria. Menor = mais alertas.",
        float,
        0.5,
        10,
    ),
    RegraParametro(
        "contextual",
        "frequencia_minima",
        "Frequência mínima da combinação",
        "Sinaliza a combinação conta × centro de custo que aparece em menos que esta "
        "fração das despesas da categoria (0,01 = 1%). Maior = mais alertas.",
        float,
        0,
        0.5,
        minimo_exclusivo=True,
    ),
    RegraParametro(
        "isolation_forest",
        "contamination",
        "Proporção esperada de anomalias",
        "Fração das despesas que o Isolation Forest sinaliza (0,05 = 5%). Maior = mais alertas.",
        float,
        0,
        0.5,
        minimo_exclusivo=True,
    ),
    RegraParametro(
        "isolation_forest",
        "random_state",
        "Seed do Isolation Forest",
        "Semente aleatória. Com a mesma seed e os mesmos dados, o resultado se repete (RNF06).",
        int,
        0,
        2**32 - 1,
    ),
    RegraParametro(
        "isolation_forest",
        "limite_aprovacao",
        "Limite de aprovação (R$)",
        "Valor a partir do qual a despesa precisa de aprovação. Lançamentos entre 85% e "
        "100% dele, repetidos pelo mesmo funcionário, indicam possível fracionamento.",
        float,
        0,
        1_000_000_000,
        minimo_exclusivo=True,
    ),
)
REGRAS_POR_NOME = {regra.nome: regra for regra in REGRAS}


class ParametrosInvalidosError(ValueError):
    """Um ou mais valores inválidos. ``erros`` mapeia ``metodo.chave`` para a mensagem."""

    def __init__(self, erros: dict[str, str]):
        super().__init__("; ".join(erros.values()))
        self.erros = erros


def _texto(numero: float) -> str:
    """Número como é gravado, sem zeros inúteis: 2.50 → "2.5", 1000.0 → "1000"."""
    return format(numero, ".12g")


def exibir(numero: float) -> str:
    """Número para a tela, com vírgula decimal: 0.05 → "0,05"."""
    return _texto(numero).replace(".", ",")


def garantir_parametros_padrao() -> int:
    """Insere os parâmetros padrão que ainda não existem. Retorna quantos inseriu.

    Não sobrescreve valores já configurados. Não faz commit.
    """
    inseridos = 0
    for metodo, parametros in PARAMETROS_PADRAO.items():
        for chave, valor in parametros.items():
            if db.session.get(ParametroMetodo, (metodo, chave)) is None:
                db.session.add(ParametroMetodo(metodo=metodo, chave=chave, valor=valor))
                inseridos += 1
    return inseridos


def obter_parametros() -> dict[str, dict[str, float | int]]:
    """Parâmetros de cada método, como números: ``{"zscore": {"limiar": 3.0}, ...}``.

    Parte dos padrões e aplica os valores gravados em ``ParametroMetodo``.
    """
    textos = {metodo: dict(parametros) for metodo, parametros in PARAMETROS_PADRAO.items()}
    for parametro in db.session.scalars(select(ParametroMetodo)):
        textos.setdefault(parametro.metodo, {})[parametro.chave] = parametro.valor
    return {
        metodo: {chave: _converter(metodo, chave, valor) for chave, valor in parametros.items()}
        for metodo, parametros in textos.items()
    }


def _converter(metodo: str, chave: str, valor: str) -> float | int:
    regra = REGRAS_POR_NOME.get(f"{metodo}.{chave}")
    return int(valor) if regra is not None and regra.tipo is int else float(valor)


def validar(regra: RegraParametro, bruto) -> float | int:
    """Converte e valida um valor. Aceita número ou texto (com ``,`` ou ``.`` decimal)."""
    if isinstance(bruto, bool) or bruto is None:
        raise ValueError(f"{regra.rotulo}: informe um número.")
    texto = str(bruto).strip()
    if "," in texto and "." not in texto:
        texto = texto.replace(",", ".")
    try:
        numero = float(texto)
    except ValueError:
        raise ValueError(f"{regra.rotulo}: informe um número.") from None
    if not math.isfinite(numero):
        raise ValueError(f"{regra.rotulo}: informe um número.")
    if regra.tipo is int:
        if not numero.is_integer():
            raise ValueError(f"{regra.rotulo}: informe um número inteiro.")
        numero = int(numero)
    abaixo = numero <= regra.minimo if regra.minimo_exclusivo else numero < regra.minimo
    if abaixo or numero > regra.maximo:
        raise ValueError(f"{regra.rotulo}: use um valor {regra.faixa}.")
    return numero


def listar_parametros() -> list[dict]:
    """Cada parâmetro com valor atual, padrão, regra e quem alterou por último."""
    gravados = {(p.metodo, p.chave): p for p in db.session.scalars(select(ParametroMetodo))}
    lista = []
    for regra in REGRAS:
        gravado = gravados.get((regra.metodo, regra.chave))
        padrao = PARAMETROS_PADRAO[regra.metodo][regra.chave]
        lista.append(
            {
                "regra": regra,
                "valor": _converter(
                    regra.metodo, regra.chave, gravado.valor if gravado else padrao
                ),
                "padrao": _converter(regra.metodo, regra.chave, padrao),
                "alterado_por": gravado.usuario if gravado else None,
                "alterado_em": gravado.alterado_em if gravado else None,
            }
        )
    return lista


def atualizar_parametros(alteracoes: dict[str, dict], usuario: Usuario) -> list[str]:
    """Aplica ``{"metodo": {"chave": valor}}``. Retorna os ``metodo.chave`` que mudaram.

    Valida tudo antes de gravar: se algum valor for inválido, nada muda e
    ``ParametrosInvalidosError`` traz os erros por parâmetro. Não faz commit.
    """
    erros, validos = {}, {}
    if not isinstance(alteracoes, dict):
        raise ParametrosInvalidosError(
            {"geral": "Envie os parâmetros como {metodo: {chave: valor}}."}
        )
    for metodo, parametros in alteracoes.items():
        if not isinstance(parametros, dict):
            erros[str(metodo)] = f"{metodo}: envie os parâmetros como {{chave: valor}}."
            continue
        for chave, bruto in parametros.items():
            nome = f"{metodo}.{chave}"
            regra = REGRAS_POR_NOME.get(nome)
            if regra is None:
                erros[nome] = f"Parâmetro desconhecido: {nome}."
                continue
            try:
                validos[regra] = validar(regra, bruto)
            except ValueError as erro:
                erros[nome] = str(erro)
    if erros:
        raise ParametrosInvalidosError(erros)

    alterados = []
    agora = agora_utc()
    for regra, numero in validos.items():
        texto = _texto(numero)
        parametro = db.session.get(ParametroMetodo, (regra.metodo, regra.chave))
        if parametro is None:  # sem linha gravada: o valor atual é o padrão
            atual = PARAMETROS_PADRAO[regra.metodo][regra.chave]
            parametro = ParametroMetodo(metodo=regra.metodo, chave=regra.chave, valor=atual)
            db.session.add(parametro)
        if _converter(regra.metodo, regra.chave, parametro.valor) == numero:
            continue  # sem mudança: não registra alteração
        parametro.valor = texto
        parametro.alterado_por = usuario.id
        parametro.alterado_em = agora
        alterados.append(regra.nome)
    return alterados
