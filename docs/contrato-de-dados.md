# Contrato de dados: ligando uma malha própria ao motor

Este projeto nasceu como uma peça fechada sobre um dataset sintético. A partir
da fase 5 ele é também um **motor**: qualquer malha que cumpra o contrato abaixo
pode ser avaliada pelo mesmo código — mesmos indicadores, mesmo rateio, mesma
regra de decisão.

O contrato existe para uma falha específica. Coluna ausente que vira zero no
meio de uma divisão produz indicador **plausível e errado**: um CASK que não
inclui tripulação é só um CASK menor, e nada na tela avisa. `margem.dados.validar`
recusa antes, nomeando a coluna e dizendo para que ela serve.

```bash
uv run margem contrato   # o contrato impresso, sem precisar ler código
```

---

## A fronteira deste repositório

> **Nenhum dado de operação real entra aqui** — nem como exemplo, nem agregado,
> nem em teste. O dataset publicado é sintético por escolha, e é isso que torna
> o repositório publicável.

A avaliação de uma malha real acontece **fora**, num projeto que instala este
pacote como biblioteca. O que pode voltar de lá para cá é método e achado
direcional — *"o degrau da dupla tripulação também aparece na operação"* — nunca
um valor de custo, tarifa ou volume.

A razão é simples: custo por km de operação é informação comercial, inclusive
arredondado. E um repositório público que um dia recebeu dado real deixa de ser
publicável para sempre, porque o histórico do git não esquece.

---

## O contrato

### Chaves — definem o grão

Um registro por linha e mês. Duplicata é recusada: o motor soma o que recebe, e
duplicata vira volume inventado.

| Coluna | Unidade | Serve para |
|---|---|---|
| `linha_id` | texto | identifica a linha; é a chave de todo recorte |
| `ano_mes` | `AAAA-MM` | o mês do registro; define a janela de decisão |

### Aditivas — as únicas que se somam

Todo indicador do modelo é razão entre duas delas. É por isso que a lista é
curta e fechada.

| Coluna | Unidade | Serve para |
|---|---|---|
| `partidas` | contagem | base de rateio por partida |
| `km_rodados` | km | base de rateio por km |
| `assentos_km` | assento-km | a oferta (ASK): denominador de RASK, CASK e load factor |
| `passageiros` | contagem | denominador da tarifa média |
| `passageiros_km` | passageiro-km | a demanda (RPK): numerador do load factor e do yield |
| `receita` | R$ | numerador de yield, RASK e margem |
| `custo_variavel` | R$ | a margem de contribuição e o CASK variável |

### Descritivas — opcionais

Não entram em conta nenhuma: rotulam a saída e permitem recortes. `linha`, `km`,
`assentos`, `classe`, `corredor`.

Se `km` e `assentos` vierem, `preparar` deriva `assentos_km`, `km_rodados` e
`passageiros_km` do que faltar.

---

## O que o motor não faz

**Não calcula custo variável.** Custo depende de premissa de operação — consumo,
salário, pedágio — e essas premissas são de quem opera. A malha sintética
calcula o dela em `custos.aplicar_variaveis`; uma malha externa chega com o dela
pronto.

O motor rateia o **fixo**, que é a parte que depende de uma convenção e não de
uma medição — e por isso essa convenção é parâmetro, não constante. A
[seção sobre rateio no README](../README.md#o-rateio-decide-mais-do-que-parece)
mostra que trocar a base reordena o ranking em até sete posições.

---

## Como ligar uma malha

```python
from margem import dados, motor

MAPA = {
    "id_linha": "linha_id",
    "mes": "ano_mes",
    "viagens": "partidas",
    "pax": "passageiros",
    "receita_bruta": "receita",
    "custo_direto": "custo_variavel",
}

fato = dados.preparar(minha_malha, mapa=MAPA)
print(fato.attrs["derivadas"])        # o que foi calculado, e não veio da fonte

janela = motor.avaliar(
    fato,
    fixo_mensal=180_000.0,            # o bloco fixo da SUA operação
    base_rateio="km",                 # km | partida | assento_km | receita
)
```

`preparar` registra em `attrs["derivadas"]` o que ele calculou. Isso não é
detalhe: número derivado e número medido têm confiabilidade diferente, e quem lê
o resultado precisa saber qual é qual. Coluna que veio da fonte **vence** a
derivação — dado medido vale mais que calculado.

O arquivo [`testes/test_motor.py`](../testes/test_motor.py) tem uma malha
estrangeira completa atravessando o motor inteiro, com vocabulário próprio e
bloco fixo próprio. É a prova de que isso funciona — e ela é inventada, porque
dado real não entra aqui.

---

## O que sobreviveu ao refactor

Separar "o modelo" dos "dados do modelo" só vale se o que já estava publicado
continuar idêntico. Verificado em três níveis:

- a janela de decisão tem a **mesma assinatura** de antes do refactor;
- os seis CSVs do Power BI saem **byte a byte iguais**;
- as células da planilha têm o **mesmo conteúdo**.

Dois acoplamentos apareceram no caminho, os dois encontrados pelo teste da malha
estrangeira e não por leitura de código:

- `janela_decisao` agrupava por uma lista fixa de colunas do catálogo sintético
  (`perfil`, `frequencia_semanal`…), e estourava com qualquer malha que não as
  tivesse. Agora agrupa por `linha_id` mais o que existir — e avisa se alguma
  descritiva variar dentro da linha, o que partiria a linha em dois registros.
- `agregar` somava os cinco componentes de custo sintéticos. Agora soma as
  aditivas presentes, exigindo só as três sem as quais não há indicador.
