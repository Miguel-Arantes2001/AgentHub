# Market B2C: pesquisa de preço de varejo em até 3 lojas.
#
# .env: GOOGLE_API_KEY (obrigatória) e TAVILY_API_KEY (opcional; sem ela,
# a busca fica com o WebSearchTools do Agno).
#
# Rodar sozinho, na raiz do projeto:
#   uv run python backend/price/agent_b2c.py

import os
import re
import windows_certs  # noqa: F401 - manter antes de imports que possam acessar a rede

from datetime import date
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from agno.agent import Agent
from agno.models.google import Gemini
from agno.tools.websearch import WebSearchTools
from agno.tools.tavily import TavilyTools
from agno.workflow import Workflow, Step, Loop
from agno.workflow.types import StepInput, StepOutput

load_dotenv()

# Para quando houver preço em 3 lojas diferentes, ou depois de 3 tentativas.
MIN_LOJAS = 3
MAX_TENTATIVAS = 3

EQUIVALENCIAS = ("identico", "equivalente", "parcial")
OFERTAS = []


def criar_modelo(model_id: str) -> Gemini:
    return Gemini(
        id=model_id,
        api_key=os.getenv("GOOGLE_API_KEY"),
        max_output_tokens=4096,
        retries=3,
        delay_between_retries=5,
        exponential_backoff=True,
        timeout=60,
    )


def _nome_loja(nome: str) -> str:
    return " ".join(nome.strip().lower().split())


def _base(quantidade: float, unidade: str) -> tuple[float, str]:
    """500 g vira 0,5 kg; 200 ml vira 0,2 L. A média usa essa base."""
    chave = unidade.strip().lower().rstrip(".")
    if chave in {"g", "gr", "grama", "gramas"}:
        return quantidade / 1000, "kg"
    if chave in {"kg", "quilo", "quilos", "kgs"}:
        return quantidade, "kg"
    if chave == "ml":
        return quantidade / 1000, "L"
    if chave in {"l", "lt", "litro", "litros"}:
        return quantidade, "L"
    return quantidade, "un"


def _brl(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pede_preco_unitario(pedido: str) -> bool:
    """'por comprimido' ou 'por kg' pede a unidade. 'caixa de 10' pede a embalagem."""
    texto = pedido.lower()
    return re.search(
        r"\bpor\s+(kg|quilos?|litros?|l|ml|g|gramas?|un|unidades?|comprimidos?|c[aá]psulas?|doses?)\b"
        r"|\b(pre[cç]o|valor)\s+d[oa]\s+(kg|quilo|litro|unidade|comprimido)"
        r"|\bunit[aá]ri[oa]\b"
        r"|/\s*(kg|l|un)\b",
        texto,
    ) is not None


def _embalagem_pedida(pedido: str) -> tuple[float, str] | None:
    """'10 comprimidos' ou '15 kg' no pedido. Caixa sem número não vira filtro."""
    conhecidas = {
        "g", "gr", "grama", "gramas", "kg", "quilo", "quilos", "kgs",
        "ml", "l", "lt", "litro", "litros",
        "un", "und", "unidade", "unidades", "comprimido", "comprimidos",
        "capsula", "capsulas", "cápsula", "cápsulas", "dose", "doses",
    }
    for achado in re.finditer(r"(\d+(?:[.,]\d+)?)\s*([A-Za-zÀ-ú]+)", pedido):
        antes = pedido[max(0, achado.start() - 5):achado.start()].lower()
        if antes.strip().endswith("por"):
            continue
        unidade = achado.group(2).lower()
        if unidade not in conhecidas:
            continue
        quantidade = float(achado.group(1).replace(",", "."))
        return _base(quantidade, unidade)
    return None


def _pacote(oferta: dict) -> tuple[float, str]:
    return _base(oferta["quantidade"], oferta["unidade"])


def ofertas_validas() -> list:
    """Ofertas com preço, embalagem e URL."""
    return [
        oferta for oferta in OFERTAS
        if oferta["preco"] > 0
        and oferta["quantidade"] > 0
        and oferta["url"].startswith("http")
    ]


def lojas_validas() -> list:
    """Uma oferta por loja. Duas páginas da mesma loja contam como uma fonte."""
    por_loja = {}
    for oferta in ofertas_validas():
        por_loja.setdefault(_nome_loja(oferta["loja"]), oferta)
    return list(por_loja.values())


def registrar_oferta(
    loja: str,
    produto: str,
    preco: float,
    quantidade: float,
    unidade: str,
    url: str,
    equivalencia: str = "identico",
    observacoes: str = "",
) -> str:
    """
    Registra uma oferta encontrada na web.

    quantidade/unidade representam o conteúdo da embalagem:
    exemplo: 15, "kg"; 1, "unidade"; 500, "g".
    """
    if preco <= 0 or quantidade <= 0:
        return "ERRO: preço e quantidade devem ser maiores que zero."

    if not str(url).startswith("http"):
        return "ERRO: informe a URL completa da oferta."

    if equivalencia not in EQUIVALENCIAS:
        return f"ERRO: equivalência deve ser uma destas opções: {EQUIVALENCIAS}."

    if any(oferta["url"].rstrip("/") == url.rstrip("/") for oferta in OFERTAS):
        return "Oferta duplicada. Procure outra página."

    if any(_nome_loja(oferta["loja"]) == _nome_loja(loja) for oferta in OFERTAS):
        return "Essa loja já foi registrada. Procure outra loja."

    quantidade_base, unidade_base = _base(float(quantidade), unidade)
    if quantidade_base <= 0:
        return "ERRO: quantidade da embalagem inválida."

    OFERTAS.append({
        "loja": loja,
        "produto": produto,
        "preco": float(preco),
        "quantidade": float(quantidade),
        "unidade": unidade,
        "preco_base": float(preco) / quantidade_base,
        "unidade_base": unidade_base,
        "url": url,
        "equivalencia": equivalencia,
        "observacoes": observacoes,
        "data_pesquisa": date.today().isoformat(),
    })

    achadas = len(lojas_validas())
    faltam = MIN_LOJAS - achadas
    if faltam > 0:
        return f"Oferta registrada. Lojas diferentes: {achadas} de {MIN_LOJAS}. Faltam {faltam}."
    return f"Oferta registrada. {MIN_LOJAS} lojas diferentes. Pode parar."


def ofertas_b2c_suficientes(outputs: List[StepOutput]) -> bool:
    """Encerra o loop com preço em pelo menos 3 lojas diferentes."""
    return bool(outputs) and len(lojas_validas()) >= MIN_LOJAS


def _rotulo_unidade(pedido: str, unidade: str) -> str:
    texto = pedido.lower()
    if "comprimid" in texto:
        return "comprimido"
    if "capsul" in texto or "cápsul" in texto:
        return "cápsula"
    return unidade


def montar_resumo(pedido: str) -> str:
    """Menor e média na embalagem pedida. Por kg ou por comprimido só se o pedido disser isso."""
    lojas = lojas_validas()
    if not lojas:
        return f"{pedido}\n\nNenhuma loja com preço publicado."

    unitario = _pede_preco_unitario(pedido)
    if unitario:
        unidade = max(
            {o["unidade_base"] for o in lojas},
            key=lambda u: sum(o["unidade_base"] == u for o in lojas),
        )
        grupo = [o for o in lojas if o["unidade_base"] == unidade]
        outras = [o for o in lojas if o["unidade_base"] != unidade]
        grupo.sort(key=lambda o: o["preco_base"])
        valores = [o["preco_base"] for o in grupo]
        rotulo = _rotulo_unidade(pedido, unidade)
        def linha(oferta: dict) -> str:
            return (
                f"- {oferta['loja']}: {_brl(oferta['preco_base'])}/{rotulo} "
                f"(embalagem de {oferta['quantidade']:g} {oferta['unidade']} por {_brl(oferta['preco'])})"
            )
        sufixo = f"/{rotulo}"
    else:
        pedida = _embalagem_pedida(pedido)
        if pedida:
            quantidade, unidade = pedida
            grupo = [
                o for o in lojas
                if _pacote(o)[1] == unidade
                and abs(_pacote(o)[0] - quantidade) / max(quantidade, 1e-9) <= 0.05
            ]
        else:
            pacotes: dict[tuple[float, str], list] = {}
            for oferta in lojas:
                pacotes.setdefault(_pacote(oferta), []).append(oferta)
            grupo = max(pacotes.values(), key=len)
        chaves = {_pacote(o) for o in grupo}
        outras = [o for o in lojas if _pacote(o) not in chaves]
        grupo.sort(key=lambda o: o["preco"])
        valores = [o["preco"] for o in grupo]
        def linha(oferta: dict) -> str:
            return (
                f"- {oferta['loja']}: {_brl(oferta['preco'])} "
                f"por {oferta['quantidade']:g} {oferta['unidade']}"
            )
        amostra = grupo[0] if grupo else None
        sufixo = f" por {amostra['quantidade']:g} {amostra['unidade']}" if amostra else ""

    linhas = [pedido, ""]
    if not grupo:
        linhas.append("Nenhuma loja com a embalagem pedida.")
        grupo_mostrar = []
    else:
        grupo_mostrar = grupo
    for oferta in grupo_mostrar:
        linhas.append(linha(oferta))
        linhas.append(f"  {oferta['url']}")
    if outras:
        linhas.append("")
        linhas.append("Fora da média, porque a embalagem é outra:")
        for oferta in outras:
            linhas.append(
                f"- {oferta['loja']}: {_brl(oferta['preco'])} "
                f"por {oferta['quantidade']:g} {oferta['unidade']}"
            )
    if valores:
        linhas.append("")
        linhas.append(f"Menor: {_brl(valores[0])}{sufixo} — {grupo[0]['loja']}")
        linhas.append(f"Média: {_brl(sum(valores) / len(valores))}{sufixo}")
    if len(lojas) < MIN_LOJAS:
        linhas.append(f"Meta de {MIN_LOJAS} lojas: achamos {len(lojas)}.")
    return "\n".join(linhas)


# Usa Tavily quando a chave estiver configurada; caso contrário, usa a busca do Agno.
ferramentas_busca = (
    [TavilyTools()]
    if os.getenv("TAVILY_API_KEY")
    else [WebSearchTools()]
)

def ler_skill(nome: str) -> str:
    """Texto da skill sem o cabeçalho. Vai direto nas instruções do agente.

    Evita a volta extra ao modelo que get_skill_instructions custava a cada coleta.
    """
    texto = (Path(__file__).parent / "skills" / nome / "SKILL.md").read_text(encoding="utf-8")
    return texto.split("---", 2)[2].strip()


coletor_precos = Agent(
    name="b2c_price_collector",
    model=criar_modelo("gemini-3.5-flash-lite"),
    tools=ferramentas_busca + [registrar_oferta],
    add_datetime_to_context=True,
    markdown=True,
    instructions=[
        "Siga a seção Coleta destas regras:\n" + ler_skill("b2c-varejo"),
        "Use registrar_oferta. No máximo duas buscas. Depois pare.",
    ],
    role="Pesquisa e registra ofertas de produtos em lojas virtuais.",
)


def coletar_precos_b2c(step_input: StepInput) -> StepOutput:
    """Busca de novo só enquanto faltarem lojas diferentes."""
    quantidade_atual = len(lojas_validas())

    if quantidade_atual >= MIN_LOJAS:
        return StepOutput(content=f"{quantidade_atual} lojas. Meta atingida.")

    pedido = step_input.get_input_as_string() or ""
    lojas_usadas = ", ".join(o["loja"] for o in lojas_validas()) or "nenhuma"
    if quantidade_atual:
        print(f"{quantidade_atual} de {MIN_LOJAS} lojas. Buscando outras...", flush=True)

    prompt = (
        f"Produto solicitado: {pedido}\n\n"
        f"Lojas com preço: {quantidade_atual} de {MIN_LOJAS}.\n"
        f"Já registradas (não repetir): {lojas_usadas}.\n\n"
        f"Busque outras lojas até completar {MIN_LOJAS}. "
        "Uma página por loja. Registre com registrar_oferta. Não invente."
    )

    try:
        coletor_precos.run(prompt)
    except Exception as erro:
        return StepOutput(content=f"Falha durante a coleta: {erro}")

    return StepOutput(content=f"{len(lojas_validas())} de {MIN_LOJAS} lojas.")


def gerar_resumo(step_input: StepInput) -> StepOutput:
    """A resposta final é a lista curta, com menor preço e média."""
    pedido = step_input.get_input_as_string() or ""
    return StepOutput(content=montar_resumo(pedido))


pesquisa_loop = Loop(
    name="coleta_de_precos",
    description="Busca ofertas até atingir a meta ou o limite de tentativas.",
    steps=[
        Step(
            name="coletar_precos_b2c",
            description="Pesquisa novas ofertas sem repetir URLs.",
            executor=coletar_precos_b2c,
        )
    ],
    max_iterations=MAX_TENTATIVAS,
    end_condition=ofertas_b2c_suficientes,
)

resumo_step = Step(
    name="organizar_ofertas",
    description="Lista as lojas, o menor preço e a média.",
    executor=gerar_resumo,
)

def preparar_pesquisa(step_input: StepInput) -> StepOutput:
    """Zera as ofertas da pesquisa anterior. O texto do produto segue igual."""
    OFERTAS.clear()
    return StepOutput(content=step_input.get_input_as_string() or "")


workflow = Workflow(
    id="market-b2c",
    name="b2c-price-research",
    steps=[
        Step(name="preparar", executor=preparar_pesquisa),
        pesquisa_loop,
        resumo_step,
    ],
)


if __name__ == "__main__":
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("Configure GOOGLE_API_KEY no arquivo .env.")

    produto = input("Qual produto deseja pesquisar? ").strip()

    if not produto:
        raise ValueError("Informe o nome do produto.")

    OFERTAS.clear()
    print(f"Buscando preços de {produto} em {MIN_LOJAS} lojas...", flush=True)
    workflow.run(produto)
    print()
    print(montar_resumo(produto))
