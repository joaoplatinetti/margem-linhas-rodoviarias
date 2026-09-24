"""
Por que o historico nao mede elasticidade — demonstrado com a resposta conhecida.

Este modulo faz uma coisa que so e possivel com dado sintetico: **liga uma
elasticidade de valor conhecido e tenta recuperar ela de volta**. Com dado real
nao se sabe a resposta certa, entao nao se sabe se o estimador errou — e um
estimador que erra em silencio e pior que nenhum, porque vira slide.

O QUE A DEMONSTRACAO MOSTRA

O gerador cria demanda que responde a preco com elasticidade `-1,2` (declarada).
Depois, quatro especificacoes tentam recuperar esse numero do painel de 20 linhas
x 24 meses:

1. **OLS simples** — regride log(passageiros) em log(tarifa), sem mais nada.
2. **Efeito fixo de linha** — cada linha tem seu proprio nivel.
3. **Efeito fixo de mes** — cada mes tem seu proprio nivel.
4. **Efeitos fixos de linha E mes** — a especificacao que todo mundo alcanca.

O problema nao e estatistico, e economico: **preco e demanda sobem juntos no
pico** por motivos que nada tem a ver com um causar o outro. A tarifa media sobe
em julho porque sobra menos promocional, e a demanda sobe em julho porque e
ferias. Um estimador que ve so isso conclui que preco alto atrai passageiro.

O QUE IDENTIFICA

Variacao de preco que nao esteja correlacionada com a demanda — ou seja, um
teste. `desenho_do_teste` diz de quanto ele precisa ser: o erro-padrao do
estimador cai com `1 / (passo de preco x raiz do numero de observacoes)`, entao
passo pequeno demais nao se compensa com paciencia.

IMPLEMENTACAO

Regressao em numpy, sem statsmodels, por duas razoes. A primeira e que o projeto
se mantem em quatro dependencias. A segunda e mais importante: a transformacao
"within" de dois sentidos e o erro-padrao agrupado por linha sao **o conteudo**
deste modulo, e escondê-los atras de uma chamada de biblioteca esvaziaria a
demonstracao. Um teste confere o estimador contra um caso de resposta conhecida.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from margem import config, estresse, sintetico

log = logging.getLogger(__name__)

# A elasticidade que o gerador usa nas demonstracoes deste modulo. Valor de
# livro para transporte de passageiros de media distancia: demanda elastica, mas
# nao muito. O que importa nao e o numero e sim que ele seja CONHECIDO.
ELASTICIDADE_VERDADEIRA = -1.2

ESPECIFICACOES: dict[str, tuple[str, ...]] = {
    "OLS simples": (),
    "+ efeito fixo de linha": ("linha_id",),
    "+ efeito fixo de mes": ("ano_mes",),
    "+ linha e mes": ("linha_id", "ano_mes"),
}


# ---------------------------------------------------------------------------
# O painel
# ---------------------------------------------------------------------------

def painel(elasticidade: float = ELASTICIDADE_VERDADEIRA,
           ruido_tarifa: float | None = None,
           semente: int | None = None) -> pd.DataFrame:
    """Gera o painel com elasticidade conhecida e devolve as variaveis em log.

    `ruido_tarifa` e a variacao de preco IDIOSSINCRATICA — a parte que nao
    acompanha a sazonalidade nem o mix. E o unico canal por onde a elasticidade
    poderia ser identificada sem experimento, e no modelo base ela vale 2%.
    """
    fatores = {}
    alteracoes = {"ELASTICIDADE_PRECO": elasticidade}
    if ruido_tarifa is not None:
        alteracoes["RUIDO_TARIFA"] = ruido_tarifa
    if semente is not None:
        alteracoes["SEED"] = semente

    originais = {nome: getattr(config, nome) for nome in alteracoes}
    try:
        for nome, valor in alteracoes.items():
            setattr(config, nome, valor)
        with estresse.cenario(**fatores):
            dados = sintetico.gerar()
    finally:
        for nome, valor in originais.items():
            setattr(config, nome, valor)

    saida = dados[["linha_id", "ano_mes", "passageiros", "tarifa_media",
                   "assentos_km", "partidas"]].copy()
    saida["log_passageiros"] = np.log(saida["passageiros"])
    saida["log_tarifa"] = np.log(saida["tarifa_media"])
    saida.attrs["elasticidade"] = elasticidade
    saida.attrs["ruido_tarifa"] = (
        ruido_tarifa if ruido_tarifa is not None else config.RUIDO_TARIFA
    )
    saida.attrs["fracao_no_teto"] = float((dados["demanda_represada"] > 0).mean())
    return saida


# ---------------------------------------------------------------------------
# O estimador
# ---------------------------------------------------------------------------

def _centrar(df: pd.DataFrame, colunas: list[str],
             efeitos: tuple[str, ...]) -> pd.DataFrame:
    """Transformacao 'within': remove as medias dos efeitos fixos pedidos.

    Para um painel balanceado com dois efeitos, a conta fecha em um passo:

        x~ = x - media_da_linha - media_do_mes + media_geral

    O termo somado de volta no fim nao e detalhe: sem ele a media geral seria
    subtraida duas vezes, e o estimador sairia com vies que ninguem nota porque
    o numero continua plausivel.
    """
    saida = df.copy()
    for coluna in colunas:
        valores = saida[coluna]
        centrado = valores.copy()
        for efeito in efeitos:
            centrado = centrado - valores.groupby(saida[efeito]).transform("mean")
        if len(efeitos) == 2:
            centrado = centrado + valores.mean()
        elif len(efeitos) > 2:
            raise NotImplementedError(
                "a transformacao em um passo so vale para ate dois efeitos fixos"
            )
        saida[coluna] = centrado
    return saida


def estimar(dados: pd.DataFrame, efeitos: tuple[str, ...] = (),
            agrupar_por: str = "linha_id") -> dict:
    """Regride log(passageiros) em log(tarifa) e devolve o coeficiente e o erro.

    O erro-padrao e **agrupado por linha**. Em painel, os choques de uma mesma
    linha sao correlacionados ao longo do tempo, e o erro classico sairia pequeno
    demais — publicando um intervalo estreito em cima de uma estimativa
    enviesada, que e o pior dos dois mundos.
    """
    usado = _centrar(dados, ["log_passageiros", "log_tarifa"], efeitos)

    y = usado["log_passageiros"].to_numpy()
    x = usado["log_tarifa"].to_numpy()
    X = np.column_stack([x, np.ones_like(x)]) if not efeitos else x[:, None]

    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    residuo = y - X @ beta

    grupos = dados[agrupar_por].to_numpy()
    meat = np.zeros((X.shape[1], X.shape[1]))
    for grupo in np.unique(grupos):
        selecao = grupos == grupo
        pedaco = X[selecao].T @ residuo[selecao]
        meat += np.outer(pedaco, pedaco)

    n_grupos = len(np.unique(grupos))
    n, k = X.shape
    # Correcao de amostra pequena, a mesma que os pacotes de painel aplicam.
    perdidos = sum(dados[efeito].nunique() for efeito in efeitos)
    perdidos = perdidos - 1 if len(efeitos) == 2 else perdidos
    ajuste = (n_grupos / (n_grupos - 1)) * ((n - 1) / (n - k - perdidos))
    variancia = ajuste * (xtx_inv @ meat @ xtx_inv)

    erro = float(np.sqrt(variancia[0, 0]))
    coeficiente = float(beta[0])
    return {
        "coeficiente": coeficiente,
        "erro_padrao": erro,
        "ic_baixo": coeficiente - 1.96 * erro,
        "ic_alto": coeficiente + 1.96 * erro,
        "n": int(n),
        "residuo_dp": float(np.std(residuo, ddof=1)),
    }


# ---------------------------------------------------------------------------
# 1. O diagnostico: as quatro especificacoes contra a verdade
# ---------------------------------------------------------------------------

def diagnostico(elasticidade: float = ELASTICIDADE_VERDADEIRA,
                ruido_tarifa: float | None = None) -> pd.DataFrame:
    """As quatro especificacoes, lado a lado, contra o valor verdadeiro."""
    dados = painel(elasticidade, ruido_tarifa)

    registros = []
    for nome, efeitos in ESPECIFICACOES.items():
        resultado = estimar(dados, efeitos)
        registros.append({
            "especificacao": nome,
            "efeitos": " + ".join(efeitos) if efeitos else "nenhum",
            **resultado,
            "verdadeira": elasticidade,
            "vies": resultado["coeficiente"] - elasticidade,
            "sinal_certo": resultado["coeficiente"] < 0,
            "cobre_a_verdade": (
                resultado["ic_baixo"] <= elasticidade <= resultado["ic_alto"]
            ),
        })

    saida = pd.DataFrame(registros)
    saida.attrs["elasticidade"] = elasticidade
    saida.attrs["ruido_tarifa"] = dados.attrs["ruido_tarifa"]
    return saida


# ---------------------------------------------------------------------------
# 2. A calibracao: o estimador se move quando a verdade se move?
# ---------------------------------------------------------------------------

def calibracao(verdadeiras: np.ndarray | None = None) -> pd.DataFrame:
    """Roda cada especificacao contra VARIAS elasticidades verdadeiras.

    Este e o teste que decide, e ele so existe com dado sintetico. Uma rodada
    unica nao distingue duas situacoes muito diferentes:

    - o estimador erra por um vies constante (ainda serve: da para corrigir, ou
      pelo menos para comparar dois trechos entre si);
    - o estimador **nao responde a verdade** (nao serve para nada: devolveria o
      mesmo numero se a elasticidade fosse -2 ou zero).

    A diferenca esta na INCLINACAO da estimativa contra a verdade. Um estimador
    que identifica tem inclinacao 1 e intercepto 0. Inclinacao perto de zero
    significa que o numero na tela nao tem relacao com o fenomeno — e ele
    continua parecendo razoavel, que e o que o torna perigoso.
    """
    if verdadeiras is None:
        verdadeiras = np.array([0.0, -0.4, -0.8, -1.2, -1.6, -2.0])

    registros = []
    for verdadeira in verdadeiras:
        dados = painel(float(verdadeira))
        for nome, efeitos in ESPECIFICACOES.items():
            resultado = estimar(dados, efeitos)
            registros.append({
                "especificacao": nome,
                "verdadeira": float(verdadeira),
                "estimada": resultado["coeficiente"],
                "erro_padrao": resultado["erro_padrao"],
                "ic_baixo": resultado["ic_baixo"],
                "ic_alto": resultado["ic_alto"],
            })

    saida = pd.DataFrame(registros)

    # Inclinacao e intercepto de estimada ~ verdadeira, por especificacao.
    ajustes = []
    for nome in ESPECIFICACOES:
        recorte = saida[saida["especificacao"] == nome]
        inclinacao, intercepto = np.polyfit(
            recorte["verdadeira"], recorte["estimada"], 1)
        ajustes.append({
            "especificacao": nome,
            "inclinacao": float(inclinacao),
            "intercepto": float(intercepto),
            # "Identifica" exige as duas coisas: acompanhar a verdade E nao ter
            # deslocamento. Uma so nao basta.
            "identifica": bool(abs(inclinacao - 1) < 0.15 and abs(intercepto) < 0.15),
        })

    saida.attrs["ajustes"] = pd.DataFrame(ajustes)
    return saida


# ---------------------------------------------------------------------------
# 3. A curva de identificacao
# ---------------------------------------------------------------------------

def curva_de_identificacao(passos: np.ndarray | None = None,
                           elasticidade: float = ELASTICIDADE_VERDADEIRA
                           ) -> pd.DataFrame:
    """A estimativa em funcao de quanta variacao de preco EXOGENA existe.

    Varre o desvio da variacao idiossincratica de tarifa. E a resposta a "e se a
    gente tivesse mais historico?": nao adianta. O que falta nao e tamanho de
    amostra, e variacao de preco que nao acompanhe a demanda — e ela nao aparece
    esperando.
    """
    passos = np.linspace(0.01, 0.20, 12) if passos is None else passos

    registros = []
    for passo in passos:
        dados = painel(elasticidade, ruido_tarifa=float(passo))
        resultado = estimar(dados, ESPECIFICACOES["+ linha e mes"])
        registros.append({
            "variacao_de_preco": float(passo),
            **resultado,
            "erro_absoluto": abs(resultado["coeficiente"] - elasticidade),
            "cobre_a_verdade": (
                resultado["ic_baixo"] <= elasticidade <= resultado["ic_alto"]
            ),
            # O teto de ocupacao censura a demanda por cima. Com variacao de
            # preco grande, parte das linhas-mes bate no teto e deixa de
            # responder — e a estimativa volta a se afastar da verdade. E um
            # limite REAL de qualquer teste de preco para baixo: o onibus enche.
            "no_teto": float(dados.attrs.get("fracao_no_teto", np.nan)),
        })

    saida = pd.DataFrame(registros)
    saida.attrs["elasticidade"] = elasticidade
    saida.attrs["base"] = config.RUIDO_TARIFA
    return saida


# ---------------------------------------------------------------------------
# 4. O desenho do teste
# ---------------------------------------------------------------------------

def desenho_do_teste(tolerancia: float = 0.20, confianca: float = 0.80,
                     passos: tuple[float, ...] = (0.02, 0.05, 0.10, 0.15, 0.20),
                     elasticidade: float = ELASTICIDADE_VERDADEIRA) -> pd.DataFrame:
    """Quantas observacoes o teste precisa, para cada passo de preco.

    Parte do erro-padrao MEDIDO numa configuracao de referencia e extrapola pela
    unica relacao que governa o problema:

        erro-padrao  ~  1 / (passo de preco x raiz do numero de observacoes)

    Extrapolar de uma medida em vez de derivar a formula do zero e deliberado: a
    medida ja carrega o ruido real da demanda, o desbalanceamento da grade e a
    perda de graus de liberdade dos efeitos fixos. Uma formula limpa erraria por
    esses tres motivos de uma vez, e erraria para menos.

    Um teste confere a escala `1/(passo x raiz de n)` por simulacao, porque a
    extrapolacao inteira depende dela.

    **Duas ressalvas que mudam o tamanho recomendado**, as duas medidas em teste
    e nao supostas:

    - O erro-padrao e agrupado por linha, entao **precisao vem do numero de
      LINHAS no teste, nao do numero de meses**. Quadruplicar os meses das
      mesmas 20 linhas rende menos que quadruplicar as linhas. A coluna
      `linhas_por_12_meses` existe por isso: e o caminho mais curto.
    - O tamanho escala com o QUADRADO do ruido mensal da demanda. Este modelo
      usa 6%; uma operacao com 12% precisa de quatro vezes mais observacoes.
    """
    referencia_passo = 0.10
    dados = painel(elasticidade, ruido_tarifa=referencia_passo)
    medida = estimar(dados, ESPECIFICACOES["+ linha e mes"])

    # Quantil normal bilateral para a confianca pedida: 80% -> 1,2816.
    z = float(np.abs(_quantil_normal((1 - confianca) / 2)))
    erro_alvo = tolerancia / z

    registros = []
    for passo in passos:
        # SE ~ 1/(passo x raiz(n))  =>  n = n_ref x (passo_ref/passo)^2 x (SE_ref/SE_alvo)^2
        necessario = (
            medida["n"]
            * (referencia_passo / passo) ** 2
            * (medida["erro_padrao"] / erro_alvo) ** 2
        )
        registros.append({
            "passo_de_preco": passo,
            "observacoes": int(np.ceil(necessario)),
            "meses_com_20_linhas": int(np.ceil(necessario / 20)),
            "linhas_por_12_meses": int(np.ceil(necessario / 12)),
        })

    saida = pd.DataFrame(registros)
    saida.attrs["tolerancia"] = tolerancia
    saida.attrs["confianca"] = confianca
    saida.attrs["referencia"] = {"passo": referencia_passo, **medida}
    saida.attrs["elasticidade"] = elasticidade
    # O tamanho necessario escala com o QUADRADO do ruido da demanda. Este
    # modelo usa 6% ao mes; uma operacao com 12% precisa de quatro vezes mais
    # observacoes. E a premissa mais influente do desenho e por isso ela sai
    # junto do resultado, e nao enterrada no codigo.
    saida.attrs["ruido_demanda"] = config.RUIDO_DEMANDA
    saida.attrs["residuo_dp"] = medida["residuo_dp"]
    return saida


def _quantil_normal(probabilidade: float) -> float:
    """Quantil da normal padrao, por bissecao sobre a funcao de distribuicao.

    Quinze linhas para nao trazer scipy so por causa de um numero. A funcao de
    distribuicao sai de `math.erf`, que e da biblioteca padrao.
    """
    from math import erf, sqrt

    def acumulada(x: float) -> float:
        return 0.5 * (1 + erf(x / sqrt(2)))

    baixo, alto = -10.0, 10.0
    for _ in range(200):
        meio = (baixo + alto) / 2
        if acumulada(meio) < probabilidade:
            baixo = meio
        else:
            alto = meio
    return (baixo + alto) / 2
