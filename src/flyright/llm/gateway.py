"""LLM gateway with primary-provider and fallback-provider support."""

import logging

import httpx

from flyright.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when all configured LLM providers fail."""


class LLMGateway:
    """Send chat requests to Gemini, falling back to Groq when necessary."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _call_provider(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        if not api_key:
            raise LLMError("Provider API key is not configured")

        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "temperature": 0,
            },
            timeout=self.settings.llm_timeout_seconds,
        )
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"].get("content")

        if not isinstance(content, str) or not content.strip():
            raise LLMError("Provider returned an empty response")

        return content.strip()

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return a response from Gemini, or Groq if Gemini fails."""
        providers = [
            (
                "Gemini",
                self.settings.llm_primary_base_url,
                self.settings.gemini_api_key,
                self.settings.llm_primary_model,
            ),
            (
                "Groq",
                self.settings.llm_fallback_base_url,
                self.settings.groq_api_key,
                self.settings.llm_fallback_model,
            ),
        ]

        errors: list[str] = []

        for name, base_url, api_key, model in providers:
            try:
                result = self._call_provider(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                )
                logger.info("LLM response received from %s", name)
                return result
            except (httpx.HTTPError, LLMError, KeyError, ValueError) as exc:
                logger.warning("%s request failed: %s", name, exc)
                errors.append(f"{name}: {type(exc).__name__}")

        raise LLMError("All LLM providers failed: " + "; ".join(errors))


def get_llm_gateway() -> LLMGateway:
    """Return an LLM gateway using application settings."""
    return LLMGateway()
