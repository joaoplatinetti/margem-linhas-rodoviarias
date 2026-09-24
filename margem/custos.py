"""
O modelo de custo: cinco componentes variaveis e um bloco fixo rateado por km.

A ideia central e a separacao entre **base por km** e **base por partida**. Elas
nao se somam antes de saber quantos km e quantas partidas o mes teve, e tratar
tripulacao como custo por km e o atalho que mais estraga um CASK: numa linha
curta de alta frequencia, a tripulacao pesa por PARTIDA e a distancia dilui
pouco; numa linha longa, o mesmo motorista cobre 1.000 km de uma vez.

A descontinuidade dos 600 km e deliberada e e o achado mais interessante do
modelo. Acima dessa distancia entra o segundo motorista e o custo de tripulacao
por km praticamente dobra — uma linha de 610 km carrega quase o dobro de
tripulacao por km de uma de 590 km, com receita por km parecida. Nao e defeito
da premissa: e o que faz linhas logo acima do limite de dupla tripulacao serem
estruturalmente mais difíceis, e vale ver isso explicito na saida.

O bloco fixo fica FORA da margem de contribuicao. Ele e rateado e publicado
porque a decisao final precisa dele, mas margem de contribuicao com fixo dentro
leva a cortar linha que cobre o variavel de sobra — e o fixo continuaria existindo
depois do corte, agora rateado entre menos linhas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from margem import config


# ---------------------------------------------------------------------------
# Componentes variaveis
# ---------------------------------------------------------------------------

def custo_combustivel_km(classe: pd.Series) -> pd.Series:
    """R$/km de diesel: preco do litro dividido pelo consumo da classe."""
    consumo = classe.map(config.CONSUMO_KM_LITRO)
    if consumo.isna().any():
        raise ValueError(
            f"Classe sem consumo em config.CONSUMO_KM_LITRO: "
            f"{sorted(classe[consumo.isna()].unique())}"
        )
    return config.DIESEL_LITRO / consumo


def custo_tripulacao_partida(duracao_horas: pd.Series, tripulantes: pd.Series) -> pd.Series:
    """R$ por PARTIDA de tripulacao: jornada + diaria + pernoite quando aplicavel.

    A pernoite entra por tripulante e por partida acima de
    `config.PERNOITE_ACIMA_DE_HORAS` — viagem que passa desse tamanho nao permite
    a escala voltar no mesmo dia, e o repouso acontece fora da base.
    """
    jornada = config.CUSTO_HORA_TRIPULANTE * duracao_horas + config.DIARIA_TRIPULANTE
    pernoite = np.where(
        duracao_horas > config.PERNOITE_ACIMA_DE_HORAS, config.PERNOITE_TRIPULANTE, 0.0
    )
    return tripulantes * (jornada + pernoite)


def aplicar_variaveis(fato: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta os cinco componentes variaveis ao fato linha x mes."""
    df = fato.copy()

    pedagio_km = df["corredor"].map(lambda c: config.CORREDORES[c]["pedagio_km"])
    fator_manutencao = df["corredor"].map(lambda c: config.CORREDORES[c]["fator_manutencao"])

    df["custo_combustivel"] = df["km_rodados"] * custo_combustivel_km(df["classe"])
    df["custo_pneus"] = df["km_rodados"] * config.PNEUS_KM
    df["custo_manutencao"] = df["km_rodados"] * config.MANUTENCAO_KM * fator_manutencao
    df["custo_pedagio"] = df["km_rodados"] * pedagio_km
    df["custo_tripulacao"] = df["partidas"] * custo_tripulacao_partida(
        df["duracao_horas"], df["tripulantes"]
    )

    df["custo_variavel"] = df[config.COMPONENTES_VARIAVEIS].sum(axis=1)
    return df


# ---------------------------------------------------------------------------
# Bloco fixo
# ---------------------------------------------------------------------------

def ratear_fixo(fato: pd.DataFrame) -> pd.DataFrame:
    """Rateia o fixo mensal da empresa pelos km rodados de cada linha no mes.

    Km rodado e a base menos ruim para um rateio que vai ser olhado por linha:
    segue a intensidade de uso de frota, oficina e combustivel de apoio, e nao
    premia nem pune frequencia como o rateio por partida faria. Continua sendo
    RATEIO, e nenhuma decisao de manter ou cortar deve sair so dele — dai a
    margem de contribuicao aparecer sempre ao lado.

    Por construcao, a soma do rateado fecha com o total declarado em cada mes
    (um dos testes fixa isso).
    """
    if config.BASE_RATEIO_FIXO != "km":
        raise NotImplementedError(
            f"base de rateio '{config.BASE_RATEIO_FIXO}' nao implementada — "
            "hoje o modelo rateia por km rodado"
        )

    df = fato.copy()
    total_mensal = sum(config.CUSTO_FIXO_MENSAL.values())

    km_do_mes = df.groupby("ano_mes")["km_rodados"].transform("sum")
    df["custo_fixo_km"] = total_mensal / km_do_mes
    df["custo_fixo_rateado"] = df["km_rodados"] * df["custo_fixo_km"]

    df["custo_total"] = df["custo_variavel"] + df["custo_fixo_rateado"]
    return df


def aplicar(fato: pd.DataFrame) -> pd.DataFrame:
    """O modelo de custo completo: variaveis e fixo rateado."""
    return ratear_fixo(aplicar_variaveis(fato))


# ---------------------------------------------------------------------------
# As premissas, em formato de tabela
# ---------------------------------------------------------------------------

def premissas(fato: pd.DataFrame | None = None) -> pd.DataFrame:
    """O catalogo de componentes com a premissa de cada um, para a aba Custos.

    Publicar a premissa junto do numero e o que permite alguem discordar do
    resultado sem precisar ler o codigo — que e o objetivo de um modelo de custo
    apresentavel. Quando o fato e passado, entra tambem quanto cada componente
    representou do custo da rede no periodo.
    """
    df = pd.DataFrame(config.COMPONENTES)
    df["entra_na_mc"] = df["entra_na_mc"].map({True: "sim", False: "nao"})

    if fato is not None:
        total = fato[config.COMPONENTES_TODOS].to_numpy().sum()
        df["custo_periodo"] = [fato[c].sum() for c in df["componente"]]
        df["participacao"] = df["custo_periodo"] / total

    return df


def custo_unitario_por_linha(catalogo: pd.DataFrame) -> pd.DataFrame:
    """R$/km de cada componente variavel por linha, sem passar pelo fato.

    Serve para a aba de premissas e para depurar: e aqui que a descontinuidade
    dos 600 km fica visivel a olho nu, na coluna de tripulacao.
    """
    df = catalogo.copy()
    pedagio_km = df["corredor"].map(lambda c: config.CORREDORES[c]["pedagio_km"])
    fator_manutencao = df["corredor"].map(lambda c: config.CORREDORES[c]["fator_manutencao"])

    df["combustivel_km"] = custo_combustivel_km(df["classe"])
    df["pneus_km"] = config.PNEUS_KM
    df["manutencao_km"] = config.MANUTENCAO_KM * fator_manutencao
    df["pedagio_km"] = pedagio_km
    df["tripulacao_partida"] = custo_tripulacao_partida(df["duracao_horas"], df["tripulantes"])
    df["tripulacao_km"] = df["tripulacao_partida"] / df["km"]
    df["variavel_km"] = (
        df["combustivel_km"] + df["pneus_km"] + df["manutencao_km"]
        + df["pedagio_km"] + df["tripulacao_km"]
    )

    colunas = [
        "linha_id", "linha", "km", "classe", "corredor", "tripulantes",
        "combustivel_km", "pneus_km", "manutencao_km", "pedagio_km",
        "tripulacao_partida", "tripulacao_km", "variavel_km",
    ]
    return df[colunas]
