"""As identidades, a agregacao por razao de somas e as fronteiras da decisao."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from margem import config, custos, indicadores, sintetico


@pytest.fixture(scope="module")
def fato() -> pd.DataFrame:
    return indicadores.calcular(custos.aplicar(sintetico.gerar()))


@pytest.fixture(scope="module")
def janela(fato) -> pd.DataFrame:
    return indicadores.janela_decisao(fato)


def test_identidades_no_fato(fato):
    erros = indicadores.reconciliar(fato)
    assert (erros["erro_maximo"] < 1e-9).all(), erros.to_string()


def test_identidades_na_janela(janela):
    erros = indicadores.reconciliar(janela)
    assert (erros["erro_maximo"] < 1e-9).all(), erros.to_string()


def test_agregacao_e_razao_de_somas_nao_media_de_razoes(fato):
    """O RASK da rede e receita total / ASK total, e nao a media dos RASK mensais.

    Este e o teste mais importante do modulo. A media de razoes da peso igual a
    um fevereiro e a um julho, e o numero resultante nao corresponde a periodo
    nenhum — e e um erro que passa despercebido porque o valor sai plausivel.
    """
    rede = indicadores.agregar(fato).iloc[0]
    razao_de_somas = fato["receita"].sum() / fato["assentos_km"].sum()
    media_de_razoes = fato["rask"].mean()

    assert rede["rask"] == pytest.approx(razao_de_somas)
    assert rede["rask"] != pytest.approx(media_de_razoes)


def test_agregar_por_recorte_preserva_os_totais(fato):
    por_classe = indicadores.agregar(fato, por=["classe"])
    assert por_classe["receita"].sum() == pytest.approx(fato["receita"].sum())
    assert por_classe["assentos_km"].sum() == pytest.approx(fato["assentos_km"].sum())


def test_denominador_zero_vira_nulo_e_nao_infinito():
    """Linha sem partida no mes tem que dar NaN. Infinito contaminaria a soma."""
    vazio = pd.DataFrame({
        "partidas": [0], "km_rodados": [0.0], "assentos_km": [0.0],
        "passageiros": [0], "passageiros_km": [0.0], "receita": [0.0],
        "custo_variavel": [0.0], "custo_total": [0.0],
        **{c: [0.0] for c in config.COMPONENTES_TODOS},
    })
    saida = indicadores.calcular(vazio)
    assert saida["rask"].isna().all()
    assert not np.isinf(saida["rask"]).any()


def test_janela_usa_os_ultimos_doze_meses(fato):
    janela = indicadores.janela_decisao(fato)
    assert len(janela) == 20
    assert janela.attrs["meses"] == sorted(fato["ano_mes"].unique())[-12:]
    assert janela.attrs["meses"][-1] == config.PERIODO_FIM


def test_janela_maior_que_o_dataset_falha(fato):
    with pytest.raises(ValueError, match="janela pede"):
        indicadores.janela_decisao(fato, meses=48)


# ---------------------------------------------------------------------------
# Load factor de equilibrio
# ---------------------------------------------------------------------------

def test_equilibrio_fecha_a_identidade(janela):
    """yield x LF de equilibrio tem que dar exatamente o CASK total."""
    produto = janela["yield_pax_km"] * janela["lf_equilibrio"]
    pd.testing.assert_series_equal(produto, janela["cask_total"], check_names=False)


def test_equilibrio_diz_o_mesmo_que_o_spread(janela):
    """Cobrir o custo cheio e ter ocupacao acima do equilibrio sao a MESMA coisa.

    As duas formas existem porque falam linguas diferentes — uma e financeira,
    a outra e operacional — mas elas nao podem discordar nunca. Se discordarem,
    o grafico de ocupacao e a coluna de classificacao contariam historias
    diferentes sobre a mesma linha.
    """
    por_spread = janela["spread_rask_cask"] >= 0
    por_ocupacao = janela["load_factor"] >= janela["lf_equilibrio"] - 1e-12
    assert (por_spread == por_ocupacao).all()
    assert (por_spread == (janela["classificacao"] == "MANTER")).all()


def test_rever_fica_abaixo_do_equilibrio_variavel(janela):
    """REVER e, em ocupacao, nao alcancar nem o equilibrio do custo variavel."""
    rever = janela["classificacao"] == "REVER"
    abaixo = janela["load_factor"] <= janela["lf_equilibrio_variavel"] + 1e-12
    assert (rever == abaixo).all()


def test_folga_e_a_diferenca_das_duas_ocupacoes(janela):
    esperado = janela["load_factor"] - janela["lf_equilibrio"]
    pd.testing.assert_series_equal(janela["folga_lf"], esperado, check_names=False)


# ---------------------------------------------------------------------------
# Fronteiras da classificacao
# ---------------------------------------------------------------------------

def _caso(receita: float, custo_variavel: float, custo_fixo: float) -> pd.DataFrame:
    """Uma linha artificial com ASK = 1, para o spread sair em reais redondos."""
    base = pd.DataFrame({
        "partidas": [1], "km_rodados": [1.0], "assentos_km": [1.0],
        "passageiros": [1], "passageiros_km": [1.0], "receita": [receita],
        "custo_variavel": [custo_variavel],
        "custo_total": [custo_variavel + custo_fixo],
        "custo_fixo_rateado": [custo_fixo],
        **{c: [0.0] for c in config.COMPONENTES_VARIAVEIS},
    })
    return indicadores.classificar(indicadores.calcular(base))


def test_manter_quando_cobre_o_custo_cheio():
    assert _caso(10.0, 5.0, 3.0).loc[0, "classificacao"] == "MANTER"


def test_ajustar_quando_cobre_o_variavel_mas_nao_o_fixo():
    assert _caso(10.0, 8.0, 3.0).loc[0, "classificacao"] == "AJUSTAR"


def test_rever_quando_nao_cobre_o_variavel():
    assert _caso(10.0, 11.0, 3.0).loc[0, "classificacao"] == "REVER"


def test_mc_negativa_vence_o_teste_do_spread():
    """MC negativa tambem produz spread negativo.

    Se a ordem dos testes inverter, a linha grave cai em AJUSTAR e o caso mais
    urgente da malha fica escondido dentro do caso administravel.
    """
    caso = _caso(10.0, 12.0, 3.0).loc[0]
    assert caso["margem_contribuicao"] < 0
    assert caso["spread_rask_cask"] < 0
    assert caso["classificacao"] == "REVER"


def test_fronteira_exata_do_spread_zero():
    """Spread exatamente zero e MANTER: a linha cobre o custo cheio."""
    caso = _caso(10.0, 7.0, 3.0).loc[0]
    assert caso["spread_rask_cask"] == pytest.approx(0.0)
    assert caso["classificacao"] == "MANTER"


def test_fronteira_exata_da_mc_zero():
    """MC exatamente zero e REVER: a linha nao sobra nada para o fixo."""
    caso = _caso(10.0, 10.0, 3.0).loc[0]
    assert caso["margem_contribuicao"] == pytest.approx(0.0)
    assert caso["classificacao"] == "REVER"


def test_no_limite_marca_a_folga_estreita():
    folgada = _caso(10.0, 5.0, 3.0).loc[0]          # spread 2,00 por ASK
    apertada = _caso(10.0, 7.0, 2.995).loc[0]       # spread 0,005 por ASK
    assert not folgada["no_limite"]
    assert apertada["no_limite"]
    assert apertada["classificacao"] == "MANTER"


def test_todas_as_classes_aparecem_no_dataset(janela):
    """O exercicio precisa exercitar as tres decisoes.

    Se a calibragem das premissas mandar as 20 linhas para MANTER, a peca nao
    demonstra nada — e o teste falha de proposito para avisar.
    """
    contagem = janela["classificacao"].value_counts()
    for nome in config.CLASSIFICACOES:
        assert contagem.get(nome, 0) > 0, f"nenhuma linha em {nome}"


def test_alavanca_cobre_todas_as_linhas(janela):
    recomendado = indicadores.recomendacao(janela)
    assert recomendado["alavanca"].notna().all()
    assert (recomendado["alavanca"] != "").all()
