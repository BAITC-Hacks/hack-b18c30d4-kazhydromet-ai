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


def read_csv(name: str) -> tuple[list[dict[str, str]], set[str]]:
    with (ROOT / "out" / name).open(encoding="utf-8-sig", newline="") as file:
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


def main() -> int:
    global failed
    start = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="aml-output-check-") as temporary:
            run(ROOT / "data" / "raw", Path(temporary))
            elapsed = time.perf_counter() - start
    except Exception as exc:
        report("full recompute under 300 s", False, f"{type(exc).__name__}: {exc}")
        return 1
    report("full recompute under 300 s", elapsed < 300, f"{elapsed:.2f} s")

    try:
        nodes, node_columns = read_csv("nodes_roles.csv")
        clusters, cluster_columns = read_csv("clusters.csv")
        top, top_columns = read_csv("top_nodes.csv")
        raw_nodes = pd.read_parquet(ROOT / "data" / "raw" / "nodes.parquet", columns=["gid", "depth"])
        raw_edges = pd.read_parquet(ROOT / "data" / "raw" / "edges.parquet", columns=["src"])
    except Exception as exc:
        report("read generated CSVs and raw parquet", False, f"{type(exc).__name__}: {exc}")
        return 1
    report("read generated CSVs and raw parquet", True)

    gids = [(row.get("gid") or "").strip() for row in nodes]
    gid_set = set(gids)
    raw_gids = {str(gid) for gid in raw_nodes.gid}
    report("nodes_roles: 2248 rows", len(nodes) == EXPECTED_NODES, f"found {len(nodes)}")
    report("nodes_roles: unique gid", len(gids) == len(gid_set) and all(gids))
    report("nodes_roles: gid match raw nodes", gid_set == raw_gids)
    report("nodes_roles: required columns", NODE_COLUMNS <= node_columns)
    report("nodes_roles: no empty required values", NODE_COLUMNS <= node_columns and all(
        (row.get(col) or "").strip() for row in nodes for col in NODE_COLUMNS
    ))
    invalid_roles = [row.get("gid", "") for row in nodes if row.get("role") not in ROLES]
    report("nodes_roles: roles in dictionary", not invalid_roles, f"invalid {len(invalid_roles)}")
    for col in ("role_score", "priority_score"):
        invalid = [row.get("gid", "") for row in nodes if not 0 <= number(row.get(col, "")) <= 1]
        report(f"nodes_roles: {col} in [0,1]", not invalid, f"invalid {len(invalid)}")
    invalid_evidence = [row.get("gid", "") for row in nodes if not (
        0 < len((row.get("evidence") or "").strip()) <= 200
        and any(char.isdigit() for char in (row.get("evidence") or ""))
    )]
    report("nodes_roles: evidence 1..200 chars with a digit", not invalid_evidence,
           f"invalid {len(invalid_evidence)}")

    report("clusters: required columns", CLUSTER_COLUMNS <= cluster_columns)
    node_cluster_ids = [integer(row.get("cluster_id", "")) for row in nodes]
    cluster_ids = [integer(row.get("cluster_id", "")) for row in clusters]
    report("clusters: covers every node cluster_id", bool(clusters) and None not in node_cluster_ids
           and None not in cluster_ids and set(node_cluster_ids) <= set(cluster_ids))
    node_counts = [integer(row.get("n_nodes", "")) for row in clusters]
    seed_counts = [integer(row.get("n_seed", "")) for row in clusters]
    report("clusters: sum n_nodes = 2248", None not in node_counts and sum(node_counts) == EXPECTED_NODES,
           f"found {sum(x for x in node_counts if x is not None)}")
    report("clusters: sum n_seed = 81", None not in seed_counts and sum(seed_counts) == EXPECTED_SEEDS,
           f"found {sum(x for x in seed_counts if x is not None)}")

    report("top_nodes: at least 20 rows", len(top) >= 20, f"found {len(top)}")
    report("top_nodes: required columns", TOP_COLUMNS <= top_columns)
    priorities = [number(row.get("priority_score", "")) for row in top]
    report("top_nodes: descending priority", all(math.isfinite(x) for x in priorities)
           and all(a >= b for a, b in zip(priorities, priorities[1:])))
    report("top_nodes: gid in nodes_roles", all(row.get("gid", "") in gid_set for row in top))
    report("top_nodes: consecutive rank", [integer(row.get("rank", "")) for row in top]
           == list(range(1, len(top) + 1)))

    depth4 = {str(row.gid) for row in raw_nodes.itertuples() if row.depth == 4}
    outgoing = {str(src) for src in raw_edges.src}
    truncated = depth4 - outgoing
    terminal = {row.get("gid", "") for row in nodes if row.get("role") == "terminal"}
    bad_terminal = truncated & terminal
    report("depth=4 with out_deg=0: no terminal role", not bad_terminal,
           f"checked {len(truncated)}, invalid {len(bad_terminal)}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
