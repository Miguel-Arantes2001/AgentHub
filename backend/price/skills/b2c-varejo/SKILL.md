---
name: b2c-varejo
description: Pesquisa preços de varejo em lojas diferentes e registra cada oferta com a ferramenta, sem inventar preço nem URL.
---

# Preço de varejo

Preço de site é referência: muda com região, frete, estoque e promoção.

## Coleta

Pesquise o produto em lojas e marketplaces brasileiros. Priorize o produto idêntico (mesma marca, peso, volume e apresentação). Equivalente só quando o idêntico não aparecer.

Registre cada preço com `registrar_oferta`:

- `loja`: nome da loja
- `produto`: nome do anúncio
- `preco`: preço da embalagem inteira, em reais
- `quantidade` e `unidade`: o que vem na embalagem vendida. Caixa de 10 comprimidos → `preco` da caixa, `10` e `comprimidos`. Ração de 15 kg → `15` e `kg`. Não registre 1 comprimido se a página vende a caixa. Se o pedido pedir o preço por kg, litro ou comprimido, registre mesmo assim a embalagem real da página
- `url`: página do produto, não a página de busca
- `equivalencia`: `identico`, `equivalente` ou `parcial`
- `observacoes`: promoção, "a partir de", ou preço que depende de CEP, login ou carrinho

Regras:

1. Sem preço explícito na página, não registre. Não invente preço, loja, embalagem nem URL.
2. Se o preço depender de CEP, login ou carrinho, descreva isso em `observacoes` e não invente o valor.
3. Não repita URL nem loja. A meta é 3 lojas diferentes; a mesma loja não conta de novo.
4. No máximo duas buscas. Depois pare.
5. Feche com uma linha. Não escreva relatório nem média: o Python calcula.
