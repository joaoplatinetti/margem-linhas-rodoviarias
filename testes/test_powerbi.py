"""O contrato das tabelas exportadas: grao, chaves e o que nao pode entrar."""
from __future__ import annotations

import pandas as pd
import pytest

from margem import custos, indicadores, powerbi, sintetico

# Razoes: nunca podem virar coluna do fato. Como coluna, o Power BI as agrega
# com Media e devolve um numero que nao corresponde a periodo nenhum.
RAZOES = [
    "load_factor", "yield_pax_km", "rask", "cask_variavel", "cask_total",
    "spread_rask_cask", "margem_contribuicao_pct", "tarifa_media", "receita_km",
]


@pytest.fixture(scope="module")
def fato() -> pd.DataFrame:
    return indicadores.calcular(custos.aplicar(sintetico.gerar()))


@pytest.fixture(scope="module")
def janela(fato) -> pd.DataFrame:
    return indicadores.recomendacao(indicadores.janela_decisao(fato))


def test_fato_mensal_nao_leva_razao(fato):
    """A regra central do modelo estrela, fixada em teste.

    Sem isso, alguem acrescenta `rask` ao fato para "facilitar", o visual passa a
    mostrar a media dos RASK mensais e o painel fica errado em silencio.
    """
    colunas = set(powerbi.fato_linha_mes(fato).columns)
    assert colunas.isdisjoint(RAZOES), colunas & set(RAZOES)


def test_fato_mensal_tem_o_grao_esperado(fato):
    tabela = powerbi.fato_linha_mes(fato)
    assert len(tabela) == 480
    assert not tabela[["linha_id", "data"]].duplicated().any()


def test_custo_despivotado_fecha_com_o_fato(fato):
    """O melt nao pode perder nem duplicar custo."""
    largo = powerbi.fato_linha_mes(fato)
    longo = powerbi.fato_custo_componente(fato)
    total_largo = largo[[c for c in largo.columns if c.startswith("custo_")]].to_numpy().sum()
    assert longo["custo"].sum() == pytest.approx(total_largo, rel=1e-9)
    assert len(longo) == 480 * 6


def test_dimensao_linha_e_chave_unica():
    dim = powerbi.dim_linha()
    assert len(dim) == 20
    assert dim["linha_id"].is_unique
    assert dim["faixa_distancia"].notna().all()


def test_calendario_cobre_o_fato_sem_buraco(fato):
    dim = powerbi.dim_calendario(fato)
    assert len(dim) == 24
    assert dim["data"].is_unique
    assert dim["ordem_mes"].tolist() == list(range(1, 25))
    # Meses consecutivos: a inteligencia de tempo do DAX depende disso.
    assert (dim["data"].diff().dropna().dt.days.between(28, 31)).all()
    assert (dim["na_janela_decisao"] == "sim").sum() == 12


def test_chaves_do_fato_existem_nas_dimensoes(fato):
    tabela = powerbi.fato_linha_mes(fato)
    assert set(tabela["linha_id"]) == set(powerbi.dim_linha()["linha_id"])
    assert set(tabela["data"]) == set(powerbi.dim_calendario(fato)["data"])


def test_classificacao_e_um_retrato_por_linha(janela):
    tabela = powerbi.fato_classificacao(janela)
    assert len(tabela) == 20
    assert tabela["linha_id"].is_unique
    assert tabela["janela_inicio"].nunique() == 1
    # Aqui as razoes PODEM vir prontas: nada sera reagregado entre as linhas.
    assert "rask" in tabela.columns
    assert set(tabela["no_limite"]) <= {"sim", "nao"}


def test_exportacao_grava_as_seis_tabelas(fato, janela, tmp_path, monkeypatch):
    from margem import config

    monkeypatch.setattr(config, "SAIDA_POWERBI", tmp_path / "powerbi")
    resultado = powerbi.exportar(fato, janela)

    assert set(resultado) == {
        "dim_linha", "dim_calendario", "dim_componente_custo",
        "fato_linha_mes", "fato_custo_componente", "fato_classificacao",
    }
    gravados = sorted(p.name for p in (tmp_path / "powerbi").glob("*.csv"))
    assert len(gravados) == 6

    # Releitura: o CSV tem que voltar com o mesmo numero de registros e com
    # acento legivel (utf-8-sig).
    lido = pd.read_csv(tmp_path / "powerbi" / "dim_linha.csv", encoding=powerbi.CODIFICACAO)
    assert len(lido) == 20
    assert "linha_id" in lido.columns
