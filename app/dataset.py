"""Совместимость прежних API загрузки, профиля и сброса таблицы.
AML-агент и графовый экран этот модуль не используют."""
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
ACTIVE = DATA / "active.csv"  # сюда кладётся загруженный файл
DEFAULT = DATA / "payments.csv"


def _path() -> Path:
    return ACTIVE if ACTIVE.exists() else DEFAULT


@lru_cache(maxsize=4)
def _read(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_csv(path)


def load() -> pd.DataFrame:
    p = _path()
    return _read(str(p), p.stat().st_mtime)


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
