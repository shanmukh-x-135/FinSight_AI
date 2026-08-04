"""Injectable chat dependencies."""

from app.intelligence.llm_client import LLMClient, get_llm_client


def get_chat_llm_client() -> LLMClient:
    return get_llm_client()
