"""Бизнес-логика. Чистые функции -> JSON-совместимые dict/list. Их вызывают и API, и агент."""
import json
from functools import cache
from pathlib import Path

import pandas as pd

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "transactions.csv"


@cache
def df() -> pd.DataFrame:
    return pd.read_csv(DATA_FILE, parse_dates=["ts"])


def _records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False))


def summary() -> dict:
    d = df()
    by_cat = d.groupby("category")["amount_kzt"].sum().sort_values(ascending=False)
    return {
        "transactions": len(d),
        "clients": int(d["client_id"].nunique()),
        "total_kzt": int(d["amount_kzt"].sum()),
        "avg_kzt": int(d["amount_kzt"].mean()),
        "flagged": int(d["is_suspicious"].sum()),
        "by_category": {k: int(v) for k, v in by_cat.items()},
    }


def find_anomalies(z: float = 3.0, limit: int = 10) -> list[dict]:
    """Транзакции, которые сильно выбиваются из обычных трат клиента (z-score)."""
    d = df()
    g = d.groupby("client_id")["amount_kzt"]
    score = (d["amount_kzt"] - g.transform("mean")) / g.transform("std")
    out = d.assign(z=score.round(1))[score > z].sort_values("z", ascending=False).head(limit)
    return _records(out)


def client_profile(client_id: str) -> dict:
    d = df()
    c = d[d["client_id"] == client_id.upper()]
    if c.empty:
        return {"error": f"Клиент {client_id} не найден"}
    return {
        "client_id": client_id.upper(),
        "city": c["city"].mode()[0],
        "transactions": len(c),
        "total_kzt": int(c["amount_kzt"].sum()),
        "avg_kzt": int(c["amount_kzt"].mean()),
        "top_categories": c.groupby("category")["amount_kzt"].sum().nlargest(3).astype(int).to_dict(),
        "suspicious": _records(c[c["is_suspicious"] == 1]),
    }


def search_transactions(category: str | None = None, city: str | None = None,
                        min_amount: int = 0, limit: int = 20) -> list[dict]:
    d = df()
    if category:
        d = d[d["category"].str.contains(category, case=False)]
    if city:
        d = d[d["city"].str.contains(city, case=False)]
    return _records(d[d["amount_kzt"] >= min_amount].sort_values("amount_kzt", ascending=False).head(limit))
