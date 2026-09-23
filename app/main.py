import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import dataset, graph, tools
from .agent import MODEL, ask

app = FastAPI(title="Граф денег")


class Chat(BaseModel):
    messages: list[dict]  # [{"role": "user" | "assistant", "content": "..."}]


@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL, "live": bool(os.getenv("OPENAI_API_KEY"))}


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
    return await ask(body.messages)


@app.get("/", include_in_schema=False)
def root():
    # главный экран — web/graph.html; когда будет готов новый index.html, убрать этот маршрут
    return RedirectResponse("/graph.html")


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
