"""Запросы к построенному графу: карточка узла, соседи, общий получатель, путь, кластеры.
Функции возвращают JSON-совместимые dict/list; gid всегда строкой (18 цифр не влезают в JS number)."""
from functools import lru_cache
from itertools import islice
from pathlib import Path

import networkx as nx
import pandas as pd

from . import pipeline

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
DATA = ROOT / "data" / "raw"


@lru_cache(maxsize=1)
def _state():
    outputs = ("nodes_roles.csv", "clusters.csv", "top_nodes.csv", "graph.json", "summary.json")
    if any(not (OUT / name).exists() for name in outputs):
        pipeline.run(DATA, OUT)
    df = pd.read_csv(OUT / "nodes_roles.csv").sort_values(
        ["priority_score", "gid"], ascending=[False, True]).set_index("gid")
    cl = pd.read_csv(OUT / "clusters.csv")
    top = pd.read_csv(OUT / "top_nodes.csv")
    edges, nodes, tx = pipeline.load(DATA)
    G = pipeline.build_graph(edges, nodes)
    return df, cl, top, G, tx


def reload():
    _state.cache_clear()
    _all_routes.cache_clear()
    return _state()[0].shape[0]


def _gid(g) -> int | None:
    try:
        g = int(str(g).strip())
    except ValueError:
        return None
    return g if g in _state()[0].index else None


def _brief(g: int) -> dict:
    r = _state()[0].loc[g]
    return {"gid": str(g), "role": r.role, "role_ru": pipeline.ROLE_RU[r.role],
            "priority_score": float(r.priority_score), "cluster_id": int(r.cluster_id), "is_seed": bool(r.is_seed),
            "plain": pipeline.plain(r)}


def _counterparts(g: int, direction: str, limit: int) -> list[dict]:
    G = _state()[3]
    it = G.in_edges(g, data=True) if direction == "in" else G.out_edges(g, data=True)
    rows = [{**_brief(u if direction == "in" else v), "sum_kzt": d["sum_kzt"], "n_tx": d["n_tx"]}
            for u, v, d in it]
    return sorted(rows, key=lambda x: -x["sum_kzt"])[:limit]


def node_card(gid, limit: int = 15) -> dict:
    """Карточка узла: роль, evidence, метрики, крупнейшие плательщики и получатели, даты."""
    g = _gid(gid)
    if g is None:
        return {"error": f"gid {gid} не найден в графе (2 248 узлов)"}
    df, _, _, _, tx = _state()
    r = df.loc[g]
    t = tx[(tx.src == g) | (tx.dst == g)]
    card = {**_brief(g), "role_score": float(r.role_score), "evidence": r.evidence,
            "metrics": {k: (v.item() if hasattr(v, "item") else v) for k, v in r.drop(
                ["role", "role_score", "cluster_id", "priority_score", "evidence"]).items()},
            "rank": int(df.index.get_loc(g) + 1),
            "first_date": t.date.min().strftime("%d.%m.%Y") if len(t) else None,
            "last_date": t.date.max().strftime("%d.%m.%Y") if len(t) else None,
            "in": _counterparts(g, "in", limit), "out": _counterparts(g, "out", limit)}
    card["gaps"] = gaps(r)
    routes = repeated_routes(str(g), limit=3)
    card["repeated_routes"] = routes["routes"]
    card["repeated_routes_count"] = routes["total"]
    card["repeated_routes_note"] = routes["note"]
    return card


@lru_cache(maxsize=1)
def _all_routes() -> list[dict]:
    from .routes import find_routes
    return find_routes(_state()[4])


def repeated_routes(gid: str | None = None, limit: int = 10) -> dict:
    """Повторяющиеся A→B→C; совпадение дат допускается, происхождение денег не устанавливается."""
    note = ("Не менее 2 пар переводов с неубывающими датами; каждая транзакция используется "
            "один раз внутри цепочки. Порядок в пределах дня неизвестен. Суммы между шагами "
            "не сопоставляются: это гипотезы маршрутов, не доказательство движения тех же средств. "
            "Разные цепочки могут включать одни и те же переводы; их суммы нельзя складывать.")
    selected = _gid(gid) if gid is not None else None
    if gid is not None and selected is None:
        return {"routes": [], "total": 0, "note": note, "error": "gid не найден"}
    rows = _all_routes()
    if selected is not None:
        rows = [row for row in rows if str(selected) in row["gids"]]
    return {"routes": rows[:max(0, min(limit, 100))], "total": len(rows), "note": note}


def gaps(r) -> list[str]:
    """Чего не хватает в данных по узлу и какой запрос сделать следующим."""
    out = []
    if r.truncated:
        out.append("исходящие не выгружались (4-е колено) — запросить исходящие переводы узла за июль")
    if r.is_seed or r.out_kzt > r.in_kzt:
        out.append("входящие видны частично — запросить входящие переводы из-за пределов выборки")
    if r.in_deg + r.out_deg == 0:
        out.append("нет переводов ≥5 000 ₸ — запросить операции ниже порога и в других банках")
    if r.max_payers_day >= 3:
        out.append("синхронные поступления — запросить устройства/IP плательщиков за эти дни")
    return out


def graph_json() -> dict:
    import json
    _state()  # построит out/, если его ещё нет
    return json.loads((OUT / "graph.json").read_text(encoding="utf-8"))


def top(n: int = 20, role: str | None = None) -> list[dict]:
    """rank — глобальный (по всем 2 248 узлам), даже при фильтре по роли."""
    df = _state()[0].sort_values("priority_score", ascending=False, kind="stable")
    df = df.assign(rank=range(1, len(df) + 1))
    d = (df[df.role == role] if role else df).head(max(0, n))
    return [{**_brief(g), "rank": int(r["rank"]), "evidence": r.evidence,
             "why": pipeline.why(r.rename(g))} for g, r in d.iterrows()]


def clusters(limit: int = 100) -> list[dict]:
    cl = _state()[1].head(limit).copy()
    return cl.to_dict(orient="records")


def cluster_detail(cluster_id: int, limit: int = 15) -> dict:
    df, cl, *_ = _state()
    row = cl[cl.cluster_id == int(cluster_id)]
    if row.empty:
        return {"error": f"кластера {cluster_id} нет; всего кластеров {len(cl)}"}
    members = df[df.cluster_id == int(cluster_id)].sort_values("priority_score", ascending=False, kind="stable")
    return {**row.iloc[0].to_dict(), "top_members": [_brief(g) | {"evidence": r.evidence}
                                                     for g, r in members.head(limit).iterrows()]}


def common_receivers(gids: list, max_hops: int = 3, limit: int = 10) -> dict:
    """Кто ниже по потоку собирает деньги сразу от нескольких заданных узлов (в пределах max_hops переводов)."""
    G = _state()[3]
    ok = list(dict.fromkeys(g for g in (_gid(x) for x in gids) if g is not None))  # без повторов
    missing = [str(x) for x in gids if _gid(x) is None]
    reach: dict[int, list] = {}
    for g in ok:
        for v, d in nx.single_source_shortest_path_length(G, g, cutoff=max_hops).items():
            if v != g:
                reach.setdefault(v, []).append({"from": str(g), "hops": d})
    rows = [{**_brief(v), "reached_from": len(src), "paths": src}
            for v, src in reach.items() if len(src) >= 2]
    rows.sort(key=lambda x: (-x["reached_from"], -x["priority_score"]))
    return {"input": [str(g) for g in ok], "not_found": missing, "max_hops": max_hops,
            "common_receivers": rows[:limit]}


def money_path(src, dst, max_len: int = 6) -> dict:
    """Кратчайшие по числу шагов пути денег от src к dst (направленно)."""
    G = _state()[3]
    a, b = _gid(src), _gid(dst)
    if a is None or b is None:
        return {"error": "gid не найден"}
    if a == b:
        return {"src": str(a), "dst": str(b), "paths": [],
                "note": "отправитель и получатель совпадают: нет шага перевода; это не маршрут денег"}
    try:
        paths = list(islice(nx.all_shortest_paths(G, a, b), 5))
    except nx.NetworkXNoPath:
        return {"src": str(a), "dst": str(b), "paths": [], "note": "направленного пути денег нет"}
    if len(paths[0]) - 1 > max_len:
        return {"src": str(a), "dst": str(b), "paths": [], "note": f"путь длиннее {max_len} шагов"}
    tx = _state()[4]
    out = []
    for p in paths:
        steps = [{**_brief(u), "next_sum_kzt": G[u][v]["sum_kzt"]} for u, v in zip(p, p[1:])] + [_brief(p[-1])]
        dates = _chronology(tx, p)
        out.append({"steps": steps, "chronology_ok": dates is not None,
                    "dates": [d.strftime("%d.%m.%Y") for d in dates] if dates else None})
    note = ("есть цепочка переводов с неубывающими датами — деньги могли пройти этим маршрутом"
            if any(x["chronology_ok"] for x in out) else
            "связь только структурная: по датам переводов деньги не могли пройти этим маршрутом в июле")
    return {"src": str(a), "dst": str(b), "paths": out, "note": note}


def _chronology(tx: pd.DataFrame, p: list[int]):
    """Жадно подбирает по каждому шагу самый ранний перевод не раньше предыдущего. None — маршрут невозможен по датам."""
    prev, dates = None, []
    for u, v in zip(p, p[1:]):
        d = tx[(tx.src == u) & (tx.dst == v)].date
        if prev is not None:
            d = d[d >= prev]
        if d.empty:
            return None
        prev = d.min()
        dates.append(prev)
    return dates


def overview() -> dict:
    import json
    df = _state()[0]
    s = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    s["seeds"] = int(df.is_seed.sum())
    s["anomalies"] = int((df.anomaly_count > 0).sum())
    s["turnover_kzt"] = float(_state()[3].size(weight="sum_kzt"))
    s["in_core"] = int(df.in_core.sum())
    s["top5"] = top(5)
    return s
