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
| 3 | Estresse de premissas e incerteza | este repo | previsto |
| 4 | Elasticidade e desenho de teste de preço | este repo | previsto |
| 5 | Revenue management: reserva, no-show, overbooking | repo novo | previsto |
| 6 | Dados abertos da ANTT | repo novo | previsto |
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

## 3. Estresse de premissas e incerteza

**O que se constrói:** o preço de diesel (e de pedágio, e de salário) em que
cada linha deixa de cobrir o próprio custo; gráfico tornado de qual premissa
move mais o resultado da rede; e Monte Carlo sobre a incerteza das premissas,
devolvendo a **probabilidade** de cada linha ser MANTER em vez de um rótulo seco.

**O achado esperado:** a classificação de várias linhas não sobrevive a uma alta
de um dígito no diesel — e duas delas já estão hoje a menos de um centavo por
assento-km da fronteira. Uma decisão apresentada como binária é, na verdade, uma
distribuição.

**Por que é barato:** `margem/config.py` já tem toda premissa declarada em um
lugar só, e o pipeline é determinístico. A infraestrutura existe.

## 4. Elasticidade e desenho de teste de preço

**O que se constrói:** gerar demanda com elasticidade **conhecida**, tentar
recuperá-la de dado observacional com a variação de preço que existe na vida
real, e mostrar a estimativa falhando. Depois, dimensionar o teste — tamanho de
amostra por passo de preço e por classe — que identificaria de verdade.

**O achado esperado:** histórico observacional de tarifa não mede elasticidade,
porque a variação de preço que existe nele é mix de seção e de classe, não
decisão de precificação. É o tipo de conclusão que só se demonstra com dado
sintético, justamente porque ali a resposta verdadeira é conhecida.

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

## — App interativo

**O que se constrói:** o modelo no ar, com controles de diesel, frequência e
tarifa, e a classificação mudando ao vivo.

**Por que vale:** transforma cada ramificação acima em algo que o leitor
manipula em vez de ler. Serve a série inteira, não a um artigo.
