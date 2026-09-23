"""Páginas de importação, despesas, cadastro manual e estatísticas."""

import io

import pytest
from sqlalchemy import func, select

CSV = (
    "Valor;Data;Categoria;Conta Contábil;Centro de Custo;Funcionário;Descrição\n"
    "1.520,75;12/09/2026;Viagens;3.1.01;CC-01;F001;Passagem aérea\n"
    ";13/09/2026;Viagens;3.1.01;CC-01;F001;sem valor\n"
).encode()


def _contar_despesas(sessao):
    from app.models import Despesa

    return sessao.scalar(select(func.count(Despesa.id)))


@pytest.mark.parametrize(
    "caminho", ["/despesas", "/despesas/nova", "/despesas/importar", "/estatisticas", "/lotes/1"]
)
def test_paginas_exigem_login(client, caminho):
    resposta = client.get(caminho)
    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]


def test_menu_na_pagina_inicial(client, entrar, auditor):
    entrar(auditor)
    html = client.get("/").get_data(as_text=True)
    for rotulo in ("Despesas", "Importar", "Estatísticas"):
        assert rotulo in html


def test_importar_mostra_o_resultado_com_erros_por_linha(client, entrar, auditor, sessao):
    entrar(auditor)
    resposta = client.post(
        "/despesas/importar",
        data={"arquivo": (io.BytesIO(CSV), "despesas.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    html = resposta.get_data(as_text=True)
    assert resposta.status_code == 200
    assert "Importação de despesas.csv" in html
    assert "Erros por linha" in html
    assert "valor é obrigatório" in html
    assert _contar_despesas(sessao) == 1


def test_importar_arquivo_sem_colunas(client, entrar, auditor):
    entrar(auditor)
    resposta = client.post(
        "/despesas/importar",
        data={"arquivo": (io.BytesIO(b"valor,data\n1,2026-09-01\n"), "x.csv")},
        content_type="multipart/form-data",
    )
    assert resposta.status_code == 400
    assert "Colunas obrigatórias ausentes" in resposta.get_data(as_text=True)


def test_importar_extensao_invalida(client, entrar, auditor):
    entrar(auditor)
    resposta = client.post(
        "/despesas/importar",
        data={"arquivo": (io.BytesIO(b"x"), "x.pdf")},
        content_type="multipart/form-data",
    )
    assert resposta.status_code == 400
    assert "Envie um arquivo .csv ou .xlsx." in resposta.get_data(as_text=True)


def test_lista_de_despesas_formata_valores(client, entrar, auditor):
    entrar(auditor)
    client.post(
        "/despesas/importar",
        data={"arquivo": (io.BytesIO(CSV), "despesas.csv")},
        content_type="multipart/form-data",
    )

    html = client.get("/despesas").get_data(as_text=True)

    assert "R$ 1.520,75" in html
    assert "12/09/2026" in html


def test_cadastro_manual(client, entrar, auditor, sessao):
    entrar(auditor)
    resposta = client.post(
        "/despesas/nova",
        data={
            "valor": "89,90",
            "data": "2026-09-10",
            "categoria": "Alimentação",
            "conta_contabil": "3.1.02",
            "centro_custo": "CC-01",
            "funcionario": "F001",
            "descricao": "Almoço",
        },
        follow_redirects=True,
    )

    assert resposta.status_code == 200
    assert "Despesa cadastrada" in resposta.get_data(as_text=True)
    assert _contar_despesas(sessao) == 1


def test_cadastro_manual_mostra_erros_nos_campos(client, entrar, auditor, sessao):
    entrar(auditor)
    resposta = client.post("/despesas/nova", data={"valor": "-5", "data": "2026-09-10"})

    html = resposta.get_data(as_text=True)
    assert resposta.status_code == 400
    assert "o valor deve ser maior que zero" in html
    assert "categoria é obrigatório" in html
    assert _contar_despesas(sessao) == 0


def test_estatisticas(client, entrar, auditor):
    entrar(auditor)
    assert "Ainda não há despesas" in client.get("/estatisticas").get_data(as_text=True)

    client.post(
        "/despesas/importar",
        data={"arquivo": (io.BytesIO(CSV), "despesas.csv")},
        content_type="multipart/form-data",
    )
    html = client.get("/estatisticas").get_data(as_text=True)

    assert "Por categoria" in html
    assert "Viagens" in html
    assert "R$ 1.520,75" in html


def test_lote_inexistente(client, entrar, auditor):
    entrar(auditor)
    assert client.get("/lotes/999").status_code == 404
