import os

# O Avast grava SSLKEYLOGFILE com um dispositivo. O OpenSSL do Python do uv aborta ao abri-lo.
os.environ.pop("SSLKEYLOGFILE", None)

import json
import re
import unicodedata
import urllib.request
from pathlib import Path

import truststore
from ddgs import DDGS
from dotenv import load_dotenv

from agno.agent import Agent
from agno.db.in_memory import InMemoryDb
from agno.models.google import Gemini
from agno.workflow import Condition, Loop, Step, Workflow
from agno.workflow.types import StepInput, StepOutput

from loja_db import buscar_produtos_da_loja, listar_categorias_da_loja, listar_produtos_da_categoria

truststore.inject_into_ssl()
load_dotenv()

RAIZ = Path(__file__).parent


def ler_skill(nome: str) -> str:
    """Texto da skill sem o cabeçalho. Vai direto nas instruções do agente.

    Evita a volta extra ao modelo que get_skill_instructions custava a cada execução.
    """
    texto = (RAIZ / "skills" / nome / "SKILL.md").read_text(encoding="utf-8")
    return texto.split("---", 2)[2].strip()


# retries curtos: erro temporário (503) tenta de novo em 3, 6 e 12 s em vez de virar a resposta.
modelo = Gemini(id="gemini-3.5-flash-lite", retries=3, delay_between_retries=3, exponential_backoff=True)


def web_search(query: str, max_results: int = 5) -> str:
    """Pesquisa texto na web. Se não houver resultado, devolve um aviso em vez de erro."""
    try:
        with DDGS() as ddgs:
            resultados = ddgs.text(query, max_results=max_results, region="br-pt")
    except Exception as exc:
        return f"Nenhum resultado para '{query}'. Tente o nome técnico ou um sinônimo. Detalhe: {exc}"
    if not resultados:
        return f"Nenhum resultado para '{query}'. Tente o nome técnico ou um sinônimo."
    return json.dumps(resultados, ensure_ascii=False)


def _imagem_abre(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    pedido = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-1023"},
    )
    try:
        with urllib.request.urlopen(pedido, timeout=5) as resposta:
            if resposta.status not in (200, 206):
                return False
            tipo = (resposta.headers.get("Content-Type") or "").lower()
            if tipo.startswith("image/"):
                return True
            caminho = url.lower().split("?", 1)[0]
            return caminho.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
    except Exception:
        return False


def _consultas_da_foto(texto: str, assunto: str) -> list[str]:
    populares = [
        nome.strip()
        for nome in re.findall(r"\*\*([^*]{3,80})\*\*", texto)
        if "?" not in nome
    ]
    tecnico = ""
    achado = re.search(r"nome técnico[^*.\n]{0,60}\*\*([^*]+)\*\*", texto, re.I)
    if achado:
        tecnico = achado.group(1).strip(" .")
    consultas: list[str] = []
    if populares:
        troca = re.match(r"(.+?)\s+de\s+(.+)", populares[0], re.I)
        if troca:
            consultas.append(f"{troca.group(1)} para {troca.group(2)}")
        else:
            consultas.append(populares[0])
    if tecnico and tecnico not in consultas:
        consultas.append(tecnico)
    if not consultas and assunto:
        consultas.append(assunto)
    texto_min = texto.lower()
    if "gás" in texto_min or " a gas" in texto_min:
        consultas = [c if "gás" in c.lower() else f"{c} a gás" for c in consultas]
    unicas: list[str] = []
    for consulta in consultas:
        if consulta not in unicas:
            unicas.append(consulta)
    return unicas


def _nota_do_titulo(titulo: str, texto: str, consulta: str) -> int:
    titulo_min = (titulo or "").lower()
    explicacao = texto.lower()
    for fora in ("camiseta", "cangaço", "cangaco", "cangaceiro", "blusa", "tshirt", "t-shirt", "rei do"):
        if fora in titulo_min and fora not in explicacao:
            return -1
    if "sem camisa" in titulo_min and "camisa" in consulta.lower():
        return -1
    if "vidro" in titulo_min and any(palavra in explicacao for palavra in ("tecido", "redinha")):
        return -1
    nota = 0
    for palavra in re.findall(r"[a-záàâãéêíóôõúç]{4,}", consulta.lower()):
        if palavra in titulo_min:
            nota += 2
    return nota


def buscar_imagem(texto: str, assunto: str = "") -> str:
    """Busca uma foto do produto e descarta resultado de outro assunto."""
    consultas = _consultas_da_foto(texto, assunto)
    melhor: tuple[int, str, str] | None = None
    for consulta in consultas:
        try:
            with DDGS() as ddgs:
                resultados = ddgs.images(consulta, max_results=8, region="br-pt")
        except Exception:
            continue
        for item in resultados or []:
            titulo = item.get("title") or ""
            nota = _nota_do_titulo(titulo, texto, consulta)
            if nota < 1:
                continue
            if melhor and nota <= melhor[0]:
                continue
            url = item.get("image")
            if _imagem_abre(url):
                melhor = (nota, titulo, url)
        if melhor and melhor[0] >= 5:
            break
    if not melhor:
        return "Nenhuma foto desse produto com link que abre."
    _, titulo, url = melhor
    return json.dumps({"titulo": titulo, "url": url}, ensure_ascii=False)


def busca_pronta(saidas: list[StepOutput]) -> bool:
    if not saidas:
        return False
    texto = saidas[-1].content
    return isinstance(texto, str) and "BUSCA_OK" in texto


identificar = Agent(
    name="identificar",
    model=modelo,
    tools=[web_search],
    instructions=[
        "Você identifica o produto que o cliente pediu no balcão de uma loja agro.",
        "Siga estas regras de nomes populares antes de pesquisar:\n" + ler_skill("nomes-populares"),
        "Pesquise na web com web_search.",
        "Se a pergunta for 'qual' produto usar, busque também 2 ou 3 nomes comerciais ou princípios ativos e inclua na resposta.",
        "Se a mensagem já trouxer um produto e a pergunta for foto, 'disso' ou 'esse', mantenha esse produto.",
        "Se der para explicar o produto, comece a resposta com BUSCA_OK.",
        "Inclua a pergunta original, se pediram imagem (sim ou nao), o nome popular, o nome técnico, para que serve e se é saúde animal.",
        "Se a busca ficar vaga, não escreva BUSCA_OK. Repita a pergunta original e diga qual termo técnico pesquisar na próxima tentativa.",
    ],
)

responder = Agent(
    name="responder",
    model=modelo,
    tools=[web_search],
    instructions=[
        "Você é o Oráculo, assistente do atendente no balcão.",
        "Siga este formato de resposta:\n" + ler_skill("resposta-balcao"),
        "A mensagem recebida é o que a identificação encontrou. Não repita o marcador BUSCA_OK.",
        "Não troque o produto por um exemplo da skill.",
        "Responda primeiro o que foi perguntado. Se pediram 'qual' produto, cite as opções encontradas antes de explicar a categoria.",
        "Use web_search só se ainda faltar o que o produto é, para que serve ou como se usa.",
        "Não escreva link de imagem. Se pediram foto, explique o produto mesmo assim.",
    ],
)

consultar_loja = Agent(
    name="consultar_loja",
    model=modelo,
    tools=[
        listar_categorias_da_loja,
        buscar_produtos_da_loja,
        listar_produtos_da_categoria,
        web_search,
    ],
    instructions=[
        "Você é o Oráculo, assistente do atendente no balcão de uma loja agro. Responda em português, para o atendente usar na hora.",
        "A pergunta é sobre o que a loja tem cadastrado no sistema. Consulte o cadastro com as tools antes de responder. Nunca responda de memória.",
        "Se não souber a categoria, chame listar_categorias_da_loja. Para um tipo de produto, use buscar_produtos_da_loja ou listar_produtos_da_categoria.",
        "Só cite como 'da loja' um produto que veio de uma tool. Não invente produto, preço nem estoque.",
        "Estoque com número é a quantidade em loja (0 é zerado). Estoque 'não controlado no sistema' quer dizer que a loja não registra a quantidade: diga isso e nunca diga que o produto está em falta ou acabou.",
        "Se a pergunta for 'qual dos que tenho serve para X' (ex.: remédio para sarna em cachorro): primeiro busque no cadastro pela palavra do problema (ex.: 'sarna'), porque a descrição de alguns itens já traz a indicação. Depois liste a categoria certa (e categorias vizinhas, como Inseticidas e venenos), escolha até 5 candidatos plausíveis e, se a descrição do cadastro não disser a indicação, confira com web_search pelo nome do produto.",
        "Confira a espécie do produto. Se a pergunta é sobre cães ou gatos, não indique produto de grande animal (bovino, equino, suíno) nem produto cuja espécie você não confirmou. Ao citar um item, diga para qual espécie ele é.",
        "Se um item do cadastro diz na descrição a indicação pedida, ele entra na resposta, mesmo sendo de outra categoria.",
        "Separe o que vem do cadastro (nome, preço, estoque, descrição) do que vem da web (indicação, princípio ativo). Se a indicação veio só da web, diga isso.",
        "Medicamento veterinário: não invente dose, via ou intervalo. Diga que a dose e o diagnóstico precisam ser confirmados na bula e com o veterinário.",
        "Se nada no cadastro servir, diga que não achou, diga o que procurou e sugira o que o cliente pode precisar, sem apresentar isso como item da loja.",
        "Formato: resposta direta primeiro, depois uma lista curta com nome, preço (R$) e estoque. Sem links de imagem.",
    ],
)


_PISTAS_DE_CADASTRO = (
    r"cadastrad",
    r"cadastro",
    r"\berp\b",
    r"\b(no|em|do|meu|nosso|pelo)\s+estoque",
    r"\b(na|da|nossa|minha)\s+loja\b",
    r"\bse\s+(eu\s+|nos\s+)?(tenho|temos)\b",
    r"^\W*(tenho|temos)\b(?!\s+(um\s+|uma\s+)?(cliente|clientes|duvida|pergunta)\b)",
    r"\b(quais|qual|quantos|quantas|que)\b.{0,60}\b(tenho|temos)\b",
    r"\b(tenho|temos)\b.{0,30}\b(aqui|a venda|disponivel)\b",
    r"\b(vendo|vendemos)\b",
)


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _pergunta_de_cadastro(step_input: StepInput) -> bool:
    """True se o atendente pergunta sobre o que a loja tem cadastrado no ERP.

    Só olha a pergunta atual (o contexto da conversa anterior não conta) e aceita
    'Contexto: Cadastros' do formulário como pedido explícito. Na dúvida devolve
    False, e a pergunta segue o fluxo de sempre.
    """
    texto = str(step_input.get_input_as_string() or "")
    texto = texto.split("Produto já explicado", 1)[0]
    texto = _sem_acento(texto.replace("Pergunta atual do atendente:", " "))
    if re.search(r"contexto:\s*cadastros", texto):
        return True
    return any(re.search(pista, texto, re.S | re.M) for pista in _PISTAS_DE_CADASTRO)


def anexar_foto_se_pediu(step_input: StepInput) -> StepOutput:
    """Último passo: se pediram foto, anexa uma. O texto da resposta continua."""
    pergunta = step_input.get_input_as_string() or ""
    texto = str(step_input.previous_step_content or "").strip()
    if not texto:
        texto = "Não consegui montar a resposta. Tente reformular a pergunta."
    if _pediu_foto(pergunta):
        texto = _anexar_foto(pergunta, texto)
    return StepOutput(content=texto)


def _pediu_foto(texto: str) -> bool:
    consulta = texto.lower()
    return any(palavra in consulta for palavra in ("foto", "imagem", "figura", "mostra", "mostre"))


def _texto_do_workflow(resultado) -> str:
    if getattr(resultado, "content", None):
        return str(resultado.content).strip()
    partes = []
    for passo in getattr(resultado, "step_results", None) or []:
        conteudo = getattr(passo, "content", None)
        if conteudo:
            partes.append(str(conteudo).strip())
    return "\n\n".join(partes).strip()


def _anexar_foto(assunto: str, texto: str) -> str:
    texto = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", texto).strip()
    print("Buscando uma foto do produto...")
    bruto = buscar_imagem(texto, assunto)
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        return f"{texto}\n\n{bruto}".strip()
    url = dados.get("url")
    titulo = dados.get("titulo") or ""
    if not url:
        return f"{texto}\n\nNão achei uma foto com link que abre.".strip()
    return f"{texto}\n\n![exemplo]({url})\n{titulo}".strip()


workflow = Workflow(
    id="oraculo",
    name="Oraculo de balcao",
    db=InMemoryDb(),
    add_workflow_history_to_steps=True,
    num_history_runs=1,
    steps=[
        Condition(
            name="rota",
            evaluator=_pergunta_de_cadastro,
            steps=[Step(name="consultar_loja", agent=consultar_loja)],
            else_steps=[
                Loop(
                    name="identificar_produto",
                    max_iterations=2,
                    forward_iteration_output=True,
                    end_condition=busca_pronta,
                    steps=[Step(name="identificar", agent=identificar)],
                ),
                Step(name="responder", agent=responder),
                Step(name="foto", executor=anexar_foto_se_pediu),
            ],
        ),
    ],
)


def main() -> None:
    print("Oráculo de balcão. Digite a pergunta do cliente. Enter vazio para sair.")
    contexto = ""
    assunto = ""
    while True:
        pergunta = input("\nAtendente: ").strip()
        if not pergunta:
            break
        if not (_pediu_foto(pergunta) and assunto):
            assunto = pergunta
        mensagem = pergunta
        if contexto:
            mensagem = (
                "Pergunta atual do atendente:\n"
                f"{pergunta}\n\n"
                "Produto já explicado nesta conversa. "
                "Se a pergunta disser 'disso', 'esse' ou pedir só a foto, continue neste produto:\n"
                f"{contexto}"
            )
        resultado = workflow.run(mensagem)
        texto = _texto_do_workflow(resultado)
        if not texto:
            texto = "Não consegui montar a resposta. Tente reformular a pergunta."
        contexto = texto
        print("\nOráculo:\n")
        print(texto)


if __name__ == "__main__":
    main()
