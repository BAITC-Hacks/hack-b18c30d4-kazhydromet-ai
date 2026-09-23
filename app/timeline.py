"""Daily observed transfers around one client; no inferred ordering within a day."""

from math import isfinite
from pathlib import Path
import re

import pandas as pd


DATA = Path(__file__).resolve().parent.parent / "data" / "raw"


def node_timeline(gid: str) -> dict:
    """Return calendar days and incident directed transfers from the raw export."""
    gid = str(gid).strip()
    missing = {"error": "Клиент не найден", "gid": gid}
    if re.fullmatch(r"\d{18}", gid) is None:
        return missing
    nodes = pd.read_parquet(DATA / "nodes.parquet")
    node = nodes.loc[nodes["gid"].astype(str) == gid]
    if node.empty:
        return missing

    transactions = pd.read_parquet(DATA / "transactions.parquet")
    if transactions.empty:
        return {"error": "В исходной выгрузке нет дат переводов", "gid": gid}
    dates = pd.to_datetime(transactions["date"], errors="coerce").dt.normalize()
    amounts = pd.to_numeric(transactions["sum_kzt"], errors="coerce")
    if dates.isna().any() or not amounts.map(isfinite).all():
        return {"error": "В исходной выгрузке есть некорректные даты или суммы", "gid": gid}
    transactions = transactions.assign(date=dates, sum_kzt=amounts)

    # Use the full calendar span of the source, including days without transfers.
    start = dates.min().replace(day=1)
    end = dates.max() + pd.offsets.MonthEnd(0)
    numeric_gid = int(gid)
    incoming = transactions.loc[transactions["dst"] == numeric_gid]
    outgoing = transactions.loc[transactions["src"] == numeric_gid]
    incident = transactions.loc[
        (transactions["src"] == numeric_gid) | (transactions["dst"] == numeric_gid)
    ]
    truncated = bool(int(node.iloc[0]["depth"]) == 4 and outgoing.empty)

    def daily_totals(rows: pd.DataFrame) -> dict:
        grouped = rows.groupby("date")["sum_kzt"].agg(["sum", "size"])
        return {date: (float(row["sum"]), int(row["size"]))
                for date, row in grouped.iterrows()}

    in_days, out_days = daily_totals(incoming), daily_totals(outgoing)
    pairs = incident.groupby(["date", "src", "dst"])["sum_kzt"].agg(["sum", "size"])
    edges_by_day = {}
    for (date, source, target), row in pairs.iterrows():
        edges_by_day.setdefault(date, []).append({
            "from": str(source), "to": str(target),
            "sum_kzt": float(row["sum"]), "n_tx": int(row["size"]),
        })
    days = []
    for date in pd.date_range(start, end, freq="D"):
        in_kzt, in_n_tx = in_days.get(date, (0.0, 0))
        out_kzt, out_n_tx = out_days.get(date, (0.0, 0))
        days.append({
            "date": date.strftime("%Y-%m-%d"), "label": date.strftime("%d.%m.%Y"),
            "in_kzt": in_kzt, "out_kzt": out_kzt,
            "in_n_tx": in_n_tx, "out_n_tx": out_n_tx,
            "edges": edges_by_day.get(date, []),
        })
    note = (
        "Показаны только наблюдаемые переводы выбранного клиента по календарным дням. "
        "Порядок операций внутри дня неизвестен; близкие даты не доказывают движение тех же средств. "
        "Входящие из-за пределов выборки и операции ниже 5 000 ₸ не видны."
    )
    if truncated:
        note += (" На четвёртом колене исходящие не выгружались: нули исходящих означают "
                 "отсутствие наблюдений, а не отсутствие переводов.")
    return {
        "gid": gid,
        "truncated": truncated,
        "period": {"start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")},
        "totals": {
            "in_kzt": float(incoming["sum_kzt"].sum()),
            "out_kzt": float(outgoing["sum_kzt"].sum()),
            "in_n_tx": int(len(incoming)), "out_n_tx": int(len(outgoing)),
        },
        "days": days,
        "note": note,
    }
