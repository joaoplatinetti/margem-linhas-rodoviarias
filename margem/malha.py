"""
O que a escolha do rateio decide, e o que o corte de uma linha provoca.

As duas perguntas usam o mesmo motor — redistribuir um bloco fixo que nao se
move — e as duas terminam no mesmo lugar: **a decisao de cortar linha depende de
coisas que nao estao na linha.**

PARTE 1 — A BASE DE RATEIO NAO E DETALHE CONTABIL

Quatro bases sao igualmente defensaveis numa reuniao, e as quatro fecham com o
mesmo total declarado. Mas cada uma penaliza sistematicamente um arquetipo de
linha, e isso e **algebra, nao simulacao**:

- **receita**: `fixo_i = F·R_i/R`. Entao
  `spread_i >= 0  <=>  MC%_i >= F/R`. A classificacao colapsa num unico corte de
  margem de contribuicao percentual, igual para todas as linhas: o rateio deixa
  de diferenciar qualquer uma. Ratear por receita nao e ratear, e diluir.
- **assento_km**: `fixo/ASK` vira a MESMA constante para todo mundo, entao
  `spread_i = MC_por_ASK_i - F/ASK_total`. A decisao vira um corte unico em
  margem de contribuicao por assento-km.
- **km** (o padrao): `fixo/ASK = (F/km_total)/assentos`. Quem tem menos assento
  carrega mais fixo por assento-km — o leito (26 assentos) leva 77% mais que o
  convencional (46). **Penaliza o leito por construcao.**
- **partida**: `fixo/ASK = (F/partidas_total)/(km x assentos)`. Quem faz viagem
  curta carrega muito mais por assento-km. **Penaliza a linha curta**, que e
  justamente a mais rentavel da malha.

Nenhuma das quatro e errada. O ponto e que a lista de linhas a cortar sai
diferente em cada uma, e quase ninguem trata essa escolha como o que ela e: uma
decisao de gestao, tomada em geral por inercia.

PARTE 2 — CORTAR A PIOR LINHA MEXE NAS OUTRAS

Tirar uma linha da malha nao tira o custo fixo dela: o bloco fixo continua
inteiro e se redistribui entre as que ficam. Disso saem dois resultados exatos:

- **O resultado da rede muda em exatamente `-MC` da linha cortada.** Se a margem
  de contribuicao dela era positiva, cortar PIORA a rede — mesmo que o spread
  dela fosse negativo e o relatorio a marcasse como problema.
- **O fixo redistribuido sobe o CASK de quem fica**, e linhas que cobriam o
  custo cheio por pouco passam a nao cobrir. E a cascata que quase nunca entra
  na conta do corte, e que faz "cortar a pior" virar um processo que se repete.

Fora de escopo, declarado: perda de trafego de conexao. O modelo nao tem malha
conectada, e inventar uma taxa de recaptura produziria um numero que parece
medido sem ser.
"""
from __future__ import annotations

import logging

import pandas as pd

from margem import config, custos, indicadores

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parte 1: a base de rateio
# ---------------------------------------------------------------------------

def janela_por_base(fato_bruto: pd.DataFrame, base: str) -> pd.DataFrame:
    """A janela de decisao recalculada sob uma base de rateio.

    Recebe o fato ANTES do custo (so oferta, demanda e receita) porque o rateio
    tem que ser refeito do zero: reaproveitar o fato ja rateado por km e so
    trocar a coluna do fixo daria um custo total inconsistente com o proprio
    rateio.
    """
    fato = indicadores.calcular(custos.aplicar(fato_bruto, base=base))
    janela = indicadores.janela_decisao(fato)
    janela["base_rateio"] = base
    return janela


def detalhar_bases(fato_bruto: pd.DataFrame) -> pd.DataFrame:
    """Tabela longa: uma linha por linha de onibus x base de rateio.

    E o formato que permite comparar magnitude, e nao so rotulo. `fixo_por_ask`
    e a coluna que carrega o argumento: e quanto de estrutura cada linha leva por
    assento-km, e ela muda muito mais entre as bases do que a classificacao.
    """
    blocos = []
    for base in config.BASES_RATEIO:
        janela = janela_por_base(fato_bruto, base)
        bloco = janela[[
            "linha_id", "linha", "km", "classe", "assentos",
            "margem_contribuicao_pct", "custo_fixo_rateado", "assentos_km",
            "cask_total", "spread_rask_cask", "classificacao",
        ]].copy()
        bloco["base_rateio"] = base
        bloco["fixo_por_ask"] = bloco["custo_fixo_rateado"] / bloco["assentos_km"]
        # Posicao no ranking de spread DENTRO da base: e o que a diretoria olha
        # quando pergunta "quais sao as piores".
        bloco["posicao"] = bloco["spread_rask_cask"].rank(ascending=False).astype(int)
        blocos.append(bloco)

    return pd.concat(blocos, ignore_index=True)


def comparar_bases(fato_bruto: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por linha de onibus, o efeito das quatro bases lado a lado.

    Tres medidas, nessa ordem de importancia — e a ordem e o proprio achado:

    - `bases_distintas` — quantos ROTULOS diferentes a linha recebeu. Costuma ser
      1: a classificacao e robusta, porque quem decide primeiro e a margem de
      contribuicao, que nao depende de rateio nenhum.
    - `razao_fixo_ask` — quantas vezes o fixo por assento-km da MESMA linha muda
      entre a base mais generosa e a mais dura com ela. Aqui o numero e grande.
    - `amplitude_posicao` — quantas posicoes a linha anda no ranking de spread.

    A conclusao que sai disso nao e "o rateio decide o corte", e uma mais fina:
    **o rateio quase nao muda o rotulo, mas muda bastante quem PARECE pior** — e
    atencao de gestao, meta e orcamento seguem o ranking, nao o rotulo.
    """
    longo = detalhar_bases(fato_bruto)
    colunas_base = [f"por_{base}" for base in config.BASES_RATEIO]

    rotulos = longo.pivot(index="linha_id", columns="base_rateio",
                          values="classificacao")
    fixo = longo.pivot(index="linha_id", columns="base_rateio", values="fixo_por_ask")
    posicao = longo.pivot(index="linha_id", columns="base_rateio", values="posicao")

    # Prefixo `por_` / `fixo_ask_` nas colunas: a base "km" tem o mesmo nome da
    # coluna de distancia da linha, e sem o prefixo o join estoura.
    rotulos.columns = [f"por_{c}" for c in rotulos.columns]
    fixo.columns = [f"fixo_ask_{c}" for c in fixo.columns]
    posicao.columns = [f"posicao_{c}" for c in posicao.columns]

    identidade = (
        longo[longo["base_rateio"] == config.BASE_RATEIO_FIXO]
        .set_index("linha_id")[["linha", "km", "classe", "assentos",
                                "margem_contribuicao_pct"]]
    )

    saida = identidade.join([rotulos, fixo, posicao]).reset_index()

    # Contar sobre as colunas JA UNIDAS: cada base ordena a janela pelo proprio
    # spread, entao alinhar por posicao em vez de por indice casaria linha errada
    # com linha errada.
    saida["bases_distintas"] = saida[colunas_base].nunique(axis=1)
    saida["sensivel_ao_rateio"] = saida["bases_distintas"] > 1

    colunas_fixo = list(fixo.columns)
    saida["razao_fixo_ask"] = saida[colunas_fixo].max(axis=1) / saida[colunas_fixo].min(axis=1)

    colunas_posicao = list(posicao.columns)
    saida["amplitude_posicao"] = (
        saida[colunas_posicao].max(axis=1) - saida[colunas_posicao].min(axis=1)
    )

    return saida.sort_values("razao_fixo_ask", ascending=False, ignore_index=True)


def resumo_bases(fato_bruto: pd.DataFrame) -> pd.DataFrame:
    """Contagem por classificacao em cada base, e a dispersao do fixo por ASK.

    `cv_fixo_por_ask` e a prova visivel da algebra: na base assento_km ele da
    ZERO, porque `fixo/ASK` e a mesma constante para todas as linhas. Uma base de
    rateio que atribui o mesmo custo unitario a todo mundo nao esta distribuindo
    estrutura, esta somando uma constante ao CASK — e a decisao que sai dela e
    um corte unico em margem de contribuicao por assento-km.
    """
    longo = detalhar_bases(fato_bruto)
    janelas = {base: janela_por_base(fato_bruto, base) for base in config.BASES_RATEIO}

    linhas_resumo = []
    for base, janela in janelas.items():
        contagem = janela["classificacao"].value_counts()
        fixo_ask = longo.loc[longo["base_rateio"] == base, "fixo_por_ask"]

        linhas_resumo.append({
            "base_rateio": base,
            "dirigente": config.BASES_RATEIO[base],
            **{nome: int(contagem.get(nome, 0)) for nome in config.CLASSIFICACOES},
            "receita_exposta": float(
                janela.loc[janela["classificacao"] != "MANTER", "receita"].sum()
                / janela["receita"].sum()
            ),
            "fixo_ask_medio": float(fixo_ask.mean()),
            "cv_fixo_por_ask": float(fixo_ask.std() / fixo_ask.mean()),
            "penaliza": _quem_a_base_penaliza(base),
        })

    return pd.DataFrame(linhas_resumo)


def _quem_a_base_penaliza(base: str) -> str:
    """O arquetipo de linha que cada base castiga, direto da algebra.

    Nao e observacao do dataset: sai de `fixo/ASK` em cada base, e valeria para
    qualquer malha. Esta aqui em texto porque e o que o leitor precisa levar do
    grafico — a tabela sozinha nao diz POR QUE a linha curta some do topo quando
    a base vira partida.
    """
    return {
        # fixo/ASK = (F/km_total) / assentos  -> quem tem menos poltrona paga mais
        "km": "o leito: fixo/ASK cai com o numero de assentos (26 contra 46)",
        # fixo/ASK = (F/partidas) / (km x assentos) -> a viagem curta dilui menos
        "partida": "a linha curta de alta frequencia: nada dilui o custo por partida",
        # fixo/ASK = F/ASK_total, constante -> nao penaliza ninguem, e nao decide nada
        "assento_km": "ninguem — e por isso que a decisao colapsa num corte unico",
        # fixo_i = F x R_i/R -> spread >= 0 <=> MC% >= F/R
        "receita": "ninguem: vira um piso unico de MC%, igual para toda a malha",
    }[base]


# ---------------------------------------------------------------------------
# Parte 2: o corte
# ---------------------------------------------------------------------------

def simular_corte(fato_bruto: pd.DataFrame, linha_id: str) -> dict:
    """Tira a linha da malha, redistribui o fixo e reclassifica quem fica.

    Devolve o antes, o depois, a variacao do resultado da rede e a cascata — as
    linhas que mudaram de classificacao **sem que nada nelas tenha mudado**.
    """
    if linha_id not in set(fato_bruto["linha_id"]):
        raise ValueError(f"linha '{linha_id}' nao existe na malha")

    antes = indicadores.recomendacao(
        indicadores.janela_decisao(indicadores.calcular(custos.aplicar(fato_bruto)))
    )

    restante = fato_bruto[fato_bruto["linha_id"] != linha_id]
    depois = indicadores.recomendacao(
        indicadores.janela_decisao(indicadores.calcular(custos.aplicar(restante)))
    )

    cortada = antes.set_index("linha_id").loc[linha_id]
    rede_antes = indicadores.agregar(antes).iloc[0]
    rede_depois = indicadores.agregar(depois).iloc[0]

    comparacao = (
        antes.set_index("linha_id")[["linha", "classificacao", "spread_rask_cask",
                                     "cask_total", "load_factor", "lf_equilibrio"]]
        .join(
            depois.set_index("linha_id")[["classificacao", "spread_rask_cask",
                                          "cask_total", "lf_equilibrio"]],
            how="inner", lsuffix="_antes", rsuffix="_depois",
        )
    )
    comparacao["delta_cask"] = comparacao["cask_total_depois"] - comparacao["cask_total_antes"]
    comparacao["delta_spread"] = (
        comparacao["spread_rask_cask_depois"] - comparacao["spread_rask_cask_antes"]
    )
    comparacao["mudou"] = (
        comparacao["classificacao_antes"] != comparacao["classificacao_depois"]
    )

    return {
        "linha_id": linha_id,
        "linha": cortada["linha"],
        "classificacao_da_cortada": cortada["classificacao"],
        "mc_da_cortada": float(cortada["margem_contribuicao"]),
        "receita_da_cortada": float(cortada["receita"]),
        "resultado_antes": float(rede_antes["resultado"]),
        "resultado_depois": float(rede_depois["resultado"]),
        "delta_resultado": float(rede_depois["resultado"] - rede_antes["resultado"]),
        "cask_antes": float(rede_antes["cask_total"]),
        "cask_depois": float(rede_depois["cask_total"]),
        "cascata": comparacao[comparacao["mudou"]],
        "comparacao": comparacao,
    }


def ranking_de_corte(janela: pd.DataFrame) -> pd.DataFrame:
    """Quanto a rede ganha (ou perde) ao cortar cada linha, uma de cada vez.

    O ganho e `-MC`, e nao `-resultado`: o bloco fixo nao sai da empresa junto
    com a linha. E o numero que separa as duas leituras — a linha pode ter
    resultado negativo (spread < 0) e ainda assim o corte dela **piorar** a rede,
    porque a margem de contribuicao que ela entregava ao fixo desaparece.
    """
    saida = janela[[
        "linha_id", "linha", "km", "classe", "receita", "margem_contribuicao",
        "margem_contribuicao_pct", "resultado", "spread_rask_cask", "classificacao",
    ]].copy()

    saida["ganho_do_corte"] = -saida["margem_contribuicao"]
    saida["vale_cortar"] = saida["ganho_do_corte"] > 0
    saida["leitura"] = [
        "cortar melhora a rede" if vale else
        ("o relatorio pede corte, a conta desmente" if spread < 0 else
         "cobre o custo cheio")
        for vale, spread in zip(saida["vale_cortar"], saida["spread_rask_cask"])
    ]
    return saida.sort_values("ganho_do_corte", ascending=False, ignore_index=True)
