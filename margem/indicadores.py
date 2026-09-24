"""
Os indicadores e a decisao: MC, yield, RASK, CASK, load factor, classificacao.

Tres identidades sustentam tudo o que sai daqui:

    yield = receita / passageiro-km
    RASK  = receita / assento-km
    LF    = passageiro-km / assento-km        =>  RASK = yield x LF
    CASK  = custo / assento-km

A terceira e a que da a leitura de gestao: RASK = yield x LF significa que a
receita por assento oferecido tem dois caminhos, preco e ocupacao, e o modelo
mostra qual dos dois esta faltando em cada linha. O par (RASK, CASK) fecha a
conta: um cobre o outro ou nao cobre.

**Regra que vale para todo este modulo: razao nunca se agrega.** Yield, RASK,
CASK e load factor de um conjunto de linhas-mes sao divisao das somas, nunca a
media das razoes. A media de razoes da peso igual a um mes de fevereiro e a um
de julho, e o numero resultante nao corresponde a nenhuma realidade — e o mesmo
motivo pelo qual, do lado do Power BI, esses indicadores tem que ser MEDIDA em
DAX e nunca coluna calculada.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from margem import config

log = logging.getLogger(__name__)

# As somas que sustentam qualquer recorte. Tudo o mais e razao entre elas.
ADITIVAS = [
    "partidas", "km_rodados", "assentos_km", "passageiros", "passageiros_km",
    "receita", "custo_variavel", "custo_total", *config.COMPONENTES_TODOS,
]


def _razoes(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula as razoes a partir das colunas aditivas ja somadas.

    Funcao unica de proposito: o fato mensal, a janela de decisao e o total da
    rede passam todos por aqui, entao nao existe a possibilidade de o RASK do
    Excel ser calculado de um jeito e o da janela de outro.
    """
    saida = df.copy()

    def dividir(numerador: pd.Series, denominador: pd.Series) -> pd.Series:
        # Denominador zero acontece de verdade (linha sem partida no mes) e tem
        # que virar NaN, nao inf: inf contamina qualquer soma ou media adiante.
        return numerador.divide(denominador.replace(0, np.nan))

    saida["load_factor"] = dividir(saida["passageiros_km"], saida["assentos_km"])
    saida["yield_pax_km"] = dividir(saida["receita"], saida["passageiros_km"])
    saida["rask"] = dividir(saida["receita"], saida["assentos_km"])
    saida["cask_variavel"] = dividir(saida["custo_variavel"], saida["assentos_km"])
    saida["cask_total"] = dividir(saida["custo_total"], saida["assentos_km"])

    saida["tarifa_media"] = dividir(saida["receita"], saida["passageiros"])
    saida["receita_km"] = dividir(saida["receita"], saida["km_rodados"])

    # Margem de contribuicao: receita menos o custo VARIAVEL. O fixo rateado
    # entra so no resultado e no CASK cheio.
    saida["margem_contribuicao"] = saida["receita"] - saida["custo_variavel"]
    saida["margem_contribuicao_pct"] = dividir(saida["margem_contribuicao"], saida["receita"])
    saida["mc_por_ask"] = dividir(saida["margem_contribuicao"], saida["assentos_km"])

    saida["resultado"] = saida["receita"] - saida["custo_total"]
    saida["resultado_pct"] = dividir(saida["resultado"], saida["receita"])

    # Spread = RASK - CASK cheio. E a mesma coisa que resultado por assento-km,
    # e e o numero que decide a classificacao.
    saida["spread_rask_cask"] = saida["rask"] - saida["cask_total"]

    # --- Load factor de equilibrio --------------------------------------
    # A ocupacao que a linha precisaria ter, ao yield que ela ja pratica, para
    # a receita empatar com o custo. Sai direto da identidade RASK = yield x LF:
    #
    #     yield x LF = CASK   =>   LF de equilibrio = CASK / yield
    #
    # A conta vale porque neste modelo NENHUM componente de custo depende do
    # numero de passageiros — todos tem base km ou base partida. Se existisse
    # comissao por passageiro, o custo subiria junto com a ocupacao e o
    # equilibrio seria ponto fixo, nao divisao. Vale conferir esta premissa
    # antes de acrescentar componente novo ao catalogo.
    #
    # E a mesma informacao do spread, em unidade que a operacao entende: "faltam
    # 8 pontos de ocupacao" e acionavel de um jeito que "spread de -R$ 0,015 por
    # assento-km" nao e.
    saida["lf_equilibrio"] = dividir(saida["cask_total"], saida["yield_pax_km"])
    saida["lf_equilibrio_variavel"] = dividir(saida["cask_variavel"], saida["yield_pax_km"])
    saida["folga_lf"] = saida["load_factor"] - saida["lf_equilibrio"]

    return saida


def calcular(fato: pd.DataFrame) -> pd.DataFrame:
    """Indicadores no grao linha x mes."""
    return _razoes(fato)


def agregar(fato: pd.DataFrame, por: list[str] | None = None) -> pd.DataFrame:
    """Soma as aditivas no recorte pedido e recalcula as razoes por cima.

    `por=None` da o total da rede. Qualquer outro recorte (linha, mes, classe,
    corredor) passa pelo mesmo caminho.
    """
    # Soma as aditivas que EXISTEM. A lista completa inclui os cinco componentes
    # de custo da malha sintetica, e uma malha externa chega so com o
    # `custo_variavel` consolidado — exigir os componentes amarraria o motor ao
    # catalogo de premissas deste projeto.
    presentes = [coluna for coluna in ADITIVAS if coluna in fato.columns]
    faltando = set(("receita", "custo_variavel", "assentos_km")) - set(presentes)
    if faltando:
        raise ValueError(
            f"nao da para agregar sem {', '.join(sorted(faltando))} — "
            "ver margem.dados.CONTRATO"
        )

    if por:
        soma = fato.groupby(por, as_index=False)[presentes].sum()
    else:
        soma = fato[presentes].sum().to_frame().T

    return _razoes(soma)


def janela_decisao(fato: pd.DataFrame, meses: int | None = None) -> pd.DataFrame:
    """Os N ultimos meses somados por linha — a base da classificacao.

    A janela existe porque **classificar no mes isolado produz rotulo instavel**:
    uma linha de lazer cobre o custo cheio com folga em julho e nao cobre nem o
    variavel em maio. Decidir mes a mes faria a mesma linha alternar entre
    MANTER e REVER tres vezes ao ano, e nenhuma decisao comercial se toma assim.
    Doze meses fecham o ciclo sazonal inteiro, entao a comparacao entre linhas
    nao depende de qual mes caiu na ponta.
    """
    meses = meses or config.JANELA_DECISAO_MESES
    ultimos = sorted(fato["ano_mes"].unique())[-meses:]
    if len(ultimos) < meses:
        raise ValueError(
            f"o dataset tem {len(ultimos)} meses e a janela pede {meses}"
        )

    recorte = fato[fato["ano_mes"].isin(ultimos)]

    # As chaves do agrupamento sao `linha_id` mais o que EXISTIR de descritivo.
    # Lista fixa aqui amarrava a janela ao catalogo sintetico: uma malha externa
    # sem `perfil` nem `frequencia_semanal` estourava com KeyError, e foi assim
    # que o teste da ponte simulada descobriu o acoplamento.
    #
    # Estas colunas sao constantes DENTRO da linha, entao entram no `groupby`
    # como carona e nao como recorte — agrupar por elas nao parte a linha em
    # duas. Se alguma variar dentro da linha (uma mudanca de classe no meio do
    # periodo), partiria, e por isso o teste seguinte confere a contagem.
    descritivas = [
        coluna for coluna in
        ("linha", "origem", "destino", "corredor", "classe", "km", "assentos",
         "frequencia_semanal", "perfil", "tripulantes")
        if coluna in recorte.columns
    ]
    chaves = ["linha_id", *descritivas]

    janela = agregar(recorte, por=chaves)
    if janela["linha_id"].duplicated().any():
        repetidas = janela.loc[janela["linha_id"].duplicated(), "linha_id"].unique()
        raise ValueError(
            f"a janela partiu {len(repetidas)} linha(s) em mais de um registro: "
            f"{list(repetidas)[:3]}. Alguma coluna descritiva ({', '.join(descritivas)}) "
            "muda ao longo do periodo — tire ela do fato antes de avaliar."
        )
    janela.attrs["meses"] = ultimos
    return classificar(janela)


# ---------------------------------------------------------------------------
# Classificacao
# ---------------------------------------------------------------------------

def classificar(df: pd.DataFrame) -> pd.DataFrame:
    """MANTER / AJUSTAR / REVER por nivel de cobertura de custo.

    A escada tem dois degraus, e e a leitura que o setor usa:

    - **MANTER** — `RASK >= CASK cheio`. A linha paga o variavel e ainda o
      pedaco de estrutura que lhe foi rateado. Nada a fazer alem de acompanhar.
    - **AJUSTAR** — cobre o variavel (`MC > 0`) mas nao o custo cheio. A linha
      CONTRIBUI: tirada da malha, o fixo que ela cobria se redistribui entre as
      outras e piora todas. O que se ajusta e frequencia, classe, horario ou
      preco — nao a existencia da linha.
    - **REVER** — `MC <= 0`. Cada partida destroi caixa, e nem o volume resolve:
      vender mais assento com margem de contribuicao negativa piora o resultado.
      Aqui a discussao e de reformulacao ou de saida.

    A ordem importa: o teste do variavel vem primeiro, porque uma linha com MC
    negativa tambem tem spread negativo e cair na regra de AJUSTAR esconderia o
    caso grave dentro do caso administravel.
    """
    saida = df.copy()

    mc_negativa = saida["margem_contribuicao"] <= 0
    nao_cobre_fixo = saida["spread_rask_cask"] < 0

    saida["classificacao"] = np.select(
        [mc_negativa, nao_cobre_fixo],
        ["REVER", "AJUSTAR"],
        default="MANTER",
    )

    # "No limite" nao muda a classificacao, qualifica ela: spread de R$ 0,01 por
    # assento-km e MANTER tecnicamente, e tratar isso como uma linha de spread
    # R$ 0,80 esconde risco que vira problema na proxima alta do diesel.
    saida["no_limite"] = saida["spread_rask_cask"].abs() < config.SPREAD_NO_LIMITE

    saida["motivo"] = np.select(
        [
            mc_negativa,
            nao_cobre_fixo,
            saida["no_limite"],
        ],
        [
            "receita nao cobre o custo variavel",
            "cobre o variavel, nao o fixo rateado",
            "cobre o custo cheio, com folga estreita",
        ],
        default="cobre o custo cheio com folga",
    )

    return saida.sort_values("spread_rask_cask", ascending=False, ignore_index=True)


def recomendacao(janela: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta a alavanca provavel de cada linha: preco, ocupacao ou custo.

    Vem de `RASK = yield x LF`: se a linha nao cobre o custo, falta preco ou
    falta ocupacao, e os dois pedem acao diferente. A comparacao e contra a
    mediana da rede, porque comparar contra media puxada por uma linha muito
    cheia mandaria quase todas para "falta ocupacao".
    """
    saida = janela.copy()
    lf_mediano = saida["load_factor"].median()
    yield_mediano = saida["yield_pax_km"].median()

    lf_baixo = saida["load_factor"] < lf_mediano
    yield_baixo = saida["yield_pax_km"] < yield_mediano
    ok = saida["classificacao"] == "MANTER"

    saida["alavanca"] = np.select(
        [
            ok & ~saida["no_limite"],
            lf_baixo & yield_baixo,
            lf_baixo,
            yield_baixo,
        ],
        [
            "acompanhar",
            "ocupacao e preco",
            "ocupacao (rever frequencia e horario)",
            "preco (rever tarifa e mix de classe)",
        ],
        default="custo (a linha e cara por km)",
    )
    return saida


def resumo_rede(fato: pd.DataFrame) -> pd.Series:
    """Os indicadores da rede inteira no periodo, numa linha."""
    return agregar(fato).iloc[0]


def reconciliar(df: pd.DataFrame) -> pd.DataFrame:
    """Confere as identidades que o modelo promete, e devolve o erro maximo.

    Existe para ser chamada no fim do pipeline e nos testes: se `RASK - yield x LF`
    nao for zero a menos de arredondamento, alguma agregacao usou media de razao
    em vez de razao de somas, e esse e o defeito mais facil de introduzir aqui.
    """
    identidades = {
        "RASK = yield x LF": df["rask"] - df["yield_pax_km"] * df["load_factor"],
        "spread = RASK - CASK total": df["spread_rask_cask"] - (df["rask"] - df["cask_total"]),
        "MC = receita - custo variavel": (
            df["margem_contribuicao"] - (df["receita"] - df["custo_variavel"])
        ),
        "CASK total = CASK var + fixo/ASK": (
            df["cask_total"]
            - (df["cask_variavel"] + df["custo_fixo_rateado"] / df["assentos_km"])
        ),
        "yield x LF de equilibrio = CASK": (
            df["yield_pax_km"] * df["lf_equilibrio"] - df["cask_total"]
        ),
    }
    return pd.DataFrame(
        {
            "identidade": list(identidades),
            "erro_maximo": [float(np.nanmax(np.abs(v))) for v in identidades.values()],
        }
    )
