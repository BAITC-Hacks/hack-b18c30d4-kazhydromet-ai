"""Recompute and validate the three CSV deliverables against the case specification."""

import csv
import math
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pipeline import run  # noqa: E402


EXPECTED_NODES = 2248
EXPECTED_SEEDS = 81
ROLES = {"coordinator", "consolidator", "distributor", "transit", "terminal", "peripheral"}
NODE_COLUMNS = {"gid", "role", "role_score", "cluster_id", "priority_score", "evidence"}
CLUSTER_COLUMNS = {"cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"}
TOP_COLUMNS = {"rank", "gid", "role", "priority_score", "why"}
failed = False


def report(label: str, ok: bool, detail: str = "") -> None:
    global failed
    print(f"{'OK  ' if ok else 'FAIL'} {label}{f' ({detail})' if detail else ''}")
    failed |= not ok


def read_csv(out_dir: Path, name: str) -> tuple[list[dict[str, str]], set[str]]:
    with (out_dir / name).open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        return rows, set(reader.fieldnames or [])


def number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def integer(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def check_outputs(out_dir: Path, raw_nodes: pd.DataFrame, raw_edges: pd.DataFrame) -> list[tuple[str, bool, str]]:
    """Validate one complete output set; callers keep fresh files alive until this returns."""
    checks = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append((label, bool(ok), detail))

    nodes, node_columns = read_csv(out_dir, "nodes_roles.csv")
    clusters, cluster_columns = read_csv(out_dir, "clusters.csv")
    top, top_columns = read_csv(out_dir, "top_nodes.csv")

    gids = [(row.get("gid") or "").strip() for row in nodes]
    gid_set = set(gids)
    raw_gids = {str(gid) for gid in raw_nodes.gid}
    check("nodes_roles: 2248 rows", len(nodes) == EXPECTED_NODES, f"found {len(nodes)}")
    check("nodes_roles: unique gid", len(gids) == len(gid_set) and all(gids))
    check("nodes_roles: gid match raw nodes", gid_set == raw_gids)
    check("nodes_roles: required columns", NODE_COLUMNS <= node_columns)
    check("nodes_roles: no empty required values", NODE_COLUMNS <= node_columns and all(
        (row.get(col) or "").strip() for row in nodes for col in NODE_COLUMNS
    ))
    invalid_roles = [row.get("gid", "") for row in nodes if row.get("role") not in ROLES]
    check("nodes_roles: roles in dictionary", not invalid_roles, f"invalid {len(invalid_roles)}")
    for col in ("role_score", "priority_score"):
        invalid = [row.get("gid", "") for row in nodes if not 0 <= number(row.get(col, "")) <= 1]
        check(f"nodes_roles: {col} in [0,1]", not invalid, f"invalid {len(invalid)}")
    invalid_evidence = [row.get("gid", "") for row in nodes if not (
        bool((row.get("evidence") or "").strip())
        and len(row.get("evidence") or "") <= 200
        and any(char.isdigit() for char in (row.get("evidence") or ""))
    )]
    check("nodes_roles: evidence 1..200 chars with a digit", not invalid_evidence,
           f"invalid {len(invalid_evidence)}")

    check("clusters: required columns", CLUSTER_COLUMNS <= cluster_columns)
    node_cluster_ids = [integer(row.get("cluster_id", "")) for row in nodes]
    cluster_ids = [integer(row.get("cluster_id", "")) for row in clusters]
    check("clusters: covers every node cluster_id", bool(clusters) and None not in node_cluster_ids
           and None not in cluster_ids and set(node_cluster_ids) <= set(cluster_ids))
    node_counts = [integer(row.get("n_nodes", "")) for row in clusters]
    seed_counts = [integer(row.get("n_seed", "")) for row in clusters]
    check("clusters: sum n_nodes = 2248", None not in node_counts and sum(node_counts) == EXPECTED_NODES,
           f"found {sum(x for x in node_counts if x is not None)}")
    check("clusters: sum n_seed = 81", None not in seed_counts and sum(seed_counts) == EXPECTED_SEEDS,
           f"found {sum(x for x in seed_counts if x is not None)}")

    check("top_nodes: at least 20 rows", len(top) >= 20, f"found {len(top)}")
    check("top_nodes: required columns", TOP_COLUMNS <= top_columns)
    priorities = [number(row.get("priority_score", "")) for row in top]
    expected_top = sorted(nodes, key=lambda row: (-number(row.get("priority_score", "")), row.get("gid", "")))[:len(top)]
    check("top_nodes: descending priority, gid breaks ties", all(math.isfinite(x) for x in priorities)
           and all(a >= b for a, b in zip(priorities, priorities[1:]))
           and [row.get("gid") for row in top] == [row.get("gid") for row in expected_top])
    check("top_nodes: gid in nodes_roles", all(row.get("gid", "") in gid_set for row in top))
    check("top_nodes: consecutive rank", [integer(row.get("rank", "")) for row in top]
           == list(range(1, len(top) + 1)))

    depth4 = {str(row.gid) for row in raw_nodes.itertuples() if row.depth == 4}
    outgoing = {str(src) for src in raw_edges.src}
    truncated = depth4 - outgoing
    terminal = {row.get("gid", "") for row in nodes if row.get("role") == "terminal"}
    bad_terminal = truncated & terminal
    check("depth=4 with out_deg=0: no terminal role", not bad_terminal,
           f"checked {len(truncated)}, invalid {len(bad_terminal)}")

    return checks


def main() -> int:
    global failed
    failed = False
    with tempfile.TemporaryDirectory(prefix="aml-output-check-") as temporary:
        fresh = Path(temporary)
        start = time.perf_counter()
        try:
            run(ROOT / "data" / "raw", fresh)
            elapsed = time.perf_counter() - start
        except Exception as exc:
            report("full recompute under 300 s", False, f"{type(exc).__name__}: {exc}")
            return 1
        report("full recompute under 300 s", elapsed < 300, f"{elapsed:.2f} s")

        try:
            raw_nodes = pd.read_parquet(ROOT / "data" / "raw" / "nodes.parquet", columns=["gid", "depth"])
            raw_edges = pd.read_parquet(ROOT / "data" / "raw" / "edges.parquet", columns=["src"])
        except Exception as exc:
            report("read generated CSVs and raw parquet", False, f"raw: {type(exc).__name__}: {exc}")
            return 1

        results = {}
        errors = []
        for source, out_dir in (("saved", ROOT / "out"), ("fresh", fresh)):
            try:
                results[source] = check_outputs(out_dir, raw_nodes, raw_edges)
            except Exception as exc:
                errors.append(f"{source}: {type(exc).__name__}: {exc}")
        report("read generated CSVs and raw parquet", not errors, "; ".join(errors) or "saved + fresh")
        if errors:
            return 1

        for saved, generated in zip(results["saved"], results["fresh"]):
            label = saved[0]
            ok = saved[1] and generated[1]
            if not ok:
                detail = "; ".join(f"{source}: {check[2] or 'failed'}"
                                   for source, check in (("saved", saved), ("fresh", generated)) if not check[1])
            else:
                detail = saved[2] if saved[2] == generated[2] else f"saved: {saved[2]}; fresh: {generated[2]}"
            report(label, ok, detail)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
