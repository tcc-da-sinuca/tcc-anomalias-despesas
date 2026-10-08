"""Decisão rápida na lista de alertas e exibição da gravidade do score."""

import re

import pytest


def _decidir(client, alerta_id, **dados):
    return client.post(f"/alertas/{alerta_id}/decisao-rapida", data=dados)


def test_aprovar_volta_para_a_lista_com_os_filtros(client, entrar, auditor, alerta, sessao):
    entrar(auditor)
    resposta = _decidir(
        client, alerta.id, status="aprovado", voltar="/alertas?metodo=zscore&pagina=1"
    )

    assert resposta.status_code == 302
    assert resposta.headers["Location"] == "/alertas?metodo=zscore&pagina=1"
    sessao.refresh(alerta)
    assert alerta.status_revisao == "aprovado"
    assert [p.usuario_id for p in alerta.pareceres] == [auditor.id]


def test_rejeitar_exige_observacao(client, entrar, auditor, alerta, sessao):
    entrar(auditor)
    resposta = _decidir(client, alerta.id, status="irregular", voltar="/alertas")
    html = client.get(resposta.headers["Location"]).get_data(as_text=True)

    assert "A observação é obrigatória" in html
    sessao.refresh(alerta)
    assert alerta.status_revisao == "pendente" and alerta.pareceres == []


def test_rejeitar_com_observacao(client, entrar, auditor, alerta, sessao):
    entrar(auditor)
    _decidir(
        client, alerta.id, status="irregular", observacao="Sem comprovante.", voltar="/alertas"
    )

    sessao.refresh(alerta)
    assert alerta.status_revisao == "irregular"
    assert alerta.pareceres[-1].observacao == "Sem comprovante."


@pytest.mark.parametrize("voltar", ["https://outro-site.com/", "//outro-site.com", ""])
def test_nao_redireciona_para_fora(client, entrar, auditor, alerta, voltar):
    entrar(auditor)
    resposta = _decidir(client, alerta.id, status="aprovado", voltar=voltar)
    assert resposta.headers["Location"] == "/alertas"


def test_status_invalido_e_alerta_inexistente(client, entrar, auditor, alerta, sessao):
    entrar(auditor)
    _decidir(client, alerta.id, status="necessita_justificativa")
    sessao.refresh(alerta)
    assert alerta.pareceres == []
    assert _decidir(client, 999, status="aprovado").status_code == 404


def test_exige_login(client, alerta):
    resposta = _decidir(client, alerta.id, status="aprovado")
    assert resposta.status_code == 302 and "/login" in resposta.headers["Location"]


def test_lista_tem_os_dois_botoes_e_a_janela(client, entrar, auditor, alerta):
    entrar(auditor)
    html = client.get("/alertas").get_data(as_text=True)

    assert f'data-acao="/alertas/{alerta.id}/decisao-rapida"' in html
    assert re.search(rf'href="/alertas/{alerta.id}"\s+title="Ver detalhes"', html)
    assert 'id="decisao-rapida"' in html


def test_score_formatado_pela_gravidade(client, entrar, auditor, alerta, sessao):
    alerta.excesso, alerta.gravidade = 4.8, "critica"
    sessao.commit()
    entrar(auditor)

    lista = client.get("/alertas").get_data(as_text=True)
    detalhe = client.get(f"/alertas/{alerta.id}").get_data(as_text=True)

    assert 'class="gravidade gravidade-critica"' in lista
    assert "4,80x o limite" in lista
    assert "Crítica" in detalhe and "4,80x o limite do método" in detalhe
