import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import dataset, tools
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
def anomalies(limit: int = 10):
    return tools.find_anomalies(limit)


@app.get("/api/refusals")
def refusals():
    return tools.refusal_rates()


@app.get("/api/dataset")
def dataset_info():
    return dataset.info()


@app.post("/api/dataset/upload")
async def upload(file: UploadFile = File(...)):
    """Загрузить свой CSV или Excel — он станет активным датасетом для агента."""
    try:
        return dataset.save_upload(file.filename, await file.read())
    except Exception as e:
        raise HTTPException(400, f"Не смог прочитать файл: {e}")


@app.post("/api/dataset/reset")
def dataset_reset():
    return dataset.reset()


@app.post("/api/chat")
async def chat(body: Chat):
    return await ask(body.messages)


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "web", html=True), name="web")
