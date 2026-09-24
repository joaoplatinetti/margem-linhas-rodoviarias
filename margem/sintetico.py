"""
O gerador do dataset: 20 linhas x 24 meses de oferta, demanda e tarifa.

O dado e inventado, mas nao e aleatorio. A demanda de cada linha-mes sai de
quatro fatores multiplicativos, todos declarados em `config`:

    passageiros = ocupacao_base x sazonalidade^amplitude x tendencia x ruido

...e depois e cortada no teto de oferta. Cada fator existe para evitar um defeito
especifico de dado sintetico:

- **sazonalidade^amplitude** — sem expoente por linha, as 20 sobem e descem
  juntas e no mesmo tamanho, o que nao acontece em rede nenhuma.
- **tendencia** — serie perfeitamente estacionaria nao aparece em series
  comerciais reais.
- **ruido** — sem ele, dois julhos consecutivos dao exatamente o mesmo numero.
- **teto de oferta** — sem ele, o pico de julho produz load factor acima de 1,
  que e o erro que denuncia qualquer dataset fabricado.

Duas normalizacoes cuidam de um detalhe que passa facil: tanto o indice sazonal
elevado ao expoente quanto o ruido lognormal tem media diferente de 1, e sem
corrigir isso o `ocupacao_base` do catalogo deixaria de ser a ocupacao media da
linha — as linhas de lazer sairiam sistematicamente mais cheias que o declarado.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from margem import config, linhas

log = logging.getLogger(__name__)


def meses() -> pd.DataFrame:
    """A dimensao tempo: um registro por mes do periodo, com os dias do mes.

    Os dias do mes entram no dataset porque a oferta depende deles — fevereiro
    tem menos partidas que marco na mesma frequencia semanal, e ignorar isso
    produziria um degrau artificial nos indicadores de fevereiro.
    """
    periodo = pd.period_range(config.PERIODO_INICIO, config.PERIODO_FIM, freq="M")
    df = pd.DataFrame({"periodo": periodo})
    df["data"] = df["periodo"].dt.to_timestamp()          # primeiro dia do mes
    df["ano_mes"] = df["periodo"].astype(str)             # '2026-09'
    df["ano"] = df["periodo"].dt.year
    df["mes"] = df["periodo"].dt.month
    df["dias_no_mes"] = df["periodo"].dt.days_in_month
    df["indice_sazonal"] = df["mes"].map(config.SAZONALIDADE_MENSAL)

    # Tendencia centrada no meio do periodo: assim `ocupacao_base` continua
    # sendo a ocupacao MEDIA da linha nos 24 meses, e nao a do primeiro mes.
    t = np.arange(len(df)) - (len(df) - 1) / 2
    df["fator_tendencia"] = config.TENDENCIA_ANUAL ** (t / 12.0)

    return df.drop(columns="periodo")


def _sazonalidade_por_linha(indice: np.ndarray, amplitude: float) -> np.ndarray:
    """Indice sazonal com a amplitude da linha, renormalizado para media 1.

    `indice ** amplitude` nao preserva a media: 0,87^0,4 = 0,95 e 1,22^0,4 = 1,08,
    entao achatar a sazonalidade ELEVA a media. Sem dividir pela media, uma linha
    corporativa acabaria com ocupacao acima da declarada so por ser corporativa.
    """
    ajustado = indice ** amplitude
    return ajustado / ajustado.mean()


def gerar() -> pd.DataFrame:
    """O fato linha x mes com oferta, demanda e receita. Deterministico (seed)."""
    catalogo = linhas.catalogo()
    calendario = meses()
    catalogo = catalogo.assign(tarifa_km_ref=linhas.tarifa_km_referencia(catalogo))

    rng = np.random.default_rng(config.SEED)

    # Correcao de media do ruido lognormal: E[exp(X)] = exp(sigma^2/2), entao
    # sem o desconto o ruido inflaria a demanda ~0,2% de forma silenciosa.
    def ruido(sigma: float, n: int) -> np.ndarray:
        return rng.lognormal(mean=-(sigma**2) / 2, sigma=sigma, size=n)

    n_meses = len(calendario)
    indice = calendario["indice_sazonal"].to_numpy()
    blocos = []

    for linha in catalogo.itertuples(index=False):
        bloco = calendario.copy()
        bloco["linha_id"] = linha.linha_id

        # --- oferta -------------------------------------------------------
        # Partidas do mes na frequencia semanal declarada. Arredondar (e nao
        # truncar) evita perder uma partida em todo mes de 30 dias.
        bloco["partidas"] = np.rint(
            linha.frequencia_semanal * bloco["dias_no_mes"] / 7.0
        ).astype(int)
        bloco["km_rodados"] = bloco["partidas"] * linha.km
        bloco["assentos_km"] = bloco["km_rodados"] * linha.assentos

        # --- demanda ------------------------------------------------------
        sazonal = _sazonalidade_por_linha(indice, linha.amplitude_sazonal)
        ocupacao = (
            linha.ocupacao_base
            * config.FATOR_DEMANDA          # 1,0 no modelo base; ver config
            * sazonal
            * bloco["fator_tendencia"].to_numpy()
            * ruido(config.RUIDO_DEMANDA, n_meses)
        )
        # O teto e o que mantem o load factor no mundo real. Guardamos quanto
        # ficou represado: demanda batendo no teto e exatamente o sinal de que a
        # linha pede mais frequencia, e isso vira recomendacao no relatorio.
        ocupacao_livre = ocupacao.copy()
        ocupacao = np.minimum(ocupacao, config.OCUPACAO_MAXIMA)
        bloco["demanda_represada"] = np.maximum(ocupacao_livre - config.OCUPACAO_MAXIMA, 0.0)

        bloco["passageiros"] = np.rint(
            ocupacao * linha.assentos * bloco["partidas"]
        ).astype(int)
        bloco["passageiros_km"] = bloco["passageiros"] * linha.km

        # --- tarifa -------------------------------------------------------
        # A tarifa media realizada acompanha o mix: no pico ha menos promocional
        # e ela sobe. Tarifa media constante em 24 meses seria a segunda coisa
        # mais improvavel deste dataset, depois de load factor 1.
        bloco["tarifa_media"] = (
            linha.tarifa_km_ref
            * linha.km
            * (sazonal ** config.TARIFA_SENSIBILIDADE_SAZONAL)
            * ruido(config.RUIDO_TARIFA, n_meses)
        ).round(2)
        bloco["receita"] = (bloco["passageiros"] * bloco["tarifa_media"]).round(2)

        blocos.append(bloco)

    fato = pd.concat(blocos, ignore_index=True)
    fato = fato.merge(catalogo, on="linha_id", how="left", validate="many_to_one")

    _conferir(fato)
    log.info(
        "dataset sintetico: %d linhas x %d meses = %d registros",
        catalogo["linha_id"].nunique(), n_meses, len(fato),
    )
    return fato


def _conferir(fato: pd.DataFrame) -> None:
    """Recusa o que nao pode existir, em vez de deixar passar para o Excel."""
    ocupacao = fato["passageiros_km"] / fato["assentos_km"]
    if (ocupacao > 1).any():
        raise AssertionError("load factor acima de 1 — o teto de oferta nao foi aplicado")
    if (fato["passageiros"] < 0).any() or (fato["receita"] < 0).any():
        raise AssertionError("passageiros ou receita negativos")
    if fato[["linha_id", "ano_mes"]].duplicated().any():
        raise AssertionError("linha_id x ano_mes duplicado no fato")
