"""Работа с ЛЮБЫМ табличным файлом: загрузили CSV или Excel — агент сразу умеет его анализировать.
Нужно, чтобы на хакатоне не переписывать логику под датасет, который выдадут."""
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
ACTIVE = DATA / "active.csv"  # сюда кладётся загруженный файл
DEFAULT = DATA / "transactions.csv"
AGGS = {"sum", "mean", "count", "min", "max", "median", "nunique"}


def _path() -> Path:
    return ACTIVE if ACTIVE.exists() else DEFAULT


@lru_cache(maxsize=4)
def _read(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_csv(path)


def load() -> pd.DataFrame:
    p = _path()
    return _read(str(p), p.stat().st_mtime)


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False))


def save_upload(filename: str, content: bytes) -> dict:
    """Принимает CSV или Excel, делает его активным датасетом."""
    tmp = DATA / ("upload" + Path(filename).suffix.lower())
    tmp.write_bytes(content)
    try:
        if tmp.suffix in (".xlsx", ".xls"):
            df = pd.read_excel(tmp)
        else:
            df = pd.read_csv(tmp, sep=None, engine="python")  # сам определит разделитель
    finally:
        tmp.unlink(missing_ok=True)
    if df.empty:
        return {"error": "Файл пустой"}
    df.to_csv(ACTIVE, index=False)
    _read.cache_clear()
    return info() | {"uploaded": filename}


def reset() -> dict:
    """Вернуться к демо-данным."""
    ACTIVE.unlink(missing_ok=True)
    _read.cache_clear()
    return info()


def info() -> dict:
    """Что за данные сейчас активны: строки, колонки, типы, примеры значений."""
    df = load()
    cols = []
    for c in df.columns:
        s = df[c]
        col = {"name": c, "type": str(s.dtype), "nulls": int(s.isna().sum()), "unique": int(s.nunique())}
        if pd.api.types.is_numeric_dtype(s):
            col |= {"min": float(s.min()), "max": float(s.max()), "mean": round(float(s.mean()), 2)}
        else:
            col["examples"] = [str(v) for v in s.dropna().unique()[:3]]
        cols.append(col)
    return {"source": _path().name, "rows": len(df), "columns": cols}


def _check(df: pd.DataFrame, *names) -> dict | None:
    bad = [n for n in names if n and n not in df.columns]
    if bad:
        return {"error": f"Нет колонок: {', '.join(bad)}", "available": list(df.columns)}
    return None


def query(where: str | None = None, group_by: str | None = None, value_column: str | None = None,
          agg: str = "sum", order_desc: bool = True, limit: int = 20) -> list[dict] | dict:
    """Фильтр + группировка + агрегат. `where` — выражение pandas, например `amount_kzt > 100000`."""
    df = load()
    if (err := _check(df, group_by, value_column)):
        return err
    if agg not in AGGS:
        return {"error": f"agg должен быть одним из: {', '.join(sorted(AGGS))}"}
    if where:
        try:
            df = df.query(where)
        except Exception as e:
            return {"error": f"Не разобрал условие «{where}»: {e}", "available": list(df.columns)}
    if df.empty:
        return []
    if group_by:
        g = df.groupby(group_by)
        res = getattr(g[value_column], agg)() if value_column else g.size().rename("count")
        res = res.sort_values(ascending=not order_desc).head(limit)
        return records(res.reset_index())
    return records(df.head(limit))


def outliers(value_column: str, group_column: str | None = None, z: float = 3.0, limit: int = 10):
    """Выбросы по z-score. С group_column — относительно среднего внутри своей группы (например, по клиенту)."""
    df = load()
    if (err := _check(df, value_column, group_column)):
        return err
    if not pd.api.types.is_numeric_dtype(df[value_column]):
        return {"error": f"Колонка {value_column} не числовая"}
    v = df[value_column]
    if group_column:
        g = df.groupby(group_column)[value_column]
        score = (v - g.transform("mean")) / g.transform("std")
    else:
        score = (v - v.mean()) / v.std()
    out = df.assign(z=score.round(1))[score.abs() > z]
    return records(out.reindex(out["z"].abs().sort_values(ascending=False).index).head(limit))
