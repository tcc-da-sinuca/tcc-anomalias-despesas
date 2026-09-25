"""API de parâmetros: GET e PUT /api/parametros (US12)."""


def test_exige_login(client):
    assert client.get("/api/parametros").status_code == 401
    assert client.put("/api/parametros", json={}).status_code == 401


def test_auditor_ve_mas_nao_altera(client, entrar, auditor):
    entrar(auditor)
    parametros = client.get("/api/parametros").get_json()["parametros"]

    limiar = next(p for p in parametros if (p["metodo"], p["chave"]) == ("zscore", "limiar"))
    assert (limiar["valor"], limiar["padrao"], limiar["minimo"], limiar["maximo"]) == (
        3.0,
        3.0,
        1,
        10,
    )
    assert client.put("/api/parametros", json={"zscore": {"limiar": 2}}).status_code == 403


def test_administrador_altera(client, entrar, administrador):
    entrar(administrador)
    resposta = client.put("/api/parametros", json={"zscore": {"limiar": 2.5}})

    assert resposta.status_code == 200
    dados = resposta.get_json()
    assert dados["alterados"] == ["zscore.limiar"]
    limiar = next(p for p in dados["parametros"] if p["chave"] == "limiar")
    assert limiar["valor"] == 2.5
    assert limiar["alterado_por"] == administrador.id


def test_valor_invalido_nao_altera_nada(client, entrar, administrador):
    entrar(administrador)
    resposta = client.put(
        "/api/parametros",
        json={"zscore": {"limiar": 2}, "isolation_forest": {"contamination": 0.9}},
    )

    assert resposta.status_code == 400
    assert set(resposta.get_json()["erros"]) == {"isolation_forest.contamination"}
    parametros = client.get("/api/parametros").get_json()["parametros"]
    assert next(p for p in parametros if p["chave"] == "limiar")["valor"] == 3.0


def test_corpo_invalido(client, entrar, administrador):
    entrar(administrador)
    assert client.put("/api/parametros", data="x", content_type="text/plain").status_code == 400


def test_parametro_alterado_vale_na_proxima_analise(client, entrar, administrador, alerta):
    entrar(administrador)
    client.put("/api/parametros", json={"zscore": {"limiar": 5}})

    execucao = client.post("/api/analises", json={"metodos": ["zscore"]}).get_json()
    assert execucao["parametros"]["zscore"] == {"limiar": 5.0}
