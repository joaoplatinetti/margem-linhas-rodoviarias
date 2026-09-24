"""O modelo de custo: as bases, o degrau da tripulacao e o fecho do rateio."""
from __future__ import annotations

import pandas as pd
import pytest

from margem import config, custos, linhas, sintetico


@pytest.fixture(scope="module")
def fato() -> pd.DataFrame:
    return custos.aplicar(sintetico.gerar())


def test_combustivel_e_preco_sobre_consumo():
    classe = pd.Series(["CONVENCIONAL", "LEITO"])
    esperado = pd.Series([
        config.DIESEL_LITRO / config.CONSUMO_KM_LITRO["CONVENCIONAL"],
        config.DIESEL_LITRO / config.CONSUMO_KM_LITRO["LEITO"],
    ])
    pd.testing.assert_series_equal(custos.custo_combustivel_km(classe), esperado)


def test_classe_desconhecida_falha_alto():
    """Classe fora do catalogo tem que estourar, nao virar custo zero."""
    with pytest.raises(ValueError, match="CONSUMO_KM_LITRO"):
        custos.custo_combustivel_km(pd.Series(["LEITO CAMA"]))


def test_segundo_motorista_acima_do_limite():
    catalogo = linhas.catalogo()
    limite = config.SEGUNDO_MOTORISTA_ACIMA_KM
    assert (catalogo.loc[catalogo["km"] > limite, "tripulantes"] == 2).all()
    assert (catalogo.loc[catalogo["km"] <= limite, "tripulantes"] == 1).all()


def test_degrau_da_tripulacao_por_km():
    """Passar dos 600 km quase dobra a tripulacao por km.

    Nao e efeito colateral: e a consequencia economica que o modelo existe para
    mostrar. Duas linhas do catalogo tem 588 e 694 km, e servem de par natural.
    """
    unitario = custos.custo_unitario_por_linha(linhas.catalogo()).set_index("km")
    abaixo = unitario.loc[588, "tripulacao_km"].max()   # ha duas linhas de 588 km
    acima = unitario.loc[694, "tripulacao_km"]
    assert acima > 2 * abaixo * 0.9   # praticamente o dobro, apesar de ser mais longa


def test_tripulacao_e_por_partida_nao_por_km():
    """A mesma duracao custa o mesmo por partida, independente da frequencia."""
    duracao = pd.Series([4.0, 4.0])
    tripulantes = pd.Series([1, 1])
    valores = custos.custo_tripulacao_partida(duracao, tripulantes)
    assert valores.iloc[0] == valores.iloc[1]
    esperado = config.CUSTO_HORA_TRIPULANTE * 4.0 + config.DIARIA_TRIPULANTE
    assert valores.iloc[0] == pytest.approx(esperado)


def test_pernoite_entra_so_nas_viagens_longas():
    curta = custos.custo_tripulacao_partida(pd.Series([6.0]), pd.Series([1])).iloc[0]
    longa = custos.custo_tripulacao_partida(pd.Series([12.0]), pd.Series([1])).iloc[0]
    jornada_extra = config.CUSTO_HORA_TRIPULANTE * 6.0
    assert longa - curta == pytest.approx(jornada_extra + config.PERNOITE_TRIPULANTE)


def test_custo_variavel_e_a_soma_dos_componentes(fato):
    soma = fato[config.COMPONENTES_VARIAVEIS].sum(axis=1)
    pd.testing.assert_series_equal(fato["custo_variavel"], soma, check_names=False)


def test_rateio_do_fixo_fecha_com_o_declarado(fato):
    """A soma do fixo rateado em cada mes tem que dar o total declarado.

    Rateio que nao fecha e o defeito mais insidioso do modelo: o CASK sai
    plausivel e o resultado da rede fica errado por um valor que ninguem procura.
    """
    declarado = sum(config.CUSTO_FIXO_MENSAL.values())
    por_mes = fato.groupby("ano_mes")["custo_fixo_rateado"].sum()
    assert len(por_mes) == 24
    assert (por_mes - declarado).abs().max() < 1e-6


def test_fixo_nao_entra_na_margem_de_contribuicao():
    """O catalogo tem que manter o fixo fora da MC — e a separacao que sustenta
    a diferenca entre AJUSTAR e REVER."""
    assert "custo_fixo_rateado" not in config.COMPONENTES_VARIAVEIS
    assert config.COMPONENTES_FIXOS == ["custo_fixo_rateado"]


def test_corredor_agressivo_custa_mais_manutencao(fato):
    """Norte tem que ter manutencao por km acima do Sudeste."""
    por_km = fato.assign(manutencao_km=fato["custo_manutencao"] / fato["km_rodados"])
    media = por_km.groupby("corredor")["manutencao_km"].mean()
    assert media["NORTE"] > media["SUDESTE"]


def test_base_de_rateio_desconhecida_falha():
    original = config.BASE_RATEIO_FIXO
    config.BASE_RATEIO_FIXO = "partida"
    try:
        with pytest.raises(NotImplementedError):
            custos.ratear_fixo(pd.DataFrame({"km_rodados": [1.0], "ano_mes": ["2026-01"]}))
    finally:
        config.BASE_RATEIO_FIXO = original
