import os
from langchain_groq import ChatGroq


def get_llm(temperature: float = 0.3) -> ChatGroq:
    return ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        temperature=temperature,
    )
