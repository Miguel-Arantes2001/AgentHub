"""Ponto de entrada do AgentHub.

O servidor é o AgentOS, do Agno. Aqui só importamos os workflows, registramos
no AgentOS e servimos a página em /hub.

    uv run python -m backend.main

Página: http://127.0.0.1:7777/hub
API do Agno: http://127.0.0.1:7777/docs
"""

import importlib.util
import sys
from pathlib import Path

from agno.os import AgentOS
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
load_dotenv(ROOT / ".env")


def carregar(nome: str, arquivo: Path):
    """Importa um script pelo caminho.

    A pasta dele entra no sys.path durante o import, para que
    `import windows_certs` ache o arquivo ao lado, como quando o script roda direto.
    """
    pasta = str(arquivo.parent)
    sys.path.insert(0, pasta)
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome] = modulo
    spec.loader.exec_module(modulo)
    sys.path.remove(pasta)
    return modulo


agro = carregar("agro_trends_agent", BACKEND / "agro_trends" / "agro_trends_agent.py")
oracle = carregar("oracle_agent", BACKEND / "oracle" / "oracle_agent.py")
b2c = carregar("agent_b2c", BACKEND / "price" / "agent_b2c.py")
b2b = carregar("b2b_workflow", BACKEND / "price" / "agent_b2b" / "b2b_workflow.py")

interface = FastAPI()


@interface.get("/hub")
def hub():
    return FileResponse(ROOT / "frontend" / "index.html")


agent_os = AgentOS(
    id="agenthub",
    name="AgentHub",
    description="Central dos workflows de mercado, agro e oráculo.",
    workflows=[
        agro.agro_trends_workflow,
        oracle.workflow,
        b2c.workflow,
        b2b.workflow,
    ],
    base_app=interface,
    on_route_conflict="preserve_base_app",
    telemetry=False,
)
app = agent_os.get_app()


if __name__ == "__main__":
    agent_os.serve(app, host="127.0.0.1", port=7777)
