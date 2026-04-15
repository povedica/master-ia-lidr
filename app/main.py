from fastapi import FastAPI

app = FastAPI(title="Master IA")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Master IA"}
