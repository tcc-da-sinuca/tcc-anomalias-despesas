"""Carga da base sintética no banco (flask seed-base)."""

import pytest
from sqlalchemy import func, select

from dados.gerar_base_sintetica import ConfiguracaoBase, gerar_base, salvar_base
from dados.seed_banco import CargaBaseError, ler_csv


@pytest.fixture
def csv_base(tmp_path):
    config = ConfiguracaoBase(n=300)
    return salvar_base(gerar_base(config), config, tmp_path)["csv"]


@pytest.fixture
def seed_base(app, administrador, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", administrador.email)
    runner = app.test_cli_runner()

    def _executar(*args):
        return runner.invoke(args=["seed-base", *args])

    return _executar


def _contar(sessao, modelo):
    return sessao.scalar(select(func.count()).select_from(modelo))


def test_carrega_as_despesas_sem_rotulos(seed_base, csv_base, sessao, administrador):
    from app.models import Despesa, LoteImportacao

    resultado = seed_base("--arquivo", str(csv_base))

    assert resultado.exit_code == 0, resultado.output
    assert "300 despesas carregadas" in resultado.output
    lote = sessao.scalar(select(LoteImportacao))
    assert lote.nome_arquivo == "despesas_sinteticas.csv"
    assert lote.importado_por == administrador.id
    assert (lote.total_linhas, lote.linhas_validas, lote.erros) == (300, 300, [])
    assert _contar(sessao, Despesa) == 300

    base = ler_csv(csv_base)
    total = sessao.scalar(select(func.sum(Despesa.valor)))
    assert total == sum(base["valor"])


def test_segunda_carga_nao_duplica(seed_base, csv_base, sessao):
    from app.models import Despesa

    seed_base("--arquivo", str(csv_base))
    resultado = seed_base("--arquivo", str(csv_base))

    assert resultado.exit_code == 0
    assert "já carregada" in resultado.output
    assert _contar(sessao, Despesa) == 300


def test_forcar_substitui_o_lote(seed_base, csv_base, sessao):
    from app.models import Despesa, LoteImportacao

    seed_base("--arquivo", str(csv_base))
    resultado = seed_base("--arquivo", str(csv_base), "--forcar")

    assert resultado.exit_code == 0, resultado.output
    assert "300 despesas carregadas" in resultado.output
    assert _contar(sessao, LoteImportacao) == 1
    assert _contar(sessao, Despesa) == 300


def test_forcar_recusa_lote_com_alertas(seed_base, csv_base, sessao):
    from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise

    seed_base("--arquivo", str(csv_base))
    despesa = sessao.scalar(select(Despesa).limit(1))
    execucao = ExecucaoAnalise(parametros={}, seed=42)
    sessao.add(
        AlertaAnomalia(despesa=despesa, execucao=execucao, metodo="zscore", score=4, motivo="x")
    )
    sessao.commit()

    resultado = seed_base("--arquivo", str(csv_base), "--forcar")

    assert resultado.exit_code != 0
    assert "alertas" in resultado.output
    assert _contar(sessao, Despesa) == 300


def test_exige_administrador(app, csv_base, monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    resultado = app.test_cli_runner().invoke(args=["seed-base", "--arquivo", str(csv_base)])

    assert resultado.exit_code != 0
    assert "flask seed-admin" in resultado.output


def test_csv_sem_colunas_obrigatorias(tmp_path):
    caminho = tmp_path / "incompleto.csv"
    caminho.write_text("data,valor\n2026-01-05,10.00\n", encoding="utf-8")

    with pytest.raises(CargaBaseError, match="categoria"):
        ler_csv(caminho)
