"""O CSV de exemplo da demonstração continua sendo importado como o roteiro descreve."""

from pathlib import Path

ARQUIVO = Path(__file__).resolve().parents[2] / "dados" / "exemplos" / "importacao_demonstracao.csv"


def test_importa_9_linhas_e_aponta_2_erros(sessao, auditor):
    from app.servicos.importacao import importar_arquivo

    lote = importar_arquivo(ARQUIVO.name, ARQUIVO.read_bytes(), auditor)

    assert (lote.total_linhas, lote.linhas_validas) == (11, 9)
    assert [(erro["linha"], erro["campo"]) for erro in lote.erros] == [(11, "valor"), (12, "data")]
