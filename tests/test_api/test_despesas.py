"""API de despesas: importação e listagem (US01)."""

import io

CSV_VALIDO = (
    b"valor,data,categoria,conta_contabil,centro_custo,funcionario\n"
    b"100.00,2026-09-01,Viagens,3.1,CC-01,F001\n"
    b"abc,2026-09-02,Viagens,3.1,CC-01,F001\n"
    b"250.50,2026-09-03,Software,3.5,CC-TI,F002\n"
)


def _enviar(client, conteudo=CSV_VALIDO, nome="despesas.csv"):
    return client.post(
        "/api/despesas/importar",
        data={"arquivo": (io.BytesIO(conteudo), nome)},
        content_type="multipart/form-data",
    )


def test_importar_exige_login(client):
    assert _enviar(client).status_code == 401


def test_importar_csv(client, entrar, auditor):
    entrar(auditor)
    resposta = _enviar(client)

    assert resposta.status_code == 201
    lote = resposta.get_json()
    assert lote["nome_arquivo"] == "despesas.csv"
    assert (lote["total_linhas"], lote["linhas_validas"]) == (3, 2)
    assert lote["erros"] == [{"linha": 3, "campo": "valor", "mensagem": "valor inválido: 'abc'"}]


def test_importar_sem_arquivo(client, entrar, auditor):
    entrar(auditor)
    resposta = client.post("/api/despesas/importar", data={})
    assert resposta.status_code == 400
    assert "arquivo" in resposta.get_json()["erro"]


def test_importar_arquivo_invalido(client, entrar, auditor):
    entrar(auditor)
    resposta = _enviar(client, b"x", nome="planilha.pdf")
    assert resposta.status_code == 400
    assert "Formato não suportado" in resposta.get_json()["erro"]


def test_listar_despesas(client, entrar, administrador):
    entrar(administrador)
    lote_id = _enviar(client).get_json()["id"]

    resposta = client.get("/api/despesas?por_pagina=1")

    assert resposta.status_code == 200
    dados = resposta.get_json()
    assert (dados["total"], dados["paginas"], dados["pagina"]) == (2, 2, 1)
    despesa = dados["itens"][0]
    assert despesa["valor"] == "250.50"  # texto, sem perder centavos
    assert despesa["data"] == "2026-09-03"  # mais recente primeiro
    assert despesa["lote_id"] == lote_id


def test_listar_filtra_por_lote(client, entrar, auditor):
    entrar(auditor)
    _enviar(client)
    segundo = _enviar(client).get_json()["id"]

    dados = client.get(f"/api/despesas?lote_id={segundo}").get_json()

    assert dados["total"] == 2
    assert {d["lote_id"] for d in dados["itens"]} == {segundo}


def test_listar_exige_login(client):
    assert client.get("/api/despesas").status_code == 401
