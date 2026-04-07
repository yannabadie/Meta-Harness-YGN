#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import re
import sys
from typing import Iterable

PLUGIN_DATA = pathlib.Path(os.environ.get("CLAUDE_PLUGIN_DATA", "/tmp/meta-harness-lab"))
PLUGIN_ROOT = pathlib.Path(os.environ.get("CLAUDE_PLUGIN_ROOT", pathlib.Path(__file__).resolve().parents[1]))
FRONTIER = PLUGIN_DATA / "frontier.tsv"
RUNS_DIR = PLUGIN_DATA / "runs"
SESSIONS_DIR = PLUGIN_DATA / "sessions"

TSV_HEADER = [
    "run_id",
    "status",
    "primary_score",
    "avg_latency_ms",
    "avg_input_tokens",
    "risk",
    "note",
    "timestamp",
]


def ensure_dirs() -> None:
    PLUGIN_DATA.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    if not FRONTIER.exists():
        with FRONTIER.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(TSV_HEADER)


def session_path() -> pathlib.Path:
    sid = os.environ.get("CLAUDE_SESSION_ID") or dt.datetime.now(dt.timezone.utc).strftime("session-%Y%m%d-%H%M%S")
    return SESSIONS_DIR / f"{sid}.log"


def read_frontier() -> list[dict[str, str]]:
    ensure_dirs()
    with FRONTIER.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


def write_frontier(rows: Iterable[dict[str, str]]) -> None:
    ensure_dirs()
    with FRONTIER.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_HEADER, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in TSV_HEADER})


def cmd_init(_: argparse.Namespace) -> int:
    ensure_dirs()
    sp = session_path()
    sp.parent.mkdir(parents=True, exist_ok=True)
    with sp.open("a", encoding="utf-8") as f:
        f.write(f"[{dt.datetime.now(dt.timezone.utc).isoformat()}Z] session_start cwd={os.getcwd()}\n")
    print(str(PLUGIN_DATA))
    return 0


def cmd_log_write(_: argparse.Namespace) -> int:
    ensure_dirs()
    raw = sys.stdin.read().strip()
    sp = session_path()
    with sp.open("a", encoding="utf-8") as f:
        stamp = dt.datetime.now(dt.timezone.utc).isoformat() + "Z"
        if not raw:
            f.write(f"[{stamp}] write_event raw=<empty>\n")
            return 0
        try:
            payload = json.loads(raw)
            tool_name = payload.get("tool_name") or payload.get("toolName") or "unknown_tool"
            tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
            file_path = tool_input.get("file_path") or tool_input.get("filePath") or tool_input.get("path") or "unknown_path"
            f.write(f"[{stamp}] write_event tool={tool_name} path={file_path}\n")
        except Exception:
            compact = re.sub(r"\s+", " ", raw)[:500]
            f.write(f"[{stamp}] write_event raw={compact}\n")
    return 0


def cmd_record_session(_: argparse.Namespace) -> int:
    ensure_dirs()
    sp = session_path()
    with sp.open("a", encoding="utf-8") as f:
        f.write(f"[{dt.datetime.now(dt.timezone.utc).isoformat()}Z] session_stop cwd={os.getcwd()}\n")
    return 0


def next_run_id() -> str:
    ensure_dirs()
    existing = []
    for p in RUNS_DIR.iterdir():
        if p.is_dir() and re.fullmatch(r"run-\d{4}", p.name):
            existing.append(int(p.name.split("-")[1]))
    n = max(existing, default=0) + 1
    return f"run-{n:04d}"


def cmd_next_run(args: argparse.Namespace) -> int:
    ensure_dirs()
    run_id = args.run_id or next_run_id()
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ["hypothesis.md", "safety-note.md", "validation.txt", "candidate.patch", "metrics.json", "notes.md"]:
        path = run_dir / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
    print(str(run_dir) if args.path else run_id)
    return 0


def as_float(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return float("nan")


def dominates(a: dict[str, str], b: dict[str, str]) -> bool:
    # maximize primary_score; minimize avg_latency_ms and avg_input_tokens
    a_score = as_float(a.get("primary_score", "nan"))
    b_score = as_float(b.get("primary_score", "nan"))
    a_latency = as_float(a.get("avg_latency_ms", "nan"))
    b_latency = as_float(b.get("avg_latency_ms", "nan"))
    a_tokens = as_float(a.get("avg_input_tokens", "nan"))
    b_tokens = as_float(b.get("avg_input_tokens", "nan"))
    if any(map(lambda x: x != x, [a_score, b_score, a_latency, b_latency, a_tokens, b_tokens])):
        return False
    better_or_equal = a_score >= b_score and a_latency <= b_latency and a_tokens <= b_tokens
    strictly_better = a_score > b_score or a_latency < b_latency or a_tokens < b_tokens
    return better_or_equal and strictly_better


def frontier_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    completed = [r for r in rows if r.get("status") == "complete"]
    frontier: list[dict[str, str]] = []
    for r in completed:
        dominated = False
        for other in completed:
            if other is r:
                continue
            if dominates(other, r):
                dominated = True
                break
        if not dominated:
            frontier.append(r)
    return sorted(frontier, key=lambda r: (-as_float(r.get("primary_score", "nan")), as_float(r.get("avg_latency_ms", "nan")), as_float(r.get("avg_input_tokens", "nan"))))


def md_table(rows: list[dict[str, str]], limit: int = 10) -> str:
    if not rows:
        return "No runs recorded yet."
    cols = ["run_id", "status", "primary_score", "avg_latency_ms", "avg_input_tokens", "risk", "note"]
    header = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    lines = [header, sep]
    for row in rows[:limit]:
        lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def cmd_frontier(args: argparse.Namespace) -> int:
    rows = read_frontier()
    fr = frontier_rows(rows)
    recent = sorted(rows, key=lambda r: r.get("timestamp", ""), reverse=True)[:5]
    if args.markdown:
        print("# Pareto frontier\n")
        print(md_table(fr, limit=args.limit))
        print("\n# Recent runs\n")
        print(md_table(recent, limit=args.limit))
    else:
        for row in fr:
            print(json.dumps(row, ensure_ascii=False))
    return 0


def cmd_record_metrics(args: argparse.Namespace) -> int:
    rows = read_frontier()
    run_id = args.run_id
    updated = False
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat() + "Z"
    for row in rows:
        if row.get("run_id") == run_id:
            row.update({
                "status": args.status,
                "primary_score": args.primary_score,
                "avg_latency_ms": args.avg_latency_ms,
                "avg_input_tokens": args.avg_input_tokens,
                "risk": args.risk,
                "note": args.note,
                "timestamp": timestamp,
            })
            updated = True
            break
    if not updated:
        rows.append({
            "run_id": run_id,
            "status": args.status,
            "primary_score": args.primary_score,
            "avg_latency_ms": args.avg_latency_ms,
            "avg_input_tokens": args.avg_input_tokens,
            "risk": args.risk,
            "note": args.note,
            "timestamp": timestamp,
        })
    write_frontier(rows)
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics.json").write_text(json.dumps({
        "run_id": run_id,
        "status": args.status,
        "primary_score": args.primary_score,
        "avg_latency_ms": args.avg_latency_ms,
        "avg_input_tokens": args.avg_input_tokens,
        "risk": args.risk,
        "note": args.note,
        "timestamp": timestamp,
    }, indent=2) + "\n", encoding="utf-8")
    print(run_id)
    return 0


def cmd_regressions(args: argparse.Namespace) -> int:
    rows = read_frontier()
    completed = [r for r in rows if r.get("status") == "complete"]
    completed.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    regressions = []
    best_so_far = -10**18
    for row in reversed(completed):
        score = as_float(row.get("primary_score", "nan"))
        if score != score:
            continue
        if score < best_so_far:
            regressions.append(row)
        best_so_far = max(best_so_far, score)
    regressions = list(reversed(regressions))[: args.limit]
    if args.markdown:
        print("# Recent regressions\n")
        if not regressions:
            print("No clear score regressions recorded yet.")
        else:
            print(md_table(regressions, limit=args.limit))
        print("\n# Heuristics\n")
        print("- Prefer additive changes over prompt + control-flow rewrites.")
        print("- Check whether multiple mechanisms changed at once.")
        print("- Audit validation gaps before assuming the idea was bad.")
    else:
        for row in regressions:
            print(json.dumps(row, ensure_ascii=False))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    # Lightweight default validator: JSON syntax + obvious file existence checks.
    target = pathlib.Path(args.path or os.getcwd())
    json_files = []
    for pattern in [".claude-plugin/*.json", ".claude/**/*.json", ".meta-harness/**/*.json", "prompts/**/*.json"]:
        json_files.extend(target.glob(pattern))
    bad = []
    for jf in json_files:
        try:
            json.loads(jf.read_text(encoding="utf-8"))
        except Exception as exc:
            bad.append(f"{jf}: {exc}")
    if bad:
        print("Validation failed:\n" + "\n".join(bad))
        return 1
    print("Lightweight validation passed. Add project-specific checks in bin/mh-validate for stronger guarantees.")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="meta_harness.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("log-write")
    s.set_defaults(func=cmd_log_write)

    s = sub.add_parser("record-session")
    s.set_defaults(func=cmd_record_session)

    s = sub.add_parser("next-run")
    s.add_argument("--run-id")
    s.add_argument("--path", action="store_true")
    s.set_defaults(func=cmd_next_run)

    s = sub.add_parser("frontier")
    s.add_argument("--markdown", action="store_true")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(func=cmd_frontier)

    s = sub.add_parser("record-metrics")
    s.add_argument("run_id")
    s.add_argument("primary_score")
    s.add_argument("avg_latency_ms")
    s.add_argument("avg_input_tokens")
    s.add_argument("risk")
    s.add_argument("note")
    s.add_argument("--status", default="complete")
    s.set_defaults(func=cmd_record_metrics)

    s = sub.add_parser("regressions")
    s.add_argument("--markdown", action="store_true")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(func=cmd_regressions)

    s = sub.add_parser("validate")
    s.add_argument("path", nargs="?")
    s.set_defaults(func=cmd_validate)

    return p


def main() -> int:
    p = parser()
    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
