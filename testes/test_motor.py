"""
O contrato de entrada e o motor — inclusive a ponte simulada.

O teste que mais importa aqui nao testa funcionalidade nova: prova que o
refactor **nao moveu um numero**. Separar "o modelo" de "os dados do modelo" so
vale a pena se o que ja estava publicado continuar identico, e a unica forma de
saber isso e comparando.

O segundo em importancia e a ponte simulada: uma malha com vocabulario
estrangeiro, bloco fixo proprio e nenhuma relacao com o gerador sintetico,
passando pelo motor inteiro. E a prova de que a fase seguinte e possivel — sem
nenhum dado real entrar neste repositorio.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from margem import config, custos, dados, indicadores, motor, sintetico


@pytest.fixture(scope="module")
def fato_bruto() -> pd.DataFrame:
    """A malha sintetica com custo variavel, antes de qualquer rateio."""
    return custos.aplicar_variaveis(sintetico.gerar())


# ---------------------------------------------------------------------------
# O contrato
# ---------------------------------------------------------------------------

def test_contrato_e_uma_lista_fechada():
    contrato = dados.descrever()
    assert set(contrato["grupo"]) == {"chave", "aditiva", "descritiva"}
    assert set(dados.OBRIGATORIAS) == set(dados.CHAVES) | set(dados.ADITIVAS)
    # Toda coluna declara unidade e proposito: contrato sem os dois nao serve
    # para quem vai ligar uma malha sem ler o codigo.
    assert contrato["unidade"].str.len().min() > 0
    assert contrato["serve_para"].str.len().min() > 10


def test_a_malha_sintetica_cumpre_o_proprio_contrato(fato_bruto):
    dados.validar(fato_bruto)


def test_coluna_ausente_estoura_nomeando_o_que_falta(fato_bruto):
    """Coluna que some nao pode virar indicador zerado em silencio.

    Um CASK sem tripulacao e so um CASK menor, e nada na tela avisa — e o defeito
    que o contrato existe para impedir.
    """
    sem_custo = fato_bruto.drop(columns=["custo_variavel"])
    with pytest.raises(ValueError, match="custo_variavel"):
        dados.validar(sem_custo)

    # A mensagem tem que dizer PARA QUE a coluna serve, e nao so o nome dela.
    try:
        dados.validar(sem_custo)
    except ValueError as erro:
        assert "margem de contribuicao" in str(erro)


def test_duplicata_no_grao_estoura(fato_bruto):
    """O motor soma o que recebe: duplicata vira volume inventado."""
    dobrado = pd.concat([fato_bruto, fato_bruto.head(1)], ignore_index=True)
    with pytest.raises(ValueError, match="duplicados"):
        dados.validar(dobrado)


def test_aditiva_negativa_estoura(fato_bruto):
    torto = fato_bruto.copy()
    torto.loc[0, "receita"] = -1.0
    with pytest.raises(ValueError, match="negativos"):
        dados.validar(torto)


def test_fato_vazio_estoura(fato_bruto):
    with pytest.raises(ValueError, match="vazio"):
        dados.validar(fato_bruto.head(0))


def test_preparar_deriva_o_que_da_e_registra(fato_bruto):
    """ASK e RPK saem de assentos, km e partidas quando nao vem prontos."""
    cru = fato_bruto.drop(columns=["assentos_km", "passageiros_km", "km_rodados"])
    preparado = dados.preparar(cru)

    assert set(preparado.attrs["derivadas"]) >= {
        "assentos_km", "km_rodados", "passageiros_km"}
    pd.testing.assert_series_equal(
        preparado["assentos_km"].astype(float),
        fato_bruto["assentos_km"].astype(float),
        check_names=False,
    )


def test_preparar_nao_sobrescreve_o_que_veio_da_fonte(fato_bruto):
    """Coluna presente vence a derivacao: dado medido vale mais que calculado."""
    medido = fato_bruto.copy()
    medido["passageiros_km"] = medido["passageiros_km"] * 0.9
    preparado = dados.preparar(medido)

    assert "passageiros_km" not in preparado.attrs["derivadas"]
    pd.testing.assert_series_equal(
        preparado["passageiros_km"], medido["passageiros_km"])


# ---------------------------------------------------------------------------
# O motor reproduz exatamente o que ja estava publicado
# ---------------------------------------------------------------------------

def test_motor_reproduz_a_janela_de_antes_do_refactor(fato_bruto):
    """A prova de que separar modelo e dados nao mexeu em numero nenhum."""
    pelo_motor = motor.avaliar(fato_bruto)

    antigo = indicadores.recomendacao(
        indicadores.janela_decisao(indicadores.calcular(custos.aplicar(sintetico.gerar())))
    )
    pd.testing.assert_frame_equal(pelo_motor, antigo)


def test_motor_mensal_mantem_as_identidades(fato_bruto):
    erros = indicadores.reconciliar(motor.mensal(fato_bruto))
    assert (erros["erro_maximo"] < 1e-9).all()


def test_motor_recusa_fato_fora_do_contrato(fato_bruto):
    with pytest.raises(ValueError, match="contrato"):
        motor.avaliar(fato_bruto.drop(columns=["assentos_km"]))


# ---------------------------------------------------------------------------
# O bloco fixo injetado
# ---------------------------------------------------------------------------

def test_fixo_injetado_fecha_com_o_valor_passado(fato_bruto):
    """Rateio com bloco de fora tem que fechar com esse bloco, nao com o config."""
    outro = 2_500_000.0
    mensal = motor.mensal(fato_bruto, fixo_mensal=outro)
    por_mes = mensal.groupby("ano_mes")["custo_fixo_rateado"].sum()

    assert (por_mes - outro).abs().max() < 1e-6
    assert outro != config.fixo_mensal_total()


def test_fixo_maior_piora_a_decisao(fato_bruto):
    """Sanidade: mais estrutura para cobrir, menos linhas cobrindo."""
    magro = motor.avaliar(fato_bruto, fixo_mensal=500_000.0)
    gordo = motor.avaliar(fato_bruto, fixo_mensal=3_000_000.0)

    assert (magro["classificacao"] == "MANTER").sum() > (
        gordo["classificacao"] == "MANTER").sum()


# ---------------------------------------------------------------------------
# A ponte simulada — sem nenhum dado real
# ---------------------------------------------------------------------------

def _malha_estrangeira() -> pd.DataFrame:
    """Uma malha inventada, com vocabulario de outro sistema.

    Nao tem relacao com o gerador sintetico: outras linhas, outro nome de
    coluna, outro bloco fixo. E de proposito que ela seja tosca — o teste nao
    mede realismo, mede se o contrato aceita quem cumpre e recusa quem nao
    cumpre.
    """
    gerador = np.random.default_rng(42)
    meses = [f"2026-{mes:02d}" for mes in range(1, 13)]
    registros = []
    for indice, (nome, km, assentos) in enumerate([
        ("Rota Norte", 420, 44), ("Rota Sul", 780, 30), ("Rota Leste", 210, 46),
    ]):
        for mes in meses:
            partidas = int(gerador.integers(40, 120))
            passageiros = int(partidas * assentos * gerador.uniform(0.45, 0.85))
            registros.append({
                "id_linha": f"R{indice + 1}",
                "mes": mes,
                "viagens": partidas,
                "assentos": assentos,
                "km": km,
                "pax": passageiros,
                "receita_bruta": passageiros * km * gerador.uniform(0.18, 0.26),
                "custo_direto": partidas * km * gerador.uniform(3.0, 4.2),
            })
    return pd.DataFrame(registros)


MAPA = {
    "id_linha": "linha_id", "mes": "ano_mes", "viagens": "partidas",
    "pax": "passageiros", "receita_bruta": "receita", "custo_direto": "custo_variavel",
}


def test_ponte_simulada_atravessa_o_motor_inteiro():
    """Malha externa, vocabulario proprio, bloco fixo proprio — e funciona.

    E a prova de que a ponte com uma malha real e possivel sem trazer dado real
    para ca: o que se testa e o CONTRATO, nao os dados.
    """
    preparado = dados.preparar(_malha_estrangeira(), mapa=MAPA)
    assert set(preparado.attrs["derivadas"]) >= {"assentos_km", "km_rodados"}

    janela = motor.avaliar(preparado, fixo_mensal=180_000.0, janela_meses=12)

    assert len(janela) == 3
    assert set(janela["classificacao"]) <= set(config.CLASSIFICACOES)
    # As identidades do modelo valem para qualquer malha, nao so para a sintetica.
    erros = indicadores.reconciliar(janela)
    assert (erros["erro_maximo"] < 1e-9).all()


def test_ponte_simulada_respeita_a_base_de_rateio():
    preparado = dados.preparar(_malha_estrangeira(), mapa=MAPA)
    por_km = motor.avaliar(preparado, fixo_mensal=180_000.0, base_rateio="km")
    por_partida = motor.avaliar(preparado, fixo_mensal=180_000.0, base_rateio="partida")

    fixo_km = por_km.set_index("linha_id")["custo_fixo_rateado"]
    fixo_partida = por_partida.set_index("linha_id")["custo_fixo_rateado"]
    assert not np.allclose(fixo_km, fixo_partida)
    # As duas fecham com o mesmo total: o rateio redistribui, nao cria custo.
    assert fixo_km.sum() == pytest.approx(fixo_partida.sum())


def test_malha_sem_traducao_e_recusada():
    """Sem o mapa, o vocabulario estrangeiro nao passa — e a mensagem diz o que falta."""
    with pytest.raises(ValueError, match="contrato"):
        dados.preparar(_malha_estrangeira())
