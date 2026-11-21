"""Consulta somente leitura ao cadastro de produtos do ERP (SQLite).

O Oráculo usa estas funções como tools. O banco é aberto com mode=ro, então
nada aqui grava no ERP. Só a tabela products é lida, e só da loja configurada.

Variáveis de ambiente (.env), as duas obrigatórias:
    ORACLE_SQLITE_PATH  caminho do erp.db
    ORACLE_STORE_ID     id da loja na tabela stores
"""

import json
import os
import re
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path

LIMITE_MAXIMO = 80
SEM_DESCRICAO = "sem descricao"
ESTOQUE_NAO_CONTROLADO = "não controlado no sistema"


def _caminho() -> Path:
    valor = os.getenv("ORACLE_SQLITE_PATH")
    if not valor:
        raise RuntimeError("Defina ORACLE_SQLITE_PATH no .env com o caminho do erp.db.")
    return Path(valor)


def _loja_id() -> int:
    valor = os.getenv("ORACLE_STORE_ID")
    if not valor:
        raise RuntimeError("Defina ORACLE_STORE_ID no .env com o id da loja (tabela stores).")
    try:
        return int(valor)
    except ValueError:
        raise RuntimeError(f"ORACLE_STORE_ID deve ser um número, mas veio '{valor}'.") from None


def _conectar() -> sqlite3.Connection:
    caminho = _caminho()
    if not caminho.is_file():
        raise FileNotFoundError(f"Banco do ERP não encontrado em {caminho}")
    con = sqlite3.connect(f"{caminho.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def _normalizar(texto: str | None) -> str:
    """Minúsculas e sem acento, para 'racao' achar 'Ração'."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


def _palavras(termo: str) -> list[str]:
    palavras = []
    for palavra in re.findall(r"[a-z0-9]+", _normalizar(termo)):
        if len(palavra) < 3:
            continue
        # tira o plural simples: fertilizantes -> fertilizante
        if len(palavra) > 4 and palavra.endswith("s"):
            palavra = palavra[:-1]
        # tira a vogal final para achar derivadas: sarna -> sarn (sarnicida), cachorro -> cachorr (cachorra)
        # 'o' só em palavras longas, para 'racao' não virar 'raca' (raças)
        if (len(palavra) >= 5 and palavra[-1] in "ae") or (len(palavra) >= 7 and palavra[-1] == "o"):
            palavra = palavra[:-1]
        palavras.append(palavra)
    return palavras


def _carregar_produtos() -> list[dict]:
    with closing(_conectar()) as con:
        linhas = con.execute(
            "SELECT id, name, description, category, price, stock, unit_of_measure "
            "FROM products WHERE store_id = ? ORDER BY name",
            (_loja_id(),),
        ).fetchall()
    produtos = []
    for linha in linhas:
        descricao = (linha["description"] or "").strip()
        if _normalizar(descricao) == SEM_DESCRICAO:
            descricao = ""
        produtos.append(
            {
                "id": linha["id"],
                "nome": linha["name"],
                "descricao": descricao,
                "categoria": linha["category"] or "Sem categoria",
                "preco": linha["price"],
                "unidade": linha["unit_of_measure"] or "un",
                "estoque": linha["stock"] if linha["stock"] is not None else ESTOQUE_NAO_CONTROLADO,
            }
        )
    return produtos


def _limite(valor: int, padrao: int) -> int:
    try:
        valor = int(valor)
    except (TypeError, ValueError):
        return padrao
    return max(1, min(valor, LIMITE_MAXIMO))


def _resposta(produtos: list[dict], total: int) -> str:
    saida = []
    for produto in produtos:
        item = {chave: valor for chave, valor in produto.items() if valor not in ("", None)}
        saida.append(item)
    return json.dumps(
        {"total_encontrado": total, "mostrando": len(saida), "produtos": saida},
        ensure_ascii=False,
    )


def listar_categorias_da_loja() -> str:
    """Lista as categorias de produtos cadastradas na loja, com a quantidade de itens em cada uma.

    Use primeiro quando a pergunta for sobre um tipo de produto e você não souber
    o nome exato da categoria (fertilizantes, medicamentos, ração, ferramentas...).
    """
    try:
        produtos = _carregar_produtos()
    except Exception as exc:
        return f"Não consegui ler o cadastro da loja. Detalhe: {exc}"
    contagem: dict[str, int] = {}
    for produto in produtos:
        contagem[produto["categoria"]] = contagem.get(produto["categoria"], 0) + 1
    ordenadas = sorted(contagem.items(), key=lambda par: (-par[1], par[0]))
    return json.dumps(
        {"total_de_produtos": len(produtos), "categorias": [{"categoria": c, "itens": n} for c, n in ordenadas]},
        ensure_ascii=False,
    )


def buscar_produtos_da_loja(termo: str, categoria: str = "", limite: int = 15) -> str:
    """Busca produtos cadastrados na loja pelo nome, descrição ou categoria.

    termo: uma ou duas palavras-chave curtas (ex.: 'sulfato', 'ivermectina', 'fertilizante').
    categoria: opcional, parte do nome de uma categoria para restringir (ex.: 'veterin').
    Os resultados vêm ordenados por relevância. Cada produto traz nome, descrição,
    categoria, preço, unidade e estoque. Estoque 'não controlado no sistema' significa
    que a loja não registra a quantidade, e não que o produto acabou.
    Se nada vier, tente outro termo ou use listar_produtos_da_categoria.
    """
    try:
        produtos = _carregar_produtos()
    except Exception as exc:
        return f"Não consegui ler o cadastro da loja. Detalhe: {exc}"

    filtro_categoria = _normalizar(categoria)
    if filtro_categoria:
        produtos = [p for p in produtos if filtro_categoria in _normalizar(p["categoria"])]

    palavras = _palavras(termo)
    if not palavras:
        return "Informe uma palavra-chave com pelo menos 3 letras."

    pontuados: list[tuple[int, dict]] = []
    for produto in produtos:
        nome = _normalizar(produto["nome"])
        categoria_p = _normalizar(produto["categoria"])
        descricao = _normalizar(produto["descricao"])
        nota = 0
        for palavra in palavras:
            if palavra in nome:
                nota += 3
            if palavra in categoria_p:
                nota += 2
            if palavra in descricao:
                nota += 1
        if nota:
            pontuados.append((nota, produto))
    pontuados.sort(key=lambda par: (-par[0], par[1]["nome"]))

    if not pontuados:
        return f"Nenhum produto cadastrado combina com '{termo}'. Tente um sinônimo ou veja as categorias."
    quantos = _limite(limite, 15)
    return _resposta([p for _, p in pontuados[:quantos]], len(pontuados))


def listar_produtos_da_categoria(categoria: str, limite: int = 60) -> str:
    """Lista os produtos cadastrados de uma categoria (aceita só parte do nome).

    Use quando a pergunta pedir 'qual dos que tenho serve para X': liste a categoria
    certa (ex.: 'Medicamentos veterinários', 'Fertilizantes') e depois julgue cada
    item pela descrição ou pela pesquisa na web. A descrição do cadastro costuma
    estar vazia, então o nome do produto é a pista principal.
    """
    try:
        produtos = _carregar_produtos()
    except Exception as exc:
        return f"Não consegui ler o cadastro da loja. Detalhe: {exc}"
    filtro = _normalizar(categoria)
    if not filtro:
        return "Informe o nome (ou parte do nome) da categoria."
    achados = [p for p in produtos if filtro in _normalizar(p["categoria"])]
    if not achados:
        return f"Nenhuma categoria cadastrada combina com '{categoria}'. Use listar_categorias_da_loja."
    quantos = _limite(limite, 60)
    return _resposta(achados[:quantos], len(achados))
