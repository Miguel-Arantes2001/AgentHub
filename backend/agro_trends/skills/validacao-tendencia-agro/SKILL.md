---
name: validacao-tendencia-agro
description: Validar se uma tendência agropecuária é sinal real ou ruído e dizer o que vale agora e nos próximos meses. Use quando precisar filtrar hype ou fazer fact-check de uma tendência agro.
metadata:
  version: "1.1.0"
  tags: ["agro", "validacao", "fact-check", "tendencias"]
---

# Validação de Tendência Agro

Análise crítica de um dossiê agropecuário. Separa sinal de ruído e devolve a leitura do que está em curso agora e do que as fontes sustentam para os próximos meses. Esta resposta é o resultado do workflow. Não grave arquivo.

## Entrada esperada

- Dossiê de evidências (produzido pela skill apuracao-fontes-agro)

## Processo

Execute TODOS os passos em sequência, sem pedir permissão:

### Passo 1 — Cruzamento inicial
Compare cada fato entre todas as fontes. Classifique como:
- **CONFIRMADO**: 2+ fontes concordam
- **DISPUTADO**: fontes divergem
- **NÃO VERIFICADO**: apenas 1 fonte

### Passo 2 — Sinal vs ruído
Avalie se a tendência é:
- **TENDÊNCIA REAL**: confirmada por fontes sólidas e com continuidade temporal
- **RUÍDO / HYPE**: menção isolada, especulação ou dado sem corroboração
- **SINAL FRACO**: possível tendência, mas ainda com lacunas relevantes

### Passo 3 — Resolução de contradições
Para cada fato DISPUTADO:
1. Busque fonte oficial/primária (Conab, MAPA, Embrapa, Cepea, USDA)
2. Se encontrou nova informação, reavalie
3. Após 2+ tentativas sem resolver → classifique como "não resolvida" com razão provável

### Passo 4 — Horizonte
Diga o que está acontecendo agora e o que as fontes sustentam para os próximos meses. Considere região, cultura ou espécie e continuidade do sinal. Não monte lista de compras nem estime preço ou estoque.

### Passo 5 — Consistência final
Revise datas, números, regiões e citações de toda a leitura.

## Formato de saída

```
## FATOS CONFIRMADOS
Fatos com alto grau de confiança + fontes que confirmam.

## FATOS DISPUTADOS RESOLVIDOS
Versão original das fontes → o que encontrou → veredito final.

## FATOS DISPUTADOS NÃO RESOLVIDOS
O que cada fonte diz, buscas feitas, razão provável.

## FATOS NÃO VERIFICADOS
Informações de fonte única não corroboradas + buscas tentadas.

## LEITURA
- Agora: o que está em curso, com região ou cultura quando a fonte trouxer
- Próximos meses: o que as fontes sustentam olhar, ou "sem base para projetar" se o sinal for curto
- O que pode ser afirmado
- O que fica em aberto

## RESUMO
Último bloco. Condense a resposta inteira sem omitir ponto importante e sem acrescentar fato novo.
- Veredito: TENDÊNCIA REAL | SINAL FRACO | RUÍDO/HYPE
- Confiança: alto/médio/baixo
- Agora: uma ou duas frases com região, cultura ou espécie e os números já citados
- Próximos meses: o que as fontes sustentam, ou "sem base para projetar"
- Confirmado: cada fato confirmado que muda a leitura (número, data, região)
- Em aberto: cada divergência não resolvida e cada fato não verificado; se não houver, escreva "nenhum"
- Pode afirmar / não pode afirmar
```

## Regras

- Execute IMEDIATAMENTE, sem pedir permissão ou fazer perguntas
- Faça as buscas necessárias antes de classificar como "não resolvido" ou "ruído"
- Seja específico: cite valores, regiões e datas exatos
- Leia a tendência. Não recomende compra, preço ou estoque
- Feche com o bloco RESUMO. Ele repete os pontos importantes das seções anteriores; não substitui essas seções e não cria dado novo
- Nunca invente URLs ou fontes; se a busca falhar, baixe a confiança e declare a limitação
- NÃO salve arquivo — retorne só o texto no formato acima
