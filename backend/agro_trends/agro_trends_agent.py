# Agro Trends: tendências do agro, agora e nos próximos meses.
#
#   tema -> pesquisa -> apuração (loop) -> validação
#
# Nada é gravado em arquivo: a resposta da validação é o resultado.

import windows_certs  # certificados do Windows antes de qualquer HTTPS

import os
import re
from typing import List
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from agno.agent import Agent
from agno.models.google import Gemini
from agno.skills import Skills, LocalSkills
from agno.tools.tavily import TavilyTools
from agno.workflow import Workflow, Step, Loop
from agno.workflow.types import StepOutput

MIN_FONTES = 3
MAX_TENTATIVAS_APURACAO = 3

_FONTES_SECAO = re.compile(
    r"##\s*FONTES COLETADAS(.*?)(##|$)", re.DOTALL | re.IGNORECASE
)
_FONTE_MARCADOR = re.compile(r"^-\s+\*\*", re.MULTILINE)
_URL = re.compile(r"https?://[^\s\)\]]+")

BASE_DIR = Path(__file__).parent

model = Gemini(
    id="gemini-3.5-flash-lite",
    api_key=os.getenv("GOOGLE_API_KEY"),
    max_output_tokens=8000,
)
shared_skills = Skills(loaders=[LocalSkills(str(BASE_DIR / "skills"))])

# Tavily: busca + extract (requer TAVILY_API_KEY no .env)
web_search = TavilyTools(
    api_key=os.getenv("TAVILY_API_KEY"),
    enable_search=True,
    enable_extract=True,
    topic="news",
    time_range="month",
    search_depth="basic",
    extract_depth="basic",
    include_answer=False,
)

REGRA_BUSCA = (
    "Use as tools do Tavily: busque com web_search_using_tavily e, "
    "nas 2-3 URLs mais promissoras, valide com extract_url_content. "
    "Só cite URL/título/data se a tool devolveu. "
    "Se a busca vier vazia, tente query mais curta. "
    "NUNCA invente URLs, títulos, datas ou fontes."
)


def make_agent(
    name: str,
    instructions: list[str],
    *,
    tools: list,
) -> Agent:
    return Agent(
        name=name,
        model=model,
        skills=shared_skills,
        instructions=instructions,
        tools=tools,
        add_datetime_to_context=True,
        markdown=True,
    )


pesquisador = make_agent(
    "Pesquisador Agro",
    [
        "Você é um pesquisador de tendências do agronegócio.",
        "Carregue a skill com get_skill_instructions e execute 'pesquisa-tendencias-agro'.",
        "Foque no que está em curso agora e no que as fontes apontam para os próximos meses.",
        REGRA_BUSCA,
        "Não salve arquivo. Retorne só o texto no formato da skill.",
    ],
    tools=[web_search],
)

apurador = make_agent(
    "Apurador de Fontes Agro",
    [
        "Você é um apurador de fontes do agronegócio.",
        "Carregue a skill e execute 'apuracao-fontes-agro'.",
        f"Encontre no mínimo {MIN_FONTES} fontes distintas com URL real da busca.",
        "Formato obrigatório: - **Nome do Veículo**: Título (URL)",
        "Se faltarem fontes, busque outras (Embrapa, Conab, MAPA, Cepea, Canal Rural).",
        REGRA_BUSCA,
        "Não salve arquivo. Retorne só o dossiê.",
    ],
    tools=[web_search],
)

validador = make_agent(
    "Validador de Tendência Agro",
    [
        "Você é um validador de tendências agropecuárias.",
        "Carregue a skill e execute 'validacao-tendencia-agro'.",
        "Separe sinal de ruído. Diga o que vale agora e o que as fontes sustentam para os próximos meses.",
        "Feche com o bloco RESUMO: veredito e os pontos importantes já citados, sem fato novo.",
        "Não recomende compra, preço ou estoque.",
        REGRA_BUSCA,
        "Não salve arquivo. Sua resposta em markdown é o resultado final.",
    ],
    tools=[web_search],
)


def contar_fontes(texto: str) -> int:
    match = _FONTES_SECAO.search(texto)
    secao = match.group(1) if match else texto
    return max(len(_FONTE_MARCADOR.findall(secao)), len(set(_URL.findall(secao))))


def fontes_suficientes(outputs: List[StepOutput]) -> bool:
    if not outputs:
        return False
    return contar_fontes(str(outputs[-1].content or "")) >= MIN_FONTES


agro_trends_workflow = Workflow(
    id="agro-trends",
    name="Agro Trends Pipeline",
    description="Pesquisa -> Apuração (loop) -> Leitura da tendência agora e nos próximos meses",
    steps=[
        Step(name="pesquisa", description="Pesquisa de tendências agro", agent=pesquisador),
        Loop(
            name="apuracao_loop",
            description="Repete a apuração até atingir o mínimo de fontes",
            steps=[
                Step(name="apuracao", description="Apuração multi-fonte", agent=apurador),
            ],
            max_iterations=MAX_TENTATIVAS_APURACAO,
            end_condition=fontes_suficientes,
        ),
        Step(
            name="validacao",
            description="Leitura da tendência: agora e próximos meses",
            agent=validador,
        ),
    ],
)


if __name__ == "__main__":
    agro_trends_workflow.print_response(
        "Tendências de nutrição animal e suplementação no Brasil",
        stream=True,
        markdown=True,
    )
