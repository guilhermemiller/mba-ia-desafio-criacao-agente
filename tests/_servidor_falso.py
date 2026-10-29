"""Sobe a API real (uvicorn) com o Gemini trocado por um roteiro fixo.

Uso: python tests/_servidor_falso.py <porta> [--restaurar]
O banco vem de DATABASE_PATH; --restaurar carrega os dados iniciais de dados/.
"""

import json
import sys

import uvicorn
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from src.gemini_model import GeminiChatModel

ROTEIRO = {
    "Reserve a quadra": ("solicitar_reserva_area", {"area": "quadra", "data": "2030-09-01"}),
    "Reserve outra quadra": ("solicitar_reserva_area", {"area": "quadra", "data": "2030-09-02"}),
    "Cancele": ("cancelar_reserva_area", {"area": "quadra", "data": "2030-03-09"}),
    "Libera": ("solicitar_autorizacao_visitante", {"nome": "Joana Ribeiro", "data": "2030-09-03"}),
}


async def _falso(self, llm_request, stream=False):
    ultima = llm_request.contents[-1].parts[-1]
    if ultima.function_response is not None:
        texto = "Feito: " + json.dumps(ultima.function_response.response, ensure_ascii=False)
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part.from_text(text=texto)]))
        return
    mensagem = ultima.text or ""
    for trecho, (nome, args) in ROTEIRO.items():
        if trecho in mensagem:
            parte = types.Part(
                function_call=types.FunctionCall(name=nome, args=args),
                thought_signature=b"\x00\xff\x10",
            )
            yield LlmResponse(content=types.Content(role="model", parts=[parte]))
            return
    yield LlmResponse(content=types.Content(role="model", parts=[types.Part.from_text(text="Ok.")]))


if __name__ == "__main__":
    GeminiChatModel.generate_content_async = _falso
    from src.db import restore_initial_data
    from src.main import app

    if "--restaurar" in sys.argv:
        restore_initial_data()
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
