from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from config.settings import settings
from core.ai.spark_client import spark_client


class LLMProvider(Protocol):
    name: str

    def chat(self, messages: list[dict[str, str]]) -> str:
        ...

    def is_available(self) -> bool:
        ...


@dataclass
class SparkProvider:
    name: str = "spark"

    def chat(self, messages: list[dict[str, str]]) -> str:
        return spark_client.chat(messages)

    def is_available(self) -> bool:
        return spark_client.is_available()


@dataclass
class MockProvider:
    name: str = "mock"

    def chat(self, messages: list[dict[str, str]]) -> str:
        latest_user_message = ""
        for item in reversed(messages):
            if item.get("role") == "user":
                latest_user_message = item.get("content", "")
                break

        return (
            "Mock provider fallback is active because the primary model provider is unavailable. "
            f"Latest user message: {latest_user_message}"
        ).strip()

    def is_available(self) -> bool:
        return True


class LLMGateway:
    def __init__(self) -> None:
        self.providers: dict[str, LLMProvider] = {
            "spark": SparkProvider(),
            "mock": MockProvider(),
        }

    def ask(self, prompt: str) -> str:
        return self.chat([{"role": "user", "content": prompt}])

    def chat(self, messages: list[dict[str, str]]) -> str:
        result = self.chat_with_metadata(messages)
        return result["content"]

    def chat_with_metadata(self, messages: list[dict[str, str]]) -> dict[str, str]:
        primary = self._get_provider(settings.LLM_PRIMARY_PROVIDER)
        fallback = self._get_provider(settings.LLM_FALLBACK_PROVIDER)

        tried_errors: list[str] = []

        for provider in [primary, fallback]:
            if provider is None:
                continue

            if not provider.is_available():
                tried_errors.append(f"{provider.name} unavailable")
                continue

            try:
                return {
                    "provider_name": provider.name,
                    "content": provider.chat(messages),
                }
            except Exception as exc:
                tried_errors.append(f"{provider.name} failed: {exc}")

        error_text = "; ".join(tried_errors) or "No LLM provider is configured."
        raise Exception(f"LLM gateway failed. {error_text}")

    def health(self) -> dict[str, object]:
        return {
            "primary_provider": settings.LLM_PRIMARY_PROVIDER,
            "fallback_provider": settings.LLM_FALLBACK_PROVIDER,
            "providers_health": {
                name: provider.is_available()
                for name, provider in self.providers.items()
            },
        }

    def _get_provider(self, provider_name: str) -> LLMProvider | None:
        if not provider_name:
            return None
        return self.providers.get(provider_name.lower())


llm_gateway = LLMGateway()
