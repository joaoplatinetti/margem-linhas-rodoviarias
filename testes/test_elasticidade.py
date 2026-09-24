"""
O estimador, a calibracao e o desenho do teste.

Dois testes carregam o peso do modulo. Um confere o estimador contra um caso de
resposta CONHECIDA — sem isso, "o estimador falhou" nao distingue um achado de
um defeito de implementacao. O outro confere a escala `1/(passo x raiz de n)`,
porque o desenho inteiro do teste de preco e uma extrapolacao em cima dela.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from margem import config, elasticidade


# ---------------------------------------------------------------------------
# O estimador, contra casos de resposta conhecida
# ---------------------------------------------------------------------------

def _painel_artificial(beta: float, n_linhas: int = 20, n_meses: int = 24,
                       ruido: float = 0.05, semente: int = 0) -> pd.DataFrame:
    """Painel de laboratorio: x independente de tudo, efeitos fixos conhecidos.

    Aqui a resposta certa e `beta` por construcao, entao qualquer desvio e do
    estimador e nao do gerador do projeto.
    """
    gerador = np.random.default_rng(semente)
    linhas = np.repeat(np.arange(n_linhas), n_meses)
    meses = np.tile(np.arange(n_meses), n_linhas)

    efeito_linha = gerador.normal(0, 1.0, n_linhas)[linhas]
    efeito_mes = gerador.normal(0, 0.5, n_meses)[meses]
    x = gerador.normal(0, 0.3, n_linhas * n_meses)
    y = beta * x + efeito_linha + efeito_mes + gerador.normal(0, ruido, len(x))

    return pd.DataFrame({
        "linha_id": linhas, "ano_mes": meses,
        "log_tarifa": x, "log_passageiros": y,
    })


@pytest.mark.parametrize("beta", [-1.2, 0.0, 0.8])
def test_estimador_recupera_coeficiente_conhecido(beta):
    """Com variacao exogena, o estimador tem que acertar. Se nao acertar aqui,
    tudo o que o modulo diz sobre vies e defeito de implementacao."""
    dados = _painel_artificial(beta)
    resultado = elasticidade.estimar(dados, ("linha_id", "ano_mes"))
    assert resultado["coeficiente"] == pytest.approx(beta, abs=0.02)


def test_efeitos_fixos_absorvem_os_niveis():
    """Sem os efeitos fixos, o mesmo painel sai enviesado — e com eles, nao.

    E a prova de que a transformacao 'within' de dois sentidos esta correta,
    incluindo o termo da media geral somado de volta.
    """
    dados = _painel_artificial(-1.2)
    dados["log_tarifa"] = dados["log_tarifa"] + dados["linha_id"] * 0.3

    sem = elasticidade.estimar(dados, ())
    com = elasticidade.estimar(dados, ("linha_id", "ano_mes"))

    assert abs(sem["coeficiente"] - (-1.2)) > 0.3
    assert com["coeficiente"] == pytest.approx(-1.2, abs=0.02)


def test_erro_agrupado_e_maior_que_o_classico():
    """Choque correlacionado dentro da linha infla o erro verdadeiro.

    O erro classico ignoraria isso e publicaria um intervalo estreito demais em
    cima de uma estimativa enviesada — o pior dos dois mundos.
    """
    dados = _painel_artificial(-1.2, ruido=0.05)
    gerador = np.random.default_rng(3)
    choque = gerador.normal(0, 0.4, dados["linha_id"].nunique())
    dados["log_passageiros"] = dados["log_passageiros"] + choque[dados["linha_id"]]
    dados["log_tarifa"] = dados["log_tarifa"] + 0.5 * choque[dados["linha_id"]]

    agrupado = elasticidade.estimar(dados, ())["erro_padrao"]
    # O erro classico equivalente: sem o somatorio por grupo.
    x = dados["log_tarifa"].to_numpy()
    y = dados["log_passageiros"].to_numpy()
    X = np.column_stack([x, np.ones_like(x)])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    residuo = y - X @ beta
    classico = float(np.sqrt(
        (residuo @ residuo) / (len(y) - 2) * np.linalg.inv(X.T @ X)[0, 0]
    ))
    assert agrupado > classico


def test_tres_efeitos_fixos_nao_e_suportado():
    dados = _painel_artificial(-1.0)
    dados["extra"] = 1
    with pytest.raises(NotImplementedError):
        elasticidade.estimar(dados, ("linha_id", "ano_mes", "extra"))


# ---------------------------------------------------------------------------
# O painel do projeto
# ---------------------------------------------------------------------------

def test_elasticidade_zero_preserva_o_baseline():
    """A premissa nova nao pode mexer no dataset ja publicado.

    Com `ELASTICIDADE_PRECO = 0` a resposta ao preco vale exatamente 1, e os
    numeros das ramificacoes 1 a 3 continuam valendo. O teste seguinte fixa isso
    contra o CSV versionado.
    """
    assert config.ELASTICIDADE_PRECO == 0.0
    dados = elasticidade.painel(elasticidade=0.0)
    from margem import sintetico

    base = sintetico.gerar()
    pd.testing.assert_series_equal(
        dados["passageiros"].reset_index(drop=True),
        base["passageiros"].reset_index(drop=True),
    )


def test_elasticidade_negativa_reduz_demanda_no_pico():
    """Elasticidade negativa tem que fazer a demanda responder ao preco.

    O pico concentra tarifa alta; com elasticidade negativa, a demanda do pico
    cresce MENOS do que cresceria sem resposta a preco.
    """
    sem = elasticidade.painel(0.0)
    com = elasticidade.painel(-1.2)
    assert com["passageiros"].sum() < sem["passageiros"].sum()


# ---------------------------------------------------------------------------
# A calibracao — o achado do modulo
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def calibracao() -> pd.DataFrame:
    return elasticidade.calibracao(np.array([0.0, -0.8, -1.6]))


def test_nenhuma_especificacao_identifica(calibracao):
    """Identificar exige inclinacao 1 E intercepto 0. Nenhuma das quatro tem."""
    ajustes = calibracao.attrs["ajustes"]
    assert not ajustes["identifica"].any()


def test_ols_simples_nao_responde_a_verdade(calibracao):
    """O caso grave: a estimativa e a mesma com elasticidade -1,6 ou zero.

    O numero sai plausivel e estavel, e nao mede nada — so reflete que linha
    cara e linha de leito, que tem menos poltrona. E o tipo de resultado que vai
    para o slide sem ninguem desconfiar.
    """
    ajustes = calibracao.attrs["ajustes"].set_index("especificacao")
    assert abs(ajustes.loc["OLS simples", "inclinacao"]) < 0.10

    estimativas = calibracao[calibracao["especificacao"] == "OLS simples"]["estimada"]
    assert estimativas.max() - estimativas.min() < 0.05


def test_efeito_fixo_de_linha_troca_o_sinal(calibracao):
    """Com efeito fixo de linha a estimativa acompanha a verdade, mas deslocada
    o bastante para inverter o sinal: 'preco alto atrai passageiro'."""
    ajustes = calibracao.attrs["ajustes"].set_index("especificacao")
    assert ajustes.loc["+ efeito fixo de linha", "inclinacao"] == pytest.approx(1.0, abs=0.05)
    assert ajustes.loc["+ efeito fixo de linha", "intercepto"] > 1.0

    recorte = calibracao[
        (calibracao["especificacao"] == "+ efeito fixo de linha")
        & (calibracao["verdadeira"] == -0.8)
    ]
    assert float(recorte["estimada"].iloc[0]) > 0


def test_dois_efeitos_fixos_acompanham_mas_nao_acertam(calibracao):
    ajustes = calibracao.attrs["ajustes"].set_index("especificacao")
    assert ajustes.loc["+ linha e mes", "inclinacao"] == pytest.approx(1.0, abs=0.05)
    assert abs(ajustes.loc["+ linha e mes", "intercepto"]) > 0.2


def test_diagnostico_reporta_sinal_e_cobertura():
    diagnostico = elasticidade.diagnostico(-1.2)
    assert len(diagnostico) == len(elasticidade.ESPECIFICACOES)
    assert not diagnostico.loc[
        diagnostico["especificacao"] == "+ efeito fixo de linha", "sinal_certo"
    ].iloc[0]


# ---------------------------------------------------------------------------
# O desenho do teste
# ---------------------------------------------------------------------------

def _erro_medio(semente_ate: int = 24, **kwargs) -> float:
    """Erro-padrao medio sobre varias sementes.

    Uma realizacao so nao serve para medir escala: com 20 grupos, o proprio
    erro agrupado e uma estimativa ruidosa, e comparar dois sorteios mediria o
    ruido da estimativa do erro e nao a relacao de escala. Foi o que derrubou a
    primeira versao deste teste.
    """
    erros = [
        elasticidade.estimar(
            _painel_artificial(-1.2, ruido=0.06, semente=semente, **kwargs),
            ("linha_id", "ano_mes"),
        )["erro_padrao"]
        for semente in range(semente_ate)
    ]
    return float(np.mean(erros))


def test_erro_padrao_escala_com_o_passo_de_preco():
    """Dobrar o passo divide o erro-padrao por dois — exato, nao aproximado.

    Vale para qualquer sorteio porque e a mesma regressao com o regressor
    reescalado, entao aqui uma realizacao basta.
    """
    dados = _painel_artificial(-1.2, ruido=0.06, semente=5)
    base = elasticidade.estimar(dados, ("linha_id", "ano_mes"))

    dobrado = dados.copy()
    dobrado["log_tarifa"] = dobrado["log_tarifa"] * 2
    com_dobro = elasticidade.estimar(dobrado, ("linha_id", "ano_mes"))

    assert com_dobro["erro_padrao"] == pytest.approx(base["erro_padrao"] / 2, rel=1e-6)


def test_erro_padrao_escala_com_a_raiz_das_observacoes():
    """Quadruplicar as observacoes divide o erro-padrao por dois.

    Medido em media sobre 24 sorteios. A tolerancia e de 12% porque a escala vale
    para choques independentes dentro da linha, que e o caso deste painel de
    laboratorio — e a ressalva que `desenho_do_teste` publica junto do resultado.
    """
    curto = _erro_medio(n_meses=24)
    longo = _erro_medio(n_meses=96)
    assert longo == pytest.approx(curto / 2, rel=0.12)


def test_mais_linhas_valem_mais_que_mais_meses():
    """Com erro agrupado por linha, precisao vem do numero de GRUPOS.

    Quadruplicar os meses das mesmas 20 linhas nao vale o mesmo que quadruplicar
    as linhas: o segundo caminho multiplica os grupos, e e a ele que a formula
    do erro agrupado responde melhor. O desenho do teste declara isso.
    """
    mais_meses = _erro_medio(n_linhas=20, n_meses=96)
    mais_linhas = _erro_medio(n_linhas=80, n_meses=24)
    assert mais_linhas < mais_meses


def test_desenho_cresce_quando_o_passo_encolhe():
    desenho = elasticidade.desenho_do_teste(tolerancia=0.20)
    assert desenho["observacoes"].is_monotonic_decreasing
    # Escala quadratica: passo cinco vezes menor pede ~25 vezes mais observacoes.
    menor = desenho[desenho["passo_de_preco"] == 0.02]["observacoes"].iloc[0]
    maior = desenho[desenho["passo_de_preco"] == 0.10]["observacoes"].iloc[0]
    assert menor / maior == pytest.approx(25, rel=0.15)


def test_desenho_declara_a_premissa_de_ruido():
    """O tamanho escala com o QUADRADO do ruido da demanda, entao a premissa sai
    junto do resultado em vez de ficar enterrada no codigo."""
    desenho = elasticidade.desenho_do_teste()
    assert desenho.attrs["ruido_demanda"] == config.RUIDO_DEMANDA
    assert desenho.attrs["referencia"]["n"] == 480


def test_tolerancia_mais_apertada_pede_mais_observacoes():
    frouxa = elasticidade.desenho_do_teste(tolerancia=0.40)
    apertada = elasticidade.desenho_do_teste(tolerancia=0.10)
    for passo in frouxa["passo_de_preco"]:
        a = apertada[apertada["passo_de_preco"] == passo]["observacoes"].iloc[0]
        f = frouxa[frouxa["passo_de_preco"] == passo]["observacoes"].iloc[0]
        assert a > f
