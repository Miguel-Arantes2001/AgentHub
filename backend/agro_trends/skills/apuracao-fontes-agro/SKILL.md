---
name: apuracao-fontes-agro
description: Apurar e cruzar múltiplas fontes sobre uma tendência agropecuária, montando um dossiê estruturado com evidências, linha do tempo, consensos, contradições e lacunas. Use quando precisar investigar fontes agro, cruzar informações de veículos do agronegócio ou montar dossiê sobre uma tendência.
metadata:
  version: "1.0.0"
  tags: ["agro", "apuracao", "fontes", "dossie"]
---

# Apuração de Fontes Agro

Workflow para investigar uma tendência agropecuária em múltiplas fontes e produzir um dossiê estruturado de evidências.

## Quando usar

- Recebeu uma tendência agro e precisa verificar em outras fontes
- Precisa montar um dossiê de evidências sobre clima, safra, pragas, preços ou demanda
- Quer cruzar informações de veículos e órgãos do agronegócio

## Entrada esperada

- Título ou resumo da tendência a ser apurada
- Palavras-chave para busca (opcional — se não fornecidas, extraia do título)

## Processo

1. **Buscar fontes**: use as palavras-chave para buscar a mesma tendência em diferentes veículos/órgãos (mínimo 3, ideal 5)
2. **Extrair fatos**: para cada fonte, registre dados, números, regiões, culturas/espécies e citações diretas
3. **Cruzar informações**: identifique consensos, contradições e exclusividades
4. **Montar dossiê**: produza o documento estruturado no formato abaixo

## Formato de saída

Produza o dossiê exatamente nesta estrutura:

```
## FONTES COLETADAS

Para cada fonte encontrada:
- **Veículo**: Título ou descrição (URL)
- Data/hora de publicação (se disponível)
- Fatos reportados (dados, números, regiões, culturas/espécies, citações diretas)
- Informação exclusiva dessa fonte (o que só ela traz)

## LINHA DO TEMPO

Eventos em ordem cronológica com a fonte entre colchetes.
Ex: "Março — Conab revisa estimativa de safra [Conab] [Globo Rural]"

## PONTOS DE CONSENSO

Fatos que TODAS ou a maioria das fontes confirmam.

## CONTRADIÇÕES E DIVERGÊNCIAS

Dados que diferem entre fontes. Seja específico:
- Ex: "Conab estima X toneladas; USDA aponta Y toneladas"
- Ex: "Canal Rural fala em alta de demanda; Cepea aponta estabilidade"

## SINAL

O que as fontes mostram agora e o que sustentam para os próximos meses (região, cultura ou espécie, sazonalidade). Sem preço, oferta ou recomendação de compra.

## LACUNAS

O que nenhuma fonte esclareceu ou o que falta confirmar.
```

## Regras

- Mínimo de **3 fontes**, ideal **5 ou mais**
- Priorize fontes agro: Embrapa, Conab, MAPA, Cepea, IBGE, USDA, Globo Rural, Canal Rural, Reuters Agriculture
- Para cada fonte, SEMPRE use o formato `- **Nome do Veículo**: ...` e inclua a URL completa **somente se a busca a retornou**
- Nunca invente dados, títulos, datas ou URLs — registre apenas o que a ferramenta de busca devolveu
- Se a busca falhar, tente query mais curta; se ainda falhar, declare a lacuna sem inventar fonte
- Seja específico nas contradições: cite valores, regiões e datas exatos de cada fonte
- Se a apuração anterior não atingiu o mínimo, busque fontes DIFERENTES das já encontradas
- NÃO salve arquivos — apenas retorne o dossiê no formato acima
