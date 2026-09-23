"""«Граф денег»: raw parquet → роли, кластеры, приоритет → out/*.csv + out/graph.json.

Запуск:  python -m app.pipeline [--data data/raw] [--out out]

Все пороги собраны в THRESHOLDS и описаны в README — роли выдаются только правилами,
без обучения и без захардкоженных gid.
"""

import argparse
import json
import time
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

THRESHOLDS = {
    "coord_in_deg": 5,        # coordinator: собирает от ≥5 плательщиков ...
    "coord_out_deg": 10,      # ... и раздаёт ≥10 получателям
    "coord_seeds": 3,         # или: в пределах 2 шагов выше ≥3 seed, и он переводит дальше ≥3 получателям
    "coord_seeds_out": 3,
    "cycle_len": 6,           # возвратные потоки: циклы длиной ≤6
    "dist_out_deg": 10,       # distributor: веер на ≥10 получателей
    "cons_in_deg": 3,         # consolidator: входящие от ≥3 разных плательщиков
    "transit_pt_lo": 0.5,     # transit: отдал дальше 50–200% полученного
    "transit_pt_hi": 2.0,
    "keep_pt": 0.2,           # terminal: отдал дальше < 20% полученного
    "terminal_min_kzt": 100_000,  # terminal: получил ≥100 тыс. или от ≥2 плательщиков
    "fast_days": 2,           # сквозной транзит: ушло в течение 2 дней после поступления
    "sync_payers": 3,         # синхронные переводы: ≥3 разных плательщика в один день
    # аномалии (флаги, на роль и приоритет не влияют)
    "small_lo": 5_000, "small_hi": 10_000,  # дробление: мелкие переводы 5–10 тыс. ₸ ...
    "small_min_tx": 5, "small_share": 0.7,  # ... ≥5 входящих, из них ≥70% мелкие
    "repeat_same_amount": 8,  # повтор: одна и та же сумма отправлена ≥8 раз
    "depth_z": 2.5,           # оборот нетипичен для своего колена: z-score log(оборота) > 2.5
}

ROLE_WEIGHT = {"coordinator": 1.0, "consolidator": 0.85, "distributor": 0.75,
               "transit": 0.5, "terminal": 0.35, "peripheral": 0.05}

ROLE_RU = {"coordinator": "координатор", "consolidator": "точка консолидации",
           "distributor": "распределитель", "transit": "транзит",
           "terminal": "конечный получатель", "peripheral": "периферия"}


def kzt(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ") + " ₸"


def plain(r) -> str:
    """Короткое объяснение для экрана; не меняет роль или оценку узла."""
    if r.truncated:
        text = "Дальше данных нет: выгрузка обрывается на 4-м шаге"
    elif r.role == "coordinator":
        text = (f"Собирает деньги от {int(r.in_deg)} человек и раздаёт {int(r.out_deg)} людям "
                "— похоже на организатора")
    elif r.role == "consolidator":
        text = f"Собирает деньги от {int(r.in_deg)} разных людей — похоже на «копилку»"
    elif r.role == "distributor":
        text = f"Раздаёт деньги {int(r.out_deg)} людям — «веер»"
    elif r.role == "transit":
        if r.is_seed or r.in_kzt == 0 or r.pass_through > 2:
            text = "Отправляет деньги дальше — возможный транзит; часть входящих не видна"
        elif r.fast_share >= 0.5:
            text = "Получает и быстро пересылает дальше — похоже на «прокладку»"
        else:
            text = "Получает и пересылает дальше — возможная «прокладка»"
    elif r.role == "terminal":
        kept = "большую часть " if r.out_deg else ""
        text = f"Похоже, получает деньги и оставляет {kept}у себя — в пределах видимой сети"
    else:
        text = "Явных признаков нет"
    return text + (" (уже известен следствию)" if r.is_seed else "")


# ------------------------------------------------------------------ загрузка и граф

def load(data_dir: Path):
    edges = pd.read_parquet(data_dir / "edges.parquet")
    nodes = pd.read_parquet(data_dir / "nodes.parquet")
    tx = pd.read_parquet(data_dir / "transactions.parquet")
    tx["date"] = pd.to_datetime(tx["date"])
    return edges, nodes, tx


def build_graph(edges, nodes) -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_nodes_from(nodes.gid.tolist())
    for r in edges.itertuples(index=False):
        G.add_edge(int(r.src), int(r.dst), sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx))
    return G


# ------------------------------------------------------------------ метрики

def temporal_features(tx: pd.DataFrame) -> pd.DataFrame:
    """Сквозной транзит и синхронные поступления по датам транзакций."""
    days = THRESHOLDS["fast_days"]
    inc = tx.rename(columns={"dst": "gid", "src": "payer"})[["gid", "payer", "date", "sum_kzt"]]
    out = tx.rename(columns={"src": "gid"})[["gid", "date", "sum_kzt"]]

    # доля исходящей суммы, ушедшей в течение N дней после какого-либо поступления
    m = out.reset_index().merge(inc[["gid", "date"]], on="gid", suffixes=("", "_in"))
    lag = (m["date"] - m["date_in"]).dt.days
    fast_ids = m.loc[(lag >= 0) & (lag <= days), "index"].unique()
    out["fast"] = out.index.isin(fast_ids)
    fast = out.groupby("gid").apply(
        lambda g: g.loc[g.fast, "sum_kzt"].sum() / g.sum_kzt.sum(), include_groups=False
    ).rename("fast_share")

    # максимум разных плательщиков за один день
    sync = inc.groupby(["gid", "date"]).payer.nunique().groupby("gid").max().rename("max_payers_day")

    active = pd.concat([inc[["gid", "date"]], out[["gid", "date"]]]).groupby("gid").date.nunique() \
        .rename("active_days")
    return pd.concat([fast, sync, active], axis=1)


def anomaly_flags(tx: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Три правила-флага: дробление на мелкие суммы, повтор одинаковых сумм, оборот нетипичен для колена."""
    T = THRESHOLDS
    flags: dict[int, list[str]] = {}
    small = (tx.sum_kzt >= T["small_lo"]) & (tx.sum_kzt < T["small_hi"])
    inc = tx.assign(small=small).groupby("dst").agg(n=("small", "size"), k=("small", "sum"), p=("src", "nunique"))
    for g, r in inc[(inc.n >= T["small_min_tx"]) & (inc.k / inc.n >= T["small_share"])].iterrows():
        flags.setdefault(g, []).append(f"дробление: {int(r.k)} из {int(r.n)} входящих по 5–10 тыс. ₸ от {int(r.p)} плательщ.")
    rep = tx.groupby(["src", "sum_kzt"]).size()
    for (g, amt), k in rep[rep >= T["repeat_same_amount"]].items():
        flags.setdefault(g, []).append(f"повтор суммы: {k}×{amt:,.0f} ₸".replace(",", " "))
    flow = np.log1p(df.in_kzt + df.out_kzt)
    z = flow.groupby(df.depth).transform(lambda x: (x - x.mean()) / x.std())
    for g, dz, dep in zip(df.gid, z, df.depth):
        if dz > T["depth_z"]:
            flags.setdefault(g, []).append(f"оборот нетипичен для колена {dep} (z={dz:.3f}, порог >2.5)")
    return pd.DataFrame({"anomaly_flags": {g: "; ".join(v) for g, v in flags.items()},
                         "anomaly_count": {g: len(v) for g, v in flags.items()}})


def features(G: nx.DiGraph, nodes: pd.DataFrame, tx: pd.DataFrame) -> pd.DataFrame:
    df = nodes[["gid", "depth", "is_seed"]].copy()
    df["depth"] = df.depth.astype(int)
    df["is_seed"] = df.is_seed.astype(bool)
    m = lambda d: df.gid.map(dict(d)).fillna(0)
    df["in_deg"] = m(G.in_degree()).astype(int)
    df["out_deg"] = m(G.out_degree()).astype(int)
    df["in_kzt"] = m(G.in_degree(weight="sum_kzt"))
    df["out_kzt"] = m(G.out_degree(weight="sum_kzt"))
    df["in_tx"] = m(G.in_degree(weight="n_tx")).astype(int)
    df["out_tx"] = m(G.out_degree(weight="n_tx")).astype(int)
    df["pass_through"] = np.where(df.in_kzt > 0, df.out_kzt / df.in_kzt.where(df.in_kzt > 0), np.nan)

    df["pagerank"] = m(nx.pagerank(G, weight="sum_kzt"))
    hubs, auths = nx.hits(G, max_iter=1000)
    df["hub"] = m(hubs)
    df["authority"] = m(auths)
    df["betweenness"] = m(nx.betweenness_centrality(G, k=None))  # направленный граф

    seeds = set(df.loc[df.is_seed, "gid"])
    df["seed_payers"] = df.gid.map(lambda g: len(set(G.predecessors(g)) & seeds))
    df["upstream_seeds"] = df.gid.map(lambda g: len(nx.ancestors(G, g) & seeds))
    R = G.reverse(copy=False)
    df["seeds_2hop"] = df.gid.map(
        lambda g: len((set(nx.single_source_shortest_path_length(R, g, cutoff=2)) - {g}) & seeds))

    # возвратные потоки: сколько циклов ≤6 проходит через узел и входит ли он в крупнейшее «кольцо» (SCC)
    cyc = {}
    for c in nx.simple_cycles(G, length_bound=THRESHOLDS["cycle_len"]):
        for g in c:
            cyc[g] = cyc.get(g, 0) + 1
    df["cycles"] = m(cyc).astype(int)
    core = max(nx.strongly_connected_components(G), key=len)
    df["in_core"] = df.gid.isin(core)

    # Обрыв обхода: исходящие выгружались у узлов колена 0–3; у колена 4 — нет.
    df["truncated"] = (df.depth == 4) & (df.out_deg == 0)
    df["isolated"] = (df.in_deg == 0) & (df.out_deg == 0)

    df = df.merge(temporal_features(tx), left_on="gid", right_index=True, how="left")
    df = df.merge(anomaly_flags(tx, df), left_on="gid", right_index=True, how="left")
    df["anomaly_flags"] = df.anomaly_flags.fillna("нет")
    df["anomaly_count"] = df.anomaly_count.fillna(0).astype(int)
    df[["fast_share", "max_payers_day", "active_days"]] = \
        df[["fast_share", "max_payers_day", "active_days"]].fillna(0)
    df["max_payers_day"] = df.max_payers_day.astype(int)
    df["active_days"] = df.active_days.astype(int)
    return df


# ------------------------------------------------------------------ роли

def assign_role(r) -> tuple[str, float, str]:
    """Правило → (роль, уверенность 0–1, evidence ≤200 символов). Порядок проверок = приоритет ролей."""
    T = THRESHOLDS
    pt = r.pass_through
    pt_txt = f"отдал дальше {pt:.0%} полученного" if pd.notna(pt) and not r.is_seed else ""
    seed_note = "seed; " if r.is_seed else ""

    if r.isolated:
        return "peripheral", 0.9, f"{seed_note}нет переводов ≥5 000 ₸ внутри выгрузки"

    if (r.in_deg >= T["coord_in_deg"] and r.out_deg >= T["coord_out_deg"]) or \
       (r.seeds_2hop >= T["coord_seeds"] and r.out_deg >= T["coord_seeds_out"]):
        score = min(1.0, 0.5 + 0.03 * r.in_deg + 0.005 * r.out_deg + 0.05 * r.seeds_2hop + (0.1 if r.in_core else 0))
        core = f"; в кольце возвратных потоков ({r.cycles} циклов)" if r.in_core else ""
        return "coordinator", score, (
            f"{seed_note}собирает от {r.in_deg} плательщ. ({kzt(r.in_kzt)}), раздаёт {r.out_deg} получ. "
            f"({kzt(r.out_kzt)}); {r.seeds_2hop} seed в 2 шагах выше{core}")

    if r.out_deg >= T["dist_out_deg"]:
        score = min(1.0, 0.5 + r.out_deg / 100)
        return "distributor", score, (
            f"{seed_note}веер: {r.out_tx} переводов на {r.out_deg} разных получателей, {kzt(r.out_kzt)}; "
            f"получил от {r.in_deg} плательщиков")

    if r.in_deg >= T["cons_in_deg"]:
        score = min(1.0, 0.45 + 0.05 * r.in_deg + (0.1 if r.max_payers_day >= T["sync_payers"] else 0))
        sync = f"; до {r.max_payers_day} плательщиков в один день" if r.max_payers_day >= 2 else ""
        tail = f", {pt_txt}" if pt_txt else ""
        if r.truncated:  # 4-е колено: сбор виден, а что стало с деньгами дальше — нет
            tail = "; 4-е колено: исходящие не выгружались"
        return "consolidator", score, (
            f"{seed_note}получает от {r.in_deg} разных плательщиков ({r.in_tx} переводов, {kzt(r.in_kzt)}){tail}{sync}")

    if r.truncated:
        # 4-е колено: исходящие не выгружались — не можем назвать конечным получателем
        return "peripheral", 0.3, (
            f"4-е колено: получил {kzt(r.in_kzt)} от {r.in_deg} плательщ.; исходящие не выгружались (обрыв обхода), "
            f"нужна доп. выгрузка")

    if r.in_deg > 0 and r.out_deg == 0:
        if r.in_kzt >= T["terminal_min_kzt"] or r.in_deg >= 2:
            score = min(1.0, 0.6 + r.in_kzt / 5_000_000)
            return "terminal", score, (
                f"получил {kzt(r.in_kzt)} от {r.in_deg} плательщ. ({r.in_tx} переводов), дальше ничего "
                f"(колено {r.depth}, исходящие выгружены — обрыва нет)")
        return "peripheral", 0.7, (
            f"получил {kzt(r.in_kzt)} ({r.in_tx} перев.) и дальше не переводил; сумма мала для роли")

    if r.in_deg > 0 and pd.notna(pt) and pt < T["keep_pt"] and not r.is_seed:
        return "terminal", 0.55, (
            f"получил {kzt(r.in_kzt)} от {r.in_deg} плательщ., дальше ушло лишь {kzt(r.out_kzt)} "
            f"({pt:.0%}, {r.out_deg} получ.) — удерживает большую часть")

    if r.out_deg > 0:
        fast = f"; {r.fast_share:.0%} суммы ушло за ≤{T['fast_days']} дня после поступления" \
            if r.fast_share > 0 else ""
        if r.is_seed:
            return "transit", 0.45, (
                f"seed: отправил {kzt(r.out_kzt)} {r.out_deg} получ.; входящие вне выгрузки — роль по исходящим{fast}")
        if pd.notna(pt) and T["transit_pt_lo"] <= pt <= T["transit_pt_hi"]:
            score = min(1.0, 0.55 + 0.4 * r.fast_share - 0.2 * abs(1 - pt))
            return "transit", score, (
                f"получил {kzt(r.in_kzt)}, {pt_txt} ({r.out_deg} получ.){fast}")
        if pd.notna(pt) and pt > T["transit_pt_hi"]:
            return "transit", 0.35, (
                f"отдал {kzt(r.out_kzt)} при видимых входящих {kzt(r.in_kzt)} — полнота входа и начальный остаток неизвестны{fast}")
        return "peripheral", 0.5, (
            f"получил {kzt(r.in_kzt)}, {pt_txt}; ни сбора, ни веера, ни чистого транзита")

    return "peripheral", 0.5, "нет выраженных признаков роли"


# ------------------------------------------------------------------ кластеры

def clusters(G: nx.DiGraph, df: pd.DataFrame) -> dict:
    """Louvain на НЕориентированной проекции (вес = сумма). Направление учитывается в ролях, не в кластерах."""
    UG = nx.Graph()
    UG.add_nodes_from(G.nodes)
    for u, v, d in G.edges(data=True):
        w = UG[u][v]["weight"] + d["sum_kzt"] if UG.has_edge(u, v) else d["sum_kzt"]
        UG.add_edge(u, v, weight=w)
    isolated = [n for n in UG if UG.degree(n) == 0]
    UG.remove_nodes_from(isolated)
    comms = nx.community.louvain_communities(UG, weight="weight", seed=42, resolution=1.0)
    comms = sorted(comms, key=len, reverse=True)
    cid = {g: i + 1 for i, c in enumerate(comms) for g in c}
    cid.update({g: 0 for g in isolated})  # 0 = изолированные узлы без переводов
    return cid


def cluster_table(G: nx.DiGraph, df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c, g in df.groupby("cluster_id"):
        members = set(g.gid)
        internal = sum(d["sum_kzt"] for u, v, d in G.edges(data=True) if u in members and v in members)
        top = g.sort_values(["priority_score", "gid"], ascending=[False, True]).head(5)
        roles = g.role.value_counts()
        rows.append({
            "cluster_id": int(c), "n_nodes": len(g), "n_seed": int(g.is_seed.sum()),
            "sum_kzt_internal": round(internal, 2),
            "top_gids": ";".join(str(x) for x in top.gid),
            "hypothesis": hypothesis(c, g, roles, internal),
            "roles": "; ".join(f"{k}:{v}" for k, v in roles.items()),
        })
    return pd.DataFrame(rows).sort_values(["sum_kzt_internal", "cluster_id"], ascending=[False, True])


def hypothesis(c, g, roles, internal) -> str:
    if c == 0:
        return f"{len(g)} seed без переводов ≥5 000 ₸ в июле: активность вне выборки неизвестна — запросить полную выписку"
    n_seed = int(g.is_seed.sum())
    lead = g.sort_values(["priority_score", "gid"], ascending=[False, True]).iloc[0]
    parts = []
    if roles.get("coordinator", 0) or roles.get("consolidator", 0):
        parts.append(f"признаки сбора средств: {roles.get('coordinator', 0)} координ., "
                     f"{roles.get('consolidator', 0)} точек консолидации")
    if roles.get("distributor", 0):
        parts.append(f"{roles['distributor']} веерных распределителя")
    if roles.get("transit", 0):
        parts.append(f"{roles['transit']} транзитных")
    if n_seed >= 2:
        parts.append(f"объединяет {n_seed} seed — вероятно, общая инфраструктура")
    elif n_seed == 1:
        parts.append("цепочка одного seed")
    else:
        parts.append("без seed — дальнее окружение сети")
    return (f"Гипотеза: {'; '.join(parts)}. Ключевой узел {lead.gid} ({ROLE_RU[lead.role]}), "
            f"оборот внутри {kzt(internal)}")[:300]


# ------------------------------------------------------------------ приоритет

def pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True, method="average") if s.max() > 0 else s * 0


def priority(df: pd.DataFrame) -> pd.Series:
    """Прозрачная формула: роль + денежный вес + сходимость seed + посредничество.
    Seed уже известны следствию — умножаем на 0.8, чтобы фокус сместился на неизвестных."""
    flow = df.in_kzt + df.out_kzt
    s = (0.40 * df.role.map(ROLE_WEIGHT) * df.role_score
         + 0.20 * pct(flow)
         + 0.15 * pct(df.pagerank)
         + 0.15 * pct(df.seeds_2hop)
         + 0.05 * pct(df.betweenness)
         + 0.05 * df.in_core)
    s = s * np.where(df.is_seed, 0.8, 1.0)
    s = s * np.where(df.truncated, 0.8, 1.0)
    return (s / s.max()).round(4)


def why(r) -> str:
    extra = []
    if r.seeds_2hop:
        extra.append(f"{r.seeds_2hop} seed в 2 шагах выше")
    if r.in_core:
        extra.append(f"в кольце возвратных потоков, {r.cycles} циклов")
    if r.fast_share >= 0.5 and r.out_deg:
        extra.append(f"{r.fast_share:.0%} ушло за ≤2 дня")
    if r.is_seed:
        extra.append("уже известен (seed)")
    extra = [x for x in extra if x.split(",")[0] not in r.evidence]
    return f"{ROLE_RU[r.role]}: {r.evidence}" + (f" | {', '.join(extra)}" if extra else "")


# ------------------------------------------------------------------ устойчивость

def resilience(G: nx.DiGraph, ranked: list[int], steps=(0, 5, 10, 20)) -> list[dict]:
    UG = G.to_undirected()
    base = max(len(c) for c in nx.connected_components(UG))
    out = []
    for n in steps:
        H = UG.copy()
        H.remove_nodes_from(ranked[:n])
        comps = [len(c) for c in nx.connected_components(H) if len(c) > 1]
        out.append({"removed_top": n, "largest_component": max(comps),
                    "largest_share": round(max(comps) / base, 3), "fragments": len(comps)})
    return out


# ------------------------------------------------------------------ main

def run(data_dir: Path, out_dir: Path) -> dict:
    t0 = time.time()
    edges, nodes, tx = load(data_dir)
    G = build_graph(edges, nodes)
    df = features(G, nodes, tx)

    res = df.apply(assign_role, axis=1, result_type="expand")
    df["role"], df["role_score"], df["evidence"] = res[0], res[1].round(3), res[2].str.slice(0, 200)

    df["cluster_id"] = df.gid.map(clusters(G, df)).astype(int)
    df["priority_score"] = priority(df)
    # Equal scores use the full gid, so pandas/NumPy versions cannot change the top-N boundary.
    df = df.sort_values(["priority_score", "gid"], ascending=[False, True])

    out_dir.mkdir(parents=True, exist_ok=True)
    cols = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence",
            "depth", "is_seed", "truncated", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx", "out_tx",
            "pass_through", "pagerank", "hub", "authority", "betweenness", "seed_payers", "seeds_2hop",
            "upstream_seeds", "cycles", "in_core",
            "fast_share", "max_payers_day", "active_days", "anomaly_count", "anomaly_flags"]
    # pass_through = -1: входящих в выгрузке нет, отношение не определено
    df[cols].fillna({"pass_through": -1}).to_csv(out_dir / "nodes_roles.csv", index=False)

    ct = cluster_table(G, df)
    ct.to_csv(out_dir / "clusters.csv", index=False)

    top = df.head(50).copy()
    top.insert(0, "rank", range(1, len(top) + 1))
    top["why"] = top.apply(why, axis=1)
    top[["rank", "gid", "role", "priority_score", "why", "cluster_id", "is_seed"]] \
        .to_csv(out_dir / "top_nodes.csv", index=False)

    resil = resilience(G, df.gid.tolist())
    graph = {
        "nodes": [{"id": str(r.gid), "label": str(r.gid)[-10:], "role": r.role, "cluster": int(r.cluster_id),
                   "priority": float(r.priority_score), "is_seed": bool(r.is_seed), "depth": int(r.depth),
                   "truncated": bool(r.truncated), "in_core": bool(r.in_core),
                   "anomalies": int(r.anomaly_count), "in_kzt": float(r.in_kzt), "out_kzt": float(r.out_kzt),
                   "evidence": r.evidence, "plain": plain(r)} for r in df.itertuples()],
        "edges": [{"from": str(r.src), "to": str(r.dst), "sum_kzt": float(r.sum_kzt), "n_tx": int(r.n_tx)}
                  for r in edges.itertuples()],
        "resilience": resil,
        "thresholds": THRESHOLDS,
    }
    (out_dir / "graph.json").write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")

    summary = {
        "nodes": len(df), "edges": len(edges), "clusters": int(ct.shape[0]),
        "roles": df.role.value_counts().to_dict(), "truncated": int(df.truncated.sum()),
        "anomalies": int((df.anomaly_count > 0).sum()),
        "resilience": resil, "seconds": round(time.time() - t0, 1),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser(description="Граф денег: роли, кластеры, приоритеты")
    ap.add_argument("--data", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--out", default=str(ROOT / "out"))
    a = ap.parse_args()
    s = run(Path(a.data), Path(a.out))
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
