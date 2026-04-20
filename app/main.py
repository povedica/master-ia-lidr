from fastapi import FastAPI

app = FastAPI(title="Master IA")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"mensaje": "¡Hola desde FastAPI!"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None) -> dict:
    return {"item_id": item_id, "q": q}
