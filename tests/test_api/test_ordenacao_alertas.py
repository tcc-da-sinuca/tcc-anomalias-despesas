"""Ordenação da lista de alertas por data e valor (tela e API)."""

import re
from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def alertas(sessao, auditor):
    """Quatro alertas com datas e valores em ordens diferentes; um já revisado."""
    from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise

    execucao = ExecucaoAnalise(parametros={}, seed=42, executada_por=auditor.id)
    dados = [
        # (descrição, data, valor, score, status)
        ("B", date(2026, 3, 10), "500.00", 9.0, "pendente"),
        ("A", date(2026, 1, 5), "1500.00", 3.0, "pendente"),
        ("D", date(2026, 5, 20), "80.00", 7.0, "aprovado"),
        ("C", date(2026, 4, 1), "2500.00", 5.0, "pendente"),
    ]
    objetos = [execucao]
    for descricao, dia, valor, score, status in dados:
        despesa = Despesa(
            valor=Decimal(valor),
            data=dia,
            categoria="Viagens",
            conta_contabil="3.1.01",
            centro_custo="CC-ADM",
            funcionario="F001",
            descricao=descricao,
        )
        objetos += [
            despesa,
            AlertaAnomalia(
                despesa=despesa,
                execucao=execucao,
                metodo="zscore",
                score=score,
                motivo="m",
                status_revisao=status,
            ),
        ]
    sessao.add_all(objetos)
    sessao.commit()


def _ordem_api(client, ordem=None):
    consulta = f"?ordem={ordem}" if ordem else ""
    resposta = client.get(f"/api/alertas{consulta}")
    assert resposta.status_code == 200, resposta.get_json()
    return "".join(a["despesa"]["descricao"] for a in resposta.get_json()["itens"])


@pytest.mark.parametrize(
    ("ordem", "esperado"),
    [
        (None, "BCAD"),  # padrão: pendentes primeiro (score 9, 5, 3), depois o aprovado
        ("padrao", "BCAD"),
        ("data_desc", "DCBA"),  # 20/05, 01/04, 10/03, 05/01
        ("data_asc", "ABCD"),
        ("valor_desc", "CABD"),  # 2.500, 1.500, 500, 80
        ("valor_asc", "DBAC"),
    ],
)
def test_ordenacoes(client, entrar, auditor, alertas, ordem, esperado):
    entrar(auditor)
    assert _ordem_api(client, ordem) == esperado


def test_ordenacao_combina_com_filtros(client, entrar, auditor, alertas):
    entrar(auditor)
    resposta = client.get("/api/alertas?status=pendente&ordem=valor_asc")
    assert "".join(a["despesa"]["descricao"] for a in resposta.get_json()["itens"]) == "BAC"


def test_ordem_invalida_na_api(client, entrar, auditor):
    entrar(auditor)
    resposta = client.get("/api/alertas?ordem=nome")

    assert resposta.status_code == 400
    assert resposta.get_json()["campo"] == "ordem"


def test_tela_mostra_a_ordem_escolhida(client, entrar, auditor, alertas):
    entrar(auditor)
    html = client.get("/alertas?ordem=valor_desc").get_data(as_text=True)

    assert '<option value="valor_desc" selected>Valor (maior primeiro)</option>' in html
    assert "Ordenados por: valor (maior primeiro)." in html
    assert "4 alerta(s)." in html  # a ordenação não conta como filtro
    valores = re.findall(r'<td class="text-end text-nowrap">(R\$ [^<]+)</td>', html)
    assert valores == ["R$ 2.500,00", "R$ 1.500,00", "R$ 500,00", "R$ 80,00"]


def test_ordem_invalida_na_tela_usa_a_padrao(client, entrar, auditor, alertas):
    entrar(auditor)
    resposta = client.get("/alertas?ordem=qualquer")

    assert resposta.status_code == 200
    assert '<option value="padrao" selected>' in resposta.get_data(as_text=True)


def test_paginacao_preserva_a_ordem(client, entrar, auditor, sessao):
    from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise

    execucao = ExecucaoAnalise(parametros={}, seed=42, executada_por=auditor.id)
    objetos = [execucao]
    for i in range(55):
        despesa = Despesa(
            valor=Decimal(100 + i),
            data=date(2026, 3, 2),
            categoria="Viagens",
            conta_contabil="3.1.01",
            centro_custo="CC-ADM",
            funcionario="F001",
        )
        objetos += [
            AlertaAnomalia(
                despesa=despesa, execucao=execucao, metodo="zscore", score=1.0, motivo="m"
            ),
            despesa,
        ]
    sessao.add_all(objetos)
    sessao.commit()
    entrar(auditor)

    html = client.get("/alertas?ordem=valor_asc").get_data(as_text=True)
    links = re.findall(r'href="(/alertas\?[^"]*pagina=2[^"]*)"', html)
    assert links and "ordem=valor_asc" in links[0]

    segunda = client.get("/api/alertas?ordem=valor_asc&pagina=2").get_json()
    assert [a["despesa"]["valor"] for a in segunda["itens"]] == [f"{v}.00" for v in range(150, 155)]
