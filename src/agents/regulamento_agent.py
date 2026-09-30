from google.adk.agents import Agent

from src.openai_model import openai_model
from src.tools.regulamento_tools import buscar_regulamento

regulamento_agent = Agent(
    name="especialista_regulamento",
    model=openai_model,
    instruction="""Você é o especialista no Regulamento Interno do Residencial Aurora.
Você responde às dúvidas dos moradores consultando obrigatoriamente a ferramenta `buscar_regulamento`.

REGRAS RÍGIDAS:
1. Sempre use a tool `buscar_regulamento` para obter as regras oficiais antes de responder.
2. Responda de forma direta, clara e precisa com base estritamente no trecho retornado.
""",
    tools=[buscar_regulamento],
)
