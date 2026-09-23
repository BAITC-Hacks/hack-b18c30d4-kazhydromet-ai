"""Бизнес-логика. Чистые функции -> JSON-совместимые dict/list. Их вызывают и API, и агент."""
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


def citizen_profile(iin: str) -> dict:
    """Всё по одному человеку: что начислено, что выплачено, что просрочено."""
    d = df()
    c = d[d["iin"].astype(str) == str(iin).strip()]
    if c.empty:
        return {"error": f"Гражданин с ИИН {iin} не найден"}
    return {
        "iin": str(iin),
        "region": c["region"].mode()[0],
        "documents": len(c),
        "to_budget_kzt": int(c[c["direction"] == "В бюджет"]["amount_kzt"].sum()),
        "from_budget_kzt": int(c[c["direction"] == "Из бюджета"]["amount_kzt"].sum()),
        "overdue": _records(c[c["status"] == "Просрочено"][["date", "service", "amount_kzt", "days_overdue"]]),
        "flagged": _records(c[c["is_flagged"] == 1][["date", "service", "amount_kzt", "flag_reason"]]),
        "by_type": {k: int(v) for k, v in c.groupby("service_type")["amount_kzt"].sum().items()},
    }


def search_payments(service_type: str | None = None, region: str | None = None, status: str | None = None,
                    min_amount: int = 0, limit: int = 20) -> list[dict]:
    """Поиск начислений и выплат по типу услуги, региону, статусу и сумме."""
    d = df()
    for col, val in (("service_type", service_type), ("region", region), ("status", status)):
        if val:
            d = d[d[col].str.contains(val, case=False, na=False)]
    out = d[d["amount_kzt"] >= min_amount].sort_values("amount_kzt", ascending=False).head(limit)
    return _records(out[["date", "iin", "region", "service_type", "service", "amount_kzt", "status"]])


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
