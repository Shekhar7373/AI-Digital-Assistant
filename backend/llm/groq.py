"""
Groq LLM fallback module.
Uses LangChain's ChatGroq (free-tier) as a faster cloud alternative to local Ollama.

Get a free API key at: https://console.groq.com
Example models: openai/gpt-oss-20b, llama-3.3-70b-versatile
"""

import os
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")


def get_groq_llm(temperature: float = 0.3):
    """
    Returns a ChatGroq instance.
    Raises ValueError if GROQ_API_KEY is not configured.
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set in environment variables.")
    return ChatGroq(
        groq_api_key=GROQ_API_KEY,
        model_name=GROQ_MODEL,
        temperature=temperature,
    )


async def groq_chat(system_prompt: str, user_message: str) -> str:
    """
    Simple one-shot chat using Groq.
    Returns the text response from the model.
    """
    llm = get_groq_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    try:
        response = await llm.ainvoke(messages)
        return response.content
    except Exception as e:
        raise RuntimeError(f"Groq error: {e}")
