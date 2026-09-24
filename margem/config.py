"""
Todas as premissas do modelo, num arquivo so.

A regra e a mesma que vale para qualquer modelo de custo que alguem vai
questionar em reuniao: **se um numero influencia um indicador, ele mora aqui** e
nao dentro da funcao que o usa. Assim da para auditar a margem lendo um arquivo,
e da para mudar o preco do diesel sem procurar constante espalhada pelo codigo.

Duas coisas que este arquivo declara de proposito:

- **A base de cada componente de custo** (`km`, `partida`). Custo por km e custo
  por partida nao se somam antes de saber quantos km e quantas partidas existem
  no mes, e confundir as duas bases e o erro que mais estraga um CASK.
- **O que e variavel e o que e fixo.** So o variavel entra na margem de
  contribuicao. Ratear garagem e administracao no grao da linha produz um
  "lucro por linha" que nao se sustenta e leva a cortar linha que contribui de
  sobra para o fixo — que ia continuar existindo depois do corte.

Os numeros sao FICTICIOS, calibrados para ficarem na ordem de grandeza do setor.
Nada aqui vem de sistema, planilha ou base de empresa nenhuma.
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "saida"
SAIDA_POWERBI = SAIDA / "powerbi"
SAIDA_IMAGENS = SAIDA / "imagens"
EXCEL = SAIDA / "margem-linhas-rodoviarias.xlsx"

# ---------------------------------------------------------------------------
# Periodo e reprodutibilidade
# ---------------------------------------------------------------------------

# 24 meses fechados. Duas passagens pela sazonalidade: sem isso, "julho e alto"
# e anedota, e nenhuma medida ano-a-ano em DAX tem contra o que comparar.
PERIODO_INICIO = "2024-10"
PERIODO_FIM = "2026-09"

# Seed fixa. O dataset e sintetico, mas tem que ser o MESMO em toda rodada:
# numero de portfolio que muda a cada execucao nao pode ser conferido por quem
# le o repo, e os testes nao teriam o que fixar.
SEED = 20260924

# Janela usada para decidir manter/ajustar/rever: os 12 ultimos meses somados.
# Nunca o mes isolado — ver `indicadores.classificar`.
JANELA_DECISAO_MESES = 12

# ---------------------------------------------------------------------------
# Capacidade e oferta
# ---------------------------------------------------------------------------

# Assentos por classe de servico. Leito tem menos da metade dos assentos de um
# convencional: e o fato que faz o mesmo onibus, na mesma estrada, precisar de
# quase o dobro de tarifa para fechar a conta.
ASSENTOS_POR_CLASSE: dict[str, int] = {
    "CONVENCIONAL": 46,
    "EXECUTIVO": 44,
    "SEMILEITO": 42,
    "LEITO": 26,
}

# Teto de ocupacao. Nenhuma linha vende 100% do mes: sobra assento no horario
# ruim, no sentido vazio e no dia de semana. Sem esse teto, o pico de julho gera
# load factor acima de 1 e o dataset se entrega como falso na primeira conferida.
OCUPACAO_MAXIMA = 0.96

# Velocidade comercial media, com paradas. Serve para estimar a duracao da
# viagem, que e o que dimensiona a tripulacao.
VELOCIDADE_COMERCIAL_KMH = 60.0

# ---------------------------------------------------------------------------
# Demanda: sazonalidade
# ---------------------------------------------------------------------------

# Indice sazonal por mes do ano, base 1,0. Ferias escolares (janeiro e julho) e
# dezembro no topo; marco e maio no fundo, que e o vale classico do rodoviario.
# A media dos doze fica proxima de 1 de proposito: o indice redistribui a
# demanda no ano, nao cria demanda.
SAZONALIDADE_MENSAL: dict[int, float] = {
    1: 1.18,   # ferias de janeiro
    2: 0.93,   # volta as aulas + carnaval encurtando o mes util
    3: 0.87,   # o fundo do ano
    4: 0.95,   # feriados de abril
    5: 0.88,
    6: 0.96,   # festas juninas no Nordeste
    7: 1.22,   # ferias de julho, o pico
    8: 0.91,
    9: 0.94,
    10: 0.99,
    11: 1.02,  # feriados e Black Friday
    12: 1.15,  # festas de fim de ano
}

# Tendencia anual da demanda da rede (1,03 = +3% ao ano). Aplicada de forma
# composta sobre os meses, para a serie nao ser estacionaria — serie sem
# tendencia nenhuma tambem tem cara de dado gerado.
TENDENCIA_ANUAL = 1.03

# Desvio-padrao do ruido multiplicativo mensal (lognormal). 6% e o bastante para
# a serie parecer viva sem virar serrote.
RUIDO_DEMANDA = 0.06

# ---------------------------------------------------------------------------
# Tarifa
# ---------------------------------------------------------------------------

# Tarifa de referencia em R$ por passageiro-km, por classe.
TARIFA_KM_POR_CLASSE: dict[str, float] = {
    "CONVENCIONAL": 0.175,
    "EXECUTIVO": 0.205,
    "SEMILEITO": 0.250,
    "LEITO": 0.400,
}

# Decaimento da tarifa por km com a distancia: R$/km cai conforme a viagem
# cresce, porque os custos de terminal, embarque e venda se diluem. Modelado
# como (500 / km) ^ 0.18, ancorado numa viagem de 500 km.
TARIFA_KM_ANCORA = 500.0
TARIFA_DECAIMENTO_DISTANCIA = 0.18

# A tarifa media realizada acompanha o mix: no pico sobra menos promocional e
# ela sobe; no vale, o inverso. Elasticidade da tarifa ao indice sazonal —
# 0,35 significa que um mes 20% acima da media roda com tarifa ~7% acima.
TARIFA_SENSIBILIDADE_SAZONAL = 0.35

# Ruido da tarifa media mensal. Menor que o da demanda: tarifa media de um mes
# inteiro e uma media de milhares de bilhetes e nao pula.
RUIDO_TARIFA = 0.02

# ---------------------------------------------------------------------------
# Custo variavel
# ---------------------------------------------------------------------------

DIESEL_LITRO = 6.15

# Consumo em km/l por classe. Leito e mais pesado e anda com ar-condicionado
# mais exigente, entao gasta mais por km do que o convencional.
CONSUMO_KM_LITRO: dict[str, float] = {
    "CONVENCIONAL": 3.00,
    "EXECUTIVO": 2.90,
    "SEMILEITO": 2.75,
    "LEITO": 2.55,
}

# R$/km, independentes de classe.
PNEUS_KM = 0.26        # jogo completo dividido pela vida util
MANUTENCAO_KM = 0.58   # preventiva + corretiva + lubrificantes

# Tripulacao, por PARTIDA (nao por km): o que dimensiona e a duracao da viagem
# e quantos motoristas embarcam.
CUSTO_HORA_TRIPULANTE = 31.00   # salario + encargos, por hora de jornada
DIARIA_TRIPULANTE = 58.00       # alimentacao em viagem, por tripulante
PERNOITE_TRIPULANTE = 120.00    # hospedagem no destino, por tripulante
PERNOITE_ACIMA_DE_HORAS = 10.0  # acima disso a escala exige repouso fora da base

# Dupla de motoristas acima desta distancia. Simplificacao declarada: a regra
# real e de jornada e de tempo de direcao continua, nao de quilometragem.
SEGUNDO_MOTORISTA_ACIMA_KM = 600.0

# Corredores: pedagio por km e agressividade da via sobre a manutencao. Pedagio
# entra como custo por km porque e praticamente proporcional a distancia dentro
# de um mesmo corredor, e e o componente que mais diferencia Sudeste de Norte.
CORREDORES: dict[str, dict[str, float]] = {
    "SUDESTE":      {"pedagio_km": 0.225, "fator_manutencao": 1.00},
    "SUL":          {"pedagio_km": 0.185, "fator_manutencao": 1.00},
    "CENTRO_OESTE": {"pedagio_km": 0.090, "fator_manutencao": 1.10},
    "NORDESTE":     {"pedagio_km": 0.055, "fator_manutencao": 1.15},
    "NORTE":        {"pedagio_km": 0.010, "fator_manutencao": 1.30},
}

# ---------------------------------------------------------------------------
# Custo fixo
# ---------------------------------------------------------------------------

# Blocos de custo fixo MENSAL da empresa, em R$. Nao dependem de quantos km a
# frota rodou no mes — e justamente por isso ficam fora da margem de
# contribuicao e entram so no custo cheio.
CUSTO_FIXO_MENSAL: dict[str, float] = {
    "garagem_e_predios": 245_000.0,
    "administracao_e_vendas": 430_000.0,
    "depreciacao_e_seguros": 315_000.0,
}

# Bases de rateio disponiveis, e a coluna do fato que serve de dirigente em cada
# uma. O rateio e sempre `total_do_mes x (dirigente_da_linha / dirigente_do_mes)`,
# entao a soma fecha com o total declarado em qualquer uma delas.
#
# A escolha da base NAO e detalhe contabil: cada uma penaliza sistematicamente um
# arquetipo de linha, e isso e demonstravel na algebra, nao so na simulacao.
# `margem/malha.py` compara as quatro e mede quantas linhas trocam de decisao.
BASES_RATEIO: dict[str, str] = {
    "km": "km_rodados",
    "partida": "partidas",
    "assento_km": "assentos_km",
    "receita": "receita",
}

# A base em vigor. `km` segue a intensidade de uso de frota e oficina, e e a
# menos ruim para um rateio que vai ser olhado linha a linha — mas continua sendo
# convencao, e trocar ela muda a lista de linhas a cortar.
BASE_RATEIO_FIXO = "km"


def fixo_mensal_total() -> float:
    """O bloco fixo declarado, somado. Usado no rateio e nos testes de fecho."""
    return sum(CUSTO_FIXO_MENSAL.values())

# ---------------------------------------------------------------------------
# Catalogo de componentes: o que cada um e e onde entra
# ---------------------------------------------------------------------------

# Ordem, grupo e base de cada componente. A coluna `entra_na_mc` e o que o
# codigo consulta para montar a margem de contribuicao — nao existe lista de
# componentes variaveis escrita duas vezes.
COMPONENTES: list[dict[str, object]] = [
    {"componente": "custo_combustivel", "rotulo": "Combustivel", "grupo": "variavel",
     "base": "km", "entra_na_mc": True,
     "premissa": f"diesel R$ {DIESEL_LITRO:.2f}/l / consumo km/l da classe"},
    {"componente": "custo_pneus", "rotulo": "Pneus", "grupo": "variavel",
     "base": "km", "entra_na_mc": True,
     "premissa": f"R$ {PNEUS_KM:.2f}/km (jogo / vida util)"},
    {"componente": "custo_manutencao", "rotulo": "Manutencao", "grupo": "variavel",
     "base": "km", "entra_na_mc": True,
     "premissa": f"R$ {MANUTENCAO_KM:.2f}/km x fator do corredor"},
    {"componente": "custo_tripulacao", "rotulo": "Tripulacao", "grupo": "variavel",
     "base": "partida", "entra_na_mc": True,
     "premissa": f"R$ {CUSTO_HORA_TRIPULANTE:.2f}/h x duracao x motoristas + diaria + pernoite"},
    {"componente": "custo_pedagio", "rotulo": "Pedagio", "grupo": "variavel",
     "base": "km", "entra_na_mc": True,
     "premissa": "R$/km do corredor"},
    {"componente": "custo_fixo_rateado", "rotulo": "Fixo rateado", "grupo": "fixo",
     "base": "rateio por km", "entra_na_mc": False,
     "premissa": f"R$ {sum(CUSTO_FIXO_MENSAL.values()):,.0f}/mes rateados pelos km do mes"
                 .replace(",", ".")},
]

# Os componentes que entram na margem de contribuicao, derivados do catalogo.
COMPONENTES_VARIAVEIS: list[str] = [
    c["componente"] for c in COMPONENTES if c["entra_na_mc"]
]
COMPONENTES_FIXOS: list[str] = [
    c["componente"] for c in COMPONENTES if not c["entra_na_mc"]
]
COMPONENTES_TODOS: list[str] = COMPONENTES_VARIAVEIS + COMPONENTES_FIXOS

# ---------------------------------------------------------------------------
# Classificacao
# ---------------------------------------------------------------------------

CLASSIFICACOES = ("MANTER", "AJUSTAR", "REVER")

# Faixa de folga, em R$ por ASSENTO-KM, para marcar uma linha como "no limite".
# Um centavo por assento-km: nessa faixa, a linha cobre o custo cheio, mas uma
# alta de diesel de 10% ja a derruba para AJUSTAR. Tratar essa linha como igual
# a uma de spread confortavel esconde risco. A unidade importa — spread por
# assento-km se mede em centavos, nao em reais: um limiar de R$ 0,15 marcaria a
# rede inteira como "no limite".
SPREAD_NO_LIMITE = 0.010
