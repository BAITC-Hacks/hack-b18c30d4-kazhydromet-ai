"""Совместимость трёх прежних API сводки, аномалий и отказов.
AML-агент и графовый экран этот модуль не используют."""
import json
from functools import cache
from pathlib import Path

import pandas as pd

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "payments.csv"


@cache
def df() -> pd.DataFrame:
    return pd.read_csv(DATA_FILE, parse_dates=["date"])


def _records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False))


def summary() -> dict:
    d = df()
    by_type = d.groupby("service_type")["amount_kzt"].sum().sort_values(ascending=False)
    return {
        "documents": len(d),
        "citizens": int(d["iin"].nunique()),
        "total_kzt": int(d["amount_kzt"].sum()),
        "to_budget_kzt": int(d[d["direction"] == "В бюджет"]["amount_kzt"].sum()),
        "from_budget_kzt": int(d[d["direction"] == "Из бюджета"]["amount_kzt"].sum()),
        "overdue": int((d["status"] == "Просрочено").sum()),
        "flagged": int(d["is_flagged"].sum()),
        "by_type": {k: int(v) for k, v in by_type.items()},
    }


def find_anomalies(limit: int = 10) -> list[dict]:
    """Записи, требующие проверки: дубли выплат, длинные просрочки, необычные отказы."""
    d = df()
    out = d[d["is_flagged"] == 1].sort_values("amount_kzt", ascending=False).head(limit)
    return _records(out[["date", "iin", "region", "service", "amount_kzt", "status", "flag_reason"]])


def refusal_rates() -> list[dict]:
    """Доля отказов по регионам: где людям чаще всего отказывают в выплатах."""
    d = df()
    apps = d[d["direction"] == "Из бюджета"]
    if apps.empty:
        return []
    g = apps.groupby("region")["status"]
    stats = pd.DataFrame({"applications": g.size(), "refused": g.apply(lambda s: (s == "Отказано").sum())})
    stats = stats[stats["applications"] >= 5]
    stats["refusal_rate_pct"] = (stats["refused"] / stats["applications"] * 100).round(1)
    return _records(stats.sort_values("refusal_rate_pct", ascending=False).reset_index())
