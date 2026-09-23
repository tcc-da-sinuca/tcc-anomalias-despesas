"""Importação de CSV/XLSX e cadastro manual de despesas (US01)."""

import io
from datetime import date, datetime
from decimal import Decimal

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from app.servicos.importacao import (
    MAXIMO_ERROS_REGISTRADOS,
    ArquivoInvalidoError,
    DespesaInvalidaError,
    cadastrar_despesa,
    converter_data,
    converter_valor,
    importar_arquivo,
    normalizar_cabecalho,
    validar_despesa,
)

HOJE = date(2026, 9, 23)
CABECALHO = "valor,data,categoria,conta_contabil,centro_custo,funcionario,descricao"


def _csv(*linhas: str, cabecalho: str = CABECALHO) -> bytes:
    return ("\n".join([cabecalho, *linhas]) + "\n").encode("utf-8")


def _xlsx(linhas: list[list]) -> bytes:
    planilha = Workbook()
    for linha in linhas:
        planilha.active.append(linha)
    saida = io.BytesIO()
    planilha.save(saida)
    return saida.getvalue()


def _importar(conteudo: bytes, usuario, nome="despesas.csv"):
    return importar_arquivo(nome, conteudo, usuario, hoje=HOJE)


def _despesas(sessao):
    from app.models import Despesa

    return list(sessao.scalars(select(Despesa).order_by(Despesa.id)))


# --- Conversões ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("bruto", "brasileiro", "esperado"),
    [
        ("1234.56", False, "1234.56"),
        ("1234,56", False, "1234.56"),
        ("1.234,56", True, "1234.56"),
        ("1,234.56", False, "1234.56"),
        ("R$ 1.234,56", True, "1234.56"),
        ("1.234", True, "1234.00"),  # formato brasileiro: ponto é milhar
        ("1.234", False, "1.23"),  # formato internacional: ponto é decimal
        ("10.005", False, "10.01"),  # arredonda para centavos
        (99.9, False, "99.90"),  # célula numérica do XLSX
        (150, False, "150.00"),
    ],
)
def test_converter_valor(bruto, brasileiro, esperado):
    assert converter_valor(bruto, brasileiro) == Decimal(esperado)


@pytest.mark.parametrize("bruto", ["abc", "0", "-10,00", "0,001", "NaN", "1e13"])
def test_converter_valor_invalido(bruto):
    with pytest.raises(ValueError):
        converter_valor(bruto)


@pytest.mark.parametrize(
    "bruto",
    ["2026-09-01", "01/09/2026", "01-09-2026", date(2026, 9, 1), datetime(2026, 9, 1, 14, 30)],
)
def test_converter_data(bruto):
    assert converter_data(bruto, HOJE) == date(2026, 9, 1)


def test_data_futura_ou_invalida():
    with pytest.raises(ValueError, match="futura"):
        converter_data("2026-09-24", HOJE)
    with pytest.raises(ValueError, match="inválida"):
        converter_data("31/02/2026", HOJE)


@pytest.mark.parametrize(
    ("nome", "campo"),
    [
        ("Conta Contábil", "conta_contabil"),
        ("  CENTRO DE CUSTO ", "centro_custo"),
        ("Funcionário", "funcionario"),
        ("Valor (R$)", "valor"),
        ("Descrição", "descricao"),
    ],
)
def test_normalizar_cabecalho(nome, campo):
    assert normalizar_cabecalho(nome) == campo


def test_validar_despesa_lista_todos_os_erros():
    dados, erros = validar_despesa(
        {"valor": "-1", "data": "", "categoria": "x" * 101, "conta_contabil": "3.1"}, HOJE
    )
    assert dados is None
    campos = [campo for campo, _ in erros]
    assert campos == ["valor", "data", "categoria", "centro_custo", "funcionario"]


# --- Importação ---------------------------------------------------------------


def test_importa_csv_valido(sessao, auditor):
    from app.models import EstatisticaReferencia

    lote = _importar(
        _csv(
            "1520.75,2026-09-12,Viagens,3.1.01,CC-01,F001,Passagem aérea",
            "80.00,2026-09-13,Alimentação,3.1.02,CC-01,F002,",
        ),
        auditor,
    )

    assert (lote.total_linhas, lote.linhas_validas, lote.erros) == (2, 2, [])
    assert lote.importado_por == auditor.id
    despesas = _despesas(sessao)
    assert [d.valor for d in despesas] == [Decimal("1520.75"), Decimal("80.00")]
    assert despesas[0].data == date(2026, 9, 12)
    assert despesas[0].lote_id == lote.id
    assert despesas[1].descricao is None
    assert sessao.scalar(select(func.count(EstatisticaReferencia.id))) > 0


def test_importa_csv_no_formato_do_excel_brasileiro(sessao, auditor):
    cabecalho = "Valor;Data;Categoria;Conta Contábil;Centro de Custo;Funcionário"
    conteudo = _csv("1.520,75;12/09/2026;Viagens;3.1.01;CC-01;João", cabecalho=cabecalho)

    lote = _importar(conteudo.decode().encode("cp1252"), auditor)

    assert lote.linhas_validas == 1, lote.erros
    despesa = _despesas(sessao)[0]
    assert despesa.valor == Decimal("1520.75")
    assert despesa.funcionario == "João"


def test_importa_xlsx(sessao, auditor):
    conteudo = _xlsx(
        [
            ["Valor", "Data", "Categoria", "Conta contábil", "Centro de custo", "Funcionário"],
            [1520.75, datetime(2026, 9, 12), "Viagens", 3101, "CC-01", "F001"],
            [None, None, None, None, None, None],  # linha em branco
            ["abc", "2026-09-12", "Viagens", "3101", "CC-01", "F001"],
        ]
    )

    lote = _importar(conteudo, auditor, nome="despesas.xlsx")

    assert (lote.total_linhas, lote.linhas_validas) == (2, 1)
    assert lote.erros == [{"linha": 4, "campo": "valor", "mensagem": "valor inválido: 'abc'"}]
    despesa = _despesas(sessao)[0]
    assert despesa.conta_contabil == "3101"
    assert despesa.data == date(2026, 9, 12)


def test_erros_por_linha_nao_impedem_as_linhas_validas(sessao, auditor):
    lote = _importar(
        _csv(
            "100.00,2026-09-01,Viagens,3.1,CC-01,F001,ok",
            ",2026-09-01,Viagens,3.1,CC-01,F001,sem valor",
            "100.00,2026-12-01,Viagens,3.1,CC-01,F001,data futura",
            "",
            "50.00,2026-09-02,Viagens,3.1,CC-01,,sem funcionário",
        ),
        auditor,
    )

    assert (lote.total_linhas, lote.linhas_validas) == (4, 1)
    assert [(e["linha"], e["campo"]) for e in lote.erros] == [
        (3, "valor"),
        (4, "data"),
        (6, "funcionario"),
    ]
    assert len(_despesas(sessao)) == 1


def test_colunas_extras_sao_ignoradas(sessao, auditor):
    cabecalho = CABECALHO + ",anomalia_real,tipo_anomalia"
    lote = _importar(
        _csv("10.00,2026-09-01,Viagens,3.1,CC-01,F001,x,1,valor_extremo", cabecalho=cabecalho),
        auditor,
    )
    assert lote.linhas_validas == 1


def test_despesas_repetidas_nao_sao_bloqueadas(sessao, auditor):
    linha = "10.00,2026-09-01,Viagens,3.1,CC-01,F001,x"
    lote = _importar(_csv(linha, linha), auditor)
    assert lote.linhas_validas == 2


def test_lote_sem_linhas_validas_fica_registrado(sessao, auditor):
    from app.models import EstatisticaReferencia

    lote = _importar(_csv("abc,2026-09-01,Viagens,3.1,CC-01,F001,x"), auditor)

    assert lote.id is not None
    assert (lote.total_linhas, lote.linhas_validas) == (1, 0)
    assert _despesas(sessao) == []
    assert sessao.scalar(select(func.count(EstatisticaReferencia.id))) == 0


def test_limite_de_erros_registrados(sessao, auditor):
    linhas = ["abc,2026-09-01,Viagens,3.1,CC-01,F001,x"] * (MAXIMO_ERROS_REGISTRADOS + 5)
    lote = _importar(_csv(*linhas), auditor)

    assert len(lote.erros) == MAXIMO_ERROS_REGISTRADOS + 1
    assert lote.erros[-1]["mensagem"] == "... e mais 5 erros."


@pytest.mark.parametrize(
    ("nome", "conteudo", "mensagem"),
    [
        ("despesas.txt", b"x", "Formato não suportado"),
        ("despesas.csv", b"", "vazio"),
        ("despesas.csv", b"valor,data\n10,2026-09-01\n", "categoria, conta contábil"),
        ("despesas.csv", _csv("", cabecalho=CABECALHO + ",Valor"), "mais de uma vez"),
        ("despesas.xlsx", b"nao e um xlsx", "XLSX válida"),
    ],
)
def test_arquivo_invalido(sessao, auditor, nome, conteudo, mensagem):
    from app.models import LoteImportacao

    with pytest.raises(ArquivoInvalidoError, match=mensagem):
        importar_arquivo(nome, conteudo, auditor, hoje=HOJE)
    assert sessao.scalar(select(func.count(LoteImportacao.id))) == 0


def test_importa_a_base_sintetica(sessao, auditor, tmp_path):
    from dados.gerar_base_sintetica import ConfiguracaoBase, gerar_base, salvar_base

    config = ConfiguracaoBase(n=300)
    caminhos = salvar_base(gerar_base(config), config, tmp_path)

    lote_csv = _importar(caminhos["csv"].read_bytes(), auditor)
    lote_xlsx = _importar(caminhos["xlsx"].read_bytes(), auditor, nome="base.xlsx")

    assert (lote_csv.linhas_validas, lote_csv.erros) == (300, [])
    assert (lote_xlsx.linhas_validas, lote_xlsx.erros) == (300, [])


# --- Cadastro manual ----------------------------------------------------------


def test_cadastro_manual(sessao):
    despesa = cadastrar_despesa(
        {
            "valor": "1.234,50",
            "data": "2026-09-10",
            "categoria": " Software ",
            "conta_contabil": "3.1.05",
            "centro_custo": "CC-TI",
            "funcionario": "F010",
            "descricao": "",
        },
        hoje=HOJE,
    )

    assert despesa.id is not None
    assert despesa.lote_id is None
    assert despesa.valor == Decimal("1234.50")
    assert despesa.categoria == "Software"
    assert despesa.descricao is None


def test_cadastro_manual_invalido(sessao):
    with pytest.raises(DespesaInvalidaError) as erro:
        cadastrar_despesa({"valor": "0", "data": "2026-09-10"}, hoje=HOJE)
    assert ("valor", "o valor deve ser maior que zero") in erro.value.erros
    assert _despesas(sessao) == []
