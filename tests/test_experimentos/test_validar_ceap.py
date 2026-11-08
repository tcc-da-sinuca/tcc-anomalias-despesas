"""Testes da verificação na CEAP (experimentos/validar_ceap.py), com um arquivo fictício
no formato publicado pela Câmara (separador ';', colunas da CEAP)."""

import zipfile

import numpy as np
import pandas as pd
import pytest

from experimentos import validar_ceap as vc

COLUNAS_CEAP = [
    "txNomeParlamentar", "cpf", "ideCadastro", "nuCarteiraParlamentar", "nuLegislatura", "sgUF",
    "sgPartido", "codLegislatura", "numSubCota", "txtDescricao", "numEspecificacaoSubCota",
    "txtDescricaoEspecificacao", "txtFornecedor", "txtCNPJCPF", "txtNumero", "indTipoDocumento",
    "datEmissao", "vlrDocumento", "vlrGlosa", "vlrLiquido", "numMes", "numAno", "numParcela",
    "txtPassageiro", "txtTrecho", "numLote", "numRessarcimento", "datPagamentoRestituicao",
    "vlrRestituicao", "nuDeputadoId", "ideDocumento", "urlDocumento",
]
TIPOS = [("3", "COMBUSTÍVEIS E LUBRIFICANTES.", "1", "Veículos Automotores", 150),
         ("13", "FORNECIMENTO DE ALIMENTAÇÃO DO PARLAMENTAR", "0", "", 60),
         ("1", "MANUTENÇÃO DE ESCRITÓRIO DE APOIO", "0", "", 900)]


def _ceap_ficticia(n=1500, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    linhas = []
    datas = pd.bdate_range("2025-01-02", "2025-12-30")
    for i in range(n):
        sub, desc, esp, desc_esp, mediana = TIPOS[i % len(TIPOS)]
        dep = int(rng.integers(1, 41))
        valor = round(float(rng.lognormal(np.log(mediana), 0.3)), 2)
        linhas.append({c: "" for c in COLUNAS_CEAP} | {
            "txNomeParlamentar": f"Parlamentar {dep}", "cpf": f"{dep:011d}", "ideCadastro": str(1000 + dep),
            "sgUF": ["SP", "MG", "RJ", "BA"][dep % 4], "sgPartido": "PX", "numSubCota": sub,
            "txtDescricao": desc, "numEspecificacaoSubCota": esp, "txtDescricaoEspecificacao": desc_esp,
            "txtFornecedor": f"Fornecedor {i % 50}", "datEmissao": f"{datas[i % len(datas)].date()}T00:00:00",
            "vlrDocumento": f"{valor:.2f}", "vlrGlosa": "0", "vlrLiquido": f"{valor:.2f}",
            "numAno": "2025", "urlDocumento": f"https://exemplo.invalid/{i}.pdf",
        })
    ceap = pd.DataFrame(linhas)
    ceap.loc[0, "vlrLiquido"] = "-350.00"              # compensação de passagem: sai
    ceap.loc[1, ["ideCadastro", "cpf"]] = ""           # liderança: sai
    ceap.loc[2, "numAno"] = "2024"                     # outro ano: sai
    ceap.loc[3, "vlrLiquido"] = "25000.00"             # valor extremo: deve ser sinalizado
    return ceap


@pytest.fixture
def arquivo_zip(tmp_path):
    caminho = tmp_path / "Ano-2025.csv.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("Ano-2025.csv", _ceap_ficticia().to_csv(sep=";", index=False))
    return caminho


def test_preparar_aplica_os_filtros_e_o_mapeamento():
    despesas, contagem = vc.preparar(_ceap_ficticia(), 2025)
    assert contagem["linhas_lidas"] == 1500
    assert contagem["no_ano"] == 1499
    assert contagem["de_parlamentares"] == 1498
    assert contagem["analisadas"] == 1497
    assert (despesas["valor"] > 0).all()
    assert set(despesas["conta_contabil"]) == {"3.1", "13.0", "1.0"}
    assert despesas["despesa_id"].is_unique


def test_ler_ceap_aceita_outra_caixa_nos_nomes_das_colunas(tmp_path):
    ceap = _ceap_ficticia(n=30).rename(columns={"numEspecificacaoSubCota": "numEspecificacaoSubcota"})
    caminho = tmp_path / "ceap.csv"
    caminho.write_text(ceap.to_csv(sep=";", index=False), encoding="utf-8")
    lida = vc.ler_ceap(caminho)
    assert "numEspecificacaoSubCota" in lida.columns
    despesas, _ = vc.preparar(lida, 2025)
    assert despesas["conta_contabil"].str.contains(r"^\d+\.\d+$").all()


def test_analisar_gera_resumo_amostra_e_planilhas(arquivo_zip, tmp_path):
    saida = tmp_path / "saida"
    caminhos = vc.main(["analisar", "--arquivo", str(arquivo_zip), "--ano", "2025",
                        "--por-metodo", "3", "--saida", str(saida)])
    amostra = pd.read_csv(caminhos["amostra"])
    assert amostra["despesa_id"].is_unique
    assert len(amostra) <= 12
    alertas = pd.read_csv(caminhos["alertas"])
    extremo = vc.preparar(_ceap_ficticia(), 2025)[0].query("valor == 25000")["despesa_id"].item()
    assert extremo in set(alertas.loc[alertas["metodo"] == "zscore", "despesa_id"])
    planilha = pd.read_excel(caminhos["revisor_1"], sheet_name="amostra")
    assert {"classificacao", "justificativa", "link_documento", "motivo"} <= set(planilha.columns)


def test_concordancia_calcula_kappa(arquivo_zip, tmp_path):
    saida = tmp_path / "saida"
    caminhos = vc.main(["analisar", "--arquivo", str(arquivo_zip), "--por-metodo", "3",
                        "--saida", str(saida)])
    for revisor, deslocamento in ((1, 0), (2, 1)):
        folha = pd.read_excel(caminhos[f"revisor_{revisor}"], sheet_name="amostra")
        classes = [vc.CLASSES[(i // 2 + deslocamento * (i % 4 == 0)) % 3] for i in range(len(folha))]
        folha["classificacao"] = classes
        with pd.ExcelWriter(caminhos[f"revisor_{revisor}"], engine="openpyxl") as w:
            folha.to_excel(w, sheet_name="amostra", index=False)
    resultado = vc.main(["concordancia", str(caminhos["revisor_1"]), str(caminhos["revisor_2"]),
                         "--saida", str(saida)])
    import json
    dados = json.loads(resultado["concordancia"].read_text(encoding="utf-8"))
    assert 0 < dados["concordancia_percentual"] < 100
    assert -1 <= dados["kappa_cohen_3_classes"] <= 1


def test_kappa_confere_com_o_scikit_learn():
    from sklearn.metrics import cohen_kappa_score

    a = pd.Series(["aprovado", "irregular", "aprovado", "necessita_justificativa", "aprovado", "irregular"])
    b = pd.Series(["aprovado", "irregular", "necessita_justificativa", "necessita_justificativa", "irregular", "irregular"])
    assert vc.kappa_cohen(a, b) == pytest.approx(cohen_kappa_score(a, b))
    assert vc.kappa_cohen(a, a) == pytest.approx(1.0)
