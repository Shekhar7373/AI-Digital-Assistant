"""
LLM Router — pluggable LLM selection.

Priority:
  1. Ollama (local, primary)
  2. Groq (cloud, fallback if Ollama fails or LLM_PROVIDER=groq)

Usage:
  from llm.router import llm_chat
  result = await llm_chat(system_prompt, user_message)
"""

import os

# Override with LLM_PROVIDER=groq to force Groq
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")


def _get_ollama_chat():
    from llm.ollama import ollama_chat

    return ollama_chat


def _get_groq_chat():
    from llm.groq import groq_chat

    return groq_chat


async def llm_chat(system_prompt: str, user_message: str) -> str:
    """
    Routes the chat request to the configured LLM provider.
    Falls back to Groq if Ollama raises an error.
    """
    if LLM_PROVIDER == "groq":
        groq_chat = _get_groq_chat()
        return await groq_chat(system_prompt, user_message)

    # Default: try Ollama, fall back to Groq
    try:
        ollama_chat = _get_ollama_chat()
        return await ollama_chat(system_prompt, user_message)
    except Exception as ollama_error:
        print(f"[LLM Router] Ollama failed ({ollama_error}). Trying Groq fallback...")
        try:
            groq_chat = _get_groq_chat()
            return await groq_chat(system_prompt, user_message)
        except Exception as groq_error:
            raise RuntimeError(
                f"Both LLM providers failed. Ollama: {ollama_error} | Groq: {groq_error}"
            )
