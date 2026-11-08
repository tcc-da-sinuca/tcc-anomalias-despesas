"""Verificação qualitativa do motor em dados reais: despesas da CEAP (Câmara dos Deputados).

Responde ao item 1 da verificação do orientador de 06/11/2026: aplicar o motor aos dados
abertos da Cota para o Exercício da Atividade Parlamentar (CEAP), contar quantas despesas
são sinalizadas e ler os alertas de maior excesso, classificados por duas pessoas de forma
independente, com a concordância entre elas (kappa de Cohen).

Os dados **não têm rótulo**: o resultado não é precisão nem recall, e sim (a) quanto o
motor sinaliza numa base real e (b) se as pessoas que leem os alertas os consideram
procedentes, e se concordam entre si. Um alerta é um indício estatístico, não uma acusação
— o mesmo princípio da aplicação vale para a leitura destes alertas.

Mapeamento da CEAP para o contrato do motor (``motor/contrato.py``):

==================  =====================================================================
Coluna do motor     Coluna da CEAP
==================  =====================================================================
``valor``           ``vlrLiquido`` (valor efetivamente debitado da cota)
``data``            ``datEmissao`` (data de emissão do documento)
``categoria``       ``txtDescricao`` (tipo de despesa, ex.: "COMBUSTÍVEIS E LUBRIFICANTES.")
``conta_contabil``  ``numSubCota`` + ``numEspecificacaoSubCota`` (tipo e subtipo da despesa)
``centro_custo``    ``sgUF`` (UF do parlamentar; o valor da cota varia por UF)
``funcionario``     ``ideCadastro`` (identificador do parlamentar)
==================  =====================================================================

Filtros: competência no ano pedido (``numAno``), só despesas de parlamentares (sem as
lideranças, que não têm ``ideCadastro``) e ``vlrLiquido`` > 0 (exclui compensações de
passagens e telefonia coberta pela franquia). Parâmetros: os padrões da aplicação, sem
ajuste (o limite de aprovação de R$ 1.000 do fracionamento não existe na CEAP e é mantido
só para rodar o motor como ele é).

Uso::

    # 1. baixa o arquivo do ano, roda o motor e gera as planilhas dos dois revisores
    python -m experimentos.validar_ceap analisar --ano 2025
    python -m experimentos.validar_ceap analisar --arquivo Ano-2025.csv.zip   # já baixado

    # 2. depois que as duas pessoas preencherem as planilhas, sem conversar entre si
    python -m experimentos.validar_ceap concordancia \\
        experimentos/resultados/validacao_ceap/revisor_1.xlsx \\
        experimentos/resultados/validacao_ceap/revisor_2.xlsx

Saída em ``experimentos/resultados/validacao_ceap/``.
Regra do projeto: nenhum número vai para o artigo sem ter saído de uma execução real.
"""

import argparse
import io
import json
import platform
import time
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

from motor.consolidador import consolidar, executar_detectores, parametros_padrao
from motor.gravidade import NIVEIS

PASTA_SAIDA = Path(__file__).resolve().parent / "resultados" / "validacao_ceap"
URL_ANO = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
POR_METODO_PADRAO = 7  # 4 métodos x 7 = 28 alertas (o orientador pediu de 20 a 30)
SEED_AMOSTRA = 42

CLASSES = ("aprovado", "necessita_justificativa", "irregular")
DESCRICAO_CLASSES = {
    "aprovado": "O documento e o contexto explicam a despesa; o alerta não se sustenta (falso positivo).",
    "necessita_justificativa": "O documento não basta para entender a despesa (valor, data, fornecedor ou "
                               "repetição); numa auditoria, seria preciso pedir explicação.",
    "irregular": "O próprio documento mostra o problema apontado pelo alerta (ex.: o mesmo documento "
                 "lançado duas vezes, despesa fora das regras da CEAP). É um indício confirmado, não uma "
                 "conclusão sobre a pessoa.",
}
# Colunas da CEAP lidas pelo script, com a grafia do arquivo publicado pela Câmara.
COLUNAS_CEAP = {nome.lower(): nome for nome in (
    "txNomeParlamentar", "ideCadastro", "sgUF", "sgPartido", "numSubCota", "txtDescricao",
    "numEspecificacaoSubCota", "txtDescricaoEspecificacao", "txtFornecedor", "txtCNPJCPF",
    "datEmissao", "vlrDocumento", "vlrLiquido", "numAno", "txtTrecho", "urlDocumento",
)}
COLUNAS_PLANILHA = {
    "id_amostra": "id_amostra", "metodo": "metodo", "gravidade": "gravidade", "motivo": "motivo",
    "txNomeParlamentar": "parlamentar", "sgUF": "uf", "sgPartido": "partido",
    "txtDescricao": "tipo_despesa", "txtDescricaoEspecificacao": "subtipo",
    "txtFornecedor": "fornecedor", "txtCNPJCPF": "cnpj_cpf_fornecedor", "data": "data_emissao",
    "valor": "valor_liquido", "vlrDocumento": "valor_documento", "txtTrecho": "trecho",
    "urlDocumento": "link_documento", "despesa_id": "despesa_id",
}


# --- Leitura e preparação ------------------------------------------------------------


def baixar(ano: int, destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"Ano-{ano}.csv.zip"
    if not caminho.exists():
        print(f"Baixando {URL_ANO.format(ano=ano)} ...")
        urllib.request.urlretrieve(URL_ANO.format(ano=ano), caminho)
    return caminho


def ler_ceap(caminho: Path) -> pd.DataFrame:
    """Lê o CSV da CEAP (zipado ou não). Separador ';' e UTF-8, como publicado pela Câmara."""
    if caminho.suffix == ".zip":
        with zipfile.ZipFile(caminho) as z:
            nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            bruto = z.read(nome)
    else:
        bruto = caminho.read_bytes()
    for codificacao in ("utf-8-sig", "latin-1"):
        try:
            texto = bruto.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    separador = ";" if texto[:2000].count(";") >= texto[:2000].count(",") else ","
    ceap = pd.read_csv(io.StringIO(texto), sep=separador, dtype=str, keep_default_na=False)
    # A Câmara já variou a caixa de alguns nomes (ex.: numEspecificacaoSubCota/Subcota).
    return ceap.rename(columns={c: COLUNAS_CEAP[c.lower()] for c in ceap.columns
                                if c.lower() in COLUNAS_CEAP})


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie.str.strip().str.replace(",", ".", regex=False), errors="coerce")


def preparar(ceap: pd.DataFrame, ano: int | None) -> tuple[pd.DataFrame, dict]:
    """Aplica os filtros e monta as colunas do contrato do motor. Devolve (despesas, contagem)."""
    contagem = {"linhas_lidas": len(ceap)}
    df = ceap.copy()
    if ano is not None and "numAno" in df:
        df = df[_numero(df["numAno"]) == ano]
    contagem["no_ano"] = len(df)
    df = df[df["ideCadastro"].str.strip() != ""]
    contagem["de_parlamentares"] = len(df)
    df = df.assign(valor=_numero(df["vlrLiquido"]),
                   data=pd.to_datetime(df["datEmissao"].str[:10], errors="coerce", format="%Y-%m-%d"))
    df = df[(df["valor"] > 0) & df["data"].notna()]
    contagem["analisadas"] = len(df)
    contagem["removidas_valor_nao_positivo_ou_sem_data"] = contagem["de_parlamentares"] - len(df)
    df = df.reset_index(drop=True)
    df["despesa_id"] = np.arange(1, len(df) + 1)
    df["categoria"] = df["txtDescricao"].str.strip()
    df["conta_contabil"] = df["numSubCota"].str.strip() + "." + df["numEspecificacaoSubCota"].str.strip()
    df["centro_custo"] = df["sgUF"].str.strip()
    df["funcionario"] = df["ideCadastro"].str.strip()
    return df, contagem


# --- Análise -------------------------------------------------------------------------


def amostrar(alertas: pd.DataFrame, por_metodo: int) -> pd.DataFrame:
    """Os ``por_metodo`` alertas de maior excesso de cada método, sem repetir despesa."""
    escolhidos, usadas = [], set()
    for metodo in ("zscore", "iqr", "contextual", "isolation_forest"):
        candidatos = alertas[alertas["metodo"] == metodo].sort_values(
            ["excesso", "score", "despesa_id"], ascending=[False, False, True])
        candidatos = candidatos[~candidatos["despesa_id"].isin(usadas)].head(por_metodo)
        usadas.update(candidatos["despesa_id"])
        escolhidos.append(candidatos)
    amostra = pd.concat(escolhidos, ignore_index=True)
    # ordem embaralhada (semente fixa) para a leitura não seguir o ranking dos métodos
    amostra = amostra.sample(frac=1, random_state=SEED_AMOSTRA).reset_index(drop=True)
    amostra.insert(0, "id_amostra", np.arange(1, len(amostra) + 1))
    return amostra


def _gravar_planilha(amostra: pd.DataFrame, caminho: Path, revisor: int) -> None:
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation

    tabela = amostra[[c for c in COLUNAS_PLANILHA if c in amostra]].rename(columns=COLUNAS_PLANILHA)
    tabela["data_emissao"] = pd.to_datetime(tabela["data_emissao"]).dt.strftime("%d/%m/%Y")
    tabela["classificacao"] = ""
    tabela["justificativa"] = ""
    instrucoes = pd.DataFrame({"campo": [
        "Revisor", "Como classificar", *CLASSES, "Regra",
        "Lembrete"], "texto": [
        f"Revisor {revisor} — preencha só a sua planilha.",
        "Para cada alerta, abra o link do documento, leia o motivo e escolha uma classificação "
        "na coluna 'classificacao'. Use a coluna 'justificativa' para uma frase curta.",
        *[DESCRICAO_CLASSES[c] for c in CLASSES],
        "Classifique sozinho. Não converse com o outro revisor nem veja a planilha dele até os dois "
        "terminarem: a concordância só vale se as leituras forem independentes.",
        "O alerta é um indício estatístico, não uma acusação. A classificação é sobre o documento, "
        "não sobre a pessoa.",
    ]})
    with pd.ExcelWriter(caminho, engine="openpyxl") as escritor:
        instrucoes.to_excel(escritor, sheet_name="instrucoes", index=False)
        tabela.to_excel(escritor, sheet_name="amostra", index=False)
    livro = load_workbook(caminho)
    folha = livro["amostra"]
    col = {c.value: c.column_letter for c in folha[1]}
    validacao = DataValidation(type="list", formula1='"' + ",".join(CLASSES) + '"', allow_blank=True)
    folha.add_data_validation(validacao)
    validacao.add(f"{col['classificacao']}2:{col['classificacao']}{len(tabela) + 1}")
    larguras = {"motivo": 60, "parlamentar": 28, "tipo_despesa": 30, "fornecedor": 30,
                "link_documento": 40, "classificacao": 24, "justificativa": 40}
    for nome, letra in col.items():
        folha.column_dimensions[letra].width = larguras.get(nome, 14)
    for celula in folha[1]:
        celula.font = Font(bold=True)
    for linha in folha.iter_rows(min_row=2):
        for celula in linha:
            celula.alignment = Alignment(wrap_text=True, vertical="top")
    folha.freeze_panes = "B2"
    livro["instrucoes"].column_dimensions["A"].width = 26
    livro["instrucoes"].column_dimensions["B"].width = 110
    for linha in livro["instrucoes"].iter_rows(min_row=2):
        linha[1].alignment = Alignment(wrap_text=True, vertical="top")
    livro.active = livro.sheetnames.index("amostra")
    livro.save(caminho)


def analisar(args) -> dict[str, Path]:
    inicio = time.perf_counter()
    args.saida.mkdir(parents=True, exist_ok=True)
    arquivo = args.arquivo or baixar(args.ano, args.saida / "dados")
    ano = args.ano
    despesas, contagem = preparar(ler_ceap(Path(arquivo)), ano)
    if despesas.empty:
        raise SystemExit("Nenhuma despesa depois dos filtros; confira o arquivo e o --ano.")

    parametros = parametros_padrao()
    t0 = time.perf_counter()
    resultados = executar_detectores(despesas, parametros)
    duracao_motor = time.perf_counter() - t0
    alertas = consolidar(resultados)
    colunas_info = ["despesa_id", "valor", "data", "categoria", "conta_contabil", "centro_custo",
                    "funcionario", *[c for c in COLUNAS_PLANILHA if c in despesas and c not in
                                     ("valor", "data", "despesa_id")]]
    alertas = alertas.merge(despesas[list(dict.fromkeys(colunas_info))], on="despesa_id", how="left")

    caminhos = {}
    caminhos["alertas"] = args.saida / "alertas.csv"
    alertas.to_csv(caminhos["alertas"], index=False, float_format="%.4f")

    n = len(despesas)
    por_metodo = []
    for metodo, resultado in resultados.items():
        sinal = resultado[resultado["sinalizado"]]
        do_metodo = alertas[alertas["metodo"] == metodo]
        linha = {"metodo": metodo, "sinalizadas": int(len(sinal)),
                 "percentual": round(100 * len(sinal) / n, 2),
                 "nao_avaliadas": int(resultado["score"].isna().sum())}
        for nivel in NIVEIS:
            linha[f"gravidade_{nivel}"] = int((do_metodo["gravidade"] == nivel).sum())
        por_metodo.append(linha)
    com_alerta = alertas["despesa_id"].nunique()
    por_metodo.append({"metodo": "qualquer_metodo", "sinalizadas": int(com_alerta),
                       "percentual": round(100 * com_alerta / n, 2)})
    caminhos["por_metodo"] = args.saida / "sinalizadas_por_metodo.csv"
    pd.DataFrame(por_metodo).to_csv(caminhos["por_metodo"], index=False)

    amostra = amostrar(alertas, args.por_metodo)
    caminhos["amostra"] = args.saida / "amostra.csv"
    amostra.to_csv(caminhos["amostra"], index=False, float_format="%.4f")
    for revisor in (1, 2):
        caminhos[f"revisor_{revisor}"] = args.saida / f"revisor_{revisor}.xlsx"
        _gravar_planilha(amostra, caminhos[f"revisor_{revisor}"], revisor)

    resumo = {
        "executado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "fonte": str(arquivo), "ano_competencia": ano, **contagem,
        "periodo_emissao": [despesas["data"].min().date().isoformat(),
                            despesas["data"].max().date().isoformat()],
        "parlamentares": int(despesas["funcionario"].nunique()),
        "tipos_de_despesa": int(despesas["categoria"].nunique()),
        "valor_total_analisado": round(float(despesas["valor"].sum()), 2),
        "despesas_com_algum_alerta": int(com_alerta),
        "percentual_com_algum_alerta": round(100 * com_alerta / n, 2),
        "valor_total_com_alerta": round(float(despesas.loc[despesas["despesa_id"].isin(
            alertas["despesa_id"]), "valor"].sum()), 2),
        "alertas_por_metodo": {l["metodo"]: l["sinalizadas"] for l in por_metodo},
        "amostra": {"por_metodo": args.por_metodo, "total": int(len(amostra)),
                    "criterio": "maior excesso de cada método, sem repetir despesa",
                    "seed_ordem": SEED_AMOSTRA},
        "parametros": parametros,
        "duracao_motor_s": round(duracao_motor, 1),
        "duracao_total_s": round(time.perf_counter() - inicio, 1),
        "versoes": {"python": platform.python_version(), "pandas": pd.__version__,
                    "numpy": np.__version__, "scikit-learn": sklearn.__version__},
    }
    caminhos["resumo"] = args.saida / "resumo.json"
    caminhos["resumo"].write_text(json.dumps(resumo, indent=2, ensure_ascii=False, default=str),
                                  encoding="utf-8")
    for c in caminhos.values():
        print(f"Gravado: {c}")
    return caminhos


# --- Concordância --------------------------------------------------------------------


def kappa_cohen(a: pd.Series, b: pd.Series, classes=CLASSES) -> float:
    """Kappa de Cohen (1960): (concordância observada − esperada) / (1 − esperada)."""
    tabela = pd.crosstab(pd.Categorical(a, classes), pd.Categorical(b, classes), dropna=False)
    total = tabela.to_numpy().sum()
    observada = np.trace(tabela.to_numpy()) / total
    esperada = (tabela.sum(axis=1).to_numpy() * tabela.sum(axis=0).to_numpy()).sum() / total**2
    return float((observada - esperada) / (1 - esperada)) if esperada < 1 else 1.0


def _ler_revisor(caminho: Path) -> pd.DataFrame:
    folha = pd.read_excel(caminho, sheet_name="amostra", dtype={"classificacao": str})
    folha["classificacao"] = folha["classificacao"].fillna("").str.strip().str.lower()
    invalidas = folha.loc[~folha["classificacao"].isin(CLASSES), "id_amostra"].tolist()
    if invalidas:
        raise SystemExit(f"{caminho.name}: classificação vazia ou inválida em id_amostra {invalidas}. "
                         f"Use uma destas: {', '.join(CLASSES)}.")
    return folha[["id_amostra", "metodo", "classificacao"]]


def concordancia(args) -> dict[str, Path]:
    r1, r2 = _ler_revisor(args.revisor_1), _ler_revisor(args.revisor_2)
    juntos = r1.merge(r2, on=["id_amostra", "metodo"], suffixes=("_1", "_2"), validate="one_to_one")
    if len(juntos) != len(r1) or len(juntos) != len(r2):
        raise SystemExit("As duas planilhas não têm os mesmos alertas (id_amostra e método).")
    a, b = juntos["classificacao_1"], juntos["classificacao_2"]
    procedente = lambda s: s.isin(["necessita_justificativa", "irregular"])  # noqa: E731
    resultado = {
        "executado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "alertas": int(len(juntos)),
        "concordancia_percentual": round(100 * float((a == b).mean()), 1),
        "kappa_cohen_3_classes": round(kappa_cohen(a, b), 3),
        "kappa_cohen_procedente_x_nao": round(kappa_cohen(
            procedente(a).map({True: "procedente", False: "nao"}),
            procedente(b).map({True: "procedente", False: "nao"}), ("procedente", "nao")), 3),
        "distribuicao_revisor_1": a.value_counts().reindex(CLASSES, fill_value=0).to_dict(),
        "distribuicao_revisor_2": b.value_counts().reindex(CLASSES, fill_value=0).to_dict(),
        "procedentes_pelos_dois": int((procedente(a) & procedente(b)).sum()),
        "procedentes_por_pelo_menos_um": int((procedente(a) | procedente(b)).sum()),
        "por_metodo": {},
    }
    for metodo, g in juntos.groupby("metodo"):
        resultado["por_metodo"][metodo] = {
            "alertas": int(len(g)),
            "concordancia_percentual": round(100 * float((g["classificacao_1"] == g["classificacao_2"]).mean()), 1),
            "procedentes_pelos_dois": int((procedente(g["classificacao_1"]) & procedente(g["classificacao_2"])).sum()),
        }
    args.saida.mkdir(parents=True, exist_ok=True)
    caminhos = {"concordancia": args.saida / "concordancia.json",
                "matriz": args.saida / "matriz_concordancia.csv"}
    caminhos["concordancia"].write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    pd.crosstab(pd.Categorical(a, CLASSES), pd.Categorical(b, CLASSES), dropna=False,
                rownames=["revisor_1"], colnames=["revisor_2"]).to_csv(caminhos["matriz"])
    for c in caminhos.values():
        print(f"Gravado: {c}")
    print(json.dumps({k: resultado[k] for k in ("alertas", "concordancia_percentual",
                                                "kappa_cohen_3_classes")}, ensure_ascii=False))
    return caminhos


def main(argv: list[str] | None = None) -> dict[str, Path]:
    parser = argparse.ArgumentParser(description="Verificação qualitativa do motor na CEAP.")
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("analisar", help="Roda o motor na CEAP e gera as planilhas de revisão.")
    p.add_argument("--ano", type=int, default=2025, help="Ano de competência (padrão: 2025).")
    p.add_argument("--arquivo", type=Path, help="CSV ou ZIP da CEAP já baixado.")
    p.add_argument("--por-metodo", type=int, default=POR_METODO_PADRAO)
    p.add_argument("--saida", type=Path, default=PASTA_SAIDA)
    c = sub.add_parser("concordancia", help="Concordância entre as duas planilhas preenchidas.")
    c.add_argument("revisor_1", type=Path)
    c.add_argument("revisor_2", type=Path)
    c.add_argument("--saida", type=Path, default=PASTA_SAIDA)
    args = parser.parse_args(argv)
    return analisar(args) if args.comando == "analisar" else concordancia(args)


if __name__ == "__main__":
    main()
