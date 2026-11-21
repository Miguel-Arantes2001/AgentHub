---
name: pesquisa-tendencias-agro
description: Pesquisar e identificar a tendência agropecuária mais relevante sobre um tema, para o momento atual e para os próximos meses. Use quando precisar detectar tendências agro, sazonalidade, pragas, clima, commodities ou insumos.
metadata:
  version: "1.0.0"
  tags: ["agro", "tendencias", "pesquisa", "loja"]
---

# Pesquisa de Tendências Agro

Busque notícias recentes sobre um tema agropecuário e identifique a tendência principal: o que está em curso agora e o que aponta para os próximos meses.

## Entrada esperada

- Tema de busca (ex: "nutrição animal", "defensivos e safra", "pecuária leiteira", "sementes de milho")
- Região ou contexto opcional (ex: "Brasil", "Sul", "Cerrado")

## Processo

1. Busque notícias, relatórios e análises **mais recentes** sobre o tema no agronegócio
2. Identifique a tendência principal (a mais clara para o momento e para os próximos meses)
3. Classifique o tipo de driver: clima, pragas/doenças, preço de commodities, demanda de insumos, sazonalidade, regulamentação ou tecnologia
4. Extraia palavras-chave para aprofundamento e liste categorias de produtos potencialmente afetadas

## Formato de saída

Retorne exatamente:

1. **Título**: nome curto da tendência principal
2. **Resumo**: 2-3 frases do que está acontecendo agora e do que isso sugere para os próximos meses
3. **Driver**: clima | pragas/doenças | commodities | insumos | sazonalidade | regulamentação | tecnologia
4. **Fonte**: veículo ou órgão onde encontrou
5. **Palavras-chave**: termos para buscar mais fontes sobre a mesma tendência
6. **Categorias impactadas**: lista breve (ex: rações, suplementos, defensivos, sementes, medicamentos veterinários, equipamentos)

## Regras

- Use fontes recentes (dias ou semanas) para ler o presente e o que elas indicam para os próximos meses
- Escolha a tendência com o sinal mais claro nesse horizonte
- Prefira fontes do agronegócio: Embrapa, Conab, MAPA, Cepea, Globo Rural, Canal Rural, AgroStats, Reuters Agriculture
- As palavras-chave devem ser específicas o suficiente para encontrar a mesma tendência em outras fontes
- Nunca invente dados, URLs ou fontes — use apenas o que as buscas retornaram
- Se a busca falhar ou vier vazia, diga isso claramente e tente query mais curta; não fabrique resultado
- NÃO salve arquivos — apenas retorne o texto no formato acima
