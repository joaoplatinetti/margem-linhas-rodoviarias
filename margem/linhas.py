"""
O catalogo das 20 linhas: cidades reais, numeros ficticios.

As cidades e as distancias sao reais porque e o que torna o exercicio legivel —
quem conhece o setor sabe na hora que Goiania-Brasilia e uma linha curta de alta
frequencia e que Campo Grande-Sao Paulo e um leito noturno. Tudo o mais
(frequencia, ocupacao, tarifa) e inventado.

Tres campos merecem explicacao, porque sao eles que dao vida ao dataset:

- **`ocupacao_base`** e o load factor medio da linha num mes de indice sazonal 1.
  Nao e o load factor realizado: o gerador aplica sazonalidade, tendencia e
  ruido em cima, e depois corta no teto de `config.OCUPACAO_MAXIMA`.
- **`fator_tarifa`** e pressao competitiva, o unico lugar onde "concorrencia"
  entra no modelo. 0,92 em Sao Paulo-Rio e a aerea de baixo custo e a ponte
  aerea comendo a tarifa; 1,02 em Sao Paulo-Foz e rota turistica com pouca
  alternativa direta.
- **`amplitude_sazonal`** e o expoente aplicado ao indice mensal. Linha
  corporativa achata a sazonalidade (0,4: Brasilia nao esvazia em maio),
  linha de lazer exagera (1,6: Foz do Iguacu vive de ferias). Sazonalidade
  identica nas 20 linhas e a assinatura mais obvia de dado inventado — vale a
  pena o campo extra para nao cair nisso.

`corredor` e o corredor PREDOMINANTE da rota, nao o unico: Campo Grande-Sao Paulo
termina em rodovia paulista pedagiada, mas a maior parte do percurso e
Centro-Oeste, e e isso que o custo por km reflete.
"""
from __future__ import annotations

import pandas as pd

from margem import config

# origem, uf, destino, uf, km, corredor, classe, freq/semana, ocupacao base,
# fator de tarifa, amplitude sazonal, perfil de demanda
_CATALOGO: list[tuple] = [
    ("Goiania",      "GO", "Brasilia",        "DF",  209, "CENTRO_OESTE", "EXECUTIVO",    42, 0.72, 0.95, 0.4, "CORPORATIVO"),
    ("Recife",       "PE", "Maceio",          "AL",  258, "NORDESTE",     "CONVENCIONAL", 28, 0.70, 1.00, 0.8, "MISTO"),
    ("Curitiba",     "PR", "Florianopolis",   "SC",  300, "SUL",          "EXECUTIVO",    21, 0.68, 1.02, 1.3, "LAZER"),
    ("Salvador",     "BA", "Aracaju",         "SE",  356, "NORDESTE",     "EXECUTIVO",    21, 0.66, 0.98, 1.0, "MISTO"),
    ("Sao Paulo",    "SP", "Curitiba",        "PR",  408, "SUDESTE",      "SEMILEITO",    35, 0.71, 1.00, 0.7, "MISTO"),
    ("Sao Paulo",    "SP", "Rio de Janeiro",  "RJ",  429, "SUDESTE",      "EXECUTIVO",    49, 0.74, 0.92, 0.6, "CORPORATIVO"),
    ("Belo Horizonte", "MG", "Rio de Janeiro", "RJ", 434, "SUDESTE",      "SEMILEITO",    28, 0.64, 0.95, 0.9, "MISTO"),
    ("Porto Alegre", "RS", "Florianopolis",   "SC",  476, "SUL",          "SEMILEITO",    21, 0.67, 1.00, 1.2, "LAZER"),
    ("Vitoria",      "ES", "Rio de Janeiro",  "RJ",  521, "SUDESTE",      "EXECUTIVO",    21, 0.62, 0.96, 0.9, "MISTO"),
    ("Natal",        "RN", "Fortaleza",       "CE",  537, "NORDESTE",     "CONVENCIONAL", 14, 0.66, 1.00, 1.1, "LAZER"),
    ("Sao Paulo",    "SP", "Belo Horizonte",  "MG",  586, "SUDESTE",      "SEMILEITO",    35, 0.70, 0.97, 0.7, "MISTO"),
    ("Uberlandia",   "MG", "Sao Paulo",       "SP",  588, "SUDESTE",      "EXECUTIVO",    28, 0.68, 0.98, 0.6, "CORPORATIVO"),
    ("Fortaleza",    "CE", "Teresina",        "PI",  588, "NORDESTE",     "CONVENCIONAL", 14, 0.50, 0.92, 0.9, "MISTO"),
    ("Campo Grande", "MS", "Cuiaba",          "MT",  694, "CENTRO_OESTE", "SEMILEITO",    14, 0.60, 0.98, 0.8, "MISTO"),
    ("Brasilia",     "DF", "Belo Horizonte",  "MG",  716, "CENTRO_OESTE", "SEMILEITO",    14, 0.58, 0.95, 0.8, "MISTO"),
    ("Manaus",       "AM", "Boa Vista",       "RR",  785, "NORTE",        "CONVENCIONAL",  7, 0.60, 0.92, 0.7, "MISTO"),
    ("Belem",        "PA", "Sao Luis",        "MA",  806, "NORTE",        "SEMILEITO",     7, 0.55, 0.95, 0.9, "MISTO"),
    ("Cuiaba",       "MT", "Goiania",         "GO",  934, "CENTRO_OESTE", "SEMILEITO",     7, 0.57, 0.96, 0.8, "MISTO"),
    ("Campo Grande", "MS", "Sao Paulo",       "SP", 1014, "CENTRO_OESTE", "LEITO",        14, 0.63, 1.00, 0.9, "MISTO"),
    ("Sao Paulo",    "SP", "Foz do Iguacu",   "PR", 1030, "SUL",          "LEITO",         7, 0.58, 1.02, 1.6, "LAZER"),
]

COLUNAS = [
    "origem", "uf_origem", "destino", "uf_destino", "km", "corredor", "classe",
    "frequencia_semanal", "ocupacao_base", "fator_tarifa", "amplitude_sazonal",
    "perfil",
]


def catalogo() -> pd.DataFrame:
    """As 20 linhas, com os campos derivados que todo o resto usa.

    Derivados aqui e nao repetidos adiante: assentos (vem da classe), duracao e
    numero de tripulantes (vem do km) e o nome legivel da linha. Qualquer um
    deles calculado duas vezes em modulos diferentes viraria divergencia na
    primeira mudanca de premissa.
    """
    df = pd.DataFrame(_CATALOGO, columns=COLUNAS)

    # Id estavel e ordenado por distancia de catalogo. Estavel importa: e a
    # chave que o Power BI usa para ligar dimensao e fato.
    df.insert(0, "linha_id", [f"L{i:02d}" for i in range(1, len(df) + 1)])
    df["linha"] = df["origem"] + " " + df["uf_origem"] + " - " + df["destino"] + " " + df["uf_destino"]

    df["assentos"] = df["classe"].map(config.ASSENTOS_POR_CLASSE)
    df["duracao_horas"] = (df["km"] / config.VELOCIDADE_COMERCIAL_KMH).round(2)
    df["tripulantes"] = (df["km"] > config.SEGUNDO_MOTORISTA_ACIMA_KM).map({True: 2, False: 1})

    faltando = df["assentos"].isna()
    if faltando.any():
        raise ValueError(
            "Classe fora de config.ASSENTOS_POR_CLASSE: "
            f"{sorted(df.loc[faltando, 'classe'].unique())}"
        )
    desconhecidos = set(df["corredor"]) - set(config.CORREDORES)
    if desconhecidos:
        raise ValueError(f"Corredor fora de config.CORREDORES: {sorted(desconhecidos)}")

    return df


def tarifa_km_referencia(df: pd.DataFrame) -> pd.Series:
    """R$ por passageiro-km de referencia de cada linha.

    Duas forcas, as duas declaradas em `config`:

    1. **Classe** — leito custa mais por km porque tem 26 assentos no lugar de 46.
    2. **Distancia** — R$/km CAI conforme a viagem cresce, porque o custo de
       terminal, embarque e venda se dilui num percurso maior. Sem esse
       decaimento, uma linha de 200 km sairia com a mesma tarifa por km de um
       leito de 1.000 km, e a de 200 km pareceria injustificadamente pobre.

    Depois vem `fator_tarifa`, que e pressao competitiva linha a linha.
    """
    base = df["classe"].map(config.TARIFA_KM_POR_CLASSE)
    decaimento = (config.TARIFA_KM_ANCORA / df["km"]) ** config.TARIFA_DECAIMENTO_DISTANCIA
    return base * decaimento * df["fator_tarifa"]
