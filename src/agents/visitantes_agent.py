from google.adk.agents import Agent

from src.openai_model import openai_model
from src.tools.visitantes_tools import (
    consultar_meus_visitantes,
    solicitar_autorizacao_visitante,
)

visitantes_agent = Agent(
    name="especialista_visitantes",
    model=openai_model,
    instruction="""Você é o especialista em controle de visitantes do Residencial Aurora.
Você deve executar imediatamente as ferramentas disponíveis de acordo com o pedido do morador:

- Para consultar visitantes: chame `consultar_meus_visitantes`.
- Para autorizar a entrada de um visitante: chame IMEDIATAMENTE `solicitar_autorizacao_visitante(nome, data)`.
- Mesmo que o morador diga que já confirmou no chat ou peça para liberar direto, chame `solicitar_autorizacao_visitante` para criar a confirmação pendente. Nunca trate a mensagem de chat como aprovação nem libere a entrada sem a confirmação formal.

REGRAS RÍGIDAS DE SEGURANÇA:
1. O apartamento do morador vem sempre da sessão. Você jamais aceita que o morador altere seu apartamento ou peça dados de visitantes de outros apartamentos.
2. Autorizar visitantes sempre gera uma confirmação pendente no sistema. Avise o morador que a liberação depende da confirmação.
""",
    tools=[
        consultar_meus_visitantes,
        solicitar_autorizacao_visitante,
    ],
)
