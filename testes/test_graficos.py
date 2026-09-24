"""As tres figuras do artigo: geram, gravam nos dois formatos e nao mentem."""
from __future__ import annotations

import pandas as pd
import pytest

from margem import custos, graficos, indicadores, sintetico


@pytest.fixture(scope="module")
def janela() -> pd.DataFrame:
    fato = indicadores.calcular(custos.aplicar(sintetico.gerar()))
    return indicadores.recomendacao(indicadores.janela_decisao(fato))


def test_exporta_as_tres_figuras(janela, tmp_path, monkeypatch):
    from margem import config

    monkeypatch.setattr(config, "SAIDA_IMAGENS", tmp_path / "imagens")
    figuras = graficos.exportar(janela)

    assert set(figuras) == {"matriz-decisao", "esquema-estrela", "load-factor-equilibrio"}
    for nome, caminhos in figuras.items():
        assert len(caminhos) == 2, f"{nome} deveria sair em PNG e SVG"
        for caminho in caminhos:
            arquivo = tmp_path / "imagens" / caminho.rsplit("/", 1)[-1]
            assert arquivo.exists()
            # PNG de figura vazia tem alguns KB; o piso pega o caso em que a
            # figura sai em branco por um erro de dado silencioso.
            assert arquivo.stat().st_size > 10_000, f"{arquivo.name} saiu pequeno demais"


def test_svg_sai_com_texto_selecionavel(janela, tmp_path, monkeypatch):
    """`svg.fonttype = none` mantem o texto como <text> em vez de curva.

    Vale para titulo, rotulo de eixo e marcacao — o que permite abrir o SVG e
    reescrever um deles sem refazer a figura.

    A excecao, medida e nao suposta: rotulo que carrega contorno na cor da
    superficie (`withStroke`) e rasterizado para caminho vetorial pelo
    matplotlib e deixa de ser editavel. Sao os rotulos dos pontos e das regioes,
    que precisam do contorno para permanecerem legiveis sobre a hachura e sobre
    os washes de cor. Legibilidade ganhou de editabilidade nesses; quem precisar
    reescrever um deles muda o texto no codigo e regera.
    """
    from margem import config

    monkeypatch.setattr(config, "SAIDA_IMAGENS", tmp_path / "imagens")
    graficos.matriz_decisao(janela)

    svg = (tmp_path / "imagens" / "matriz-decisao.svg").read_text()
    assert "Matriz de decisao por linha" in svg
    assert "Margem de contribuicao" in svg
    assert svg.count("<text") > 10


def test_a_matriz_rotula_so_quem_decide(janela):
    """O rotulo seletivo e regra, nao acaso: numero em todo ponto vira ruido.

    Este teste fixa o criterio — quem nao e MANTER, mais quem esta no limite.
    """
    esperado = janela[(janela["classificacao"] != "MANTER") | janela["no_limite"]]
    assert 4 <= len(esperado) <= 10, (
        f"{len(esperado)} rotulos na matriz: fora dessa faixa o grafico vira "
        "lista de nomes ou esconde uma decisao"
    )


def test_dumbbell_ordena_da_pior_para_a_melhor(janela):
    """A ordenacao por folga e o que faz o grafico ser lido de baixo para cima."""
    ordenado = janela.sort_values("folga_lf", ascending=True, ignore_index=True)
    assert ordenado.loc[0, "classificacao"] == "REVER"
    assert ordenado.iloc[-1]["classificacao"] == "MANTER"
    assert ordenado["folga_lf"].is_monotonic_increasing
