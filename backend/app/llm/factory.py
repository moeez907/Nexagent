from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.nebius import NebiusProvider


def create_llm_provider(provider_name: str | None = None) -> LLMProvider:
    provider = (provider_name or settings.LLM_PROVIDER or "nebius").strip().lower()
    if provider in ("nebius", "tokenfactory", "openai"):
        return NebiusProvider()
    # Default provider is Nebius
    return NebiusProvider()