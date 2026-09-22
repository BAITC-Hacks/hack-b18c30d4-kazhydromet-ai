import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import tools
from .agent import MODEL, ask

app = FastAPI(title="HackAlem Starter")


class Chat(BaseModel):
    messages: list[dict]  # [{"role": "user" | "assistant", "content": "..."}]


@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL, "live": bool(os.getenv("OPENAI_API_KEY"))}


@app.get("/api/summary")
def summary():
    return tools.summary()


@app.get("/api/anomalies")
def anomalies(z: float = 3.0, limit: int = 10):
    return tools.find_anomalies(z, limit)


@app.post("/api/chat")
async def chat(body: Chat):
    return await ask(body.messages)


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "web", html=True), name="web")
