from __future__ import annotations

import logging
from typing import Any, Callable

from opencad_agent.models import ChatHistoryItem

logger = logging.getLogger(__name__)

LiteLlmCompletion = Callable[..., Any]
DEFAULT_CODE_TEMPERATURE = 0.2


def _default_completion(**kwargs: Any) -> Any:
    from litellm import completion

    return completion(**kwargs)


def _resolve_model_name(provider: str | None, model: str) -> str:
    if provider and "/" not in model:
        return f"{provider}/{model}"
    return model


def _supports_custom_temperature(resolved_model: str) -> bool:
    model_name = resolved_model.rsplit("/", 1)[-1].lower()
    return not model_name.startswith("gpt-5")


def _strip_code_fences(code: str) -> str:
    code = code.strip()
    if code.startswith("```python"):
        code = code[len("```python"):]
    elif code.startswith("```"):
        code = code[len("```"):]
    if code.endswith("```"):
        code = code[:-len("```")]
    return code.strip()


def _extract_message_content(response: Any) -> str:
    choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
    if not choices:
        raise ValueError("LLM response did not include any choices.")

    first_choice = choices[0]
    message = first_choice.get("message") if isinstance(first_choice, dict) else getattr(first_choice, "message", None)
    if message is None:
        raise ValueError("LLM response choice did not include a message.")

    content = message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "\n".join(parts)
        raise ValueError("LLM response content list did not include any text items.")
    raise ValueError("LLM response message did not include text content.")


class LiteLlmProvider:
    def __init__(self, completion_func: LiteLlmCompletion | None = None) -> None:
        self._completion = completion_func or _default_completion

    def generate_code(
        self,
        *,
        provider: str | None,
        model: str,
        system_prompt: str,
        user_message: str,
        conversation_history: list[ChatHistoryItem],
    ) -> str:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend({"role": item.role, "content": item.content} for item in conversation_history)
        messages.append({"role": "user", "content": user_message})
        resolved_model = _resolve_model_name(provider, model)
        completion_options: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "max_tokens": 1600,
            "seed": 0,
        }
        if _supports_custom_temperature(resolved_model):
            completion_options["temperature"] = DEFAULT_CODE_TEMPERATURE
        if resolved_model.startswith("ollama/"):
            completion_options["reasoning_effort"] = "none"
        response = self._completion(**completion_options)
        logger.debug("Received LLM code-generation response")
        cleaned_response = _strip_code_fences(_extract_message_content(response))
        return cleaned_response
