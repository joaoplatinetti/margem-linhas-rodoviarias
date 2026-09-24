"""
Quanto a decisao aguenta: ponto de ruptura, sensibilidade e probabilidade.

O modelo base entrega um rotulo por linha. Um rotulo esconde duas coisas que
quem decide precisa saber: **a que distancia da fronteira a linha esta** e
**qual premissa a empurra para la**. Este modulo responde as duas, e a terceira
que sai delas: se as premissas sao incertas, o rotulo tambem e — entao ele vira
probabilidade.

TRES PERGUNTAS, TRES FUNCOES

- `ruptura()` — a que preco de diesel (ou de pedagio, ou de salario) cada linha
  deixa de cobrir o custo. Para quem ja nao cobre, e o preco a que ela voltaria
  a cobrir: a mesma conta, lida ao contrario.
- `tornado()` — qual premissa move mais o resultado da rede. Serve para dizer
  onde vale gastar esforco de apuracao: refinar uma premissa que move 0,2% do
  resultado e trabalho perdido.
- `monte_carlo()` — a probabilidade de cada linha ser MANTER, sorteando todas as
  premissas juntas dentro da incerteza declarada em `config.INCERTEZA`.

COMO OS CENARIOS SAO APLICADOS

Por mutacao temporaria das constantes de `config`, dentro de um gerenciador de
contexto que restaura tudo ao sair. Nao e elegante — a alternativa seria passar
um dicionario de premissas por toda a cadeia de funcoes — mas e o unico jeito de
garantir que o cenario percorre EXATAMENTE o mesmo caminho de calculo que a
rodada normal. Um segundo caminho de calculo para cenarios seria a forma mais
provavel de o estresse e o relatorio discordarem sem ninguem perceber.

Por que a reutilizacao do dataset importa: sintetizar os 480 registros custa
~29 ms e o resto da cadeia custa ~6 ms. Cenario que mexe so em custo NAO precisa
regerar demanda, e reaproveitar o dataset deixa o Monte Carlo cinco vezes mais
rapido. Cenario que mexe em demanda ou em tarifa precisa, e o catalogo de
parametros declara qual e qual.
"""
from __future__ import annotations

import copy
import logging
from contextlib import contextmanager

import numpy as np
import pandas as pd

from margem import config, custos, indicadores, sintetico

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# O catalogo de parametros
# ---------------------------------------------------------------------------

def _escalar(nome: str):
    """Multiplica uma constante escalar de `config`."""
    def aplicar(fator: float) -> None:
        setattr(config, nome, getattr(config, nome) * fator)
    return aplicar


def _escalar_varios(*nomes: str):
    def aplicar(fator: float) -> None:
        for nome in nomes:
            setattr(config, nome, getattr(config, nome) * fator)
    return aplicar


def _escalar_dicionario(nome: str):
    """Multiplica todos os valores de um dicionario de `config`."""
    def aplicar(fator: float) -> None:
        atual = getattr(config, nome)
        setattr(config, nome, {chave: valor * fator for chave, valor in atual.items()})
    return aplicar


def _escalar_pedagio(fator: float) -> None:
    """O pedagio mora dentro do dicionario aninhado de corredores."""
    config.CORREDORES = {
        corredor: {**dados, "pedagio_km": dados["pedagio_km"] * fator}
        for corredor, dados in config.CORREDORES.items()
    }


# `regenera`: o cenario muda a demanda ou a tarifa e exige refazer o dataset.
# `unidade`: como ler o fator em valor absoluto, para o ponto de ruptura.
PARAMETROS: dict[str, dict] = {
    "diesel": {
        "rotulo": "Diesel (R$/l)",
        "aplicar": _escalar("DIESEL_LITRO"),
        "regenera": False,
        "valor_base": lambda: config.DIESEL_LITRO,
        "formato": "R$ {:.2f}/l",
    },
    "pneus_e_manutencao": {
        "rotulo": "Pneus e manutencao (R$/km)",
        "aplicar": _escalar_varios("PNEUS_KM", "MANUTENCAO_KM"),
        "regenera": False,
        "valor_base": lambda: config.PNEUS_KM + config.MANUTENCAO_KM,
        "formato": "R$ {:.3f}/km",
    },
    "tripulacao": {
        "rotulo": "Tripulacao (R$/h)",
        "aplicar": _escalar_varios(
            "CUSTO_HORA_TRIPULANTE", "DIARIA_TRIPULANTE", "PERNOITE_TRIPULANTE"),
        "regenera": False,
        "valor_base": lambda: config.CUSTO_HORA_TRIPULANTE,
        "formato": "R$ {:.2f}/h",
    },
    "pedagio": {
        "rotulo": "Pedagio",
        "aplicar": _escalar_pedagio,
        "regenera": False,
        "valor_base": lambda: config.CORREDORES["SUDESTE"]["pedagio_km"],
        "formato": "R$ {:.3f}/km (Sudeste)",
    },
    "custo_fixo": {
        "rotulo": "Bloco de custo fixo",
        "aplicar": _escalar_dicionario("CUSTO_FIXO_MENSAL"),
        "regenera": False,
        "valor_base": config.fixo_mensal_total,
        "formato": "R$ {:,.0f}/mes",
    },
    "tarifa": {
        "rotulo": "Tarifa",
        "aplicar": _escalar("FATOR_TARIFA"),
        "regenera": True,
        "valor_base": lambda: 1.0,
        "formato": "{:.0%} da tarifa base",
    },
    "demanda": {
        "rotulo": "Demanda",
        "aplicar": _escalar("FATOR_DEMANDA"),
        "regenera": True,
        "valor_base": lambda: 1.0,
        "formato": "{:.0%} da demanda base",
    },
}

# As constantes que algum parametro toca — o que o cenario precisa restaurar.
_ALVOS = [
    "DIESEL_LITRO", "PNEUS_KM", "MANUTENCAO_KM", "CUSTO_HORA_TRIPULANTE",
    "DIARIA_TRIPULANTE", "PERNOITE_TRIPULANTE", "CORREDORES",
    "CUSTO_FIXO_MENSAL", "FATOR_TARIFA", "FATOR_DEMANDA",
]


@contextmanager
def cenario(**fatores: float):
    """Aplica fatores multiplicativos as premissas e restaura ao sair.

    O `finally` nao e zelo excessivo: sem ele, um cenario que estourasse no meio
    deixaria `config` alterado e TODA rodada seguinte do processo sairia errada,
    inclusive as que nada tem a ver com estresse. O erro apareceria longe da
    causa.
    """
    desconhecidos = set(fatores) - set(PARAMETROS)
    if desconhecidos:
        raise ValueError(
            f"parametro desconhecido: {', '.join(sorted(desconhecidos))} — "
            f"use um de {', '.join(PARAMETROS)}"
        )

    original = {nome: copy.deepcopy(getattr(config, nome)) for nome in _ALVOS}
    try:
        for parametro, fator in fatores.items():
            PARAMETROS[parametro]["aplicar"](fator)
        yield
    finally:
        for nome, valor in original.items():
            setattr(config, nome, valor)


def precisa_regerar(fatores: dict[str, float]) -> bool:
    """O cenario mexe em demanda ou tarifa? Entao o dataset tem que ser refeito."""
    return any(
        PARAMETROS[parametro]["regenera"] and abs(fator - 1.0) > 1e-12
        for parametro, fator in fatores.items()
    )


def rodar(fatores: dict[str, float] | None = None,
          dataset: pd.DataFrame | None = None,
          gerador=None) -> pd.DataFrame:
    """A janela de decisao sob um cenario. Devolve a janela ja classificada.

    `gerador` e injetavel para o cenario poder rodar sobre outra malha que nao a
    sintetica. O padrao continua sendo `sintetico.gerar`, e os sete parametros
    de `PARAMETROS` so fazem sentido com ele — uma malha externa chega com o
    custo ja calculado e nao tem preco de diesel para perturbar. Quem quiser
    estressar malha propria perturba o proprio catalogo e passa o resultado como
    `dataset`.
    """
    fatores = fatores or {}
    gerador = gerador or sintetico.gerar
    with cenario(**fatores):
        bruto = gerador() if (dataset is None or precisa_regerar(fatores)) else dataset
        fato = indicadores.calcular(custos.aplicar(bruto))
        return indicadores.janela_decisao(fato)


def _dataset_base() -> pd.DataFrame:
    """O dataset do cenario base, para reuso por quem so mexe em custo."""
    return sintetico.gerar()


# ---------------------------------------------------------------------------
# 1. Ponto de ruptura
# ---------------------------------------------------------------------------

def ruptura(parametro: str = "diesel", limites: tuple[float, float] = (0.35, 3.0),
            passos: int = 60) -> pd.DataFrame:
    """Em que nivel do parametro cada linha cruza o proprio ponto de equilibrio.

    Varre uma grade de fatores e interpola o cruzamento do spread por zero em
    cada linha. Grade e nao busca binaria por linha porque uma rodada devolve as
    vinte linhas de uma vez: 60 rodadas resolvem a malha inteira, contra 20
    buscas de ~15 iteracoes cada.

    A grade comeca ABAIXO de 1 de proposito. Para a linha que ja nao cobre o
    custo, o cruzamento fica a esquerda do cenario atual, e a leitura se inverte
    sem mudar a conta: nao e "a que preco ela quebra", e "a que preco ela
    voltaria a cobrir". E a informacao mais acionavel que existe sobre uma linha
    em AJUSTAR.
    """
    if parametro not in PARAMETROS:
        raise ValueError(f"parametro desconhecido: {parametro}")

    dataset = _dataset_base()
    fatores = np.linspace(*limites, passos)

    curvas = {}
    for fator in fatores:
        janela = rodar({parametro: float(fator)}, dataset=dataset)
        curvas[float(fator)] = janela.set_index("linha_id")["spread_rask_cask"]

    spreads = pd.DataFrame(curvas)           # linhas x fatores
    identidade = rodar({}, dataset=dataset).set_index("linha_id")

    registros = []
    for linha_id, serie in spreads.iterrows():
        registros.append({
            "linha_id": linha_id,
            "linha": identidade.loc[linha_id, "linha"],
            "km": identidade.loc[linha_id, "km"],
            "classe": identidade.loc[linha_id, "classe"],
            "classificacao": identidade.loc[linha_id, "classificacao"],
            "spread_atual": identidade.loc[linha_id, "spread_rask_cask"],
            **_cruzamento(serie.index.to_numpy(), serie.to_numpy()),
        })

    saida = pd.DataFrame(registros)
    base = PARAMETROS[parametro]["valor_base"]()
    saida["valor_ruptura"] = saida["fator_ruptura"] * base
    saida["valor_base"] = base
    saida["folga"] = saida["fator_ruptura"] - 1.0
    saida["parametro"] = parametro

    saida.attrs["limites"] = limites
    saida.attrs["faixa_valor"] = (limites[0] * base, limites[1] * base)
    saida.attrs["formato"] = PARAMETROS[parametro]["formato"]
    return saida.sort_values("fator_ruptura", ascending=False, ignore_index=True)


def _cruzamento(fatores: np.ndarray, spreads: np.ndarray) -> dict:
    """O fator em que o spread cruza zero, por interpolacao linear na grade.

    Quando a grade inteira fica do mesmo lado do zero, devolve NaN **com a
    direcao**, e nao so o NaN. A distincao importa e foi um erro que eu quase
    publiquei: Manaus-Boa Vista nao cruza dentro da faixa varrida, e isso NAO
    quer dizer "nao cobre nem com diesel de graca" — quer dizer que o diesel
    teria que cair abaixo do piso da grade. Sao duas frases diferentes, e so uma
    delas e verdade.

    Extrapolar para fora da faixa daria um numero mais bonito e nao medido.
    """
    sinais = np.sign(spreads)
    trocas = np.nonzero(np.diff(sinais) != 0)[0]

    if len(trocas) == 0:
        acima = bool(spreads[0] > 0)
        return {
            "fator_ruptura": float("nan"),
            "situacao": ("cobre em toda a faixa varrida" if acima
                         else "nao cobre em toda a faixa varrida"),
        }

    i = trocas[0]
    x0, x1 = fatores[i], fatores[i + 1]
    y0, y1 = spreads[i], spreads[i + 1]
    fator = float(x0) if y1 == y0 else float(x0 - y0 * (x1 - x0) / (y1 - y0))
    return {"fator_ruptura": fator, "situacao": "medido"}


# ---------------------------------------------------------------------------
# 2. Tornado
# ---------------------------------------------------------------------------

def tornado(amplitude: float = 0.10) -> pd.DataFrame:
    """O efeito de mover cada premissa isoladamente, para cima e para baixo.

    Responde onde vale gastar esforco de apuracao. Refinar uma premissa que move
    0,2% do resultado e trabalho perdido; a que move 15% merece a planilha que
    ninguem quer montar.

    Uma premissa de cada vez, de proposito: o tornado mede sensibilidade
    isolada. O efeito conjunto — que e o que de fato acontece — esta em
    `monte_carlo`, e as duas leituras juntas sao mais uteis que qualquer uma
    sozinha.
    """
    dataset = _dataset_base()
    base = rodar({}, dataset=dataset)
    resultado_base = float(base["resultado"].sum())
    manter_base = int((base["classificacao"] == "MANTER").sum())

    registros = []
    for parametro, definicao in PARAMETROS.items():
        linha = {"parametro": parametro, "rotulo": definicao["rotulo"]}

        for direcao, fator in (("baixa", 1 - amplitude), ("alta", 1 + amplitude)):
            janela = rodar({parametro: fator}, dataset=dataset)
            resultado = float(janela["resultado"].sum())
            linha[f"resultado_{direcao}"] = resultado
            linha[f"variacao_{direcao}"] = resultado / resultado_base - 1
            linha[f"manter_{direcao}"] = int((janela["classificacao"] == "MANTER").sum())

        linha["amplitude_resultado"] = abs(
            linha["resultado_alta"] - linha["resultado_baixa"]
        )
        linha["elasticidade"] = (
            linha["variacao_baixa"] - linha["variacao_alta"]
        ) / (2 * amplitude)
        registros.append(linha)

    saida = pd.DataFrame(registros)
    saida.attrs["resultado_base"] = resultado_base
    saida.attrs["manter_base"] = manter_base
    saida.attrs["amplitude"] = amplitude
    return saida.sort_values("amplitude_resultado", ascending=False, ignore_index=True)


# ---------------------------------------------------------------------------
# 3. Monte Carlo
# ---------------------------------------------------------------------------

def sortear(n: int, semente: int | None = None) -> pd.DataFrame:
    """N cenarios, com as sete premissas sorteadas juntas.

    Cada fator e lognormal de media 1, com o desvio declarado em
    `config.INCERTEZA`. Os fatores de CUSTO compartilham um choque comum, na
    intensidade de `config.CORRELACAO_CUSTOS`: sortear os sete de forma
    independente subestimaria a cauda, porque na vida real diesel, pedagio,
    manutencao e salario sobem juntos — e o cenario que interessa e justamente
    o que junta todos.
    """
    gerador = np.random.default_rng(semente if semente is not None else config.SEED)
    custos_correlacionados = [
        "diesel", "pneus_e_manutencao", "tripulacao", "pedagio", "custo_fixo",
    ]

    rho = config.CORRELACAO_CUSTOS
    comum = gerador.standard_normal(n)

    colunas = {}
    for parametro, desvio in config.INCERTEZA.items():
        proprio = gerador.standard_normal(n)
        if parametro in custos_correlacionados:
            z = np.sqrt(rho) * comum + np.sqrt(1 - rho) * proprio
        else:
            z = proprio
        # Correcao de media: E[exp(X)] = exp(sigma^2/2). Sem o desconto, o
        # sorteio inflaria todas as premissas de forma silenciosa.
        colunas[parametro] = np.exp(desvio * z - desvio**2 / 2)

    return pd.DataFrame(colunas)


def monte_carlo(n: int = 500, semente: int | None = None) -> dict:
    """A classificacao de cada linha sob incerteza, como probabilidade.

    O rotulo unico do relatorio afirma uma certeza que as premissas nao
    sustentam. Aqui a mesma linha aparece como "MANTER em 62% dos cenarios", que
    e uma frase que se pode defender.
    """
    sorteios = sortear(n, semente)
    dataset = _dataset_base()

    # A identidade e a classificacao BASE vem da rodada sem cenario nenhum. Tirar
    # do primeiro sorteio — que foi o que eu fiz primeiro — rotula cada linha com
    # um cenario aleatorio e faz `p_rotulo_base` medir a coisa errada: a chance
    # de repetir um sorteio, nao a de confirmar o relatorio.
    identidade = rodar({}, dataset=dataset).set_index("linha_id")[
        ["linha", "km", "classe", "classificacao"]
    ].rename(columns={"classificacao": "classificacao_base"})

    contagens: dict[str, dict[str, int]] = {}
    resultados = []

    for _, fatores in sorteios.iterrows():
        janela = rodar(fatores.to_dict(), dataset=dataset)
        resultados.append(float(janela["resultado"].sum()))
        for registro in janela.itertuples(index=False):
            alvo = contagens.setdefault(
                registro.linha_id, dict.fromkeys(config.CLASSIFICACOES, 0))
            alvo[registro.classificacao] += 1

    probabilidades = (
        pd.DataFrame(contagens).T.reindex(columns=list(config.CLASSIFICACOES)) / n
    )
    probabilidades.index.name = "linha_id"

    por_linha = identidade.join(probabilidades).reset_index()
    # `incerta` e a linha cujo rotulo do relatorio nao se sustenta na maioria dos
    # cenarios: e onde a decisao binaria mais engana.
    por_linha["p_rotulo_base"] = [
        registro[registro["classificacao_base"]] for _, registro in por_linha.iterrows()
    ]
    por_linha["incerta"] = por_linha["p_rotulo_base"] < 0.90

    resultados = np.array(resultados)
    return {
        "por_linha": por_linha.sort_values("MANTER", ascending=False, ignore_index=True),
        "sorteios": sorteios,
        "resultado": pd.Series(resultados),
        "n": n,
        "resumo_resultado": {
            "media": float(resultados.mean()),
            "p05": float(np.percentile(resultados, 5)),
            "p50": float(np.percentile(resultados, 50)),
            "p95": float(np.percentile(resultados, 95)),
            "prob_prejuizo": float((resultados < 0).mean()),
        },
    }
