"""
O ponto de entrada unico: de um fato que cumpre o contrato ate a decisao.

Ate a ramificacao 4, o caminho da decisao existia espalhado em `pipeline.py`:
gerar, aplicar custo, calcular indicadores, fechar a janela, classificar,
recomendar. Funcionava porque so havia um chamador e uma malha.

Este modulo junta esses passos num lugar so, e com isso resolve dois problemas
de uma vez:

- **A malha deixa de precisar ser a sintetica.** Qualquer fato que cumpra o
  contrato de `margem.dados` entra aqui — inclusive um montado a partir de um
  sistema de venda. O motor nao pergunta de onde veio.
- **O caminho da decisao passa a ser um so.** Antes, quem quisesse avaliar outra
  malha reescreveria a sequencia e, na primeira divergencia, teria dois
  resultados diferentes para a mesma pergunta sem saber qual esta certo.

O QUE O MOTOR NAO FAZ

Nao calcula custo variavel. Custo depende de premissa de operacao — consumo,
salario, pedagio — e essas premissas sao de quem opera, nao do motor. A malha
sintetica calcula o seu em `custos.aplicar_variaveis`; uma malha real chega com
o dela ja pronto. O motor rateia o FIXO, que e a parte que depende de uma
convencao e nao de uma medicao, e essa convencao ele expoe como parametro.

FRONTEIRA DESTE REPOSITORIO

O contrato existe para que uma malha real possa ser avaliada pelo mesmo codigo.
Essa avaliacao acontece **fora daqui**: nenhum dado de operacao real entra neste
repositorio. Ver `docs/contrato-de-dados.md`.
"""
from __future__ import annotations

import logging

import pandas as pd

from margem import custos, dados, indicadores

log = logging.getLogger(__name__)


def avaliar(fato: pd.DataFrame, *,
            fixo_mensal: float | None = None,
            base_rateio: str | None = None,
            janela_meses: int | None = None,
            recomendar: bool = True) -> pd.DataFrame:
    """Do fato mensal ate a janela de decisao classificada.

    Espera um fato que cumpra o contrato — chaves, aditivas e `custo_variavel`
    ja calculado. Devolve uma linha por linha de onibus, com indicadores,
    classificacao e, por padrao, a alavanca recomendada.

    `fixo_mensal` e `base_rateio` sao a convencao de rateio, e sao parametro
    justamente porque sao convencao: a ramificacao 2 mostrou que trocar a base
    reordena o ranking em ate sete posicoes.
    """
    dados.validar(fato)

    rateado = custos.ratear_fixo(fato, base=base_rateio, total_mensal=fixo_mensal)
    com_indicadores = indicadores.calcular(rateado)
    janela = indicadores.janela_decisao(com_indicadores, meses=janela_meses)

    return indicadores.recomendacao(janela) if recomendar else janela


def mensal(fato: pd.DataFrame, *,
           fixo_mensal: float | None = None,
           base_rateio: str | None = None) -> pd.DataFrame:
    """O fato mensal com custo fixo rateado e todos os indicadores.

    E o grao anterior ao da decisao: serve para serie temporal e para conferir
    identidade com `indicadores.reconciliar`.
    """
    dados.validar(fato)
    return indicadores.calcular(
        custos.ratear_fixo(fato, base=base_rateio, total_mensal=fixo_mensal)
    )
