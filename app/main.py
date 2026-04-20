from fastapi import FastAPI, HTTPException

from app.llm_demo import openai_responses_demo
from app.schemas_llm import ChatDemoRequest

app = FastAPI(title="Master IA")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"mensaje": "¡Hola desde FastAPI!"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None) -> dict:
    return {"item_id": item_id, "q": q}


@app.post("/llm/demo")
def llm_demo(body: ChatDemoRequest) -> dict:
    """Demo de OpenAI Responses API. Requiere OPENAI_API_KEY en el servidor."""
    try:
        return openai_responses_demo(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
