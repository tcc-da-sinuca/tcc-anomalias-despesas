"""API do dashboard: GET /api/dashboard (US09)."""


def test_exige_login(client):
    assert client.get("/api/dashboard").status_code == 401


def test_indicadores(client, entrar, auditor, alerta):
    entrar(auditor)
    dados = client.get("/api/dashboard").get_json()

    assert dados["total_despesas"] == 1
    assert dados["valor_despesas"] == "1520.75"  # texto, sem perder centavos
    assert dados["despesas_sinalizadas"] == 1
    assert dados["percentual_sinalizado"] == 100.0
    assert dados["alertas_por_status"]["pendente"] == 1
    assert dados["alertas_por_metodo"]["zscore"] == 1
    assert dados["ultima_analise"]["id"] == alerta.execucao_id


def test_sem_analise(client, entrar, auditor):
    entrar(auditor)
    dados = client.get("/api/dashboard").get_json()
    assert dados["ultima_analise"] is None
    assert dados["total_alertas"] == 0
