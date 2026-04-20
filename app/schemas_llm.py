from pydantic import BaseModel, Field


class ChatDemoRequest(BaseModel):
    user_message: str = Field(
        default="Di una sola frase de saludo para un alumno del máster IA.",
        min_length=1,
        max_length=4000,
    )
