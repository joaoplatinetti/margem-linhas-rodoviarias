"""
O contrato de entrada: o que o motor precisa saber sobre uma linha.

Ate aqui o modelo so consumia o proprio gerador, e por isso nunca precisou
declarar o que espera. Isso muda quando a malha vem de fora — de um BI, de uma
planilha, de outro projeto — e a pergunta "que colunas voce precisa?" passa a
ter que ter resposta escrita, e nao "leia o codigo".

**O contrato existe para uma falha especifica.** Coluna ausente que vira zero no
meio de uma divisao produz indicador plausivel e errado: um CASK que nao inclui
tripulacao e so um CASK menor, e nada na tela avisa. `validar` recusa antes,
nomeando a coluna e dizendo para que ela serve.

TRES GRUPOS DE COLUNA

- **Chaves** — definem o grao. Uma linha de dado por `linha_id` x `ano_mes`.
- **Aditivas** — as unicas que se somam. Todo indicador do modelo e razao entre
  duas delas, e e por isso que a lista e curta e fechada.
- **Descritivas** — opcionais. Nao entram em conta nenhuma; servem para rotular
  saida e para os recortes por classe e corredor.

ONDE ESTE REPOSITORIO PARA

Este projeto e publico e o dataset dele e sintetico **por escolha**. O contrato
existe para que uma malha real possa ser avaliada pelo mesmo motor — mas essa
avaliacao acontece FORA daqui. Nenhum dado de operacao real entra neste
repositorio, nem como exemplo, nem agregado, nem em teste. Ver
`docs/contrato-de-dados.md`.
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)


# grupo, unidade, para que serve
CONTRATO: dict[str, dict[str, str]] = {
    # --- chaves ------------------------------------------------------------
    "linha_id": {
        "grupo": "chave", "unidade": "texto",
        "serve_para": "identifica a linha; e a chave de todo recorte",
    },
    "ano_mes": {
        "grupo": "chave", "unidade": "AAAA-MM",
        "serve_para": "o mes do registro; define a janela de decisao",
    },
    # --- aditivas ----------------------------------------------------------
    "partidas": {
        "grupo": "aditiva", "unidade": "contagem",
        "serve_para": "base de rateio por partida e denominador da tripulacao",
    },
    "km_rodados": {
        "grupo": "aditiva", "unidade": "km",
        "serve_para": "base de rateio por km; km percorrido no mes",
    },
    "assentos_km": {
        "grupo": "aditiva", "unidade": "assento-km",
        "serve_para": "a oferta (ASK); denominador de RASK, CASK e load factor",
    },
    "passageiros": {
        "grupo": "aditiva", "unidade": "contagem",
        "serve_para": "denominador da tarifa media",
    },
    "passageiros_km": {
        "grupo": "aditiva", "unidade": "passageiro-km",
        "serve_para": "a demanda (RPK); numerador do load factor e do yield",
    },
    "receita": {
        "grupo": "aditiva", "unidade": "R$",
        "serve_para": "numerador de yield, RASK e margem",
    },
    "custo_variavel": {
        "grupo": "aditiva", "unidade": "R$",
        "serve_para": "a margem de contribuicao e o CASK variavel",
    },
    # --- descritivas -------------------------------------------------------
    "linha": {
        "grupo": "descritiva", "unidade": "texto",
        "serve_para": "nome legivel nas saidas; cai para o linha_id se faltar",
    },
    "km": {
        "grupo": "descritiva", "unidade": "km",
        "serve_para": "distancia da linha; permite derivar ASK e RPK",
    },
    "assentos": {
        "grupo": "descritiva", "unidade": "contagem",
        "serve_para": "capacidade por partida; permite derivar ASK",
    },
    "classe": {
        "grupo": "descritiva", "unidade": "texto",
        "serve_para": "recorte por tipo de servico",
    },
    "corredor": {
        "grupo": "descritiva", "unidade": "texto",
        "serve_para": "recorte geografico",
    },
}

CHAVES = [nome for nome, d in CONTRATO.items() if d["grupo"] == "chave"]
ADITIVAS = [nome for nome, d in CONTRATO.items() if d["grupo"] == "aditiva"]
DESCRITIVAS = [nome for nome, d in CONTRATO.items() if d["grupo"] == "descritiva"]
OBRIGATORIAS = CHAVES + ADITIVAS


def descrever() -> pd.DataFrame:
    """O contrato como tabela, para a documentacao e para `margem contrato`."""
    return pd.DataFrame(
        [{"coluna": nome, **detalhe} for nome, detalhe in CONTRATO.items()]
    )


def validar(fato: pd.DataFrame, exigir: list[str] | None = None) -> None:
    """Recusa o que produziria indicador plausivel e errado.

    Nao devolve nada: ou passa, ou estoura com a lista do que falta e para que
    cada coisa serve. Devolver um booleano convidaria a ignorar o resultado, que
    e exatamente o que nao pode acontecer aqui.
    """
    exigir = exigir or OBRIGATORIAS

    faltando = [nome for nome in exigir if nome not in fato.columns]
    if faltando:
        detalhe = "\n".join(
            f"  - {nome} ({CONTRATO[nome]['unidade']}): {CONTRATO[nome]['serve_para']}"
            for nome in faltando
        )
        raise ValueError(
            f"o fato nao cumpre o contrato — faltam {len(faltando)} coluna(s):\n"
            f"{detalhe}\n"
            "Use margem.dados.preparar() para traduzir de outro vocabulario, "
            "ou `margem contrato` para ver o contrato inteiro."
        )

    if fato.empty:
        raise ValueError("o fato esta vazio")

    duplicadas = fato.duplicated(subset=CHAVES)
    if duplicadas.any():
        exemplo = fato.loc[duplicadas, CHAVES].head(3).to_dict("records")
        raise ValueError(
            f"{int(duplicadas.sum())} registros duplicados no grao "
            f"{' x '.join(CHAVES)} — o motor soma o que recebe, entao duplicata "
            f"vira volume inventado. Exemplos: {exemplo}"
        )

    negativas = [
        nome for nome in ADITIVAS
        if nome in fato.columns and (fato[nome] < 0).any()
    ]
    if negativas:
        raise ValueError(
            f"valores negativos em coluna aditiva: {', '.join(negativas)}. "
            "Estorno e devolucao entram como reducao da soma, nao como linha "
            "negativa no fato."
        )


def preparar(fato: pd.DataFrame, mapa: dict[str, str] | None = None,
             derivar: bool = True) -> pd.DataFrame:
    """Traduz de um vocabulario externo para o contrato e valida.

    `mapa` vai de nome de origem para nome do contrato — `{"id_linha":
    "linha_id"}`. E a peca que permite ligar uma malha de outro sistema sem
    renomear coluna na mao a cada rodada.

    `derivar` calcula o que da para calcular a partir do que veio: assento-km de
    `assentos x km x partidas`, passageiro-km de `passageiros x km`. O que for
    derivado fica registrado em `.attrs["derivadas"]` — numero calculado aqui
    nao pode se confundir com numero que veio da fonte, porque os dois tem
    confiabilidade diferente.
    """
    saida = fato.rename(columns=mapa or {}).copy()
    derivadas = []

    if derivar:
        if "assentos_km" not in saida.columns and {
            "assentos", "km", "partidas"
        } <= set(saida.columns):
            saida["assentos_km"] = saida["assentos"] * saida["km"] * saida["partidas"]
            derivadas.append("assentos_km")

        if "km_rodados" not in saida.columns and {"km", "partidas"} <= set(saida.columns):
            saida["km_rodados"] = saida["km"] * saida["partidas"]
            derivadas.append("km_rodados")

        if "passageiros_km" not in saida.columns and {
            "passageiros", "km"
        } <= set(saida.columns):
            # Supoe que todo passageiro viaja o trecho inteiro — a mesma
            # simplificacao declarada do modelo sintetico. Malha com secao
            # intermediaria tem que trazer passageiro-km medido, e nao derivado.
            saida["passageiros_km"] = saida["passageiros"] * saida["km"]
            derivadas.append("passageiros_km")

        if "linha" not in saida.columns and "linha_id" in saida.columns:
            saida["linha"] = saida["linha_id"].astype(str)
            derivadas.append("linha")

    validar(saida)
    saida.attrs["derivadas"] = derivadas
    if derivadas:
        log.info("colunas derivadas do que veio: %s", ", ".join(derivadas))
    return saida
