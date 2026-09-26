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
    assert "Análise concluída: 121 despesa(s) analisada(s), 3 alerta(s) novo(s)." in html
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
    assert "121 despesas, 3 alertas novos" in resultado.output


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


def test_dashboard_com_alertas(client, entrar, auditor, alerta):
    entrar(auditor)
    html = client.get("/").get_data(as_text=True)

    assert '<h1 class="h4 m-0">Dashboard</h1>' in html
    assert 'data-indicador="despesas_sinalizadas">1<' in html
    assert 'data-indicador="percentual_sinalizado">100,00%<' in html
    assert "grafico-status" in html and "chart.umd.min.js" in html
    assert "/alertas?status=pendente" in html


def test_dashboard_sem_alertas(client, entrar, auditor):
    entrar(auditor)
    html = client.get("/").get_data(as_text=True)

    assert "Ainda não há alertas." in html
    assert "chart.umd.min.js" not in html


def test_dashboard_exige_login(client):
    resposta = client.get("/")
    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]


def test_grafico_do_dashboard_alinha_rotulos_e_valores(client, entrar, auditor, alerta, sessao):
    import json

    alerta.status_revisao = "irregular"  # só "irregular" tem valor 1; o resto é 0
    sessao.commit()
    entrar(auditor)
    html = client.get("/").get_data(as_text=True)

    def lista(nome):
        return json.loads(re.search(rf"const {nome} = (\[.*?\]);", html).group(1))

    status, valores, nomes = lista("status"), lista("valores"), lista("nomes")
    assert len(status) == len(valores) == len(nomes) == 4
    assert valores[status.index("irregular")] == 1
    assert nomes[status.index("irregular")] == "Irregular"
    assert nomes[status.index("pendente")] == "Pendente"


@pytest.fixture
def varios_alertas(sessao, auditor):
    """60 alertas pendentes em Viagens/CC-ADM e 1 em Software, para testar paginação."""
    from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise

    execucao = ExecucaoAnalise(parametros={}, seed=42, executada_por=auditor.id)
    objetos = [execucao]
    for i in range(61):
        categoria = "Software" if i == 60 else "Viagens"
        despesa = Despesa(
            valor=Decimal("100.00"),
            data=date(2026, 3, 2),
            categoria=categoria,
            conta_contabil="3.1.01",
            centro_custo="CC-ADM",
            funcionario="F001",
        )
        objetos += [
            despesa,
            AlertaAnomalia(
                despesa=despesa, execucao=execucao, metodo="zscore", score=i, motivo="m"
            ),
        ]
    sessao.add_all(objetos)
    sessao.commit()


def test_formulario_de_filtros_mantem_as_escolhas(client, entrar, auditor, varios_alertas):
    entrar(auditor)
    html = client.get("/alertas?categoria=Viagens&data_inicio=2026-03-01&status=pendente").get_data(
        as_text=True
    )

    assert '<option value="Viagens" selected>' in html
    assert '<option value="Software" >' in html  # opções vêm das despesas existentes
    assert re.search(r'name="data_inicio"[^>]*value="2026-03-01"', html)
    assert "60 alerta(s) com 3 filtro(s) ativo(s)." in html


def test_paginacao_preserva_os_filtros(client, entrar, auditor, varios_alertas):
    entrar(auditor)
    html = client.get("/alertas?categoria=Viagens&status=pendente").get_data(as_text=True)

    links = re.findall(r'href="(/alertas\?[^"]*pagina=2[^"]*)"', html)
    assert links
    assert "categoria=Viagens" in links[0] and "status=pendente" in links[0]


def test_filtro_invalido_na_tela(client, entrar, auditor, varios_alertas):
    entrar(auditor)
    resposta = client.get("/alertas?data_inicio=2026-04-01&data_fim=2026-03-01")

    html = resposta.get_data(as_text=True)
    assert resposta.status_code == 400
    assert "A data final não pode ser anterior à inicial." in html
    assert "Os filtros não foram aplicados." in html


def test_parametros_somente_leitura_para_auditor(client, entrar, auditor):
    entrar(auditor)
    html = client.get("/parametros").get_data(as_text=True)

    assert "Limiar do |z|" in html
    assert "Só o administrador pode alterar" in html
    assert "Salvar parâmetros" not in html
    assert client.post("/parametros", data={"zscore.limiar": "2"}).status_code == 403


def test_administrador_salva_parametros(client, entrar, administrador, sessao):
    from app.models import ParametroMetodo
    from app.servicos.parametros import REGRAS, listar_parametros

    entrar(administrador)
    atuais = {item["regra"].nome: str(item["valor"]) for item in listar_parametros()}
    atuais["zscore.limiar"] = "2.5"
    resposta = client.post("/parametros", data=atuais, follow_redirects=True)

    html = resposta.get_data(as_text=True)
    assert "1 parâmetro(s) alterado(s)." in html
    assert "alterado</span>" in html
    assert sessao.get(ParametroMetodo, ("zscore", "limiar")).valor == "2.5"
    assert len(REGRAS) == len(atuais)


def test_parametro_invalido_na_tela(client, entrar, administrador):
    from app.servicos.parametros import listar_parametros

    entrar(administrador)
    dados = {item["regra"].nome: str(item["valor"]) for item in listar_parametros()}
    dados["iqr.fator"] = "0.1"
    resposta = client.post("/parametros", data=dados)

    html = resposta.get_data(as_text=True)
    assert resposta.status_code == 400
    assert "Nenhum parâmetro foi alterado." in html
    assert "Fator do IQR: use um valor de 0,5 a 10." in html
    assert 'value="0.1"' in html  # mantém o que foi digitado


def test_relatorio_abre_no_mes_da_despesa_mais_recente(client, entrar, auditor, alerta):
    entrar(auditor)
    html = client.get("/relatorios").get_data(as_text=True)

    assert "Setembro de 2026" in html
    assert 'data-indicador="total_despesas">1<' in html
    assert "indefinida" in html
    assert "/api/relatorios/mensal?ano=2026&amp;mes=9&amp;formato=csv" in html
    assert ">Relatório</a>" in html


def test_relatorio_mes_sem_despesas_e_invalido(client, entrar, auditor, alerta):
    entrar(auditor)
    assert "Nenhuma despesa com data neste mês." in client.get(
        "/relatorios?ano=2025&mes=1"
    ).get_data(as_text=True)
    resposta = client.get("/relatorios?ano=2026&mes=13")
    assert resposta.status_code == 400
    assert "O mês deve estar entre 1 e 12." in resposta.get_data(as_text=True)


@pytest.mark.parametrize(
    ("caminho", "botao"), [("/alertas", "Filtrar"), ("/relatorios", "Ver relatório")]
)
def test_filtros_aplicados_ao_mudar(client, entrar, auditor, alerta, caminho, botao):
    entrar(auditor)
    html = client.get(caminho).get_data(as_text=True)

    assert re.search(r"<form method=\"get\"[^>]*data-aplicar-ao-mudar>", html)
    assert "/static/js/app.js" in html
    # o botão de envio só aparece para quem estiver sem JavaScript
    assert re.search(rf"<noscript><button type=\"submit\"[^>]*>{botao}</button></noscript>", html)


def test_script_dos_filtros_e_servido(client):
    resposta = client.get("/static/js/app.js")
    assert resposta.status_code == 200
    assert "data-aplicar-ao-mudar" in resposta.get_data(as_text=True)
    resposta.close()
