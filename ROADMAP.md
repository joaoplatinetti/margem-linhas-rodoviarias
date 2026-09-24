# Roadmap

Este repositório não é uma peça fechada: é a **base de uma série**. Cada
ramificação abaixo existe porque produz um achado demonstrável — um resultado
que contraria o reflexo de quem decide malha e preço — e não porque acrescenta
mais uma técnica ao modelo.

A regra que organiza a lista: **nada entra sem uma virada**. Se a análise só
confirma o que todo mundo já supõe, ela vira uma coluna a mais na planilha, não
uma seção do README.

| # | Tema | Onde | Estado |
|---|---|---|---|
| 1 | O modelo base: margem, RASK/CASK, decisão | este repo | ✅ publicado |
| 2 | Rateio e corte de malha | este repo | ✅ publicado |
| 3 | Estresse de premissas e incerteza | este repo | ✅ publicado |
| 4 | Elasticidade e desenho de teste de preço | este repo | previsto |
| 5 | Revenue management: reserva, no-show, overbooking | repo novo | previsto |
| 6 | Dados abertos da ANTT | repo novo | previsto |
| 7 | Motor reutilizável: o contrato de dados | este repo | ✅ publicado |
| — | Avaliar uma malha real com o mesmo motor | fora deste repo | previsto |
| — | App interativo | transversal | previsto |

---

## 1. O modelo base ✅

Modelo de custo em seis componentes, indicadores de _revenue management_ e a
decisão manter/ajustar/rever, sobre 20 linhas × 24 meses sintéticos.

**O achado:** o degrau dos 600 km. Acima dessa distância entra o segundo
motorista e a tripulação por km salta 151% — de R$ 0,615 (588 km) para R$ 1,547
(694 km) — enquanto o yield *cai* com a distância. Linhas logo acima do limite
de dupla tripulação são estruturalmente mais difíceis, e o modelo mostra por quê.

**Figuras:** `matriz-decisao`, `load-factor-equilibrio`, `esquema-estrela`.

## 2. Rateio e corte de malha ✅

Quatro bases de rateio do custo fixo (km, partida, assento-km, receita) e a
simulação de tirar uma linha da malha.

**Os achados, os dois algébricos e não simulados:**

- **O rótulo é robusto, o ranking não.** Só 2 das 20 linhas trocam de
  classificação entre as quatro bases — quem decide primeiro é a margem de
  contribuição, que não depende de rateio nenhum. Mas o fixo por assento-km da
  *mesma linha* varia até **2,35×**, e uma linha anda **7 posições** no ranking.
  Meta, atenção de gestão e orçamento seguem o ranking.
- **Cortar a pior linha costuma piorar a rede.** O resultado muda em exatamente
  −MC da linha cortada, porque o bloco fixo não sai da empresa junto com ela.
  Brasília–BH está classificada como AJUSTAR e custaria **R$ 429 mil** se fosse
  cortada — e ainda derrubaria Campo Grande–Cuiabá de MANTER para AJUSTAR.

**Figuras:** `rateio-por-base`, `ganho-do-corte`.

## 3. Estresse de premissas e incerteza ✅

Ponto de ruptura por linha, tornado de sensibilidade e Monte Carlo sobre as sete
premissas.

**Os achados:**

- **Campo Grande–Cuiabá quebra com o diesel a R$ 6,25** — 1,6% acima da
  premissa. Uma decisão que o relatório apresenta como estável.
- **A receita move seis vezes mais que o custo.** 10% de tarifa valem 59% do
  resultado; 10% de pedágio valem 1%. Refinar a premissa de pedágio é trabalho
  perdido, e a conversa que importa é sobre preço — não sobre mais um corte.
- **Dez das vinte linhas têm rótulo que não se sustenta em 90% dos cenários.**
  Campo Grande–Cuiabá é MANTER em 55% deles. A rede fecha no vermelho em 6%.

**Figuras:** `ponto-de-ruptura`, `tornado-premissas`,
`probabilidade-classificacao`.

**O que ficou declarado como falso de propósito:** a linha da tarifa no tornado
supõe demanda que não reage a preço. É exatamente a premissa que o item 4
ataca.

## 4. Elasticidade e desenho de teste de preço ✅

Painel gerado com elasticidade **conhecida**, quatro especificações tentando
recuperá-la, e o dimensionamento do teste que a mediria.

**Os achados:**

- **Inclinação zero é o defeito perigoso.** O OLS simples devolve −1,04 tanto
  com elasticidade verdadeira −1,2 quanto com ela em zero. O número é plausível
  e estável, e não mede nada — só reflete que linha cara é linha de leito.
- **A correção óbvia piora.** Com efeito fixo de linha a estimativa vira +1,03:
  "preço alto atrai passageiro". Preço e demanda sobem juntos no pico por
  motivos independentes.
- **Nenhuma das quatro identifica.** Duas não respondem à verdade; duas
  acompanham mas ficam deslocadas em +2,23 e +0,54.
- **Com os 2% de variação que existem, medir a ±0,20 pediria quatro anos.**
  Com 10% de passo, três meses.

**Figuras:** `elasticidade-calibracao`, `desenho-do-teste`.

**Ressalvas medidas, não supostas:** o tamanho do teste escala com o quadrado do
ruído mensal da demanda, e o erro agrupado por linha faz mais LINHAS render mais
que mais meses.

## 5. Revenue management: curva de reserva, no-show e overbooking

**Repo próprio** — muda o grão: bilhete e antecedência, não linha × mês.

**O que se constrói:** curva de reserva por antecedência, proteção de assento
por classe (Littlewood e EMSR), distribuição de no-show e nível ótimo de
overbooking.

**Por que separado:** o modelo de custo daqui não serve lá, e o README desta
peça já está no limite do que alguém lê de uma vez.

## 6. Dados abertos da ANTT

**Repo próprio** — sai do sintético.

**O que se constrói:** sazonalidade real, tamanho de mercado por trecho e
concentração, a partir de MONITRIIP e do export de empresas/linhas/seções, que
são **dados abertos**.

**Por que separado:** misturar "modelo com premissa declarada" e "apuração de
dado real" no mesmo README confunde os dois registros. Aqui cada número é uma
escolha auditável; lá cada número é uma fonte com data de acesso.

A ponte entre os dois já existe: [`docs/fontes-publicas.md`](docs/fontes-publicas.md)
liga cada premissa deste modelo à fonte pública que a calibraria.

## 7. Motor reutilizável: o contrato de dados ✅

O modelo deixou de exigir a malha sintética. `margem/dados.py` declara o que o
motor precisa saber sobre uma linha — chaves, aditivas, descritivas, com unidade
e propósito — e `margem/motor.py` é o ponto de entrada único: qualquer fato que
cumpra o contrato entra e sai classificado.

**O achado veio do teste, não da leitura do código.** Uma malha estrangeira
inventada atravessando o motor revelou dois acoplamentos que ninguém tinha
notado: `janela_decisao` agrupava por colunas fixas do catálogo sintético, e
`agregar` exigia os cinco componentes de custo do modelo. Os dois estouravam com
qualquer malha que não fosse esta.

**O refactor não moveu um número** — verificado na assinatura da janela, nos
CSVs byte a byte e nas células da planilha.

**Doc:** [`docs/contrato-de-dados.md`](docs/contrato-de-dados.md).

## — Avaliar uma malha real com o mesmo motor

**O que se constrói, e onde:** fora deste repositório. Um projeto que instala
este pacote como biblioteca, monta o fato a partir do próprio sistema de venda,
traduz pelo contrato e chama o motor.

**As perguntas que só o dado real responde:**

1. O degrau da dupla tripulação existe na operação, ou é artefato da premissa?
2. Qual base de rateio o setor usa hoje, e quantas linhas mudariam de leitura em
   outra?
3. Quantas linhas estão a menos de um dígito de diesel da própria fronteira?
4. A amplitude sazonal varia entre linhas como o sintético supõe?

**A regra de fronteira**, escrita também em `docs/contrato-de-dados.md`: nenhum
dado de operação real entra neste repositório. O que volta é método e achado
direcional, nunca um valor.

## — App interativo

**O que se constrói:** o modelo no ar, com controles de diesel, frequência e
tarifa, e a classificação mudando ao vivo.

**Por que vale:** transforma cada ramificação acima em algo que o leitor
manipula em vez de ler. Serve a série inteira, não a um artigo.
