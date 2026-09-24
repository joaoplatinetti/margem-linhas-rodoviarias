"""O que o gerador nao pode produzir, e o que ele tem que preservar."""
from __future__ import annotations

import pandas as pd
import pytest

from margem import config, linhas, sintetico


@pytest.fixture(scope="module")
def fato() -> pd.DataFrame:
    return sintetico.gerar()


def test_grao_e_tamanho(fato):
    assert len(fato) == 20 * 24
    assert fato["linha_id"].nunique() == 20
    assert fato["ano_mes"].nunique() == 24
    assert not fato[["linha_id", "ano_mes"]].duplicated().any()


def test_deterministico():
    """Seed fixa tem que devolver o mesmo dataset.

    E o que permite versionar a saida no repo e conferir um numero da planilha
    contra o codigo seis meses depois.
    """
    pd.testing.assert_frame_equal(sintetico.gerar(), sintetico.gerar())


def test_load_factor_dentro_do_teto(fato):
    """Load factor acima de 1 e o defeito que denuncia dado sintetico."""
    ocupacao = fato["passageiros_km"] / fato["assentos_km"]
    assert ocupacao.max() <= config.OCUPACAO_MAXIMA + 1e-9
    assert ocupacao.min() > 0


def test_oferta_acompanha_os_dias_do_mes(fato):
    """Fevereiro tem que ter menos partidas que marco na mesma frequencia."""
    uma_linha = fato[fato["linha_id"] == "L01"]
    fevereiro = uma_linha.loc[uma_linha["mes"] == 2, "partidas"].mean()
    marco = uma_linha.loc[uma_linha["mes"] == 3, "partidas"].mean()
    assert fevereiro < marco


def test_sazonalidade_aparece_na_rede(fato):
    """Julho acima de maio no total da rede, como as premissas mandam."""
    por_mes = fato.groupby("mes")["passageiros"].sum()
    assert por_mes[7] > por_mes[5]
    assert por_mes[1] > por_mes[3]


def test_amplitude_sazonal_diferencia_as_linhas(fato):
    """A linha corporativa tem que oscilar menos que a de lazer.

    E o teste que protege o campo `amplitude_sazonal`: se alguem passar a aplicar
    o indice sazonal cru, as duas curvas ficam identicas e o dataset perde a
    caracteristica mais visivel de uma rede real.
    """
    catalogo = linhas.catalogo().set_index("linha_id")
    corporativa = catalogo["amplitude_sazonal"].idxmin()
    lazer = catalogo["amplitude_sazonal"].idxmax()

    def variacao(linha_id: str) -> float:
        serie = fato.loc[fato["linha_id"] == linha_id].set_index("ano_mes")
        ocupacao = serie["passageiros_km"] / serie["assentos_km"]
        return float(ocupacao.std() / ocupacao.mean())

    assert variacao(corporativa) < variacao(lazer)


def test_ocupacao_media_fica_perto_da_declarada(fato):
    """`ocupacao_base` tem que continuar sendo a ocupacao MEDIA da linha.

    Sem a renormalizacao do indice sazonal elevado a amplitude, achatar a
    sazonalidade elevaria a media (0,87^0,4 = 0,95) e as linhas corporativas
    sairiam mais cheias do que o catalogo declara. A tolerancia acomoda o teto de
    oferta, que corta o pico das linhas mais cheias.
    """
    catalogo = linhas.catalogo().set_index("linha_id")["ocupacao_base"]
    medida = fato.groupby("linha_id").apply(
        lambda g: g["passageiros_km"].sum() / g["assentos_km"].sum(), include_groups=False
    )
    diferenca = (medida - catalogo).abs()
    assert diferenca.max() < 0.03, f"maior desvio: {diferenca.idxmax()} {diferenca.max():.4f}"


def test_tarifa_sobe_no_pico(fato):
    """Tarifa media acompanhando o mix: julho acima de maio."""
    uma_linha = fato[fato["linha_id"] == "L20"]   # a de maior amplitude
    julho = uma_linha.loc[uma_linha["mes"] == 7, "tarifa_media"].mean()
    maio = uma_linha.loc[uma_linha["mes"] == 5, "tarifa_media"].mean()
    assert julho > maio


def test_catalogo_consistente():
    catalogo = linhas.catalogo()
    assert len(catalogo) == 20
    assert catalogo["linha_id"].is_unique
    assert set(catalogo["classe"]) <= set(config.ASSENTOS_POR_CLASSE)
    assert set(catalogo["corredor"]) <= set(config.CORREDORES)
    # Cidades reais: nenhuma linha comeca e termina no mesmo lugar.
    assert (catalogo["origem"] != catalogo["destino"]).all()
