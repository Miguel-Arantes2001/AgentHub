# Market B2B: pesquisa de fornecedores e preços de compra.
#
# Lê PDFs e imagens de catalogos/, pesquisa na web e salva o relatório em output/.
# Para OCR de imagem, instale também pillow, pytesseract e o Tesseract.
#
# Rodar sozinho, na raiz do projeto:
#   uv run python backend/price/agent_b2b/b2b_workflow.py

import os
import re
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import windows_certs  # noqa: F401 - manter antes dos imports que acessam a rede

from dotenv import load_dotenv
from pypdf import PdfReader

from agno.agent import Agent
from agno.models.google import Gemini
from agno.skills import LocalSkills, Skills
from agno.tools.websearch import WebSearchTools
from agno.tools.tavily import TavilyTools
from agno.tools.file import FileTools
from agno.team import Team, TeamMode
from agno.workflow import Workflow, Step, Loop
from agno.workflow.types import StepInput, StepOutput


# --- Configuração ---

load_dotenv()

BASE_DIR = Path(__file__).parent
CATALOGOS_DIR = BASE_DIR / "catalogos"
OUTPUT_DIR = BASE_DIR / "output"

CATALOGOS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

MIN_OFERTAS_POR_ITEM = 2
MAX_TENTATIVAS = 2

TIPOS_FORNECEDOR = (
    "fabricante",
    "distribuidor",
    "cooperativa",
    "loja",
    "marketplace",
)

EQUIVALENCIAS = ("identico", "equivalente", "parcial")

API_KEY = os.getenv("GOOGLE_API_KEY")

# Se o Tesseract não estiver no PATH do Windows, aponte o executável:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Estado da pesquisa atual. Fica em memória e é zerado a cada execução.
ITENS_SOLICITADOS = []
FORNECEDORES_PREFERENCIA = []
FORNECEDORES = []
OFERTAS = []

PEDIDO_COMPLETO = ""
AVISOS_CATALOGOS = []


# --- Ferramentas e funções auxiliares ---

file_tools = FileTools(
    base_dir=OUTPUT_DIR,
    enable_save_file=True,
    enable_read_file=True,
    enable_list_files=True,
)


def criar_modelo(model_id: str) -> Gemini:
    return Gemini(
        id=model_id,
        api_key=API_KEY,
        max_output_tokens=4096,
        retries=2,
        delay_between_retries=30,
        exponential_backoff=True,
        timeout=60,
    )


def criar_ferramentas_web():
    if os.getenv("TAVILY_API_KEY"):
        return [TavilyTools()]

    return [WebSearchTools()]


busca_web = criar_ferramentas_web()
skill_pesquisa = Skills(loaders=[LocalSkills(str(BASE_DIR.parent / "skills" / "b2b-pesquisa"))])
skill_relatorio = Skills(loaders=[LocalSkills(str(BASE_DIR.parent / "skills" / "b2b-relatorio"))])


def normalizar_unidade(quantidade: float, unidade: str):
    """500 g vira 0,5 kg; 500 ml vira 0,5 L. Serve para comparar preço por unidade."""

    unidade = unidade.strip().lower()

    if unidade in ("g", "grama", "gramas"):
        return quantidade / 1000, "kg"

    if unidade in ("kg", "quilo", "quilos", "quilograma"):
        return quantidade, "kg"

    if unidade in ("ml", "mililitro", "mililitros"):
        return quantidade / 1000, "L"

    if unidade in ("l", "litro", "litros"):
        return quantidade, "L"

    if unidade in ("un", "un.", "unidade", "unidades"):
        return quantidade, "unidade"

    return quantidade, unidade


def extrair_itens(texto: str) -> list:
    """Separa os produtos por vírgula, ponto e vírgula ou quebra de linha, sem repetir."""

    itens = re.split(r"[,;\n]+", texto)

    return list(dict.fromkeys(
        item.strip()
        for item in itens
        if item.strip()
    ))


def extrair_catalogos() -> str:
    """Lê os arquivos de catalogos/: texto dos PDFs e OCR das imagens.

    O resultado vai para os agentes como contexto do pedido.
    """

    textos = []
    AVISOS_CATALOGOS.clear()

    arquivos = [
        arquivo for arquivo in CATALOGOS_DIR.iterdir()
        if arquivo.is_file()
    ]

    if not arquivos:
        return "Nenhum catálogo foi disponibilizado."

    for arquivo in arquivos:
        try:
            texto = ""

            if arquivo.suffix.lower() == ".pdf":
                leitor = PdfReader(str(arquivo))

                paginas = []
                for pagina in leitor.pages:
                    paginas.append(pagina.extract_text() or "")

                texto = "\n".join(paginas)

                if not texto.strip():
                    AVISOS_CATALOGOS.append(
                        f"{arquivo.name}: PDF sem texto extraível. "
                        "Pode ser um documento digitalizado."
                    )

            elif arquivo.suffix.lower() in (
                ".png", ".jpg", ".jpeg", ".webp", ".bmp"
            ):
                try:
                    from PIL import Image
                    import pytesseract
                except ImportError:
                    AVISOS_CATALOGOS.append(
                        f"{arquivo.name}: para ler imagem, instale pillow e pytesseract."
                    )
                    continue
                imagem = Image.open(arquivo)
                texto = pytesseract.image_to_string(
                    imagem,
                    lang="por+eng"
                )

            else:
                continue

            if texto.strip():
                textos.append(
                    f"\n\n### CATÁLOGO: {arquivo.name}\n{texto[:20000]}"
                )

        except Exception as erro:
            AVISOS_CATALOGOS.append(
                f"{arquivo.name}: não foi possível extrair o conteúdo: {erro}"
            )

    if not textos:
        return "Nenhum texto foi extraído dos catálogos."

    # Teto de 60 mil caracteres no total, para não estourar o contexto.
    return "\n".join(textos)[:60000]


# --- Registro de fornecedores e ofertas ---

def registrar_fornecedor(
    nome: str,
    tipo: str,
    url: str,
    regiao_atendida: str = "",
    pedido_minimo: float = 0,
    prazo_entrega_dias: int = 0,
    formas_pagamento: str = "",
    observacoes: str = "",
) -> str:

    if not url.startswith("http"):
        return "ERRO: informe uma URL real do fornecedor."

    if tipo not in TIPOS_FORNECEDOR:
        return f"Tipo inválido. Use: {TIPOS_FORNECEDOR}"

    dados = {
        "nome": nome,
        "tipo": tipo,
        "url": url,
        "regiao": regiao_atendida,
        "pedido_minimo": pedido_minimo,
        "prazo_entrega": prazo_entrega_dias,
        "pagamento": formas_pagamento,
        "observacoes": observacoes,
    }

    for fornecedor in FORNECEDORES:
        if fornecedor["nome"].lower() == nome.lower():
            fornecedor.update(dados)
            return f"Fornecedor {nome} atualizado."

    FORNECEDORES.append(dados)

    return f"Fornecedor {nome} registrado."


def registrar_oferta(
    item_solicitado: str,
    fonte: str,
    item_ofertado: str,
    preco: float,
    quantidade_embalagem: float,
    unidade_embalagem: str,
    referencia: str,
    tipo_fonte: str = "web",
    equivalencia: str = "identico",
    url: str = "",
    frete: float = 0,
    desconto_percentual: float = 0,
    data_preco: str = "",
    observacoes: str = "",
) -> str:
    """
    Registra uma oferta encontrada na web ou em catálogo.

    Para ofertas da web, informe uma URL.
    Para ofertas de catálogo, informe o nome do arquivo e página,
    por exemplo: catalogo_fornecedor.pdf, página 4.
    """

    if preco <= 0 or quantidade_embalagem <= 0:
        return "ERRO: preço e quantidade devem ser maiores que zero."

    if item_solicitado not in ITENS_SOLICITADOS:
        return (
            "ERRO: item_solicitado deve corresponder a um dos "
            f"itens da pesquisa: {ITENS_SOLICITADOS}"
        )

    if tipo_fonte not in ("web", "catalogo"):
        return "ERRO: tipo_fonte deve ser web ou catalogo."

    if tipo_fonte == "web" and not url.startswith("http"):
        return "ERRO: ofertas da web precisam de uma URL válida."

    if tipo_fonte == "catalogo" and not referencia.strip():
        return "ERRO: informe o arquivo e a página do catálogo."

    if equivalencia not in EQUIVALENCIAS:
        return f"ERRO: equivalência deve ser {EQUIVALENCIAS}."

    # Mesma fonte não entra duas vezes para o mesmo item.
    for oferta in OFERTAS:
        if (
            oferta["item_solicitado"].lower() == item_solicitado.lower()
            and oferta["referencia"].lower() == referencia.lower()
        ):
            return "Oferta dessa fonte já registrada para esse item."

    quantidade_base, unidade_base = normalizar_unidade(
        quantidade_embalagem,
        unidade_embalagem,
    )

    if quantidade_base <= 0:
        return "ERRO: quantidade da embalagem inválida."

    preco_unitario = preco / quantidade_base

    OFERTAS.append({
        "item_solicitado": item_solicitado,
        "fonte": fonte,
        "item_ofertado": item_ofertado,
        "preco": float(preco),
        "quantidade": float(quantidade_embalagem),
        "unidade_embalagem": unidade_embalagem,
        "embalagem": f"{quantidade_embalagem:g} {unidade_embalagem}",
        "preco_unitario": preco_unitario,
        "unidade_base": unidade_base,
        "referencia": referencia,
        "tipo_fonte": tipo_fonte,
        "url": url,
        "equivalencia": equivalencia,
        "frete": float(frete),
        "desconto_percentual": float(desconto_percentual),
        "data_preco": data_preco or date.today().isoformat(),
        "observacoes": observacoes,
    })

    return (
        f"Oferta registrada para {item_solicitado}. "
        f"Total de ofertas: {len(OFERTAS)}."
    )


def ofertas_do_item(item: str) -> list:
    return [
        oferta for oferta in OFERTAS
        if oferta["item_solicitado"].lower() == item.lower()
    ]


def ofertas_validas() -> list:
    return [
        oferta for oferta in OFERTAS
        if oferta["preco"] > 0
        and oferta["quantidade"] > 0
        and (
            oferta["tipo_fonte"] == "catalogo"
            or oferta["url"].startswith("http")
        )
    ]


def ofertas_b2b_suficientes(outputs: list) -> bool:
    """Para o loop quando todo produto já tem o mínimo de ofertas."""

    return all(
        len(ofertas_do_item(item)) >= MIN_OFERTAS_POR_ITEM
        for item in ITENS_SOLICITADOS
    )


# --- Avisos e dossiê ---

def avisos_qualidade() -> list:
    avisos = []

    for item in ITENS_SOLICITADOS:
        ofertas = ofertas_do_item(item)

        if len(ofertas) < MIN_OFERTAS_POR_ITEM:
            avisos.append(
                f"{item}: foram encontradas {len(ofertas)} oferta(s). "
                f"Meta: {MIN_OFERTAS_POR_ITEM}."
            )

        if ofertas and all(
            oferta["tipo_fonte"] == "catalogo"
            for oferta in ofertas
        ):
            avisos.append(
                f"{item}: ofertas encontradas somente em catálogos. "
                "É recomendável confirmar os preços com os fornecedores."
            )

    tem_b2b = any(
        fornecedor["tipo"] in (
            "fabricante", "distribuidor", "cooperativa"
        )
        for fornecedor in FORNECEDORES
    )

    if FORNECEDORES and not tem_b2b:
        avisos.append(
            "Nenhum fabricante, distribuidor ou cooperativa foi "
            "identificado. As fontes encontradas podem ser apenas varejistas."
        )

    if AVISOS_CATALOGOS:
        avisos.extend(AVISOS_CATALOGOS)

    return avisos


def montar_dossie() -> str:
    linhas = [
        "# Dossiê da pesquisa B2B",
        f"Data: {date.today().isoformat()}",
        f"Itens solicitados: {', '.join(ITENS_SOLICITADOS)}",
    ]

    linhas.append("\n## Fornecedores encontrados")

    if FORNECEDORES:
        for fornecedor in FORNECEDORES:
            linhas.append(
                f"- {fornecedor['nome']} | "
                f"{fornecedor['tipo']} | "
                f"{fornecedor['url']} | "
                f"Região: {fornecedor['regiao']} | "
                f"Pedido mínimo: R$ {fornecedor['pedido_minimo']:.2f}"
            )
    else:
        linhas.append("- Nenhum fornecedor registrado.")

    linhas.append("\n## Ofertas por produto")

    for item in ITENS_SOLICITADOS:
        ofertas = sorted(
            ofertas_do_item(item),
            key=lambda oferta: oferta["preco_unitario"],
        )

        linhas.append(f"\n### {item}")

        if not ofertas:
            linhas.append("- Nenhuma oferta encontrada.")
            continue

        for oferta in ofertas:
            linhas.append(
                f"- Fonte: {oferta['fonte']}\n"
                f"  Produto encontrado: {oferta['item_ofertado']}\n"
                f"  Embalagem: {oferta['embalagem']}\n"
                f"  Preço: R$ {oferta['preco']:.2f}\n"
                f"  Preço por {oferta['unidade_base']}: "
                f"R$ {oferta['preco_unitario']:.2f}\n"
                f"  Equivalência: {oferta['equivalencia']}\n"
                f"  Tipo de fonte: {oferta['tipo_fonte']}\n"
                f"  Referência: {oferta['referencia']}\n"
                f"  URL: {oferta['url'] or 'Não se aplica'}\n"
                f"  Frete informado: R$ {oferta['frete']:.2f}\n"
                f"  Desconto: {oferta['desconto_percentual']}%\n"
                f"  Data do preço: {oferta['data_preco']}\n"
                f"  Observações: {oferta['observacoes']}"
            )

    linhas.append("\n## Avisos de qualidade")

    avisos = avisos_qualidade()

    if avisos:
        linhas.extend(f"- {aviso}" for aviso in avisos)
    else:
        linhas.append("- Nenhum aviso automático.")

    return "\n".join(linhas)


# --- Agentes ---

supplier_collector_agent = Agent(
    name="supplier_collector_agent",
    model=criar_modelo("gemini-3.5-flash-lite"),
    tools=busca_web + [registrar_fornecedor],
    skills=skill_pesquisa,
    add_datetime_to_context=True,
    markdown=True,
    instructions=[
        "Carregue a skill 'b2b-pesquisa' com get_skill_instructions e siga só Fornecedores.",
    ],
    role="Encontra fabricantes, distribuidores e fornecedores.",
)


price_collector_agent = Agent(
    name="price_collector_agent",
    model=criar_modelo("gemini-3.5-flash-lite"),
    tools=busca_web + [registrar_oferta],
    skills=skill_pesquisa,
    add_datetime_to_context=True,
    markdown=True,
    instructions=[
        "Carregue a skill 'b2b-pesquisa' com get_skill_instructions e siga só Preços.",
    ],
    role="Pesquisa preços, embalagens e condições comerciais.",
)


analyst_agent = Agent(
    name="analyst_agent",
    model=criar_modelo("gemini-3.5-flash-lite"),
    skills=skill_relatorio,
    markdown=True,
    instructions=[
        "Carregue a skill 'b2b-relatorio' com get_skill_instructions e siga só Análise.",
    ],
)


report_agent = Agent(
    name="report_agent",
    model=criar_modelo("gemini-3.5-flash-lite"),
    tools=[file_tools],
    skills=skill_relatorio,
    markdown=True,
    instructions=[
        "Carregue a skill 'b2b-relatorio' com get_skill_instructions e siga só Relatório.",
        "Salve com save_file em relatorio_compras_b2b.md.",
    ],
)


# --- Time de pesquisa ---

research_team = Team(
    name="research_team",
    members=[
        supplier_collector_agent,
        price_collector_agent,
    ],
    mode=TeamMode.coordinate,
    model=criar_modelo("gemini-3.5-flash-lite"),
    add_datetime_to_context=True,
    markdown=True,
    share_member_interactions=True,
    skills=skill_pesquisa,
    instructions=[
        "Carregue a skill 'b2b-pesquisa' com get_skill_instructions e siga só Coordenação.",
    ],
)


# --- Passos e loop ---

def coletar_precos_b2b(step_input: StepInput) -> StepOutput:
    """Pesquisa de novo só os produtos que ainda estão abaixo do mínimo de ofertas."""

    itens_pendentes = [
        item for item in ITENS_SOLICITADOS
        if len(ofertas_do_item(item)) < MIN_OFERTAS_POR_ITEM
    ]

    if not itens_pendentes:
        return StepOutput(
            content="Todos os produtos atingiram a meta de ofertas."
        )

    contexto = (
        f"{PEDIDO_COMPLETO}\n\n"
        f"Produtos que ainda precisam de ofertas: {itens_pendentes}\n"
        "Busque fontes novas e não repita as ofertas já registradas.\n"
        "Concentre a pesquisa somente nos produtos pendentes.\n"
    )

    try:
        price_collector_agent.run(contexto)
    except Exception as erro:
        return StepOutput(content=f"Falha na coleta: {erro}")

    resumo = {
        item: len(ofertas_do_item(item))
        for item in ITENS_SOLICITADOS
    }

    return StepOutput(
        content=f"Quantidade de ofertas por produto: {resumo}"
    )


def gerar_dossie(step_input: StepInput) -> StepOutput:
    texto = montar_dossie()

    print(
        f"\nDossiê: {len(FORNECEDORES)} fornecedores e "
        f"{len(ofertas_validas())} ofertas válidas."
    )

    return StepOutput(content=texto)


# --- Workflow ---

pesquisa_step = Step(
    name="pesquisa_inicial",
    description="Pesquisa fornecedores e preços de todos os produtos.",
    team=research_team,
)

precos_loop = Loop(
    name="complementar_precos",
    description="Busca novas ofertas para produtos com poucos resultados.",
    steps=[
        Step(
            name="coletar_precos_b2b",
            description="Pesquisa ofertas adicionais para os itens pendentes.",
            executor=coletar_precos_b2b,
        )
    ],
    max_iterations=MAX_TENTATIVAS,
    end_condition=ofertas_b2b_suficientes,
)

dossie_step = Step(
    name="dossie",
    description="Organiza fornecedores e ofertas por produto.",
    executor=gerar_dossie,
)

analise_step = Step(
    name="analise",
    description="Analisa e compara os preços encontrados.",
    agent=analyst_agent,
)

relatorio_step = Step(
    name="relatorio",
    description="Gera e salva o relatório final.",
    agent=report_agent,
)

def _bloco(texto: str, rotulo: str) -> str | None:
    """Trecho depois de 'Produtos:' ou 'Fornecedores:', até o outro rótulo."""
    achado = re.search(
        rf"(?im)^{rotulo}\s*:\s*(.*?)(?=^(?:Produtos|Fornecedores)\s*:|\Z)",
        texto,
        re.S,
    )
    if not achado:
        return None
    return achado.group(1).strip()


def preparar_pedido(step_input: StepInput) -> StepOutput:
    """O AgentOS entrega só o texto. Este passo monta o mesmo pedido que o __main__ monta."""
    global ITENS_SOLICITADOS, FORNECEDORES_PREFERENCIA, PEDIDO_COMPLETO

    OFERTAS.clear()
    FORNECEDORES.clear()

    texto = step_input.get_input_as_string() or ""
    produtos = _bloco(texto, "Produtos")
    fornecedores = _bloco(texto, "Fornecedores")
    if produtos is None:
        ITENS_SOLICITADOS = extrair_itens(texto)
        FORNECEDORES_PREFERENCIA = []
    else:
        ITENS_SOLICITADOS = extrair_itens(produtos)
        FORNECEDORES_PREFERENCIA = extrair_itens(fornecedores or "")

    if not ITENS_SOLICITADOS:
        return StepOutput(content="Informe pelo menos um produto.", stop=True)

    PEDIDO_COMPLETO = (
        "PESQUISA DE COMPRAS B2B\n\n"
        f"Produtos solicitados: {ITENS_SOLICITADOS}\n\n"
        f"Fornecedores preferenciais: "
        f"{FORNECEDORES_PREFERENCIA or 'Nenhum informado'}\n\n"
        "CATÁLOGOS DISPONÍVEIS:\n"
        f"{extrair_catalogos()}\n\n"
        "Pesquise todos os produtos. Registre fornecedores e ofertas "
        "usando as funções disponíveis. Não invente informações."
    )
    return StepOutput(content=PEDIDO_COMPLETO)


workflow = Workflow(
    id="market-b2b",
    name="workflow-b2b-price-research",
    steps=[
        Step(name="preparar", executor=preparar_pedido),
        pesquisa_step,
        precos_loop,
        dossie_step,
        analise_step,
        relatorio_step,
    ],
)


# --- Execução pelo terminal ---

if __name__ == "__main__":

    if not API_KEY:
        raise ValueError(
            "GOOGLE_API_KEY não encontrada no arquivo .env."
        )

    print("\n=== PESQUISA B2B ===\n")

    texto_itens = input(
        "Informe os produtos que deseja pesquisar "
        "(separe por vírgula):\n> "
    )

    ITENS_SOLICITADOS = extrair_itens(texto_itens)

    if not ITENS_SOLICITADOS:
        raise ValueError("Informe pelo menos um produto.")

    texto_fornecedores = input(
        "\nFornecedores preferenciais (opcional, separados por vírgula):\n> "
    )

    FORNECEDORES_PREFERENCIA = extrair_itens(texto_fornecedores)

    # Começa sem sobras de uma pesquisa anterior.
    OFERTAS.clear()
    FORNECEDORES.clear()

    print("\nLendo catálogos...")
    catalogos_texto = extrair_catalogos()

    print(f"Produtos: {ITENS_SOLICITADOS}")
    print(f"Fornecedores informados: {FORNECEDORES_PREFERENCIA or 'Nenhum'}")
    print(f"Catálogos: {CATALOGOS_DIR}")

    PEDIDO_COMPLETO = (
        "PESQUISA DE COMPRAS B2B\n\n"
        f"Produtos solicitados: {ITENS_SOLICITADOS}\n\n"
        f"Fornecedores preferenciais: "
        f"{FORNECEDORES_PREFERENCIA or 'Nenhum informado'}\n\n"
        "CATÁLOGOS DISPONÍVEIS:\n"
        f"{catalogos_texto}\n\n"
        "Pesquise todos os produtos. Registre fornecedores e ofertas "
        "usando as funções disponíveis. Não invente informações."
    )

    print("\nIniciando workflow...\n")

    workflow.print_response(
        PEDIDO_COMPLETO,
        stream=True,
        markdown=True,
    )

    print("\n=== PESQUISA FINALIZADA ===")
    print(f"Fornecedores: {len(FORNECEDORES)}")
    print(f"Ofertas válidas: {len(ofertas_validas())}")

    for item in ITENS_SOLICITADOS:
        print(f"- {item}: {len(ofertas_do_item(item))} oferta(s)")

    print(f"\nRelatório esperado em: {OUTPUT_DIR}")