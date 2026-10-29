"""
Gemini model implementation for Google ADK.

This module provides a compatible LLM wrapper for Google's Gemini models via
the official Google GenAI SDK, integrated with Google AI Studio API.
"""
import json
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from typing import Any, override

from google.adk.models.base_llm import BaseLlm
from google.adk.models.base_llm_connection import BaseLlmConnection
from google.adk.models.interactions_utils import extract_system_instruction
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from src.config import GEMINI_API_KEY, MODEL_NAME


def _normalize_schema_types(schema: Any) -> Any:
    """Normalize JSON schema types to lowercase for compatibility."""
    if isinstance(schema, dict):
        return {
            key: value.lower()
            if key == "type" and isinstance(value, str)
            else _normalize_schema_types(value)
            for key, value in schema.items()
        }
    if isinstance(schema, list):
        return [_normalize_schema_types(value) for value in schema]
    return schema


class GeminiChatModel(BaseLlm):
    """Gemini chat model implementation compatible with Google ADK."""

    api_key: str
    model: str = MODEL_NAME
    _client: Any = None

    def _get_client(self) -> Any:
        """Initialize and return the Google GenAI client."""
        if self._client is None:
            from google.genai import Client

            self._client = Client(api_key=self.api_key)
        return self._client

    @override
    def connect(
        self, llm_request: LlmRequest
    ) -> AbstractAsyncContextManager[BaseLlmConnection]:
        """Connect not supported for streaming in this implementation."""
        raise NotImplementedError("Straming connections are not yet supported.")

    def _build_messages(self, llm_request: LlmRequest) -> list[dict[str, Any]]:
        """Convert ADK request messages to Gemini format."""
        messages: list[dict[str, Any]] = []
        system_instruction = extract_system_instruction(llm_request.config)
        if system_instruction:
            messages.append(
                {
                    "role": "user",
                    "parts": [{"text": system_instruction}],
                }
            )

        for content in llm_request.contents:
            parts = content.parts or []
            tool_responses = [
                part.function_response for part in parts if part.function_response
            ]
            for tool_response in tool_responses:
                result = tool_response.response
                messages.append(
                    {
                        "role": "model",
                        "parts": [{"function_response": {"name": tool_response.id, "response": result}}],
                    }
                )

            ordinary_parts = [part for part in parts if not part.function_response]
            text = "".join(
                part.text for part in ordinary_parts if part.text and not part.thought
            )
            function_calls = [
                part.function_call for part in ordinary_parts if part.function_call
            ]

            if text or function_calls:
                if function_calls:
                    messages.append(
                        {
                            "role": "model",
                            "parts": [
                                {
                                    "function_call": {
                                        "name": call.name,
                                        "args": call.args or {},
                                    }
                                }
                                for call in function_calls
                            ],
                        }
                    )
                else:
                    messages.append(
                        {
                            "role": "user",
                            "parts": [{"text": text}],
                        }
                    )

        return messages

    def _build_tools(self, llm_request: LlmRequest) -> list[dict[str, Any]]:
        """Convert ADK tools to Gemini format."""
        tools: list[dict[str, Any]] = []
        for tool in llm_request.config.tools or []:
            for declaration in getattr(tool, "function_declarations", None) or []:
                parameters = declaration.parameters_json_schema
                if parameters is None and declaration.parameters is not None:
                    parameters = declaration.parameters.model_dump(
                        by_alias=True, exclude_none=True, mode="json"
                    )
                parameters = _normalize_schema_types(
                    parameters
                    or {
                        "type": "object",
                        "properties": {},
                    }
                )
                tools.append(
                    {
                        "function_declarations": [
                            {
                                "name": declaration.name,
                                "description": declaration.description or "",
                                "parameters": parameters,
                            }
                        ]
                    }
                )
        return tools

    @override
    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """
        Generate content using Google Gemini API.

        Args:
            llm_request: The request containing messages, tools, and config.
            stream: Whether to stream results (not currently supported).

        Yields:
            LlmResponse: Responses from the Gemini model.
        """
        config = llm_request.config.model_copy() if llm_request.config else None
        if config is not None:
            if config.temperature is None:
                config.temperature = 0
            # AI Studio (Gemini Developer API) não aceita labels.
            config.labels = None

        try:
            response = await self._get_client().aio.models.generate_content(
                model=self.model,
                contents=llm_request.contents,
                config=config,
            )
            yield LlmResponse.create(response)
        except Exception as e:
            raise RuntimeError(f"Gemini API call failed: {e}")


gemini_model = GeminiChatModel(
    model=MODEL_NAME,
    api_key=GEMINI_API_KEY,
)