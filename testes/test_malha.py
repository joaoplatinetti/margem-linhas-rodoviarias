"""
O rateio e o corte — e as identidades algebricas que provam que os dois estao certos.

O valor destes testes nao e pegar regressao: e que cada um deles e uma
DEMONSTRACAO. Se `spread >= 0 <=> MC% >= F/R` falhar na base receita, o motor de
rateio esta errado; se `delta_resultado != -MC`, a simulacao de corte esta
movendo custo fixo que nao deveria se mover. Sao resultados de algebra, nao
propriedades observadas neste dataset, e valeriam para qualquer malha.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from margem import config, custos, indicadores, malha, sintetico


@pytest.fixture(scope="module")
def bruto() -> pd.DataFrame:
    """O fato com custo variavel e receita, antes de qualquer rateio."""
    fato = custos.aplicar_variaveis(sintetico.gerar())
    return indicadores.calcular(
        fato.assign(custo_fixo_rateado=0.0, custo_total=fato["custo_variavel"])
    )


@pytest.fixture(scope="module")
def janela(bruto) -> pd.DataFrame:
    return indicadores.recomendacao(
        indicadores.janela_decisao(indicadores.calcular(custos.aplicar(sintetico.gerar())))
    )


# ---------------------------------------------------------------------------
# O rateio fecha em todas as bases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("base", list(config.BASES_RATEIO))
def test_rateio_fecha_com_o_total_declarado(bruto, base):
    """Trocar a base redistribui, nao cria nem destroi custo.

    E a primeira coisa a garantir: se o total nao fechasse, qualquer comparacao
    entre bases estaria comparando blocos fixos de tamanhos diferentes e o
    argumento inteiro do artigo cairia.
    """
    rateado = custos.ratear_fixo(bruto, base=base)
    por_mes = rateado.groupby("ano_mes")["custo_fixo_rateado"].sum()

    assert len(por_mes) == 24
    assert (por_mes - config.fixo_mensal_total()).abs().max() < 1e-6


# ---------------------------------------------------------------------------
# O que cada base faz, provado
# ---------------------------------------------------------------------------

def test_base_assento_km_da_fixo_unitario_constante(bruto):
    """Ratear por ASK atribui o MESMO fixo por assento-km a todas as linhas.

    E o que esvazia essa base como criterio de decisao: somar a mesma constante
    ao CASK de todo mundo nao distribui estrutura, so desloca o corte. A decisao
    que sai dela e um corte unico em margem de contribuicao por assento-km.
    """
    janela = malha.janela_por_base(bruto, "assento_km")
    fixo_por_ask = janela["custo_fixo_rateado"] / janela["assentos_km"]

    assert fixo_por_ask.std() / fixo_por_ask.mean() < 1e-12


def test_base_receita_colapsa_a_decisao_no_grao_do_mes(bruto):
    """Com rateio por receita, a decisao vira um piso unico de MC% — exato no mes.

    Demonstracao, para o mes m: fixo_i = F x R_i/R_m, entao
        spread_i x ASK_i = R_i - CV_i - F x R_i/R_m = R_i(1 - F/R_m) - CV_i
    e dividir por R_i da  MC%_i - F/R_m.  O rateio some da decisao: sobra um
    piso de margem de contribuicao igual para a malha inteira naquele mes.
    """
    mensal = indicadores.calcular(custos.ratear_fixo(bruto, base="receita"))
    um_mes = mensal[mensal["ano_mes"] == config.PERIODO_FIM]
    piso = um_mes["custo_fixo_rateado"].sum() / um_mes["receita"].sum()

    esperado = um_mes["margem_contribuicao_pct"] - piso
    medido = um_mes["spread_rask_cask"] / um_mes["rask"]
    assert np.abs(esperado - medido).max() < 1e-12


def test_base_receita_mantem_o_piso_unico_na_janela(bruto):
    """Na janela de 12 meses o piso continua decidindo, mas deixa de ser exato.

    O motivo nao e defeito de calculo: o piso e `F/R_m`, que muda todo mes com a
    sazonalidade, e somar doze meses de uma razao nao e a razao das somas. O
    desvio fica na terceira casa — pequeno o bastante para nao trocar a decisao
    de nenhuma linha, que e o que o artigo afirma — e a tolerancia aqui existe
    para registrar que a aproximacao e conhecida, nao para esconder erro.
    """
    janela = malha.janela_por_base(bruto, "receita")
    piso = janela["custo_fixo_rateado"].sum() / janela["receita"].sum()

    por_spread = janela["spread_rask_cask"] >= -1e-12
    por_mc = janela["margem_contribuicao_pct"] >= piso - 1e-12
    assert (por_spread == por_mc).all(), "o piso unico deixou de classificar igual"

    desvio = np.abs(
        (janela["margem_contribuicao_pct"] - piso)
        - janela["spread_rask_cask"] / janela["rask"]
    ).max()
    assert desvio < 0.005, f"desvio de {desvio:.4f} — grande demais para ser sazonalidade"


def test_base_km_penaliza_quem_tem_menos_assento(bruto):
    """Com rateio por km, `fixo/ASK = (F/km_total)/assentos`.

    Consequencia: o leito (26 poltronas) carrega 46/26 = 1,77x o fixo por
    assento-km do convencional (46). Nao e caracteristica do dataset — e a
    formula, e ela penaliza o leito em qualquer malha.
    """
    janela = malha.janela_por_base(bruto, "km")
    fixo_por_ask = janela["custo_fixo_rateado"] / janela["assentos_km"]

    leito = fixo_por_ask[janela["classe"] == "LEITO"].mean()
    convencional = fixo_por_ask[janela["classe"] == "CONVENCIONAL"].mean()

    assert leito / convencional == pytest.approx(46 / 26, rel=1e-6)


def test_base_partida_penaliza_a_linha_curta(bruto):
    """Com rateio por partida, `fixo/ASK = (F/partidas)/(km x assentos)`.

    A viagem curta dilui o custo da partida em menos assento-km, entao carrega
    muito mais. A linha mais curta da malha tem que ser a de maior fixo por
    assento-km nessa base — e e o oposto do que acontece na base km.
    """
    janela = malha.janela_por_base(bruto, "partida")
    fixo_por_ask = janela["custo_fixo_rateado"] / janela["assentos_km"]

    mais_curta = janela["km"].idxmin()
    assert fixo_por_ask.idxmax() == mais_curta


def test_a_comparacao_cobre_as_quatro_bases(bruto):
    comparacao = malha.comparar_bases(bruto)

    assert len(comparacao) == 20
    for base in config.BASES_RATEIO:
        assert f"por_{base}" in comparacao.columns
        assert f"fixo_ask_{base}" in comparacao.columns
    assert (comparacao["razao_fixo_ask"] >= 1).all()


def test_o_rotulo_e_mais_robusto_que_o_ranking(bruto):
    """O achado do artigo, fixado em teste.

    A classificacao quase nao se move porque quem decide primeiro e a margem de
    contribuicao, que nao depende de rateio. O ranking se move bastante. Se um
    dia isso inverter, o texto do artigo passa a estar errado e o teste avisa.
    """
    comparacao = malha.comparar_bases(bruto)

    mudam_de_rotulo = int(comparacao["sensivel_ao_rateio"].sum())
    assert mudam_de_rotulo < len(comparacao) / 4, "o rotulo deixou de ser robusto"
    assert comparacao["razao_fixo_ask"].max() > 1.5, "o fixo por ASK parou de variar"
    assert comparacao["amplitude_posicao"].max() >= 3, "o ranking parou de se mover"


# ---------------------------------------------------------------------------
# O corte
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("linha_id", ["L16", "L15", "L01"])
def test_o_corte_muda_o_resultado_em_menos_a_mc(bruto, linha_id):
    """`delta_resultado = -MC da linha cortada`, exatamente.

    E a identidade central da simulacao, e ela vale porque o bloco fixo NAO sai
    da empresa junto com a linha: a receita e o custo variavel dela somem, o
    fixo permanece. Qualquer outro resultado significa que a simulacao esta
    movendo custo que nao deveria se mover.
    """
    resultado = malha.simular_corte(bruto, linha_id)
    assert resultado["delta_resultado"] == pytest.approx(
        -resultado["mc_da_cortada"], rel=1e-9
    )


def test_cortar_linha_com_mc_positiva_piora_a_rede(bruto):
    """O achado que sustenta o artigo: AJUSTAR nao quer dizer cortar.

    Brasilia-BH e classificada AJUSTAR (nao cobre o custo cheio) e ainda assim
    entrega margem de contribuicao positiva. Cortada, a rede perde exatamente
    essa margem.
    """
    resultado = malha.simular_corte(bruto, "L15")

    assert resultado["classificacao_da_cortada"] == "AJUSTAR"
    assert resultado["mc_da_cortada"] > 0
    assert resultado["delta_resultado"] < 0


def test_cortar_linha_com_mc_negativa_melhora_a_rede(bruto):
    resultado = malha.simular_corte(bruto, "L16")

    assert resultado["classificacao_da_cortada"] == "REVER"
    assert resultado["mc_da_cortada"] < 0
    assert resultado["delta_resultado"] > 0


def test_o_corte_sobe_o_cask_de_quem_fica(bruto):
    """O fixo redistribuido encarece todas as linhas remanescentes.

    E a cascata: nenhuma delas mudou de operacao, de preco ou de ocupacao, e
    mesmo assim o custo cheio delas subiu.
    """
    resultado = malha.simular_corte(bruto, "L15")
    comparacao = resultado["comparacao"]

    assert (comparacao["delta_cask"] > 0).all()
    assert resultado["cask_depois"] > resultado["cask_antes"]
    # E o LF de equilibrio sobe junto: a mesma linha passa a precisar de mais
    # ocupacao para empatar, sem nada ter mudado nela.
    assert (comparacao["lf_equilibrio_depois"] > comparacao["lf_equilibrio_antes"]).all()


def test_a_cascata_existe_e_e_so_para_pior(bruto):
    """Quem muda de rotulo por causa do corte so pode piorar, nunca melhorar."""
    resultado = malha.simular_corte(bruto, "L15")
    cascata = resultado["cascata"]

    assert len(cascata) >= 1
    ordem = {nome: posicao for posicao, nome in enumerate(config.CLASSIFICACOES)}
    for _, registro in cascata.iterrows():
        assert ordem[registro["classificacao_depois"]] > ordem[registro["classificacao_antes"]]


def test_cortar_linha_inexistente_falha(bruto):
    with pytest.raises(ValueError, match="nao existe"):
        malha.simular_corte(bruto, "L99")


def test_ranking_de_corte_so_aprova_mc_negativa(janela):
    """O ganho do corte e `-MC`, entao so linha com MC negativa vale cortar.

    O teste amarra as duas leituras: existe linha com spread negativo (que o
    relatorio aponta) e ganho de corte negativo (que a conta desmente), e e
    exatamente esse par que o artigo discute.
    """
    ranking = malha.ranking_de_corte(janela)

    assert (ranking["vale_cortar"] == (ranking["margem_contribuicao"] < 0)).all()

    enganosas = ranking[(~ranking["vale_cortar"]) & (ranking["spread_rask_cask"] < 0)]
    assert len(enganosas) > 0, "sem esse caso o artigo nao tem o que mostrar"
    assert (enganosas["classificacao"] == "AJUSTAR").all()
