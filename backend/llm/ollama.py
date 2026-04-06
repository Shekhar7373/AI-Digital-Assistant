"""
Ollama LLM module.
Uses LangChain's ChatOllama to run llama3 (or any local model) via Ollama.

Prerequisites:
  1. Install Ollama: https://ollama.ai
  2. Pull a model:  ollama pull llama3
  3. Start server:  ollama serve
"""

import os
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3")


def get_ollama_llm(temperature: float = 0.3):
    """
    Returns a ChatOllama instance.
    temperature: 0 = deterministic, 1 = creative
    """
    return ChatOllama(
        base_url=OLLAMA_BASE_URL,
        model=OLLAMA_MODEL,
        temperature=temperature,
    )


async def ollama_chat(system_prompt: str, user_message: str) -> str:
    """
    Simple one-shot chat using Ollama.
    Returns the text response from the model.
    """
    llm = get_ollama_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    try:
        response = await llm.ainvoke(messages)
        return response.content
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")
