"""Páginas de análises e alertas (US06) e comando executar-analise."""

import re
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select


@pytest.fixture
def despesas(sessao):
    from app.models import Despesa

    valores = [f"{95 + i % 11}.00" for i in range(120)] + ["2500.00"]
    sessao.add_all(
        Despesa(
            valor=Decimal(v),
            data=date(2026, 3, 2),
            categoria="Viagens",
            conta_contabil="3.1.01",
            centro_custo="CC-ADM",
            funcionario="F001",
        )
        for v in valores
    )
    sessao.commit()


def _csrf(html):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


@pytest.mark.parametrize("caminho", ["/analises", "/analises/1", "/alertas", "/alertas/1"])
def test_paginas_exigem_login(client, caminho):
    resposta = client.get(caminho)
    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]


def test_menu_tem_analises_e_alertas(client, entrar, auditor):
    entrar(auditor)
    html = client.get("/").get_data(as_text=True)
    assert "Análises" in html and "Alertas" in html


def test_executar_analise_pela_tela(client, entrar, auditor, despesas, sessao, app):
    from app.models import ExecucaoAnalise

    entrar(auditor)
    app.config["WTF_CSRF_ENABLED"] = True  # depois do login, que não envia token
    token = _csrf(client.get("/analises").get_data(as_text=True))

    resposta = client.post("/analises", data={"csrf_token": token}, follow_redirects=True)

    html = resposta.get_data(as_text=True)
    assert resposta.status_code == 200
    assert "Análise concluída: 121 despesa(s) analisada(s), 2 alerta(s) novo(s)." in html
    assert "Ver os alertas desta análise" in html
    assert sessao.scalar(select(func.count(ExecucaoAnalise.id))) == 1


def test_executar_sem_csrf_nao_roda(client, entrar, auditor, despesas, sessao, app):
    from app.models import ExecucaoAnalise

    entrar(auditor)
    app.config["WTF_CSRF_ENABLED"] = True  # depois do login, que não envia token
    resposta = client.post("/analises")

    assert resposta.status_code == 400
    assert sessao.scalar(select(func.count(ExecucaoAnalise.id))) == 0


def test_lista_de_alertas_mostra_score_metodo_e_motivo(client, entrar, auditor, alerta):
    entrar(auditor)
    html = client.get("/alertas").get_data(as_text=True)

    assert "Z-score" in html
    assert "4,20" in html
    assert "Valor 4,2x acima da média da categoria Viagens" in html
    assert "Pendente" in html


def test_filtro_da_lista(client, entrar, auditor, alerta):
    entrar(auditor)
    assert "Nenhum alerta com esses filtros" in client.get("/alertas?metodo=iqr").get_data(
        as_text=True
    )
    assert "Nenhum alerta com esses filtros" not in client.get("/alertas?metodo=zscore").get_data(
        as_text=True
    )


def test_detalhe_do_alerta(client, entrar, auditor, alerta):
    entrar(auditor)
    html = client.get(f"/alertas/{alerta.id}").get_data(as_text=True)

    assert f"Alerta #{alerta.id}" in html
    assert "R$ 1.520,75" in html
    assert "Nenhum parecer registrado" in html
    assert client.get("/alertas/999").status_code == 404


def test_detalhe_da_analise(client, entrar, auditor, alerta):
    entrar(auditor)
    html = client.get(f"/analises/{alerta.execucao_id}").get_data(as_text=True)

    assert f"Análise #{alerta.execucao_id}" in html
    assert "Parâmetros usados" in html


def test_comando_executar_analise(app, despesas, auditor):
    resultado = app.test_cli_runner().invoke(args=["executar-analise", "--email", auditor.email])

    assert resultado.exit_code == 0, resultado.output
    assert "121 despesas, 2 alertas novos" in resultado.output


def test_comando_com_metodo_invalido(app):
    resultado = app.test_cli_runner().invoke(args=["executar-analise", "--metodo", "xyz"])
    assert resultado.exit_code != 0
    assert "xyz" in resultado.output


def test_registrar_parecer_pela_tela(client, entrar, auditor, alerta):
    entrar(auditor)
    resposta = client.post(
        f"/alertas/{alerta.id}",
        data={"status": "necessita_justificativa", "observacao": "Pedir o comprovante."},
        follow_redirects=True,
    )

    html = resposta.get_data(as_text=True)
    assert resposta.status_code == 200
    assert "Parecer registrado." in html
    assert "Pedir o comprovante." in html
    assert "Registrar novo parecer" in html
    assert alerta.status_revisao == "necessita_justificativa"


def test_parecer_sem_observacao_mostra_o_erro(client, entrar, auditor, alerta, sessao):
    from app.models import Parecer

    entrar(auditor)
    resposta = client.post(f"/alertas/{alerta.id}", data={"status": "irregular"})

    assert resposta.status_code == 400
    assert "A observação é obrigatória para o status irregular." in resposta.get_data(as_text=True)
    assert sessao.query(Parecer).count() == 0


def test_parecer_sem_status_mostra_o_erro(client, entrar, auditor, alerta):
    entrar(auditor)
    resposta = client.post(f"/alertas/{alerta.id}", data={"observacao": "texto"})

    assert resposta.status_code == 400
    assert "Escolha a classificação" in resposta.get_data(as_text=True)
