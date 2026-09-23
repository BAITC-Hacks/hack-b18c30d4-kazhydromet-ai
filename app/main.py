import os
import asyncio
from collections import deque
from pathlib import Path
from time import monotonic
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import dataset, graph, tools
from .agent import CONFIG_ERROR, LIVE, MODEL, PROVIDER, ask

app = FastAPI(title="Граф денег")
PUBLIC_DEMO = os.getenv("PUBLIC_DEMO", "").strip().lower() in {"1", "true", "yes"}
_chat_slots = asyncio.Semaphore(2)
_chat_times: deque[float] = deque()


@app.middleware("http")
async def public_demo_guard(request: Request, call_next):
    if (PUBLIC_DEMO and request.method == "POST"
            and request.url.path in {"/api/recompute", "/api/dataset/upload", "/api/dataset/reset"}):
        return JSONResponse({"detail": "В публичном демо используется готовая выгрузка."}, status_code=403)
    return await call_next(request)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(strict=True, min_length=1)


class Chat(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)


@app.get("/api/health")
def health():
    return {"ok": True, "provider": PROVIDER, "model": MODEL, "live": LIVE,
            "config_error": CONFIG_ERROR, "public_demo": PUBLIC_DEMO}


@app.get("/api/overview")
def overview():
    return graph.overview()


@app.get("/api/graph")
def graph_all():
    return graph.graph_json()


@app.get("/api/node/{gid}")
def node(gid: str):
    card = graph.node_card(gid)
    if "error" in card:
        raise HTTPException(404, card["error"])
    return card


@app.get("/api/top")
def top(n: int = 50, role: str | None = None):
    return graph.top(n, role)


@app.get("/api/clusters")
def clusters():
    return graph.clusters()


@app.get("/api/clusters/{cluster_id}")
def cluster(cluster_id: int):
    return graph.cluster_detail(cluster_id)


@app.get("/api/path")
def path(src: str, dst: str):
    return graph.money_path(src, dst)


@app.get("/api/routes")
def routes(gid: str | None = None, limit: int = 10):
    return graph.repeated_routes(gid, limit)


@app.get("/api/timeline/{gid}")
def timeline(gid: str):
    """Наблюдаемые переводы клиента по календарным дням."""
    from .timeline import node_timeline

    result = node_timeline(gid)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.post("/api/recompute")
def recompute():
    """Полный пересчёт от сырых parquet до выгрузок."""
    from . import pipeline
    s = pipeline.run(graph.DATA, graph.OUT)
    graph.reload()
    return s


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
    messages = [message.model_dump() for message in body.messages]
    if not PUBLIC_DEMO:
        return await ask(messages)
    if sum(len(message.content) for message in body.messages) > 24000:
        raise HTTPException(413, "Слишком длинная история. Начните новый диалог.")
    now = monotonic()
    while _chat_times and now - _chat_times[0] >= 60:
        _chat_times.popleft()
    if len(_chat_times) >= 20 or _chat_slots.locked():
        raise HTTPException(429, "AI сейчас занят. Повторите вопрос через минуту.", headers={"Retry-After": "60"})
    _chat_times.append(now)
    async with _chat_slots:
        return await ask(messages)


@app.get("/api/report")
def analyst_report(top: int = 10, gids: str | None = None):
    from fastapi.responses import PlainTextResponse

    from .report import build_report

    selected = gids.split(",") if gids is not None else None
    markdown = build_report(gids=selected, top=top)
    return PlainTextResponse(
        markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=aml_report.md"},
    )


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "web", html=True), name="web")
