"""API dos pedidos de aprovação."""


def test_listar_e_detalhar(client, entrar, auditor, historico, lancar):
    pedido = lancar(auditor, "140.00").solicitacao
    entrar(auditor)

    lista = client.get("/api/solicitacoes?status=pendente").get_json()
    assert lista["total"] == 1 and lista["itens"][0]["despesa"]["situacao"] == "pendente"

    detalhe = client.get(f"/api/solicitacoes/{pedido.id}").get_json()
    assert detalhe["gravidade"] == "alta"
    assert detalhe["alertas"] and all("gravidade" in a for a in detalhe["alertas"])
    assert [e["tipo"] for e in detalhe["eventos"]] == ["criada"]


def test_status_invalido(client, entrar, auditor):
    entrar(auditor)
    assert client.get("/api/solicitacoes?status=xyz").status_code == 400


def test_fluxo_pela_api(client, entrar, auditor, administrador, historico, lancar):
    automatica = lancar(auditor, "2500.00").solicitacao
    entrar(auditor)
    assert client.post(f"/api/solicitacoes/{automatica.id}/encaminhar", json={}).status_code == 400
    encaminhada = client.post(
        f"/api/solicitacoes/{automatica.id}/encaminhar", json={"justificativa": "Reavaliar."}
    ).get_json()
    assert (encaminhada["status"], encaminhada["prioritaria"]) == ("pendente", True)
    assert client.post(f"/api/solicitacoes/{automatica.id}/aprovar").status_code == 403

    client.post("/logout")
    entrar(administrador)
    aprovada = client.post(f"/api/solicitacoes/{automatica.id}/aprovar", json={}).get_json()
    assert aprovada["status"] == "aprovada" and aprovada["despesa"]["situacao"] == "valida"


def test_pedido_inexistente(client, entrar, administrador):
    entrar(administrador)
    assert client.get("/api/solicitacoes/999").status_code == 404
    assert client.post("/api/solicitacoes/999/aprovar").status_code == 404


def test_importacao_informa_o_resultado(client, entrar, auditor, historico):
    import io

    csv = (
        b"valor,data,categoria,conta_contabil,centro_custo,funcionario\n"
        b"101.00,2026-03-10,Viagens,3.1.01,CC-ADM,F005\n"
        b"2500.00,2026-03-12,Viagens,3.1.01,CC-ADM,F007\n"
    )
    entrar(auditor)
    lote = client.post(
        "/api/despesas/importar",
        data={"arquivo": (io.BytesIO(csv), "novas.csv")},
        content_type="multipart/form-data",
    ).get_json()
    assert lote["situacoes"] == {"valida": 1, "pendente": 0, "rejeitada": 1}
