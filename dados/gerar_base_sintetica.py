"""Gera a base sintética de despesas com anomalias rotuladas (seção 7 do CLAUDE.md).

Uso::

    python -m dados.gerar_base_sintetica                   # seed 42, 5.000 linhas
    python -m dados.gerar_base_sintetica --seed 7 --n 10000

Saída em ``dados/gerados/``: ``despesas_sinteticas.csv``, ``despesas_sinteticas.xlsx``
e ``metadados.json`` (seed, parâmetros e contagens, para reprodutibilidade — RNF06).

Como a base é montada:

- despesas normais em dias úteis, com valor log-normal por categoria, contas e
  centros de custo típicos de cada categoria e sazonalidade mensal;
- anomalias injetadas como linhas novas, rotuladas com ``anomalia_real = 1`` e
  ``tipo_anomalia``: valor extremo, combinação categoria/conta/centro de custo
  incompatível, despesa duplicada, fracionamento logo abaixo de um limite e
  lançamento em fim de semana ou feriado;
- ``grupo_anomalia`` liga linhas relacionadas: as partes de um fracionamento
  (``FRAC-...``) e a despesa duplicada com a sua original (``DUP-...``). A
  original continua com ``anomalia_real = 0``.

Os rótulos e o ``id_sintetico`` servem ao experimento e não vão para o banco.
"""

import argparse
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from math import log
from pathlib import Path

import numpy as np
import pandas as pd

from motor.calendario import dias_no_intervalo, eh_dia_util

PASTA_PADRAO = Path(__file__).resolve().parent / "gerados"
NOME_BASE = "despesas_sinteticas"

COLUNAS_DESPESA = (
    "data",
    "valor",
    "categoria",
    "conta_contabil",
    "centro_custo",
    "funcionario",
    "descricao",
)
COLUNAS_ROTULO = ("anomalia_real", "tipo_anomalia", "grupo_anomalia")
COLUNAS = ("id_sintetico",) + COLUNAS_DESPESA + COLUNAS_ROTULO

TIPO_VALOR_EXTREMO = "valor_extremo"
TIPO_COMBINACAO_INCOMPATIVEL = "combinacao_incompativel"
TIPO_DUPLICADA = "duplicada"
TIPO_FRACIONAMENTO = "fracionamento"
TIPO_FIM_SEMANA_FERIADO = "fim_semana_feriado"
TIPOS_ANOMALIA = (
    TIPO_VALOR_EXTREMO,
    TIPO_COMBINACAO_INCOMPATIVEL,
    TIPO_DUPLICADA,
    TIPO_FRACIONAMENTO,
    TIPO_FIM_SEMANA_FERIADO,
)

# Valor extremo: de 5 a 15 vezes a mediana da categoria.
FATOR_EXTREMO = (5.0, 15.0)
# Fracionamento: 2 a 4 lançamentos entre 88% e 99,9% do limite, em até 3 dias úteis.
PARTES_FRACIONAMENTO = (2, 4)
FAIXA_FRACIONAMENTO = (0.88, 0.999)
JANELA_FRACIONAMENTO_DIAS = 3
# Duplicada: mesma despesa lançada de 0 a 3 dias úteis depois da original.
ATRASO_DUPLICADA_DIAS = (0, 3)

# Centro de custo → número de funcionários.
CENTROS_CUSTO = {"CC-ADM": 6, "CC-COM": 12, "CC-TI": 8, "CC-OPS": 10, "CC-RH": 4}

# Multiplicador do volume de lançamentos por mês (jan..dez).
VOLUME_MENSAL = (0.8, 0.95, 1.05, 1.0, 1.0, 1.0, 0.95, 1.05, 1.05, 1.05, 1.0, 0.8)


@dataclass(frozen=True)
class Categoria:
    mediana: float  # R$; a média da log-normal fica acima disso
    sigma: float  # desvio padrão do logaritmo do valor
    peso: float  # participação no volume de lançamentos
    contas: tuple[str, ...]
    centros: dict[str, int]  # centro de custo → peso
    descricoes: tuple[str, ...]
    sazonalidade: tuple[float, ...] = (1.0,) * 12  # multiplicador por mês (jan..dez)


# Plano de contas fictício: cada conta pertence a uma única categoria.
CATEGORIAS = {
    "Viagens": Categoria(
        mediana=850,
        sigma=0.55,
        peso=12,
        contas=("3.1.01.001",),
        centros={"CC-COM": 5, "CC-OPS": 3, "CC-ADM": 1, "CC-TI": 1},
        descricoes=(
            "Passagem aérea",
            "Passagem aérea ida e volta",
            "Passagem rodoviária",
            "Remarcação de passagem",
        ),
        sazonalidade=(0.5, 0.9, 1.2, 1.2, 1.2, 1.0, 0.8, 1.1, 1.2, 1.2, 1.0, 0.6),
    ),
    "Hospedagem": Categoria(
        mediana=420,
        sigma=0.45,
        peso=10,
        contas=("3.1.01.002",),
        centros={"CC-COM": 5, "CC-OPS": 3, "CC-ADM": 1, "CC-TI": 1},
        descricoes=("Diárias de hotel", "Hospedagem em visita a cliente", "Hotel para evento"),
        sazonalidade=(0.5, 0.9, 1.2, 1.2, 1.2, 1.0, 0.8, 1.1, 1.2, 1.2, 1.0, 0.6),
    ),
    "Alimentação": Categoria(
        mediana=55,
        sigma=0.5,
        peso=30,
        contas=("3.1.02.001", "3.1.02.002"),
        centros={"CC-ADM": 2, "CC-COM": 3, "CC-TI": 2, "CC-OPS": 3, "CC-RH": 1},
        descricoes=("Refeição em viagem", "Almoço com cliente", "Lanche em reunião", "Jantar"),
    ),
    "Combustível": Categoria(
        mediana=180,
        sigma=0.4,
        peso=18,
        contas=("3.1.03.001",),
        centros={"CC-COM": 4, "CC-OPS": 5},
        descricoes=("Abastecimento de veículo", "Combustível para visita técnica"),
    ),
    "Material de escritório": Categoria(
        mediana=120,
        sigma=0.7,
        peso=14,
        contas=("3.1.04.001",),
        centros={"CC-ADM": 4, "CC-RH": 2, "CC-COM": 1, "CC-TI": 1, "CC-OPS": 1},
        descricoes=("Papel e toner", "Material de papelaria", "Suprimentos de escritório"),
        sazonalidade=(1.5, 1.3, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.8),
    ),
    "Software": Categoria(
        mediana=350,
        sigma=0.8,
        peso=8,
        contas=("3.1.05.001", "3.1.05.002"),
        centros={"CC-TI": 6, "CC-ADM": 1},
        descricoes=("Licença de software", "Assinatura mensal de serviço em nuvem", "Plugin"),
    ),
    "Treinamentos": Categoria(
        mediana=1200,
        sigma=0.6,
        peso=8,
        contas=("3.1.06.001",),
        centros={"CC-RH": 3, "CC-TI": 3, "CC-COM": 1, "CC-ADM": 1, "CC-OPS": 1},
        descricoes=("Curso online", "Inscrição em congresso", "Treinamento presencial"),
        sazonalidade=(0.3, 0.8, 1.5, 1.5, 1.5, 0.8, 0.8, 1.4, 1.4, 1.4, 0.8, 0.3),
    ),
}

# Categorias em que o fracionamento de uma compra é plausível.
CATEGORIAS_FRACIONAMENTO = ("Material de escritório", "Software", "Hospedagem")


@dataclass(frozen=True)
class ConfiguracaoBase:
    seed: int = 42
    n: int = 5000  # total de linhas (normais + anômalas)
    inicio: date = date(2025, 9, 1)
    fim: date = date(2026, 8, 31)
    taxa_anomalias: float = 0.03  # eventos de anomalia / n
    limite_fracionamento: Decimal = field(default=Decimal("1000.00"))

    def validar(self) -> None:
        if self.fim <= self.inicio:
            raise ValueError("A data final deve ser posterior à inicial.")
        if (self.fim - self.inicio).days < 60:
            raise ValueError("Use um período de pelo menos 60 dias.")
        if not 0 < self.taxa_anomalias <= 0.2:
            raise ValueError("A taxa de anomalias deve estar entre 0 e 0,2.")
        if self.limite_fracionamento <= 0:
            raise ValueError("O limite de fracionamento deve ser positivo.")
        if self.n < 200:
            raise ValueError("Gere pelo menos 200 linhas.")


def _dinheiro(valor: float) -> Decimal:
    """Arredonda para centavos, com mínimo de R$ 1,00."""
    return max(Decimal(str(valor)).quantize(Decimal("0.01"), ROUND_HALF_UP), Decimal("1.00"))


def _funcionarios_por_centro() -> dict[str, list[str]]:
    funcionarios, proximo = {}, 1
    for centro, quantidade in CENTROS_CUSTO.items():
        funcionarios[centro] = [f"F{i:03d}" for i in range(proximo, proximo + quantidade)]
        proximo += quantidade
    return funcionarios


class _Gerador:
    def __init__(self, config: ConfiguracaoBase):
        self.config = config
        self.rng = np.random.default_rng(config.seed)
        dias = dias_no_intervalo(config.inicio, config.fim)
        self.dias_uteis = [d for d in dias if eh_dia_util(d)]
        self.dias_nao_uteis = [d for d in dias if not eh_dia_util(d)]
        self.posicao_dia_util = {d: i for i, d in enumerate(self.dias_uteis)}
        self.funcionarios = _funcionarios_por_centro()

    # --- sorteios -------------------------------------------------------------

    def _escolher(self, opcoes, pesos=None):
        opcoes = list(opcoes)
        if pesos is not None:
            pesos = np.asarray(pesos, dtype=float)
            pesos = pesos / pesos.sum()
        return opcoes[self.rng.choice(len(opcoes), p=pesos)]

    def _valor(self, categoria: Categoria) -> Decimal:
        return _dinheiro(self.rng.lognormal(log(categoria.mediana), categoria.sigma))

    def _deslocar_dia_util(self, dia: date, dias: int) -> date:
        """Avança ``dias`` dias úteis; se passar do fim do período, recua."""
        posicao = self.posicao_dia_util[dia] + dias
        if posicao >= len(self.dias_uteis):
            posicao = self.posicao_dia_util[dia] - dias
        return self.dias_uteis[posicao]

    @staticmethod
    def _rotular(linha: dict, tipo: str, grupo: str = "") -> dict:
        return {**linha, "anomalia_real": 1, "tipo_anomalia": tipo, "grupo_anomalia": grupo}

    # --- despesas normais -----------------------------------------------------

    def _despesa(self, dia: date, nome_categoria: str) -> dict:
        categoria = CATEGORIAS[nome_categoria]
        centro = self._escolher(categoria.centros, list(categoria.centros.values()))
        return {
            "data": dia,
            "valor": self._valor(categoria),
            "categoria": nome_categoria,
            "conta_contabil": self._escolher(categoria.contas),
            "centro_custo": centro,
            "funcionario": self._escolher(self.funcionarios[centro]),
            "descricao": self._escolher(categoria.descricoes),
            "anomalia_real": 0,
            "tipo_anomalia": "",
            "grupo_anomalia": "",
        }

    def _normais(self, quantidade: int) -> list[dict]:
        pesos_dia = np.array([VOLUME_MENSAL[d.month - 1] for d in self.dias_uteis])
        indices = self.rng.choice(
            len(self.dias_uteis), size=quantidade, p=pesos_dia / pesos_dia.sum()
        )
        normais = []
        for indice in indices:
            dia = self.dias_uteis[indice]
            pesos = [c.peso * c.sazonalidade[dia.month - 1] for c in CATEGORIAS.values()]
            normais.append(self._despesa(dia, self._escolher(CATEGORIAS, pesos)))
        return normais

    # --- anomalias ------------------------------------------------------------

    def _valor_extremo(self, base: dict) -> dict:
        mediana = CATEGORIAS[base["categoria"]].mediana
        valor = _dinheiro(mediana * self.rng.uniform(*FATOR_EXTREMO))
        return self._rotular({**base, "valor": valor}, TIPO_VALOR_EXTREMO)

    def _combinacao_incompativel(self, base: dict) -> dict:
        """Troca o centro de custo ou a conta por um que a categoria nunca usa.

        O valor é sorteado de novo: a despesa modelo continua na base, e copiar o
        valor dela criaria um "gêmeo" que se confunde com duplicidade.
        """
        categoria = CATEGORIAS[base["categoria"]]
        base = {**base, "valor": self._valor(categoria)}
        centros_fora = [c for c in CENTROS_CUSTO if c not in categoria.centros]
        if centros_fora and self.rng.random() < 0.5:
            centro = self._escolher(centros_fora)
            alterada = {
                **base,
                "centro_custo": centro,
                "funcionario": self._escolher(self.funcionarios[centro]),
            }
        else:
            contas_fora = [
                conta
                for nome, outra in CATEGORIAS.items()
                if nome != base["categoria"]
                for conta in outra.contas
            ]
            alterada = {**base, "conta_contabil": self._escolher(contas_fora)}
        return self._rotular(alterada, TIPO_COMBINACAO_INCOMPATIVEL)

    def _duplicada(self, base: dict, numero: int) -> dict:
        grupo = f"DUP-{numero:03d}"
        base["grupo_anomalia"] = grupo  # a original continua com anomalia_real = 0
        atraso = int(self.rng.integers(ATRASO_DUPLICADA_DIAS[0], ATRASO_DUPLICADA_DIAS[1] + 1))
        dia = self._deslocar_dia_util(base["data"], atraso)
        return self._rotular({**base, "data": dia}, TIPO_DUPLICADA, grupo)

    def _fracionamento(self, partes: int, numero: int) -> list[dict]:
        """Uma compra dividida em ``partes`` lançamentos logo abaixo do limite."""
        grupo = f"FRAC-{numero:03d}"
        nome_categoria = self._escolher(CATEGORIAS_FRACIONAMENTO)
        modelo = self._despesa(self.dias_uteis[0], nome_categoria)
        limite = self.config.limite_fracionamento
        inicio = int(self.rng.integers(0, len(self.dias_uteis) - JANELA_FRACIONAMENTO_DIAS))
        linhas = []
        for _ in range(partes):
            dia = self.dias_uteis[inicio + int(self.rng.integers(0, JANELA_FRACIONAMENTO_DIAS))]
            valor = _dinheiro(float(limite) * self.rng.uniform(*FAIXA_FRACIONAMENTO))
            parte = {
                **modelo,
                "data": dia,
                "valor": min(valor, limite - Decimal("0.01")),
                "descricao": self._escolher(CATEGORIAS[nome_categoria].descricoes),
            }
            linhas.append(self._rotular(parte, TIPO_FRACIONAMENTO, grupo))
        return linhas

    def _fim_semana_feriado(self, base: dict) -> dict:
        """Lança uma despesa como a modelo num sábado, domingo ou feriado do mesmo mês.

        O valor é sorteado de novo, pelo mesmo motivo de ``_combinacao_incompativel``.
        """
        mes = (base["data"].year, base["data"].month)
        candidatos = [d for d in self.dias_nao_uteis if (d.year, d.month) == mes]
        alterada = {
            **base,
            "data": self._escolher(candidatos),
            "valor": self._valor(CATEGORIAS[base["categoria"]]),
        }
        return self._rotular(alterada, TIPO_FIM_SEMANA_FERIADO)

    # --- montagem -------------------------------------------------------------

    def _eventos_por_tipo(self) -> dict[str, int]:
        total = round(self.config.n * self.config.taxa_anomalias)
        por_tipo, sobra = divmod(total, len(TIPOS_ANOMALIA))
        return {tipo: por_tipo + (1 if i < sobra else 0) for i, tipo in enumerate(TIPOS_ANOMALIA)}

    def gerar(self) -> pd.DataFrame:
        eventos = self._eventos_por_tipo()
        partes = self.rng.integers(
            PARTES_FRACIONAMENTO[0], PARTES_FRACIONAMENTO[1] + 1, size=eventos[TIPO_FRACIONAMENTO]
        )
        linhas_anomalas = int(partes.sum()) + sum(
            q for tipo, q in eventos.items() if tipo != TIPO_FRACIONAMENTO
        )
        normais = self._normais(self.config.n - linhas_anomalas)

        # Cada despesa normal serve de modelo para no máximo uma anomalia.
        tipos_com_modelo = [t for t in TIPOS_ANOMALIA if t != TIPO_FRACIONAMENTO]
        modelos = iter(
            self.rng.choice(
                len(normais), size=sum(eventos[t] for t in tipos_com_modelo), replace=False
            )
        )
        anomalias = []
        for tipo in tipos_com_modelo:
            for numero in range(1, eventos[tipo] + 1):
                base = normais[next(modelos)]
                if tipo == TIPO_VALOR_EXTREMO:
                    anomalias.append(self._valor_extremo(base))
                elif tipo == TIPO_COMBINACAO_INCOMPATIVEL:
                    anomalias.append(self._combinacao_incompativel(base))
                elif tipo == TIPO_DUPLICADA:
                    anomalias.append(self._duplicada(base, numero))
                else:
                    anomalias.append(self._fim_semana_feriado(base))
        for numero, quantidade in enumerate(partes, start=1):
            anomalias.extend(self._fracionamento(int(quantidade), numero))

        # Embaralha e ordena por data (ordenação estável), como num razão contábil.
        base = pd.DataFrame(normais + anomalias)
        base = base.iloc[self.rng.permutation(len(base))]
        base = base.sort_values("data", kind="mergesort").reset_index(drop=True)
        base.insert(0, "id_sintetico", range(1, len(base) + 1))
        return base[list(COLUNAS)]


def gerar_base(config: ConfiguracaoBase | None = None) -> pd.DataFrame:
    """Gera a base sintética. A mesma configuração sempre produz a mesma base."""
    config = config or ConfiguracaoBase()
    config.validar()
    return _Gerador(config).gerar()


def metadados(base: pd.DataFrame, config: ConfiguracaoBase) -> dict:
    """Seed, parâmetros e contagens da base, para registrar junto com os arquivos."""
    anomalas = base[base["anomalia_real"] == 1]
    por_tipo = {}
    for tipo in TIPOS_ANOMALIA:
        linhas = anomalas[anomalas["tipo_anomalia"] == tipo]
        agrupado = tipo in (TIPO_DUPLICADA, TIPO_FRACIONAMENTO)
        eventos = linhas["grupo_anomalia"].nunique() if agrupado else len(linhas)
        por_tipo[tipo] = {"eventos": int(eventos), "linhas": len(linhas)}
    return {
        "seed": config.seed,
        "parametros": {
            "n": config.n,
            "inicio": config.inicio.isoformat(),
            "fim": config.fim.isoformat(),
            "taxa_anomalias": config.taxa_anomalias,
            "limite_fracionamento": str(config.limite_fracionamento),
            "fator_extremo": FATOR_EXTREMO,
            "partes_fracionamento": PARTES_FRACIONAMENTO,
            "faixa_fracionamento": FAIXA_FRACIONAMENTO,
            "janela_fracionamento_dias": JANELA_FRACIONAMENTO_DIAS,
            "atraso_duplicada_dias": ATRASO_DUPLICADA_DIAS,
        },
        "total_linhas": len(base),
        "linhas_normais": int((base["anomalia_real"] == 0).sum()),
        "linhas_anomalas": len(anomalas),
        "anomalias_por_tipo": por_tipo,
        "categorias": {
            nome: {
                "mediana": c.mediana,
                "sigma": c.sigma,
                "contas": c.contas,
                "centros_custo": list(c.centros),
            }
            for nome, c in CATEGORIAS.items()
        },
        "funcionarios_por_centro_custo": CENTROS_CUSTO,
    }


def salvar_base(
    base: pd.DataFrame, config: ConfiguracaoBase, pasta: Path = PASTA_PADRAO
) -> dict[str, Path]:
    """Grava CSV, XLSX e metadados. Retorna os caminhos gerados."""
    pasta.mkdir(parents=True, exist_ok=True)
    caminhos = {
        "csv": pasta / f"{NOME_BASE}.csv",
        "xlsx": pasta / f"{NOME_BASE}.xlsx",
        "metadados": pasta / "metadados.json",
    }
    base.to_csv(caminhos["csv"], index=False, lineterminator="\n")
    base.to_excel(caminhos["xlsx"], index=False, sheet_name="despesas")
    caminhos["metadados"].write_text(
        json.dumps(metadados(base, config), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return caminhos


def main(argv: list[str] | None = None) -> None:
    padrao = ConfiguracaoBase()
    parser = argparse.ArgumentParser(description="Gera a base sintética de despesas rotulada.")
    parser.add_argument("--seed", type=int, default=padrao.seed)
    parser.add_argument("--n", type=int, default=padrao.n, help="total de linhas")
    parser.add_argument("--inicio", type=date.fromisoformat, default=padrao.inicio)
    parser.add_argument("--fim", type=date.fromisoformat, default=padrao.fim)
    parser.add_argument("--taxa", type=float, default=padrao.taxa_anomalias)
    parser.add_argument("--limite", type=Decimal, default=padrao.limite_fracionamento)
    parser.add_argument("--saida", type=Path, default=PASTA_PADRAO)
    args = parser.parse_args(argv)

    config = ConfiguracaoBase(
        seed=args.seed,
        n=args.n,
        inicio=args.inicio,
        fim=args.fim,
        taxa_anomalias=args.taxa,
        limite_fracionamento=args.limite,
    )
    try:
        base = gerar_base(config)
    except ValueError as erro:
        parser.error(str(erro))
    caminhos = salvar_base(base, config, args.saida)
    info = metadados(base, config)
    print(
        f"{info['total_linhas']} linhas ({info['linhas_anomalas']} anômalas), seed {config.seed}."
    )
    for tipo, contagem in info["anomalias_por_tipo"].items():
        print(f"  {tipo}: {contagem['eventos']} eventos, {contagem['linhas']} linhas")
    for caminho in caminhos.values():
        print(f"  -> {caminho}")


if __name__ == "__main__":
    main()
