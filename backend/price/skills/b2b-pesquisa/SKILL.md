---
name: b2b-pesquisa
description: Pesquisa fornecedores e preços B2B para revenda agropecuária, em catálogo e na web, sem inventar URL nem preço.
---

# Pesquisa B2B

Siga só a seção que a instrução indicar. Preço de site ou catálogo é referência, não cotação firme.

## Coordenação

Trabalhe com todos os produtos do pedido. Não ignore nenhum item. Chame um membro por vez. Primeiro os fornecedores, depois os preços. O coletor de preços usa os catálogos do pedido e os fornecedores já registrados. Não invente dados. Se um item ficar sem preço, diga isso.

## Fornecedores

Pesquise todos os itens. Priorize fabricante, distribuidor e cooperativa. Loja e marketplace só como complemento. Se o pedido trouxer fornecedores preferenciais, comece por eles.

Registre com `registrar_fornecedor`:

- `nome` e `tipo`: `fabricante`, `distribuidor`, `cooperativa`, `loja` ou `marketplace`
- `url`: site real da empresa
- `regiao_atendida`, `pedido_minimo`, `prazo_entrega_dias`, `formas_pagamento` e `observacoes`: só se a página mostrar. Senão, 0 ou vazio

Não registre preço nesta etapa. Não repita empresa. Sem URL, não registre.

## Preços

Pesquise todos os itens, mesmo os que ficarem sem preço. Use primeiro o texto dos catálogos e os sites dos fornecedores já achados. Depois, outras fontes na web. Fabricante e distribuidor vêm antes do varejo. Preço de loja é referência: diga isso em `observacoes`.

Registre com `registrar_oferta`. `item_solicitado` tem de ser um dos produtos do pedido.

- `fonte`: loja ou fornecedor
- `item_ofertado`: nome do anúncio
- `preco`: preço de uma embalagem
- `quantidade_embalagem` e `unidade_embalagem`: conteúdo real. 15 kg → `15` e `kg`. 500 g → `500` e `g`
- `referencia`: na web, a URL; no catálogo, arquivo e página (ex.: `catalogo.pdf, página 4`)
- `tipo_fonte`: `web` ou `catalogo`
- `url`: obrigatória na web; vazia no catálogo
- `equivalencia`: `identico` só se for o mesmo produto; `equivalente` se for comparável; `parcial` se a comparação for limitada
- `frete` e `desconto_percentual`: só com número visível. Se não aparecer, descreva em `observacoes` e não trate como zero confirmado
- `data_preco`: a data escrita na página, se houver

Sem preço explícito, não registre. Não invente URL, embalagem nem condição. Não repita a mesma referência para o mesmo item. Feche com uma linha.
