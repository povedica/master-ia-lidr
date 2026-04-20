import os

from openai import OpenAI

from app.schemas_llm import ChatDemoRequest

DEFAULT_MODEL = "gpt-4o-mini"


def openai_responses_demo(body: ChatDemoRequest) -> dict:
    """Demo con Responses API (recomendada por OpenAI para proyectos nuevos)."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        msg = "OPENAI_API_KEY no configurada en el entorno del servidor."
        raise RuntimeError(msg)

    client = OpenAI(api_key=key)
    response = client.responses.create(
        model=DEFAULT_MODEL,
        instructions="Eres un asistente breve y claro. Responde en español.",
        input=body.user_message,
        temperature=0.3,
        max_output_tokens=300,
    )
    usage = response.usage.model_dump() if response.usage else {}
    return {
        "respuesta": response.output_text,
        "modelo": response.model,
        "id": response.id,
        "usage": usage,
    }
