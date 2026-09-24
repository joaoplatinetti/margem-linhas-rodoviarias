"""
CLI do projeto.

Nenhum subcomando depende de estado deixado pelo anterior, e nao existe pasta de
dados intermediarios. O motivo e que o dataset e **deterministico**: a mesma
semente devolve os mesmos 480 registros em alguns milissegundos, entao recomputar
e mais barato e mais seguro do que guardar um Parquet que pode ficar velho em
relacao as premissas de `config.py`. Guardar estado intermediario faria sentido
se o dado viesse de uma extracao cara — aqui ele nao vem.

    margem tudo          gera, calcula e exporta Excel + CSVs + imagens
    margem linhas        o catalogo e o custo unitario por linha
    margem indicadores   a tabela de decisao (janela de 12 meses)
    margem excel         so a planilha
    margem powerbi       so os CSVs do Power BI
    margem imagens       so as figuras do artigo (PNG + SVG)
    margem rateio        o efeito da base de rateio do custo fixo
    margem corte LINHA   o que acontece com a malha ao cortar uma linha
    margem conferir      as identidades do modelo (RASK = yield x LF etc.)
"""
from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from margem import config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Apresentacao no terminal
# ---------------------------------------------------------------------------

def _moeda(valor: float) -> str:
    """1234567.8 -> 'R$ 1.234.567,80'.

    O `replace` ingenuo trocaria o separador decimal junto e imprimiria
    'R$ 1.234.567.80'. Dai o passo intermediario com o arroba.
    """
    texto = f"{float(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"R$ {texto}"


def _milhar(valor: float) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _dec(valor: float, casas: int = 4) -> str:
    """Decimal com virgula. So o separador decimal, sem milhar."""
    return f"{float(valor):.{casas}f}".replace(".", ",")


def _pct(valor: float, casas: int = 1) -> str:
    return f"{float(valor) * 100:.{casas}f}".replace(".", ",") + "%"


def _log(verboso: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verboso else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _montar() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """O caminho inteiro: dataset -> custo -> indicadores -> decisao.

    Devolve (fato mensal com indicadores, janela de decisao, catalogo).
    """
    from margem import custos, indicadores, linhas, sintetico

    fato = indicadores.calcular(custos.aplicar(sintetico.gerar()))
    janela = indicadores.recomendacao(indicadores.janela_decisao(fato))
    return fato, janela, linhas.catalogo()


def _fato_sem_fixo() -> pd.DataFrame:
    """O fato com custo VARIAVEL e receita, antes de qualquer rateio.

    E o ponto de partida obrigatorio para comparar bases de rateio: reaproveitar
    o fato ja rateado por km e so trocar a coluna do fixo deixaria o custo total
    inconsistente com o proprio rateio. A base `receita` ainda exige os
    indicadores ja calculados, dai o passo por `indicadores.calcular` com o fixo
    zerado.
    """
    from margem import custos, indicadores, sintetico

    fato = custos.aplicar_variaveis(sintetico.gerar())
    return indicadores.calcular(
        fato.assign(custo_fixo_rateado=0.0, custo_total=fato["custo_variavel"])
    )


def _resumo_terminal(fato: pd.DataFrame, janela: pd.DataFrame) -> None:
    from margem import indicadores

    rede = indicadores.resumo_rede(fato)
    meses = janela.attrs.get("meses") or []

    print()
    print(f"REDE  |  {fato['linha_id'].nunique()} linhas  x  "
          f"{fato['ano_mes'].nunique()} meses  =  {len(fato)} registros")
    print(f"  receita               {_moeda(rede['receita'])}")
    print(f"  custo variavel        {_moeda(rede['custo_variavel'])}")
    print(f"  margem contribuicao   {_moeda(rede['margem_contribuicao'])}"
          f"   ({_pct(rede['margem_contribuicao_pct'])})")
    print(f"  custo total           {_moeda(rede['custo_total'])}")
    print(f"  resultado             {_moeda(rede['resultado'])}"
          f"   ({_pct(rede['resultado_pct'])})")
    print(f"  passageiros           {_milhar(rede['passageiros'])}")
    print(f"  load factor           {_pct(rede['load_factor'])}")
    print(f"  yield                 R$ {_dec(rede['yield_pax_km'])} por passageiro-km")
    print(f"  RASK / CASK total     R$ {_dec(rede['rask'])}  /  "
          f"R$ {_dec(rede['cask_total'])} por assento-km  "
          f"(spread R$ {_dec(rede['spread_rask_cask'])})")
    print()
    print(f"DECISAO  |  janela de {len(meses)} meses"
          f"{f' ({meses[0]} a {meses[-1]})' if meses else ''}")
    contagem = janela["classificacao"].value_counts()
    for nome in config.CLASSIFICACOES:
        quantidade = int(contagem.get(nome, 0))
        receita = janela.loc[janela["classificacao"] == nome, "receita"].sum()
        parcela = receita / janela["receita"].sum() if janela["receita"].sum() else 0
        print(f"  {nome:<8} {quantidade:>2} linhas   {_moeda(receita):>18}"
              f"   {_pct(parcela):>6} da receita")
    no_limite = janela[janela["no_limite"] & (janela["classificacao"] == "MANTER")]
    if len(no_limite):
        print(f"  (e {len(no_limite)} delas cobrem o custo cheio no limite: "
              f"{', '.join(no_limite['linha_id'])})")
    print()


# ---------------------------------------------------------------------------
# Subcomandos
# ---------------------------------------------------------------------------

def cmd_tudo(args: argparse.Namespace) -> int:
    from margem import excel, graficos, malha, powerbi

    fato, janela, catalogo = _montar()
    _resumo_terminal(fato, janela)

    caminho = excel.exportar(fato, janela, catalogo)
    tabelas = powerbi.exportar(fato, janela)

    bruto = _fato_sem_fixo()
    figuras = graficos.exportar(
        janela,
        comparacao=malha.comparar_bases(bruto),
        ranking=malha.ranking_de_corte(janela),
        cascata=malha.simular_corte(bruto, _pior_linha(janela)),
    )

    print(f"Excel     {caminho}")
    print(f"Power BI  {config.SAIDA_POWERBI}  "
          f"({len(tabelas)} tabelas, {sum(tabelas.values())} linhas)")
    print(f"Imagens   {config.SAIDA_IMAGENS}  "
          f"({len(figuras)} figuras, PNG + SVG)")
    print()
    return 0


def cmd_linhas(args: argparse.Namespace) -> int:
    from margem import custos, linhas

    catalogo = linhas.catalogo()
    unitario = custos.custo_unitario_por_linha(catalogo).sort_values("km")

    colunas = ["linha_id", "linha", "km", "classe", "corredor", "tripulantes",
               "combustivel_km", "manutencao_km", "pedagio_km",
               "tripulacao_km", "variavel_km"]
    print()
    print(unitario[colunas].to_string(index=False, float_format=lambda v: f"{v:8.3f}"))
    print()
    print("A coluna tripulacao_km e onde se ve o degrau dos "
          f"{config.SEGUNDO_MOTORISTA_ACIMA_KM:.0f} km: acima disso entra o segundo "
          "motorista.")
    print()
    return 0


def cmd_indicadores(args: argparse.Namespace) -> int:
    fato, janela, _ = _montar()

    colunas = ["linha_id", "linha", "km", "classe", "load_factor", "yield_pax_km",
               "rask", "cask_variavel", "cask_total", "spread_rask_cask",
               "margem_contribuicao_pct", "classificacao", "alavanca"]
    print()
    print(janela[colunas].to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
    _resumo_terminal(fato, janela)
    return 0


def cmd_excel(args: argparse.Namespace) -> int:
    from margem import excel

    fato, janela, catalogo = _montar()
    print()
    print(excel.exportar(fato, janela, catalogo))
    print()
    return 0


def cmd_powerbi(args: argparse.Namespace) -> int:
    from margem import powerbi

    fato, janela, _ = _montar()
    tabelas = powerbi.exportar(fato, janela)
    print()
    for nome, linhas_gravadas in tabelas.items():
        print(f"  {nome:<24} {linhas_gravadas:>5} linhas")
    print(f"\n{config.SAIDA_POWERBI}\n")
    return 0


def _pior_linha(janela: pd.DataFrame) -> str:
    """A linha AJUSTAR de maior margem de contribuicao.

    E o caso que a figura do corte existe para mostrar: a que o relatorio aponta
    como problema e que, cortada, tira mais margem da rede. Se nao houver
    nenhuma AJUSTAR, cai para a de pior spread.
    """
    ajustar = janela[janela["classificacao"] == "AJUSTAR"]
    if len(ajustar):
        return ajustar.loc[ajustar["margem_contribuicao"].idxmax(), "linha_id"]
    return janela.loc[janela["spread_rask_cask"].idxmin(), "linha_id"]


def cmd_imagens(args: argparse.Namespace) -> int:
    from margem import graficos, malha

    _, janela, _ = _montar()
    bruto = _fato_sem_fixo()
    figuras = graficos.exportar(
        janela,
        comparacao=malha.comparar_bases(bruto),
        ranking=malha.ranking_de_corte(janela),
        cascata=malha.simular_corte(bruto, _pior_linha(janela)),
    )
    print()
    for nome, caminhos in figuras.items():
        print(f"  {nome:<26} {'  '.join(p.rsplit('.', 1)[-1] for p in caminhos)}")
    print(f"\n{config.SAIDA_IMAGENS}\n")
    return 0


def cmd_rateio(args: argparse.Namespace) -> int:
    """O efeito da base de rateio sobre a decisao e sobre o ranking."""
    from margem import malha

    bruto = _fato_sem_fixo()
    resumo = malha.resumo_bases(bruto)
    comparacao = malha.comparar_bases(bruto)

    print()
    print("O MESMO BLOCO FIXO, QUATRO BASES DE RATEIO")
    print(f"  bloco fixo declarado: {_moeda(config.fixo_mensal_total())}/mes, "
          "identico nas quatro")
    print()
    colunas = ["base_rateio", "dirigente", *config.CLASSIFICACOES,
               "fixo_ask_medio", "cv_fixo_por_ask"]
    print(resumo[colunas].to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
    print()
    for registro in resumo.itertuples(index=False):
        print(f"  {registro.base_rateio:<11} penaliza {registro.penaliza}")
    print()

    sensiveis = comparacao[comparacao["sensivel_ao_rateio"]]
    print(f"ROTULO: muda em {len(sensiveis)} de {len(comparacao)} linhas")
    for registro in sensiveis.itertuples(index=False):
        rotulos = {getattr(registro, f"por_{base}") for base in config.BASES_RATEIO}
        print(f"  {registro.linha:<38} {' / '.join(sorted(rotulos))}")
    print()
    print("MAGNITUDE: quanto o fixo por assento-km da MESMA linha varia")
    topo = comparacao.head(5)
    for registro in topo.itertuples(index=False):
        print(f"  {registro.linha:<38} {registro.razao_fixo_ask:.2f}x"
              f"   anda {int(registro.amplitude_posicao)} posicoes no ranking")
    print()
    print("  O rotulo e robusto porque quem decide primeiro e a margem de")
    print("  contribuicao, que nao depende de rateio. O ranking nao e — e meta,")
    print("  atencao e orcamento seguem o ranking.")
    print()
    return 0


def cmd_corte(args: argparse.Namespace) -> int:
    """O que acontece com a malha inteira ao cortar uma linha."""
    from margem import malha

    bruto = _fato_sem_fixo()
    resultado = malha.simular_corte(bruto, args.linha.upper())

    print()
    print(f"CORTE DE {resultado['linha_id']} — {resultado['linha']}")
    print(f"  classificada como     {resultado['classificacao_da_cortada']}")
    print(f"  receita               {_moeda(resultado['receita_da_cortada'])}")
    print(f"  margem de contribuicao {_moeda(resultado['mc_da_cortada'])}")
    print()
    print(f"  resultado da rede antes   {_moeda(resultado['resultado_antes'])}")
    print(f"  resultado da rede depois  {_moeda(resultado['resultado_depois'])}")
    print(f"  variacao                  {_moeda(resultado['delta_resultado'])}"
          f"   (= menos a MC da linha, exatamente)")
    print()
    veredito = ("o corte MELHORA a rede" if resultado["delta_resultado"] > 0
                else "o corte PIORA a rede")
    print(f"  {veredito}")
    print()
    print(f"  CASK da rede: R$ {_dec(resultado['cask_antes'])} -> "
          f"R$ {_dec(resultado['cask_depois'])} por assento-km")
    print("  (o bloco fixo nao saiu: ele se redistribuiu entre quem ficou)")
    print()

    cascata = resultado["cascata"]
    if len(cascata):
        print(f"CASCATA: {len(cascata)} linha(s) mudaram de classificacao sem que")
        print("nada nelas tenha mudado —")
        for linha_id, registro in cascata.iterrows():
            print(f"  {registro['linha']:<38} "
                  f"{registro['classificacao_antes']} -> {registro['classificacao_depois']}")
    else:
        print("CASCATA: nenhuma linha mudou de classificacao.")
    print()
    return 0


def cmd_conferir(args: argparse.Namespace) -> int:
    """As identidades do modelo, medidas no fato e na janela.

    Erro diferente de zero a menos de arredondamento significa que alguma
    agregacao usou media de razao em vez de razao de somas — o defeito mais facil
    de introduzir num modelo destes, e o mais dificil de notar olhando o numero.
    """
    from margem import indicadores

    fato, janela, _ = _montar()

    print()
    print("Identidades no fato mensal (480 registros):")
    print(indicadores.reconciliar(fato).to_string(index=False))
    print()
    print("Identidades na janela de decisao (20 linhas):")
    print(indicadores.reconciliar(janela).to_string(index=False))
    print()

    # O rateio tem que fechar com o total declarado em cada mes e em CADA BASE.
    # Conferir so a base em vigor deixaria passar erro nas outras tres, que e
    # justamente onde a comparacao de `margem rateio` iria buscar o numero.
    from margem import custos

    declarado = config.fixo_mensal_total()
    bruto = _fato_sem_fixo()
    print(f"Rateio do fixo: declarado {_moeda(declarado)}/mes")
    for base in config.BASES_RATEIO:
        por_mes = (
            custos.ratear_fixo(bruto, base=base)
            .groupby("ano_mes")["custo_fixo_rateado"].sum()
        )
        erro = (por_mes - declarado).abs().max()
        print(f"  por {base:<11} erro maximo {_moeda(erro)}")
    print()
    return 0


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(
        prog="margem",
        description="Margem por linha de onibus interestadual, sobre dataset sintetico.",
    )
    analisador.add_argument("-v", "--verboso", action="store_true", help="log em DEBUG")
    subcomandos = analisador.add_subparsers(dest="comando")

    for nome, funcao, ajuda in [
        ("tudo", cmd_tudo, "gera, calcula e exporta Excel + CSVs"),
        ("linhas", cmd_linhas, "o catalogo e o custo unitario por linha"),
        ("indicadores", cmd_indicadores, "a tabela de decisao por linha"),
        ("excel", cmd_excel, "so a planilha formatada"),
        ("powerbi", cmd_powerbi, "so os CSVs do Power BI"),
        ("imagens", cmd_imagens, "so as figuras do artigo (PNG + SVG)"),
        ("rateio", cmd_rateio, "o efeito da base de rateio do custo fixo"),
        ("corte", cmd_corte, "o efeito de cortar uma linha da malha"),
        ("conferir", cmd_conferir, "as identidades do modelo"),
    ]:
        sub = subcomandos.add_parser(nome, help=ajuda)
        sub.set_defaults(funcao=funcao)
        if nome == "corte":
            sub.add_argument("linha", help="id da linha a cortar, por exemplo L16")

    args = analisador.parse_args(argv)
    _log(args.verboso)

    # Sem subcomando, roda o caminho completo: e o que alguem que acabou de
    # clonar o repo quer.
    funcao = getattr(args, "funcao", cmd_tudo)
    return funcao(args)


if __name__ == "__main__":
    sys.exit(main())
