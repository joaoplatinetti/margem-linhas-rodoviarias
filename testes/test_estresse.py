"""
Cenario, ponto de ruptura, tornado e Monte Carlo.

O teste mais importante deste arquivo nao e sobre numero nenhum: e o que garante
que o cenario RESTAURA `config`. Mutar constante global e o preco que este
modulo paga para percorrer o mesmo caminho de calculo da rodada normal, e uma
restauracao que falha contaminaria todas as rodadas seguintes do processo —
inclusive as que nada tem a ver com estresse, e num lugar longe da causa.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from margem import config, estresse, indicadores


# ---------------------------------------------------------------------------
# O gerenciador de cenario
# ---------------------------------------------------------------------------

def test_cenario_restaura_tudo_ao_sair():
    antes = {nome: getattr(config, nome) for nome in estresse._ALVOS}

    with estresse.cenario(diesel=1.5, custo_fixo=0.8, demanda=1.2):
        assert config.DIESEL_LITRO == pytest.approx(antes["DIESEL_LITRO"] * 1.5)
        assert config.FATOR_DEMANDA == pytest.approx(1.2)

    for nome, valor in antes.items():
        assert getattr(config, nome) == valor, f"{nome} nao voltou ao valor original"


def test_cenario_restaura_mesmo_com_erro():
    """O `finally` e a razao de o modulo ser seguro. Este teste prova que ele esta la."""
    diesel = config.DIESEL_LITRO
    with pytest.raises(RuntimeError):
        with estresse.cenario(diesel=2.0):
            raise RuntimeError("estouro no meio do cenario")
    assert config.DIESEL_LITRO == diesel


def test_cenario_nao_altera_dicionario_original():
    """Os corredores sao dicionario aninhado: o cenario nao pode mutar em lugar."""
    original = config.CORREDORES["SUDESTE"]["pedagio_km"]
    with estresse.cenario(pedagio=3.0):
        assert config.CORREDORES["SUDESTE"]["pedagio_km"] == pytest.approx(original * 3)
    assert config.CORREDORES["SUDESTE"]["pedagio_km"] == original


def test_parametro_desconhecido_falha():
    with pytest.raises(ValueError, match="parametro desconhecido"):
        with estresse.cenario(cambio=1.1):
            pass


def test_cenario_neutro_reproduz_o_modelo_base():
    """Fator 1,0 em tudo tem que dar exatamente a rodada normal.

    Se nao der, alguma mutacao esta escapando da restauracao ou o caminho de
    calculo do cenario divergiu do caminho normal — que e o defeito que este
    modulo inteiro existe para evitar.
    """
    from margem import custos, sintetico

    base = indicadores.janela_decisao(
        indicadores.calcular(custos.aplicar(sintetico.gerar()))
    )
    pela_estresse = estresse.rodar({})
    pd.testing.assert_frame_equal(
        base.reset_index(drop=True), pela_estresse.reset_index(drop=True)
    )


def test_so_demanda_e_tarifa_exigem_regerar():
    """Reaproveitar o dataset e o que deixa o Monte Carlo cinco vezes mais rapido.

    Se um parametro de custo passar a exigir regeracao sem necessidade, o ganho
    some em silencio — e ninguem procura desempenho num modulo que "funciona".
    """
    assert not estresse.precisa_regerar({"diesel": 1.5, "custo_fixo": 0.7})
    assert estresse.precisa_regerar({"demanda": 1.1})
    assert estresse.precisa_regerar({"tarifa": 0.9})
    assert not estresse.precisa_regerar({"demanda": 1.0})   # fator neutro nao conta


# ---------------------------------------------------------------------------
# Ponto de ruptura
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ruptura() -> pd.DataFrame:
    return estresse.ruptura("diesel", limites=(0.35, 3.0), passos=40)


def test_ruptura_separa_quem_tem_folga_de_quem_nao_tem(ruptura):
    """Fator acima de 1 tem que corresponder a linha que cobre o custo hoje."""
    medidos = ruptura[ruptura["situacao"] == "medido"]
    cobre_hoje = medidos["classificacao"] == "MANTER"
    tem_folga = medidos["fator_ruptura"] > 1
    assert (cobre_hoje == tem_folga).all()


def test_ruptura_e_o_ponto_em_que_o_spread_zera(ruptura):
    """Rodar no fator de ruptura tem que dar spread praticamente zero.

    E a verificacao direta da interpolacao: se a grade fosse grossa demais ou a
    conta estivesse errada, o spread no ponto devolvido nao seria zero.
    """
    caso = ruptura[ruptura["situacao"] == "medido"].iloc[0]
    janela = estresse.rodar({"diesel": float(caso["fator_ruptura"])})
    spread = float(
        janela.set_index("linha_id").loc[caso["linha_id"], "spread_rask_cask"]
    )
    assert abs(spread) < 1e-3


def test_fora_da_faixa_nao_vira_numero_inventado(ruptura):
    """Linha sem cruzamento na grade devolve NaN e a direcao, nunca extrapolacao."""
    fora = ruptura[ruptura["situacao"] != "medido"]
    assert fora["fator_ruptura"].isna().all()
    assert fora["situacao"].isin(
        ["cobre em toda a faixa varrida", "nao cobre em toda a faixa varrida"]
    ).all()


def test_ha_linha_que_quebra_com_alta_de_um_digito(ruptura):
    """O achado do artigo: decisao apresentada como estavel e nao e."""
    medidos = ruptura[ruptura["situacao"] == "medido"]
    frageis = medidos[(medidos["folga"] > 0) & (medidos["folga"] < 0.10)]
    assert len(frageis) >= 1, "sem esse caso o artigo perde o gancho"


def test_ruptura_de_parametro_desconhecido_falha():
    with pytest.raises(ValueError, match="parametro desconhecido"):
        estresse.ruptura("cambio")


# ---------------------------------------------------------------------------
# Tornado
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sensibilidade() -> pd.DataFrame:
    return estresse.tornado(amplitude=0.10)


def test_tornado_cobre_todas_as_premissas(sensibilidade):
    assert set(sensibilidade["parametro"]) == set(estresse.PARAMETROS)
    assert sensibilidade["amplitude_resultado"].is_monotonic_decreasing


def test_receita_manda_mais_que_custo(sensibilidade):
    """Alavancagem operacional: a margem e ~15% da receita.

    Entao 10% de receita a mais vira ~60% de resultado, enquanto 10% de diesel a
    mais tira ~20%. E a razao pela qual o proximo item do roadmap e sobre preco,
    e nao sobre mais uma rodada de corte de custo.
    """
    por_parametro = sensibilidade.set_index("parametro")["elasticidade"].abs()
    assert por_parametro["tarifa"] > por_parametro["diesel"] * 2
    assert por_parametro["demanda"] > por_parametro["custo_fixo"] * 2


def test_direcoes_do_custo_e_da_receita_sao_opostas(sensibilidade):
    """Custo mais alto piora; receita mais alta melhora. Sinal trocado denunciaria
    fator aplicado ao contrario em algum parametro."""
    por_parametro = sensibilidade.set_index("parametro")
    for custo in ("diesel", "tripulacao", "pedagio", "custo_fixo", "pneus_e_manutencao"):
        assert por_parametro.loc[custo, "variacao_alta"] < 0
        assert por_parametro.loc[custo, "variacao_baixa"] > 0
    for receita in ("tarifa", "demanda"):
        assert por_parametro.loc[receita, "variacao_alta"] > 0
        assert por_parametro.loc[receita, "variacao_baixa"] < 0


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------

def test_sorteio_tem_media_um():
    """A correcao de media do lognormal: sem ela o sorteio infla tudo em silencio."""
    sorteios = estresse.sortear(6000, semente=1)
    for parametro in config.INCERTEZA:
        assert sorteios[parametro].mean() == pytest.approx(1.0, abs=0.01), parametro
        assert (sorteios[parametro] > 0).all()


def test_sorteio_respeita_o_desvio_declarado():
    sorteios = estresse.sortear(6000, semente=1)
    for parametro, desvio in config.INCERTEZA.items():
        medido = np.std(np.log(sorteios[parametro]))
        assert medido == pytest.approx(desvio, rel=0.08), parametro


def test_custos_sobem_juntos_e_receita_nao():
    """O choque comum entre os custos, e a ausencia dele em tarifa e demanda.

    Sortear os sete de forma independente subestimaria a cauda: o cenario ruim
    de verdade e o que junta diesel, pedagio e salario.
    """
    sorteios = estresse.sortear(4000, semente=7)
    correlacao = np.corrcoef(
        np.log(sorteios["diesel"]), np.log(sorteios["tripulacao"])
    )[0, 1]
    assert correlacao == pytest.approx(config.CORRELACAO_CUSTOS, abs=0.08)

    com_receita = np.corrcoef(
        np.log(sorteios["diesel"]), np.log(sorteios["tarifa"])
    )[0, 1]
    assert abs(com_receita) < 0.08


def test_sorteio_e_reproduzivel():
    pd.testing.assert_frame_equal(
        estresse.sortear(50, semente=3), estresse.sortear(50, semente=3)
    )


@pytest.fixture(scope="module")
def incerteza() -> dict:
    return estresse.monte_carlo(n=60, semente=11)


def test_probabilidades_somam_um(incerteza):
    soma = incerteza["por_linha"][list(config.CLASSIFICACOES)].sum(axis=1)
    assert (soma - 1).abs().max() < 1e-12


def test_classificacao_base_vem_do_cenario_base(incerteza):
    """A base e a rodada SEM cenario, nao o primeiro sorteio.

    Foi o bug da primeira versao: tirar a identidade do primeiro sorteio rotulava
    cada linha com um cenario aleatorio, e `p_rotulo_base` passava a medir a
    chance de repetir aquele sorteio em vez da de confirmar o relatorio.
    """
    base = estresse.rodar({}).set_index("linha_id")["classificacao"]
    medido = incerteza["por_linha"].set_index("linha_id")["classificacao_base"]
    pd.testing.assert_series_equal(
        base.sort_index(), medido.sort_index(), check_names=False
    )


def test_ha_linha_com_rotulo_que_nao_se_sustenta(incerteza):
    """O achado: o relatorio entrega rotulo, as premissas nao sustentam certeza."""
    por_linha = incerteza["por_linha"]
    assert por_linha["incerta"].sum() >= 3
    assert (por_linha["p_rotulo_base"] < 0.70).any()


def test_resumo_do_resultado_e_coerente(incerteza):
    resumo = incerteza["resumo_resultado"]
    assert resumo["p05"] < resumo["p50"] < resumo["p95"]
    assert 0.0 <= resumo["prob_prejuizo"] <= 1.0
    assert len(incerteza["resultado"]) == incerteza["n"]
