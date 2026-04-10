"""
llm_client.py
Thin wrapper around Groq and Google Gemini free-tier LLM APIs.
"""

import os
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


# ---------------------------------------------------------------------------
# Groq (free tier — llama3-8b-8192 / mixtral-8x7b-32768)
# ---------------------------------------------------------------------------

class GroqClient:
    def __init__(self, model: str = "llama3-8b-8192") -> None:
        try:
            from groq import Groq  # pip install groq
        except ImportError as exc:
            raise ImportError(
                "groq package not installed. Run: pip install groq"
            ) from exc
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY environment variable is not set."
            )
        self._client = Groq(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        logger.debug("Groq request | model=%s | prompt[:80]=%s", self._model, prompt[:80])
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=4096,
        )
        return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Google Gemini (free tier)
# ---------------------------------------------------------------------------

class GeminiClient:
    def __init__(self, model: str = "gemini-1.5-flash") -> None:
        try:
            import google.generativeai as genai  # pip install google-generativeai
        except ImportError as exc:
            raise ImportError(
                "google-generativeai package not installed. Run: pip install google-generativeai"
            ) from exc
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY environment variable is not set."
            )
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)

    def complete(self, prompt: str) -> str:
        logger.debug("Gemini request | prompt[:80]=%s", prompt[:80])
        response = self._model.generate_content(prompt)
        return response.text.strip()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_llm_client(llm_config: dict) -> LLMClient:
    """Return the appropriate LLM client based on the channel config."""
    provider = llm_config.get("provider", "groq").lower()
    model = llm_config.get("model", "llama3-8b-8192")
    if provider == "groq":
        return GroqClient(model=model)
    elif provider == "gemini":
        return GeminiClient(model=model)
    else:
        raise ValueError(f"Unknown LLM provider: '{provider}'. Use 'groq' or 'gemini'.")
