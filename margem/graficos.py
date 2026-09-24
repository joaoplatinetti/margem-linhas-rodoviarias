"""
As tres imagens do artigo: matriz de decisao, esquema estrela e LF de equilibrio.

PNG a 200 dpi para publicar e SVG para quem for reeditar. Nada aqui recalcula
indicador: as tres figuras consomem o que `indicadores.py` produziu, porque
grafico que refaz a propria conta e grafico que um dia discorda da planilha.

DECISOES DE VISUALIZACAO, que sao escolhas tecnicas e nao gosto:

- **A paleta das classes e azul / amarelo / vermelho, e nao verde / amarelo /
  vermelho.** O semaforo obvio falha em daltonismo: medido em OKLab, o par
  verde-vermelho do semaforo fica a Delta E 4,1 sob deuteranopia — praticamente a
  mesma cor para ~8% dos leitores homens. O trio adotado mede Delta E 19,8 no
  pior par. O vermelho continua sendo vermelho (REVER le como ruim), e quem
  perde a distincao verde/vermelho ainda separa azul de vermelho.
- **Cada regiao tambem carrega rotulo escrito.** Cor nunca e o unico canal: a
  regiao tem nome, contagem e participacao na receita impressos dentro dela.
- **A matriz desenha a REGRA, nao uma correlacao.** Os eixos sao MC % e folga de
  ocupacao, os dois testes da classificacao, e as linhas de zero sao os dois
  cortes de verdade. A alternativa tentadora — yield x load factor com uma
  fronteira de equilibrio desenhada — exigiria uma fronteira unica para a rede,
  e o CASK varia de R$ 0,10 a R$ 0,23 por assento-km entre um convencional e um
  leito: a curva contradiria a cor de varios pontos. Fronteira aproximada num
  grafico que decide corte de linha e pior que fronteira nenhuma.
- **Nenhum numero em todos os pontos.** Rotulo so nas linhas que exigem decisao
  e nas que passam raspando. A tabela inteira esta no Excel e no CSV.

Um limite conhecido do SVG: `svg.fonttype = "none"` mantem o texto editavel, mas
rotulo com contorno na cor da superficie (`withStroke`) e rasterizado para
caminho vetorial pelo matplotlib e deixa de ser texto. Sao os rotulos dos pontos
e das regioes, que precisam do contorno para continuarem legiveis sobre a
hachura e sobre os washes. Titulo, eixos e marcacoes seguem editaveis.
"""
from __future__ import annotations

import logging

import matplotlib
import pandas as pd

matplotlib.use("Agg")   # sem display: e geracao de arquivo, nao janela

import matplotlib.patheffects as efeitos
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

from margem import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paleta (instancia clara; os valores vem de uma paleta validada)
# ---------------------------------------------------------------------------

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_FRACA = "#898781"
GRADE = "#e1e0d9"
EIXO = "#c3c2b7"

AZUL = "#2a78d6"
AMARELO = "#eda100"
VERMELHO = "#d03b3b"
AZUL_CLARO = "#cde2fb"

COR_CLASSE = {"MANTER": AZUL, "AJUSTAR": AMARELO, "REVER": VERMELHO}
MARCA_CLASSE = {"MANTER": "o", "AJUSTAR": "s", "REVER": "D"}

FONTES = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]


def _estilo() -> None:
    """Tipografia e cromo sobrios, aplicados uma vez por figura."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": FONTES,
        "figure.facecolor": SUPERFICIE,
        "axes.facecolor": SUPERFICIE,
        "savefig.facecolor": SUPERFICIE,
        "text.color": TINTA,
        "axes.labelcolor": TINTA_2,
        "axes.edgecolor": EIXO,
        "xtick.color": TINTA_FRACA,
        "ytick.color": TINTA_FRACA,
        "axes.linewidth": 0.8,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "axes.labelsize": 10,
        "legend.frameon": False,
        "svg.fonttype": "none",   # texto editavel no SVG, nao curva
    })


def _pct(valor: float, casas: int = 1) -> str:
    return f"{valor * 100:.{casas}f}".replace(".", ",") + "%"


def _pp(valor: float, casas: int = 1) -> str:
    """Pontos percentuais, com sinal explicito."""
    return f"{valor * 100:+.{casas}f}".replace(".", ",") + " p.p."


def _gravar(fig: plt.Figure, nome: str) -> list[str]:
    """Grava PNG (publicar) e SVG (reeditar). Devolve os caminhos."""
    destino = config.SAIDA_IMAGENS
    destino.mkdir(parents=True, exist_ok=True)

    caminhos = []
    for extensao, dpi in (("png", 200), ("svg", None)):
        caminho = destino / f"{nome}.{extensao}"
        fig.savefig(caminho, dpi=dpi, bbox_inches="tight", pad_inches=0.25)
        caminhos.append(str(caminho))
    plt.close(fig)
    log.info("%-26s -> %s.png + .svg", nome, nome)
    return caminhos


def _rodape(fig: plt.Figure, texto: str) -> None:
    fig.text(0.0, -0.02, texto, fontsize=7.5, color=TINTA_FRACA, va="top", ha="left")


# ---------------------------------------------------------------------------
# 1. Matriz de decisao
# ---------------------------------------------------------------------------

def matriz_decisao(janela: pd.DataFrame) -> list[str]:
    """A regra de classificacao desenhada, com as 20 linhas dentro dela.

    Eixo x: MC % — a linha cobre o custo variavel?
    Eixo y: folga de ocupacao em pontos percentuais — a linha cobre o custo cheio?

    O quadrante superior esquerdo fica vazio **por construcao**, e isso e
    informacao: nao existe linha que cubra o custo cheio sem cobrir o variavel.
    A escada tem dois degraus e eles estao na mesma ordem para todas as linhas.
    """
    _estilo()
    fig, ax = plt.subplots(figsize=(10.5, 7.2))

    x = janela["margem_contribuicao_pct"]
    y = janela["folga_lf"]

    limite_x = (min(-0.09, x.min() - 0.04), max(x.max() + 0.08, 0.58))
    limite_y = (min(-0.26, y.min() - 0.055), y.max() + 0.10)

    # --- as quatro regioes da regra ---------------------------------------
    # Wash de 8%: a cor diz qual decisao, sem competir com os pontos.
    regioes = [
        # (x0, x1, y0, y1, cor, titulo)
        (0, limite_x[1], 0, limite_y[1], AZUL, "MANTER"),
        (0, limite_x[1], limite_y[0], 0, AMARELO, "AJUSTAR"),
        (limite_x[0], 0, limite_y[0], 0, VERMELHO, "REVER"),
    ]
    for x0, x1, y0, y1, cor, titulo in regioes:
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=cor,
                               alpha=0.08, edgecolor="none", zorder=0))
        quantidade = int((janela["classificacao"] == titulo).sum())
        receita = janela.loc[janela["classificacao"] == titulo, "receita"].sum()
        parcela = receita / janela["receita"].sum()

        # Os rotulos ficam ancorados nos CANTOS DOS EIXOS (fracao, nao dado):
        # assim nunca disputam espaco com um ponto quando os limites mudam.
        # Uma linha por regiao, ancorada no canto dos eixos (fracao, nao dado).
        # O criterio de cada regiao NAO se repete aqui: os dois rotulos de eixo
        # ja enunciam os dois testes ("cobre o custo variavel?" e "cobre o custo
        # cheio?"), e o bloco de tres linhas que estava aqui antes brigava por
        # espaco com o rotulo de Manaus-Boa Vista, no canto da propria regiao.
        cantos = {
            "MANTER": (0.99, 0.985, "right", "top"),
            "AJUSTAR": (0.99, 0.015, "right", "bottom"),
            "REVER": (0.015, 0.015, "left", "bottom"),
        }
        frac_x, frac_y, horizontal, vertical = cantos[titulo]
        marca = ax.text(
            frac_x, frac_y,
            f"{titulo}  ·  {quantidade} linhas  ·  {_pct(parcela, 0)} da receita",
            transform=ax.transAxes, fontsize=11.5, fontweight="bold", color=cor,
            ha=horizontal, va=vertical, zorder=2,
        )
        marca.set_path_effects([efeitos.withStroke(linewidth=3.2, foreground=SUPERFICIE)])

    # O quadrante impossivel. Deixar o espaco em branco e sinalizar por que ele
    # esta vazio vale mais do que cortar o eixo e esconder a assimetria.
    plt.rcParams["hatch.linewidth"] = 0.6
    ax.add_patch(Rectangle((limite_x[0], 0), -limite_x[0], limite_y[1],
                           facecolor="none", edgecolor=GRADE,
                           zorder=0, hatch="//", linewidth=0))
    marca = ax.text(0.015, 0.985, "IMPOSSIVEL", transform=ax.transAxes,
                    fontsize=10, fontweight="bold", color=TINTA_FRACA,
                    ha="left", va="top", zorder=2)
    nota = ax.text(0.015, 0.94,
                   "cobrir o custo cheio sem cobrir\no variavel nao existe:\n"
                   "o fixo entra depois",
                   transform=ax.transAxes, fontsize=8.5, color=TINTA_FRACA,
                   ha="left", va="top", zorder=2, linespacing=1.7)
    for elemento in (marca, nota):
        elemento.set_path_effects([efeitos.withStroke(linewidth=3.4,
                                                      foreground=SUPERFICIE)])

    # --- os dois cortes ---------------------------------------------------
    for eixo_zero in (ax.axvline, ax.axhline):
        eixo_zero(0, color=EIXO, linewidth=1.0, zorder=1)

    # --- as linhas --------------------------------------------------------
    # Ponto em tinta escura: a cor da regiao ja diz a decisao, e repetir a
    # informacao na cor do ponto gastaria o unico canal livre sem acrescentar
    # nada. O anel na cor da superficie mantem os pontos legiveis onde se
    # aproximam.
    ax.scatter(x, y, s=64, facecolor=TINTA, edgecolor=SUPERFICIE,
               linewidth=1.6, zorder=4)

    # Rotulo seletivo: so quem exige decisao e quem passa raspando. O ponto de
    # maior folga nao ganha rotulo — ele nao decide nada e o rotulo dele disputava
    # espaco com o bloco do MANTER.
    rotular = janela[
        (janela["classificacao"] != "MANTER") | (janela["no_limite"])
    ].sort_values("folga_lf", ascending=False)

    # Afastamento vertical minimo entre rotulos, em unidade de dado. Dois pontos
    # proximos (Belem-Sao Luis e Cuiaba-Goiania ficam a 0,4 p.p. um do outro)
    # escreveriam um por cima do outro; empilhar sem mais nada descolaria o texto
    # do ponto, entao o que se afasta ganha uma linha de chamada.
    espacamento = (limite_y[1] - limite_y[0]) * 0.042
    ultimo_y: float | None = None

    for registro in rotular.itertuples(index=False):
        destino_y = registro.folga_lf
        if ultimo_y is not None and abs(destino_y - ultimo_y) < espacamento:
            destino_y = ultimo_y - espacamento
        ultimo_y = destino_y

        recuo = 0.009
        if destino_y != registro.folga_lf:
            ax.plot([registro.margem_contribuicao_pct + 0.002,
                     registro.margem_contribuicao_pct + recuo],
                    [registro.folga_lf, destino_y],
                    color=TINTA_FRACA, linewidth=0.7, zorder=4)

        texto = ax.text(
            registro.margem_contribuicao_pct + recuo, destino_y,
            f"{registro.linha}  ({_pp(registro.folga_lf)})",
            fontsize=8.2, color=TINTA, ha="left", va="center", zorder=5,
        )
        texto.set_path_effects([efeitos.withStroke(linewidth=2.6, foreground=SUPERFICIE)])

    # --- cromo ------------------------------------------------------------
    ax.set_xlim(limite_x)
    ax.set_ylim(limite_y)
    ax.xaxis.set_major_formatter(lambda v, _: _pct(v, 0))
    # "+0" nao existe: o zero e o corte, e escreve-se zero.
    ax.yaxis.set_major_formatter(
        lambda v, _: "0" if abs(v) < 1e-9 else f"{v * 100:+.0f}")
    ax.set_xlabel("Margem de contribuicao (% da receita)   —   cobre o custo variavel?")
    ax.set_ylabel("Folga de ocupacao (p.p.)   —   cobre o custo cheio?")
    ax.grid(axis="both", color=GRADE, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)

    meses = janela.attrs.get("meses") or []
    periodo = f"{meses[0]} a {meses[-1]}" if meses else ""
    ax.set_title("Matriz de decisao por linha", fontsize=15, fontweight="bold",
                 color=TINTA, loc="left", pad=22)
    ax.text(0, 1.015, f"20 linhas interestaduais · janela de 12 meses ({periodo}) · "
                      "dados sinteticos",
            transform=ax.transAxes, fontsize=9.5, color=TINTA_2, va="bottom")

    _rodape(fig, "Folga de ocupacao = load factor realizado - load factor de equilibrio "
                 "(CASK total / yield). MC % = (receita - custo variavel) / receita.\n"
                 "A regra e uma escada de dois degraus: o teste do custo variavel vem "
                 "primeiro, senao a linha grave se esconderia dentro do caso administravel.")
    return _gravar(fig, "matriz-decisao")


# ---------------------------------------------------------------------------
# 2. Diagrama do esquema estrela
# ---------------------------------------------------------------------------

def diagrama_estrela() -> list[str]:
    """O modelo do Power BI: tres dimensoes, tres fatos, e o que cada um guarda.

    O diagrama existe para mostrar UMA coisa: os fatos so levam coluna aditiva.
    Por isso cada caixa de fato lista as suas medidas e traz, embaixo, o aviso de
    que razao nao mora ali. Diagrama de modelagem que so desenha os retangulos e
    as setas nao ensina nada que o nome dos arquivos ja nao dissesse.
    """
    _estilo()
    fig, ax = plt.subplots(figsize=(11.5, 7.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(8, 78)
    ax.axis("off")

    def caixa(x, y, largura, altura, titulo, linhas_texto, *, fato: bool,
              nota: str = "") -> tuple[float, float]:
        cor = AZUL if fato else TINTA_2
        fundo = AZUL_CLARO if fato else "#f1f0ec"
        ax.add_patch(FancyBboxPatch(
            (x, y), largura, altura, boxstyle="round,pad=0.35,rounding_size=1.2",
            facecolor=fundo, edgecolor=cor, linewidth=1.3 if fato else 1.0, zorder=3,
        ))
        ax.text(x + 1.4, y + altura - 2.2, titulo, fontsize=10,
                fontweight="bold", color=cor, va="top", zorder=4)
        ax.text(x + 1.4, y + altura - 5.0, "\n".join(linhas_texto), fontsize=7.6,
                color=TINTA_2, va="top", zorder=4, linespacing=1.55)
        if nota:
            ax.text(x + 1.4, y + 1.2, nota, fontsize=7.2, color=cor,
                    style="italic", va="bottom", zorder=4)
        return x + largura / 2, y + altura / 2

    # Layout em tres colunas. `fato_classificacao` fica na coluna da esquerda,
    # embaixo da sua unica dimensao: com ele na coluna central, a ligacao ate
    # dim_linha passava POR TRAS de fato_custo_componente e parecia entrar nele.
    # Num diagrama de modelagem, uma ligacao ambigua e pior que um layout feio.
    centro_fato = caixa(
        36, 42, 28, 24, "fato_linha_mes  (480)",
        ["partidas", "km_rodados", "assentos_km  (ASK)", "passageiros",
         "passageiros_km  (RPK)", "receita", "custo_* (6 componentes)"],
        fato=True, nota="so coluna ADITIVA — nenhuma razao",
    )
    centro_componente = caixa(
        36, 19, 28, 15, "fato_custo_componente  (2.880)",
        ["linha_id, data, componente", "custo"],
        fato=True, nota="o custo despivotado",
    )
    centro_classificacao = caixa(
        2, 14, 27, 18, "fato_classificacao  (20)",
        ["janela_inicio, janela_fim", "as somas + as razoes prontas",
         "classificacao, motivo, alavanca"],
        fato=True, nota="retrato fechado: nada se reagrega",
    )

    centro_linha = caixa(
        2, 46, 27, 20, "dim_linha  (20)",
        ["linha_id  (chave)", "linha, origem, destino", "corredor, classe, perfil",
         "km, faixa_distancia, assentos", "frequencia_semanal, tripulantes"],
        fato=False,
    )
    centro_calendario = caixa(
        70, 46, 27, 20, "dim_calendario  (24)",
        ["data  (chave)", "ano_mes, ano, mes, nome_mes", "trimestre, mes_ano, ordem_mes",
         "dias_no_mes, indice_sazonal", "na_janela_decisao"],
        fato=False,
    )
    centro_componente_dim = caixa(
        70, 20, 27, 13, "dim_componente_custo  (6)",
        ["componente  (chave)", "rotulo, grupo, base", "entra_na_mc, premissa"],
        fato=False,
    )

    # Relacionamentos: um-para-muitos, filtro descendo da dimensao para o fato.
    ligacoes = [
        (centro_linha, centro_fato, "1 --> *"),
        (centro_linha, centro_componente, "1 --> *"),
        (centro_linha, centro_classificacao, "1 --> 1"),
        (centro_calendario, centro_fato, "1 --> *"),
        (centro_calendario, centro_componente, "1 --> *"),
        (centro_componente_dim, centro_componente, "1 --> *"),
    ]
    for origem, destino, cardinalidade in ligacoes:
        ax.add_patch(FancyArrowPatch(
            origem, destino, arrowstyle="-", color=EIXO, linewidth=1.1,
            connectionstyle="arc3,rad=0.06", zorder=1,
        ))
        meio_x = (origem[0] + destino[0]) / 2
        meio_y = (origem[1] + destino[1]) / 2
        texto = ax.text(meio_x, meio_y, cardinalidade, fontsize=7.4,
                        color=TINTA_FRACA, ha="center", va="center", zorder=2)
        texto.set_path_effects([efeitos.withStroke(linewidth=3.2, foreground=SUPERFICIE)])

    ax.text(0, 76.5, "Esquema estrela para Power BI", fontsize=15,
            fontweight="bold", color=TINTA, va="top")
    ax.text(0, 72.8, "Tres dimensoes, tres fatos. O filtro desce sempre da dimensao "
                     "para o fato, por um caminho so.",
            fontsize=9.5, color=TINTA_2, va="top")

    legenda = [
        Line2D([0], [0], marker="s", color="none", markerfacecolor=AZUL_CLARO,
               markeredgecolor=AZUL, markersize=11, label="fato (o que se soma)"),
        Line2D([0], [0], marker="s", color="none", markerfacecolor="#f1f0ec",
               markeredgecolor=TINTA_2, markersize=11, label="dimensao (por onde se filtra)"),
    ]
    ax.legend(handles=legenda, loc="lower right", bbox_to_anchor=(1.0, 0.0),
              fontsize=8.5, ncols=1, labelcolor=TINTA_2, handletextpad=0.5)

    _rodape(fig, "Yield, RASK, CASK e load factor NAO estao nos fatos: sao razao "
                 "entre duas somas e viram medida em DAX, calculada depois do filtro.\n"
                 "Como coluna, o visual mostraria a media das razoes mensais — peso "
                 "igual para fevereiro e julho, e um numero que nao corresponde a "
                 "periodo nenhum.")
    return _gravar(fig, "esquema-estrela")


# ---------------------------------------------------------------------------
# 3. Load factor realizado x load factor de equilibrio
# ---------------------------------------------------------------------------

def load_factor_equilibrio(janela: pd.DataFrame) -> list[str]:
    """Dumbbell: a ocupacao que a linha tem contra a que ela precisaria ter.

    Forma escolhida porque o dado e "antes x depois por item" — duas medidas
    comparaveis para cada uma de 20 linhas. Barra agrupada gastaria o dobro de
    tinta e esconderia justamente o que interessa, que e o TAMANHO do vao.

    O segmento carrega o sinal (azul quando sobra ocupacao, vermelho quando
    falta), porque aqui o vao e delta contra uma meta e sinal e polaridade. Os
    dois pontos ficam em canais separados: azul e o realizado, cinza e a meta —
    meta nao e serie que se comemora.
    """
    _estilo()
    ordenado = janela.sort_values("folga_lf", ascending=True, ignore_index=True)
    fig, ax = plt.subplots(figsize=(10.5, 8.4))

    posicoes = range(len(ordenado))
    for posicao, registro in zip(posicoes, ordenado.itertuples(index=False)):
        falta = registro.folga_lf < 0
        cor = VERMELHO if falta else AZUL

        ax.plot([registro.lf_equilibrio, registro.load_factor], [posicao, posicao],
                color=cor, linewidth=2.4, solid_capstyle="round", zorder=2)
        # Meta primeiro, realizado por cima: o anel de superficie deixa os dois
        # legiveis mesmo quando quase coincidem (Campo Grande-Cuiaba, 0,4 p.p.).
        ax.scatter(registro.lf_equilibrio, posicao, s=78, facecolor=TINTA_FRACA,
                   edgecolor=SUPERFICIE, linewidth=1.6, zorder=3)
        ax.scatter(registro.load_factor, posicao, s=88, facecolor=cor,
                   edgecolor=SUPERFICIE, linewidth=1.6, zorder=4)

        # Rotulo do vao a direita do par, so onde ele decide algo: quem falta
        # ocupacao e quem sobra pouca.
        if falta or registro.no_limite:
            borda = max(registro.load_factor, registro.lf_equilibrio)
            ax.text(borda + 0.012, posicao, _pp(registro.folga_lf), fontsize=8.4,
                    color=cor, fontweight="bold", va="center", ha="left", zorder=5)

    etiquetas = [
        f"{r.linha}   {r.km} km · {r.classe.lower()}"
        for r in ordenado.itertuples(index=False)
    ]
    ax.set_yticks(list(posicoes), etiquetas, fontsize=8.6)
    ax.tick_params(axis="y", length=0)
    for etiqueta, registro in zip(ax.get_yticklabels(), ordenado.itertuples(index=False)):
        etiqueta.set_color(TINTA if registro.folga_lf < 0 else TINTA_2)

    ax.set_xlim(0.45, 0.99)
    ax.set_ylim(-0.8, len(ordenado) - 0.2)
    ax.xaxis.set_major_formatter(lambda v, _: _pct(v, 0))
    ax.set_xlabel("Load factor")
    ax.grid(axis="x", color=GRADE, linewidth=0.7)
    ax.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)

    # O teto de oferta do modelo, que e o limite fisico da alavanca "ocupacao":
    # linha que precisa de mais que isso nao se resolve enchendo o onibus.
    ax.axvline(config.OCUPACAO_MAXIMA, color=EIXO, linewidth=1.0,
               linestyle=(0, (1, 2)), zorder=1)
    ax.text(config.OCUPACAO_MAXIMA - 0.006, 0.2,
            f"teto de oferta do modelo ({_pct(config.OCUPACAO_MAXIMA, 0)})",
            fontsize=8, color=TINTA_FRACA, rotation=90, ha="right", va="bottom")

    legenda = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=TINTA_FRACA,
               markeredgecolor=SUPERFICIE, markersize=9,
               label="LF de equilibrio (CASK total / yield)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=AZUL,
               markeredgecolor=SUPERFICIE, markersize=9,
               label="LF realizado — sobra ocupacao"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=VERMELHO,
               markeredgecolor=SUPERFICIE, markersize=9,
               label="LF realizado — falta ocupacao"),
    ]
    ax.legend(handles=legenda, loc="upper right", fontsize=8.8,
              labelcolor=TINTA_2, handletextpad=0.5)

    meses = janela.attrs.get("meses") or []
    periodo = f"{meses[0]} a {meses[-1]}" if meses else ""
    ax.set_title("Ocupacao realizada x ocupacao de equilibrio", fontsize=15,
                 fontweight="bold", color=TINTA, loc="left", pad=22)
    ax.text(0, 1.012, f"Quanto a linha precisaria vender, ao yield que ja pratica, "
                      f"para empatar com o custo cheio · janela de 12 meses ({periodo})",
            transform=ax.transAxes, fontsize=9.5, color=TINTA_2, va="bottom")

    _rodape(fig, "LF de equilibrio = CASK total / yield, da identidade "
                 "RASK = yield x load factor. A conta vale porque nenhum componente "
                 "de custo do modelo depende do numero de passageiros.\n"
                 "Manaus-Boa Vista precisaria de 81,9% de ocupacao e roda com 61,6%: "
                 "nao e uma linha que se conserta enchendo o onibus.")
    return _gravar(fig, "load-factor-equilibrio")


# ---------------------------------------------------------------------------

def exportar(janela: pd.DataFrame) -> dict[str, list[str]]:
    """As tres figuras. Devolve nome -> caminhos gravados."""
    return {
        "matriz-decisao": matriz_decisao(janela),
        "esquema-estrela": diagrama_estrela(),
        "load-factor-equilibrio": load_factor_equilibrio(janela),
    }
