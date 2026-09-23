"""Exercise the local HTTP API without reading .env or calling a paid model."""

import argparse
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
CONTROL_GID = "100000008603629100"
TRUNCATED_GID = "100000003037476100"
UNKNOWN_GID = "000000000000000000"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8013, help="Temporary localhost port (default: 8013)")
    parser.add_argument("--timeout", type=float, default=30, help="Timeout of each HTTP request in seconds")
    parser.add_argument("--startup-timeout", type=float, default=60, help="Server startup deadline in seconds")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.port == 8000:
        parser.error("use a port from 1024 to 65535 other than the owner's port 8000")
    if args.timeout <= 0 or args.startup_timeout <= 0:
        parser.error("timeouts must be positive")

    # Refuse an occupied port; never stop or attach to an existing server.
    try:
        with socket.socket() as probe:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(("127.0.0.1", args.port))
    except OSError:
        print(f"FAIL port {args.port} is occupied; choose another --port")
        return 1

    required = ("nodes_roles.csv", "clusters.csv", "top_nodes.csv", "graph.json", "summary.json")
    if any(not (ROOT / "out" / name).is_file() for name in required):
        print("FAIL missing outputs; first run: python -m app.pipeline")
        return 1

    child_env = os.environ.copy()
    child_env.update({
        "PYTHON_DOTENV_DISABLED": "1",
        "OPENAI_API_KEY": "",
        "NVIDIA_API_KEY": "",
        "LLM_PROVIDER": "openai",
        "OPENAI_MODEL": "gpt-5-mini",
        "PUBLIC_DEMO": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    base_url = f"http://127.0.0.1:{args.port}"
    opener = build_opener(ProxyHandler({}))
    checks = 0
    process = None

    def check(label: str, condition: bool) -> None:
        nonlocal checks
        if not condition:
            raise AssertionError(label)
        checks += 1
        print("OK   " + label, flush=True)

    def request(path: str, method: str = "GET", payload=None, timeout=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(base_url + path, data=body, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            response = opener.open(req, timeout=timeout or args.timeout)
        except HTTPError as error:
            response = error
        with response:
            return response.status, dict(response.headers), response.read().decode("utf-8")

    def get_json(path: str):
        status, _, body = request(path)
        if status != 200:
            raise AssertionError(f"GET {path}: expected HTTP 200, got {status}")
        return json.loads(body)

    # The log has no secrets: credentials are blank and dotenv loading is disabled.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as server_log:
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                 "--port", str(args.port), "--no-access-log"],
                cwd=ROOT, env=child_env, stdout=server_log, stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + args.startup_timeout
            health = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"server exited during startup with code {process.returncode}")
                try:
                    status, _, body = request("/api/health", timeout=1)
                    if status == 200:
                        health = json.loads(body)
                        break
                except (URLError, TimeoutError, OSError):
                    pass
                time.sleep(0.2)
            if health is None:
                raise TimeoutError("server did not become ready before the startup deadline")
            check("health: ready, mock provider, public demo", health.get("ok") is True
                  and health.get("live") is False and health.get("provider") == "openai"
                  and health.get("public_demo") is True)

            for path in ("/", "/graph.html", "/vendor/tailwind.js", "/vendor/vis-network.min.js"):
                status, _, body = request(path)
                check(f"static {path}: HTTP 200", status == 200 and bool(body))
            overview = get_json("/api/overview")
            check("overview: 2248 nodes and 81 seeds", overview["nodes"] == 2248 and overview["seeds"] == 81)
            graph = get_json("/api/graph")
            check("graph: 2248 string gids and 3119 directed edges", len(graph["nodes"]) == 2248
                  and len(graph["edges"]) == 3119
                  and all(isinstance(n["id"], str) and len(n["id"]) == 18 and n["id"].isdigit()
                          for n in graph["nodes"])
                  and all(isinstance(e["from"], str) and isinstance(e["to"], str) for e in graph["edges"]))
            top = get_json("/api/top?n=20")
            check("top: 20 clients in descending priority", len(top) == 20
                  and all(top[i]["priority_score"] >= top[i + 1]["priority_score"] for i in range(19)))
            card = get_json("/api/node/" + CONTROL_GID)
            check("control card: 19 payers, 61 receivers, evidence and gaps", card["gid"] == CONTROL_GID
                  and card["metrics"]["in_deg"] == 19 and card["metrics"]["out_deg"] == 61
                  and bool(card["evidence"]) and isinstance(card["gaps"], list))
            truncated = get_json("/api/node/" + TRUNCATED_GID)
            check("fourth hop remains truncated, not terminal", truncated["metrics"]["truncated"] is True
                  and truncated["role"] != "terminal")
            timeline = get_json("/api/timeline/" + CONTROL_GID)
            check("timeline: 31 days, monthly sums match card", len(timeline["days"]) == 31
                  and math.isclose(sum(day["in_kzt"] for day in timeline["days"]), card["metrics"]["in_kzt"], abs_tol=0.01)
                  and math.isclose(sum(day["out_kzt"] for day in timeline["days"]), card["metrics"]["out_kzt"], abs_tol=0.01))
            selected = {CONTROL_GID, TRUNCATED_GID}
            query = "gids=" + CONTROL_GID + "," + TRUNCATED_GID
            coverage = get_json("/api/review-coverage?" + query)
            edges = [edge for edge in graph["edges"] if edge["from"] in selected or edge["to"] in selected]
            check("review coverage: union of transfers, no double counting", coverage["n_selected"] == 2
                  and coverage["n_edges"] == len(edges)
                  and coverage["n_transactions"] == sum(edge["n_tx"] for edge in edges)
                  and math.isclose(coverage["sum_kzt"], sum(edge["sum_kzt"] for edge in edges), abs_tol=0.01))

            status, headers, markdown = request("/api/report?" + query)
            check("report: Markdown attachment with exactly selected cards", status == 200
                  and headers.get("content-type", headers.get("Content-Type", "")).startswith("text/markdown")
                  and "attachment" in headers.get("content-disposition", headers.get("Content-Disposition", ""))
                  and markdown.count("## Узел `") == 2
                  and all(f"## Узел `{gid}`" in markdown for gid in selected)
                  and "## Охват выбранной проверки" in markdown)
            status, _, unknown_report = request("/api/report?gids=" + UNKNOWN_GID)
            check("unknown gid: report remains readable", status == 200 and "не найден" in unknown_report)
            for path in ("/api/node/" + UNKNOWN_GID, "/api/timeline/" + UNKNOWN_GID):
                check(f"unknown gid: {path.split('/')[2]} returns 404", request(path)[0] == 404)
            schema = get_json("/openapi.json")
            if "/api/report/view" in schema["paths"]:
                status, headers, preview = request("/api/report/view?" + query)
                check("report preview: HTML with selected gids", status == 200
                      and headers.get("content-type", headers.get("Content-Type", "")).startswith("text/html")
                      and all(gid in preview for gid in selected))
            else:
                print("SKIP report preview: this revision has no /api/report/view", flush=True)

            status, _, reply = request("/api/chat", "POST", {
                "messages": [{"role": "user", "content": "Объясни роль клиента " + CONTROL_GID}],
            })
            chat = json.loads(reply)
            check("chat: HTTP 200, mock answer grounded in node_card", status == 200
                  and chat.get("mode") == "mock" and CONTROL_GID in chat.get("reply", "")
                  and any(item.get("tool") == "node_card" for item in chat.get("trace", [])))
            selected_date = "2026-07-23"
            day = next(item for item in timeline["days"] if item["date"] == selected_date)
            status, _, reply = request("/api/chat", "POST", {
                "messages": [{"role": "user", "content": "Что произошло в этот день?"}],
                "context": {"selected_gid": CONTROL_GID, "selected_date": selected_date},
            })
            daily_chat = json.loads(reply)
            daily_trace = [item for item in daily_chat.get("trace", []) if item.get("tool") == "daily_transfers"]
            check("chat context: selected client and day reach daily_transfers", status == 200
                  and daily_chat.get("mode") == "mock" and bool(daily_trace)
                  and json.loads(daily_trace[0]["args"]) == {"gid": CONTROL_GID, "date": selected_date}
                  and day["label"] in daily_chat.get("reply", "")
                  and f"{day['in_kzt']:,.0f}".replace(",", " ") in daily_chat["reply"]
                  and f"{day['out_kzt']:,.0f}".replace(",", " ") in daily_chat["reply"])
            status, _, reply = request("/api/chat", "POST", {
                "messages": [{"role": "user", "content": "Какой охват перечня?"}],
                "context": {"review_gids": [CONTROL_GID, TRUNCATED_GID]},
            })
            scope_chat = json.loads(reply)
            scope_trace = [item for item in scope_chat.get("trace", []) if item.get("tool") == "review_scope"]
            check("chat context: selected review list reaches review_scope", status == 200
                  and scope_chat.get("mode") == "mock" and bool(scope_trace)
                  and set(json.loads(scope_trace[0]["args"])["gids"]) == selected
                  and f"{coverage['n_transactions']} переводов" in scope_chat.get("reply", ""))
            status, _, _ = request("/api/chat", "POST", {
                "messages": [{"role": "user", "content": "Объясни роль клиента"}],
                "context": {"selected_gid": CONTROL_GID + "0"},
            })
            check("chat context: 19-digit gid rejected with HTTP 422", status == 422)
            for path in ("/api/recompute", "/api/dataset/upload", "/api/dataset/reset"):
                check(f"public demo: POST {path} is blocked", request(path, "POST")[0] == 403)
            print(f"PASS {checks} checks; no API key or external model used", flush=True)
            return 0
        except Exception as error:
            print(f"FAIL {type(error).__name__}: {error}", flush=True)
            if process is not None and process.poll() is not None:
                server_log.seek(0)
                print("".join(server_log.readlines()[-16:]), flush=True)
            return 1
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                print(f"STOPPED own test server on 127.0.0.1:{args.port}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
