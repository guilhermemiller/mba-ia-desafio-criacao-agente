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
from openai import AsyncOpenAI
from pydantic import PrivateAttr, SecretStr

from src.config import MODEL_NAME, OPENAI_API_KEY, OPENAI_BASE_URL


def _normalize_schema_types(schema: Any) -> Any:
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


class OpenAIChatModel(BaseLlm):
    api_key: SecretStr
    base_url: str
    _client: AsyncOpenAI | None = PrivateAttr(default=None)

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key.get_secret_value() or "local-openai-compatible",
                base_url=self.base_url,
            )
        return self._client

    @override
    def connect(
        self, llm_request: LlmRequest
    ) -> AbstractAsyncContextManager[BaseLlmConnection]:
        raise NotImplementedError("Conexões OpenAI em tempo real não são suportadas.")

    def _build_messages(self, llm_request: LlmRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        system_instruction = extract_system_instruction(llm_request.config)
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})

        for content in llm_request.contents:
            parts = content.parts or []
            tool_responses = [
                part.function_response for part in parts if part.function_response
            ]
            for tool_response in tool_responses:
                result = tool_response.response
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_response.id or "",
                        "content": result
                        if isinstance(result, str)
                        else json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

            ordinary_parts = [part for part in parts if not part.function_response]
            text = "".join(
                part.text for part in ordinary_parts if part.text and not part.thought
            )
            function_calls = [
                part.function_call for part in ordinary_parts if part.function_call
            ]
            role = "assistant" if content.role == "model" else "user"
            message: dict[str, Any] = {"role": role, "content": text or None}

            if role == "assistant" and function_calls:
                message["tool_calls"] = [
                    {
                        "id": call.id or "",
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(
                                call.args or {}, ensure_ascii=False, default=str
                            ),
                        },
                    }
                    for call in function_calls
                ]

            if text or function_calls:
                messages.append(message)

        return messages

    def _build_tools(self, llm_request: LlmRequest) -> list[dict[str, Any]]:
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
                        "type": "function",
                        "function": {
                            "name": declaration.name,
                            "description": declaration.description or "",
                            "parameters": parameters,
                        },
                    }
                )
        return tools

    @override
    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self._maybe_append_user_content(llm_request)
        request: dict[str, Any] = {
            "model": self.model.removeprefix("openai/"),
            "messages": self._build_messages(llm_request),
            "temperature": 0,
        }

        tools = self._build_tools(llm_request)
        if tools:
            request["tools"] = tools

        config = llm_request.config
        generation_options = {
            "temperature": "temperature",
            "max_output_tokens": "max_completion_tokens",
            "top_p": "top_p",
            "stop_sequences": "stop",
            "presence_penalty": "presence_penalty",
            "frequency_penalty": "frequency_penalty",
            "seed": "seed",
        }
        for source, target in generation_options.items():
            value = getattr(config, source, None)
            if value is not None:
                request[target] = value

        function_config = getattr(
            getattr(config, "tool_config", None), "function_calling_config", None
        )
        if tools and function_config is not None:
            if function_config.mode == types.FunctionCallingConfigMode.ANY:
                request["tool_choice"] = "required"
            elif function_config.mode == types.FunctionCallingConfigMode.NONE:
                request["tool_choice"] = "none"

        completion = await self._get_client().chat.completions.create(**request)
        if not completion.choices:
            raise RuntimeError("A API OpenAI retornou uma resposta sem escolhas.")

        message = completion.choices[0].message
        response_parts: list[types.Part] = []
        if message.content:
            response_parts.append(types.Part.from_text(text=message.content))

        for tool_call in message.tool_calls or []:
            arguments = json.loads(tool_call.function.arguments or "{}")
            if not isinstance(arguments, dict):
                raise TypeError(
                    f"Argumentos inválidos na ferramenta {tool_call.function.name}."
                )
            part = types.Part.from_function_call(
                name=tool_call.function.name,
                args=arguments,
            )
            if part.function_call:
                object.__setattr__(part.function_call, "id", tool_call.id)
            response_parts.append(part)

        yield LlmResponse(
            content=types.Content(role="model", parts=response_parts),
            model_version=completion.model,
        )


openai_model = OpenAIChatModel(
    model=MODEL_NAME,
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
)
