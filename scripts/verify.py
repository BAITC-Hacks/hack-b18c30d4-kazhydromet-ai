"""Run output and HTTP checks, then save their results and artifact hashes as JSON."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = (
    "data/raw/nodes.parquet", "data/raw/edges.parquet", "data/raw/transactions.parquet",
    "out/nodes_roles.csv", "out/clusters.csv", "out/top_nodes.csv",
    "out/graph.json", "out/summary.json",
)


def git_metadata() -> dict:
    """Record revision and a dirty flag, without including filenames or file contents."""
    result = {"git_commit": None, "workingtree_dirty_before": None}
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        if revision.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", revision.stdout.strip()):
            result["git_commit"] = revision.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal", "--", ".",
             ":(exclude).env", ":(exclude)**/.env"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        if status.returncode == 0:
            result["workingtree_dirty_before"] = bool(status.stdout.strip())
        if revision.returncode or status.returncode:
            result["git_metadata_error"] = "Git metadata is unavailable for this checkout"
    except (OSError, subprocess.TimeoutExpired) as error:
        result["git_metadata_error"] = type(error).__name__
    return result


def stop_step(process: subprocess.Popen) -> None:
    """Stop only this verifier's child tree, including its temporary HTTP server."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)


def run_step(script: str, arguments: list[str], timeout: int, env: dict) -> dict:
    command = ["python", script, *arguments]
    result = {"command": command, "exit_code": 1, "elapsed_seconds": 0.0,
              "check_count": 0, "stdout": ""}
    process = None
    started = time.monotonic()
    print("RUN  " + " ".join(command), flush=True)
    try:
        process = subprocess.Popen(
            [sys.executable, script, *arguments], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        try:
            output, _ = process.communicate(timeout=timeout)
            result["exit_code"] = process.returncode
        except subprocess.TimeoutExpired:
            stop_step(process)
            output, _ = process.communicate(timeout=5)
            result.update(exit_code=124, timed_out=True, timeout_seconds=timeout)
        result["stdout"] = output
    except (OSError, subprocess.SubprocessError) as error:
        result["error"] = type(error).__name__
    finally:
        if process is not None and process.poll() is None:
            stop_step(process)
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["check_count"] = sum(bool(re.match(r"^OK(?:\s|$)", line))
                                for line in result["stdout"].splitlines())
    if result["stdout"]:
        print(result["stdout"], end="" if result["stdout"].endswith("\n") else "\n", flush=True)
    print(f"STEP exit={result['exit_code']} checks={result['check_count']} "
          f"seconds={result['elapsed_seconds']}", flush=True)
    if result.get("error"):
        print("FAIL " + result["error"], flush=True)
    return result


def artifact_hashes() -> tuple[dict, dict]:
    hashes, errors = {}, {}
    for name in ARTIFACTS:
        try:
            digest = hashlib.sha256()
            with (ROOT / name).open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            hashes[name] = digest.hexdigest()
        except OSError as error:
            hashes[name] = None
            errors[name] = type(error).__name__
    return hashes, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8013, help="Temporary HTTP port; 8000 is forbidden")
    parser.add_argument("--out", type=Path, default=Path("out/verification.json"), help="JSON evidence file")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.port == 8000:
        parser.error("use a port from 1024 to 65535 other than the owner's port 8000")

    report = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **git_metadata(),
        "platform": platform.platform(),
        "python": {"version": platform.python_version(), "implementation": platform.python_implementation()},
    }
    child_env = os.environ.copy()
    child_env.update({"PYTHON_DOTENV_DISABLED": "1", "OPENAI_API_KEY": "", "NVIDIA_API_KEY": "",
                      "LLM_PROVIDER": "openai", "PYTHONIOENCODING": "utf-8"})
    report["steps"] = [
        run_step("scripts/check_outputs.py", [], 350, child_env),
        run_step("scripts/smoke_api.py", ["--port", str(args.port)], 90, child_env),
    ]
    report["sha256"], hash_errors = artifact_hashes()
    if hash_errors:
        report["hash_errors"] = hash_errors
    report["overall_passed"] = all(step["exit_code"] == 0 for step in report["steps"]) and not hash_errors
    destination = args.out if args.out.is_absolute() else ROOT / args.out
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        print("FAIL could not write verification JSON: " + type(error).__name__)
        return 1
    print(("PASS" if report["overall_passed"] else "FAIL") + " verification; JSON: " + str(args.out))
    return 0 if report["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
