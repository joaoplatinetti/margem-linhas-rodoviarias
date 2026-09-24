"""
Exportacao em esquema estrela: tres dimensoes, tres fatos, CSV.

O modelo e estrela e nao uma tabela unica achatada porque e o que o Power BI
consome bem: relacionamento um-para-muitos da dimensao para o fato, filtro
descendo por um caminho so, e nenhuma coluna repetida 480 vezes. Tabela larga
funciona no primeiro grafico e cobra depois, quando alguem precisa de um recorte
que ela nao previu.

**A regra que organiza os arquivos: o fato guarda somente o que e ADITIVO.**
Partidas, assento-km, passageiro-km, passageiros, receita e custo por componente
somam. Yield, RASK, CASK e load factor nao somam — sao razao entre duas dessas
somas e tem que ser MEDIDA em DAX, calculada depois do filtro do usuario.
Gravar RASK como coluna e depois arrastar para o visual com `Media` e o erro
classico: da peso igual a fevereiro e a julho e devolve um numero que nao
corresponde a nenhum periodo.

A excecao e `fato_classificacao`, e ela e deliberada: aquele arquivo e um
retrato de uma janela JA FECHADA de 12 meses, com uma linha por linha de onibus.
Nada ali sera somado entre linhas, entao as razoes podem vir prontas — e e o que
permite montar o cartao de decisao sem replicar a regra de classificacao em DAX.
"""
from __future__ import annotations

import logging

import pandas as pd

from margem import config, custos, indicadores, linhas

log = logging.getLogger(__name__)

# BOM no UTF-8: o Power BI Desktop identifica a codificacao sozinho e o Excel
# para de abrir "Goiania" como "GoiÃ¢nia" ao dar um duplo clique no CSV.
CODIFICACAO = "utf-8-sig"

MESES_PT = {
    1: "jan", 2: "fev", 3: "mar", 4: "abr", 5: "mai", 6: "jun",
    7: "jul", 8: "ago", 9: "set", 10: "out", 11: "nov", 12: "dez",
}


def _faixa_distancia(km: pd.Series) -> pd.Series:
    """Faixas de distancia, na dimensao e nao no fato.

    Os cortes nao sao redondos por acaso: 600 km e onde entra a segunda
    tripulacao, e e o corte que explica boa parte da diferenca de CASK entre as
    faixas. Faixa de 500 em 500 km esconderia exatamente esse degrau.
    """
    return pd.cut(
        km,
        bins=[0, 300, 600, 900, 10_000],
        labels=["ate 300 km", "301 a 600 km", "601 a 900 km", "acima de 900 km"],
    )


def dim_linha() -> pd.DataFrame:
    catalogo = linhas.catalogo()
    unitario = custos.custo_unitario_por_linha(catalogo)

    df = catalogo.merge(
        unitario[["linha_id", "variavel_km", "tripulacao_partida"]],
        on="linha_id", validate="one_to_one",
    )
    df["faixa_distancia"] = _faixa_distancia(df["km"])
    df["tarifa_km_referencia"] = linhas.tarifa_km_referencia(catalogo).round(4)
    df["dupla_tripulacao"] = df["tripulantes"].map({2: "sim", 1: "nao"})

    colunas = [
        "linha_id", "linha", "origem", "uf_origem", "destino", "uf_destino",
        "corredor", "classe", "perfil", "km", "faixa_distancia", "assentos",
        "frequencia_semanal", "duracao_horas", "tripulantes", "dupla_tripulacao",
        "ocupacao_base", "fator_tarifa", "amplitude_sazonal",
        "tarifa_km_referencia", "variavel_km", "tripulacao_partida",
    ]
    return df[colunas]


def dim_calendario(fato: pd.DataFrame) -> pd.DataFrame:
    """A tabela de datas, no grao mensal do fato.

    Mensal e nao diaria porque o fato e mensal: uma tabela de datas diaria com
    um fato mensal obriga o usuario a lembrar de somar sempre no mes, e a
    primeira soma por dia devolve zero em 30 dias de cada 31. `data` e o primeiro
    dia do mes, que e o padrao que a inteligencia de tempo do DAX espera.
    """
    df = (
        fato[["data", "ano_mes", "ano", "mes", "dias_no_mes", "indice_sazonal"]]
        .drop_duplicates()
        .sort_values("data", ignore_index=True)
    )
    df["nome_mes"] = df["mes"].map(MESES_PT)
    df["mes_ano"] = df["nome_mes"] + "/" + df["ano"].astype(str).str[-2:]
    df["trimestre"] = "T" + ((df["mes"] - 1) // 3 + 1).astype(str)
    df["ano_trimestre"] = df["ano"].astype(str) + "-" + df["trimestre"]

    # Chave de ordenacao: sem ela o Power BI ordena "abr, ago, dez..." em ordem
    # alfabetica no eixo do grafico.
    df["ordem_mes"] = range(1, len(df) + 1)

    # Marca os 12 meses da janela de decisao, para o relatorio poder filtrar a
    # mesma janela que classificou as linhas sem repetir a regra em DAX.
    ultimos = sorted(df["ano_mes"])[-config.JANELA_DECISAO_MESES:]
    df["na_janela_decisao"] = df["ano_mes"].isin(ultimos).map({True: "sim", False: "nao"})

    return df


def dim_componente_custo(fato: pd.DataFrame) -> pd.DataFrame:
    df = custos.premissas(fato)
    df["participacao"] = df["participacao"].round(4)
    df["custo_periodo"] = df["custo_periodo"].round(2)
    df.insert(0, "ordem", range(1, len(df) + 1))
    return df


def fato_linha_mes(fato: pd.DataFrame) -> pd.DataFrame:
    """So colunas aditivas, no grao linha x mes. Nenhuma razao."""
    colunas = [
        "linha_id", "data", "ano_mes",
        "partidas", "km_rodados", "assentos_km", "passageiros", "passageiros_km",
        "receita", *config.COMPONENTES_TODOS,
    ]
    df = fato[colunas].copy()
    for coluna in ["receita", *config.COMPONENTES_TODOS]:
        df[coluna] = df[coluna].round(2)
    return df.sort_values(["linha_id", "data"], ignore_index=True)


def fato_custo_componente(fato: pd.DataFrame) -> pd.DataFrame:
    """O custo despivotado: uma linha por linha x mes x componente.

    E o formato que deixa "custo por componente" virar um grafico com
    segmentacao, em vez de seis medidas escritas a mao. O total continua fechando
    com `fato_linha_mes`, e um teste garante isso.
    """
    df = fato.melt(
        id_vars=["linha_id", "data"],
        value_vars=config.COMPONENTES_TODOS,
        var_name="componente",
        value_name="custo",
    )
    df["custo"] = df["custo"].round(2)
    return df.sort_values(["linha_id", "data", "componente"], ignore_index=True)


def fato_classificacao(janela: pd.DataFrame, estresse: dict | None = None) -> pd.DataFrame:
    """A janela de 12 meses fechada, uma linha por linha de onibus.

    Aqui as razoes vem prontas de proposito (ver a docstring do modulo): e um
    retrato, nada sera reagregado entre as linhas.
    """
    df = janela.copy()
    meses = df.attrs.get("meses") or []
    if meses:
        df["janela_inicio"] = meses[0]
        df["janela_fim"] = meses[-1]

    colunas = [
        "linha_id", "janela_inicio", "janela_fim",
        "partidas", "assentos_km", "passageiros", "passageiros_km",
        "receita", "custo_variavel", "custo_fixo_rateado", "custo_total",
        "margem_contribuicao", "margem_contribuicao_pct", "resultado",
        "load_factor", "lf_equilibrio", "folga_lf",
        "yield_pax_km", "tarifa_media", "rask",
        "cask_variavel", "cask_total", "spread_rask_cask",
        "classificacao", "no_limite", "motivo", "alavanca",
    ]
    colunas = [c for c in colunas if c in df.columns]
    saida = df[colunas].copy()
    saida["no_limite"] = saida["no_limite"].map({True: "sim", False: "nao"})

    if estresse is not None:
        # A incerteza entra no MESMO retrato, e nao numa tabela nova: e um valor
        # por linha, da mesma janela fechada, e uma tabela so para tres colunas
        # exigiria mais um relacionamento sem nada em troca.
        probabilidades = estresse["incerteza"]["por_linha"].set_index("linha_id")
        for classe in config.CLASSIFICACOES:
            saida[f"prob_{classe.lower()}"] = (
                saida["linha_id"].map(probabilidades[classe]).round(4)
            )
        saida["confianca_no_rotulo"] = (
            saida["linha_id"].map(probabilidades["p_rotulo_base"]).round(4)
        )
        ruptura = estresse["ruptura"].set_index("linha_id")
        saida["diesel_de_ruptura"] = (
            saida["linha_id"].map(ruptura["valor_ruptura"]).round(2)
        )

    quatro_casas = ["margem_contribuicao_pct", "load_factor", "lf_equilibrio",
                    "folga_lf", "yield_pax_km", "rask", "cask_variavel",
                    "cask_total", "spread_rask_cask"]
    for coluna in quatro_casas:
        saida[coluna] = saida[coluna].round(4)
    for coluna in ["receita", "custo_variavel", "custo_fixo_rateado", "custo_total",
                   "margem_contribuicao", "resultado", "tarifa_media"]:
        saida[coluna] = saida[coluna].round(2)

    return saida


def exportar(fato: pd.DataFrame, janela: pd.DataFrame,
             estresse: dict | None = None) -> dict[str, int]:
    """Grava as seis tabelas em saida/powerbi/. Devolve nome -> numero de linhas."""
    config.SAIDA_POWERBI.mkdir(parents=True, exist_ok=True)

    tabelas = {
        "dim_linha": dim_linha(),
        "dim_calendario": dim_calendario(fato),
        "dim_componente_custo": dim_componente_custo(fato),
        "fato_linha_mes": fato_linha_mes(fato),
        "fato_custo_componente": fato_custo_componente(fato),
        "fato_classificacao": fato_classificacao(janela, estresse),
    }

    for nome, df in tabelas.items():
        destino = config.SAIDA_POWERBI / f"{nome}.csv"
        df.to_csv(destino, index=False, encoding=CODIFICACAO, date_format="%Y-%m-%d")
        log.info("%-24s %5d linhas -> %s", nome, len(df), destino.name)

    return {nome: len(df) for nome, df in tabelas.items()}
