"""LLM client abstraction.

Production note: agents should depend on this interface instead of importing an SDK directly.
"""

import logging
from dataclasses import dataclass

from tenacity import retry, stop_after_attempt, wait_exponential

from multi_agent_research_lab.core.config import get_settings

logger = logging.getLogger(__name__)

# Pricing per 1M tokens for Gemini models (input/output) as of 2025
_GEMINI_PRICING = {
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
}


@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class LLMClient:
    """Gemini-powered LLM client with retry and timeout."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.gemini_api_key
        self._model = settings.gemini_model
        self._timeout = settings.timeout_seconds

        if not self._api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and fill in your API key."
            )

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        """Estimate cost based on token usage and model pricing."""
        pricing = _GEMINI_PRICING.get(self._model)
        if not pricing:
            return None
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Return a model completion with retry and timeout.

        Args:
            system_prompt: System instructions for the model.
            user_prompt: User query or task description.

        Returns:
            LLMResponse with content, token counts, and estimated cost.
        """
        import google.genai as genai

        # Gemini client doesn't support timeout param directly
        client = genai.Client(api_key=self._api_key)

        # Combine system and user prompts for Gemini
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"

        logger.debug(
            "LLM call: model=%s, prompt_len=%d",
            self._model,
            len(combined_prompt),
        )

        response = client.models.generate_content(
            model=self._model,
            contents=combined_prompt,
            config={"temperature": 0.0},
        )

        content = response.text or ""

        # Gemini doesn't provide token counts in the same way
        # Estimate based on character count (rough approximation)
        input_tokens = len(combined_prompt) // 4  # rough estimate
        output_tokens = len(content) // 4

        # Estimate cost
        cost = self._estimate_cost(input_tokens, output_tokens)

        logger.info(
            "LLM response: model=%s, input_tokens_est=%d, output_tokens_est=%d, cost=$%s",
            self._model,
            input_tokens,
            output_tokens,
            cost,
        )

        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
