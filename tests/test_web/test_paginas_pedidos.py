"""Telas da aprovação prévia: cadastro, importação, fila de pedidos e decisão."""

import io
import re

import pytest

FORM_DESPESA = {
    "data": "10/03/2026",
    "categoria": "Viagens",
    "conta_contabil": "3.1.01",
    "centro_custo": "CC-ADM",
    "funcionario": "F005",
    "descricao": "",
}


def test_cadastro_dentro_do_padrao(client, entrar, auditor, historico):
    entrar(auditor)
    resposta = client.post(
        "/despesas/nova", data={**FORM_DESPESA, "valor": "101,00"}, follow_redirects=True
    )
    assert "Despesa cadastrada: dentro do padrão do histórico." in resposta.get_data(as_text=True)


def test_cadastro_fora_do_padrao_abre_pedido(client, entrar, auditor, historico):
    entrar(auditor)
    resposta = client.post(
        "/despesas/nova", data={**FORM_DESPESA, "valor": "140,00"}, follow_redirects=True
    )
    html = resposta.get_data(as_text=True)

    assert "Despesa fora do padrão do histórico" in html
    assert re.search(r"<h1[^>]*>Pedido #\d+</h1>", html)
    assert "Aguardando a decisão de um administrador" in html
    assert "Por que ficou fora do padrão" in html


def test_cadastro_critico_e_rejeitado_e_pode_ser_encaminhado(
    client, entrar, auditor, historico, sessao
):
    from app.models import SolicitacaoAprovacao

    entrar(auditor)
    html = client.post(
        "/despesas/nova", data={**FORM_DESPESA, "valor": "2500,00"}, follow_redirects=True
    ).get_data(as_text=True)
    assert "Despesa rejeitada automaticamente" in html
    assert "Encaminhar com prioridade" in html

    pedido = sessao.query(SolicitacaoAprovacao).one()
    html = client.post(
        f"/pedidos/{pedido.id}/encaminhar",
        data={"justificativa": "Compra emergencial."},
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "encaminhado para aprovação, com prioridade" in html
    assert "Prioritário" in html


def test_fila_destaca_prioritarios_e_menu_mostra_selo(
    client, entrar, auditor, historico, lancar, sessao
):
    from app.servicos import solicitacoes

    lancar(auditor, "140.00")
    automatica = lancar(auditor, "2500.00", funcionario="F010").solicitacao
    solicitacoes.encaminhar(automatica, auditor, "Reavaliar.")
    sessao.commit()
    entrar(auditor)

    html = client.get("/pedidos").get_data(as_text=True)
    assert "1 pedido(s) prioritário(s)" in html
    assert html.index("pedido-prioritario") < html.index(f'href="/pedidos/{automatica.id - 1}"')
    assert 'class="badge rounded-pill text-bg-danger selo-menu"' in html
    dashboard = client.get("/").get_data(as_text=True)
    assert "2 pedido(s) de aprovação pendente(s)" in dashboard


def test_administrador_aprova_e_rejeita(
    client, entrar, auditor, administrador, historico, lancar, sessao
):
    pedido_a = lancar(auditor, "140.00").solicitacao
    pedido_b = lancar(auditor, "135.00", funcionario="F011").solicitacao
    entrar(administrador)

    html = client.post(f"/pedidos/{pedido_a.id}/aprovar", data={}, follow_redirects=True).get_data(
        as_text=True
    )
    assert f"Pedido #{pedido_a.id} aprovado" in html

    sem_justificativa = client.post(
        f"/pedidos/{pedido_b.id}/rejeitar", data={}, follow_redirects=True
    )
    assert "Informe a justificativa" in sem_justificativa.get_data(as_text=True)
    client.post(f"/pedidos/{pedido_b.id}/rejeitar", data={"justificativa": "Sem autorização."})

    sessao.refresh(pedido_a)
    sessao.refresh(pedido_b)
    assert (pedido_a.despesa.situacao, pedido_b.despesa.situacao) == ("valida", "rejeitada")


def test_auditor_nao_decide(client, entrar, auditor, historico, lancar):
    pedido = lancar(auditor, "140.00").solicitacao
    entrar(auditor)
    assert client.post(f"/pedidos/{pedido.id}/aprovar").status_code == 403
    assert "Aprovar: a despesa é válida" not in client.get(f"/pedidos/{pedido.id}").get_data(
        as_text=True
    )


def test_resultado_da_importacao(client, entrar, auditor, historico):
    csv = (
        b"valor;data;categoria;conta_contabil;centro_custo;funcionario\n"
        b"101,00;10/03/2026;Viagens;3.1.01;CC-ADM;F005\n"
        b"140,00;11/03/2026;Viagens;3.1.01;CC-ADM;F006\n"
        b"2500,00;12/03/2026;Viagens;3.1.01;CC-ADM;F007\n"
    )
    entrar(auditor)
    html = client.post(
        "/despesas/importar",
        data={"arquivo": (io.BytesIO(csv), "novas.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    ).get_data(as_text=True)

    for indicador in ("validas", "pendentes", "rejeitadas"):
        assert re.search(rf'data-indicador="{indicador}">1<', html)


@pytest.mark.parametrize("caminho", ["/pedidos", "/pedidos/1"])
def test_pedidos_exigem_login(client, caminho):
    resposta = client.get(caminho)
    assert resposta.status_code == 302 and "/login" in resposta.headers["Location"]
