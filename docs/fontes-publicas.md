# Fontes públicas: onde cada premissa seria calibrada

Este modelo é sintético **por escolha**, não por falta de dado. Toda premissa
está declarada em [`margem/config.py`](../margem/config.py), e quase todas têm
uma fonte pública que as ancoraria na realidade brasileira.

Este arquivo é o mapa entre as duas coisas. Ele serve a três propósitos:

1. **Torna o sintético auditável.** Quem discordar de um número sabe onde
   conferir o número de verdade.
2. **É a ponte para os artigos.** Cada publicação da série pode abrir com o que
   a fonte pública diz naquele momento e fechar com o que o modelo faz com isso.
3. **É a semente do repositório de dados abertos** (item 6 do
   [ROADMAP](../ROADMAP.md)).

---

## A regra deste arquivo

> **Nenhum valor real entra aqui sem coleta verificada e data de acesso
> registrada.** Enquanto não houver essa coleta, a célula fica `a verificar` —
> mesmo quando o valor "parece óbvio".

O motivo é prático, não cerimonioso. Número de resolução, preço de combustível e
piso salarial envelhecem em meses; portal de dados abertos muda de estrutura e
de URL. **Um valor errado com aparência de apurado é pior que uma lacuna
assumida**: a lacuna alguém preenche, o valor errado alguém cita.

O mesmo vale para as descrições de fonte abaixo. Elas registram o que se espera
encontrar, e a coluna de estado diz o que já foi confirmado contra o portal.

---

## O mapa

| Premissa do modelo | Constante | Fonte que a calibraria | Cadência | Estado |
|---|---|---|---|---|
| Tarifa de referência por passageiro-km, por classe | `TARIFA_KM_POR_CLASSE` | Coeficiente tarifário do transporte rodoviário interestadual (ANTT), publicado por resolução | revisão periódica por ato normativo | valor `a verificar` · fonte a confirmar |
| Preço do diesel | `DIESEL_LITRO` | Levantamento de preços de combustíveis (ANP), série por estado | semanal | valor `a verificar` · fonte a confirmar |
| Piso e encargos da tripulação | `CUSTO_HORA_TRIPULANTE`, `DIARIA_TRIPULANTE`, `PERNOITE_TRIPULANTE` | Convenção coletiva da categoria (rodoviários), por sindicato e estado | anual | valor `a verificar` · fonte a confirmar |
| Regra de dupla tripulação | `SEGUNDO_MOTORISTA_ACIMA_KM` | Legislação de jornada e tempo de direção contínua — a regra real é de **tempo**, não de quilometragem | mudança por lei | **premissa declaradamente simplificada** |
| Pedágio por km, por corredor | `CORREDORES[...]["pedagio_km"]` | Tarifas de praças das concessionárias federais e estaduais | reajuste anual por contrato | valor `a verificar` · fonte a confirmar |
| Sazonalidade mensal da demanda | `SAZONALIDADE_MENSAL` | MONITRIIP — bilhetes de passagem (dados abertos da ANTT) | mensal | valor `a verificar` · fonte a confirmar |
| Tendência anual da demanda | `TENDENCIA_ANUAL` | MONITRIIP, série longa | mensal | valor `a verificar` |
| Distâncias das linhas | `linhas.py`, coluna `km` | Malha rodoviária federal / seções outorgadas | — | plausíveis, não conferidas |
| Consumo por classe, pneus, manutenção | `CONSUMO_KM_LITRO`, `PNEUS_KM`, `MANUTENCAO_KM` | Planilhas de custo operacional do setor (metodologia tarifária) | — | valor `a verificar` |
| Assentos por classe | `ASSENTOS_POR_CLASSE` | Configurações usuais de fabricante por tipo de serviço | — | plausíveis, não conferidas |
| Bloco de custo fixo mensal | `CUSTO_FIXO_MENSAL` | **Não tem fonte pública**: depende do porte da empresa | — | premissa livre, calibrada para a escala da malha |
| Base de rateio do fixo | `BASE_RATEIO_FIXO` | **Não tem fonte**: é decisão de gestão | — | ver o item 2 do [ROADMAP](../ROADMAP.md) |

---

## O que muda quando a fonte entra

Três premissas mudam de natureza ao serem ancoradas, e vale saber disso antes:

- **A tarifa deixa de ser livre.** Existe teto tarifário no interestadual, e boa
  parte da venda real acontece nele. Um modelo calibrado com o coeficiente
  oficial passa a ter uma fronteira superior que o modelo atual não tem — e essa
  fronteira é o que torna elasticidade tão difícil de medir (item 4 do roadmap).
- **A sazonalidade real não é uma curva só.** Corredor de lazer e corredor
  corporativo têm amplitudes diferentes, que é justamente o que o campo
  `amplitude_sazonal` representa aqui. O MONITRIIP permite medir isso por trecho
  em vez de arbitrar.
- **O custo fixo continua sem fonte.** É estrutura de empresa, não dado público.
  Qualquer trabalho com dado aberto vai conseguir receita e volume, e vai
  continuar arbitrando o fixo — o que reforça o achado do item 2: a parte do
  custo que menos se conhece é a que mais depende de convenção.

## Limite honesto

Dado público de transporte rodoviário é **bom em volume e fraco em custo**. Dá
para medir mercado, sazonalidade e concentração; não dá para medir margem. Este
repositório resolve isso do lado oposto — declara o custo e assume que ele é
premissa — e o repositório de dados abertos vai resolver o outro lado. Nenhum dos
dois sozinho fecha a conta, e apresentar qualquer um deles como se fechasse seria
o erro mais fácil de cometer aqui.
