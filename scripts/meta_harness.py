#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.config import (
    EVALUATION_VERDICTS,
    FRONTIER,
    MEASURED_RUN_STATUSES,
    REPORT_VERDICTS,
    PLUGIN_DATA,
    RUN_STATUS_COMPLETE,
    RUN_STATUS_PROMOTED,
    RUN_STATUS_RESERVED,
    RUN_STATUSES,
    RUNS_DIR,
    TSV_HEADER,
    as_float,
    build_metrics_row,
    ensure_dirs,
    iso_timestamp,
    METRICS_SCHEMA_VERSION,
    next_run_id,
    read_frontier,
    session_path,
    update_frontier_row,
    upsert_frontier_row,
)


def cmd_init(_: argparse.Namespace) -> int:
    ensure_dirs()
    sp = session_path()
    sp.parent.mkdir(parents=True, exist_ok=True)
    with sp.open("a", encoding="utf-8") as f:
        f.write(f"[{iso_timestamp()}] session_start cwd={os.getcwd()}\n")
    print(str(PLUGIN_DATA))
    return 0


def cmd_log_write(_: argparse.Namespace) -> int:
    ensure_dirs()
    raw = sys.stdin.read().strip()
    sp = session_path()
    with sp.open("a", encoding="utf-8") as f:
        stamp = iso_timestamp()
        if not raw:
            f.write(f"[{stamp}] write_event raw=<empty>\n")
            return 0
        try:
            payload = json.loads(raw)
            tool_name = payload.get("tool_name") or payload.get("toolName") or "unknown_tool"
            tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
            tool_response = payload.get("tool_response") or payload.get("toolResponse") or ""
            file_path = tool_input.get("file_path") or tool_input.get("filePath") or tool_input.get("path") or "unknown_path"
            f.write(f"[{stamp}] write_event tool={tool_name} path={file_path}\n")
            input_excerpt = json.dumps(tool_input, ensure_ascii=False)[:1500]
            f.write(f"  input: {input_excerpt}\n")
            if isinstance(tool_response, str):
                response_excerpt = tool_response[:500]
            else:
                response_excerpt = json.dumps(tool_response, ensure_ascii=False)[:500]
            f.write(f"  response: {response_excerpt}\n")
        except Exception:
            compact = re.sub(r"\s+", " ", raw)[:500]
            f.write(f"[{stamp}] write_event raw={compact}\n")
    return 0


def cmd_record_session(_: argparse.Namespace) -> int:
    ensure_dirs()
    sp = session_path()
    with sp.open("a", encoding="utf-8") as f:
        f.write(f"[{iso_timestamp()}] session_stop cwd={os.getcwd()}\n")
    return 0


def write_checkpoint(run_dir: pathlib.Path, phase: str, turn: int, objective: str) -> None:
    """Write a checkpoint file for crash recovery."""
    data = {
        "run_id": run_dir.name,
        "phase": phase,
        "turn": turn,
        "objective": objective,
        "last_updated": iso_timestamp(),
    }
    (run_dir / "checkpoint.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def detect_incomplete_runs() -> dict | None:
    """Find a run with checkpoint but no metrics (incomplete)."""
    ensure_dirs()
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        checkpoint = run_dir / "checkpoint.json"
        metrics = run_dir / "metrics.json"
        if checkpoint.exists() and not metrics.exists():
            data = json.loads(checkpoint.read_text(encoding="utf-8"))
            if data.get("phase") != "COMPLETED":
                return data
    return None


def _reserved_row(run_id: str, timestamp: str | None = None) -> dict[str, str]:
    return build_metrics_row(run_id, RUN_STATUS_RESERVED, timestamp=timestamp)


def _reserve_run_dir(run_id: str, initialize_reserved: bool) -> pathlib.Path:
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ["hypothesis.md", "safety-note.md", "validation.txt", "candidate.patch", "notes.md"]:
        path = run_dir / name
        if not path.exists():
            path.write_text("", encoding="utf-8")

    if initialize_reserved:
        reserved_row = _reserved_row(run_id)
        upsert_frontier_row(reserved_row)
        (run_dir / "metrics.json").write_text(
            json.dumps(reserved_row, indent=2) + "\n",
            encoding="utf-8",
        )
    elif not (run_dir / "metrics.json").exists():
        (run_dir / "metrics.json").write_text("", encoding="utf-8")

    return run_dir


def cmd_next_run(args: argparse.Namespace) -> int:
    ensure_dirs()
    if args.run_id:
        run_id = args.run_id
        run_dir = _reserve_run_dir(run_id, initialize_reserved=not (RUNS_DIR / run_id).exists())
    else:
        run_id = next_run_id()
        run_dir = _reserve_run_dir(run_id, initialize_reserved=True)
    print(str(run_dir) if args.path else run_id)
    return 0


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
    completed = [r for r in rows if r.get("status") in MEASURED_RUN_STATUSES]
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
    run_id = args.run_id
    row = build_metrics_row(
        run_id,
        args.status,
        primary_score=args.primary_score,
        avg_latency_ms=args.avg_latency_ms,
        avg_input_tokens=args.avg_input_tokens,
        risk=args.risk,
        consistency=args.consistency,
        instruction_adherence=args.instruction_adherence,
        tool_efficiency=args.tool_efficiency,
        error_count=args.error_count,
        sample_size=args.sample_size,
        eval_method=args.eval_method,
        deterministic_score=args.deterministic_score,
        llm_judge_score=args.llm_judge_score,
        evaluation_verdict=args.evaluation_verdict,
        report_verdict=args.report_verdict,
        benchmark_version=args.benchmark_version,
        baseline_run_id=args.baseline_run_id,
        seed=args.seed,
        note=args.note,
    )
    upsert_frontier_row(row)
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics.json").write_text(
        json.dumps(row, indent=2) + "\n",
        encoding="utf-8",
    )
    print(run_id)
    return 0


def cmd_regressions(args: argparse.Namespace) -> int:
    rows = read_frontier()
    completed = [r for r in rows if r.get("status") in MEASURED_RUN_STATUSES]
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
    for pattern in [".claude-plugin/*.json", ".claude/**/*.json", ".meta-harness/**/*.json", "prompts/**/*.json", ".mcp.json"]:
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


def cmd_compare_projects(args: argparse.Namespace) -> int:
    """Compare frontier data across projects by scanning ~/.claude/plugins/data/."""
    projects_data = pathlib.Path.home() / ".claude" / "plugins" / "data"

    # Also check PLUGIN_DATA parent for sibling project data
    comparisons = []

    # Current project
    rows = read_frontier()
    fr = frontier_rows(rows)
    best_score = max((as_float(r.get("primary_score", "0")) for r in fr), default=0.0)
    comparisons.append({
        "project": "current",
        "runs": len(rows),
        "frontier_size": len(fr),
        "best_score": best_score,
    })

    # Scan for other meta-harness data directories
    for search_dir in [projects_data, PLUGIN_DATA.parent]:
        if not search_dir.exists():
            continue
        for d in search_dir.iterdir():
            if not d.is_dir() or d == PLUGIN_DATA:
                continue
            other_frontier = d / "frontier.tsv"
            if not other_frontier.exists():
                continue
            try:
                with other_frontier.open("r", newline="", encoding="utf-8") as f:
                    import csv as _csv
                    reader = _csv.DictReader(f, delimiter="\t")
                    other_rows = list(reader)
                other_fr = frontier_rows(other_rows)
                other_best = max((as_float(r.get("primary_score", "0")) for r in other_fr), default=0.0)
                if other_rows:  # skip empty/header-only frontiers
                    comparisons.append({
                        "project": d.name,
                        "runs": len(other_rows),
                        "frontier_size": len(other_fr),
                        "best_score": other_best,
                    })
            except Exception:
                pass

    print("# Cross-Project Frontier Comparison\n")
    print(f"| Project | Runs | Frontier | Best Score |")
    print(f"|---------|------|----------|------------|")
    for c in sorted(comparisons, key=lambda x: x["best_score"], reverse=True):
        print(f"| {c['project'][:30]} | {c['runs']} | {c['frontier_size']} | {c['best_score']:.3f} |")

    print(f"\n{len(comparisons)} project(s) found.")
    return 0


def cmd_timeline(args: argparse.Namespace) -> int:
    """Show frontier metrics over time with sparkline visualization."""
    rows = read_frontier()
    completed = [r for r in rows if r.get("status") in ("complete", "promoted")]
    completed.sort(key=lambda r: r.get("timestamp", ""))

    if not completed:
        print("No completed runs to visualize.")
        return 0

    SPARKS = "▁▂▃▄▅▆▇█"

    def sparkline(values: list[float]) -> str:
        if not values or all(v != v for v in values):
            return ""
        valid = [v for v in values if v == v]
        if not valid:
            return ""
        lo, hi = min(valid), max(valid)
        rng = hi - lo if hi > lo else 1.0
        return "".join(
            SPARKS[min(int((v - lo) / rng * 7), 7)] if v == v else " "
            for v in values
        )

    scores = [as_float(r.get("primary_score", "nan")) for r in completed]
    latencies = [as_float(r.get("avg_latency_ms", "nan")) for r in completed]
    tokens = [as_float(r.get("avg_input_tokens", "nan")) for r in completed]

    valid_scores = [s for s in scores if s == s]
    valid_latencies = [l for l in latencies if l == l]
    valid_tokens = [t for t in tokens if t == t]

    print("# Frontier Timeline\n")
    print(f"Runs: {len(completed)} | Period: {completed[0].get('timestamp', '?')[:10]} to {completed[-1].get('timestamp', '?')[:10]}\n")

    if valid_scores:
        best = max(valid_scores)
        latest = valid_scores[-1]
        delta = latest - valid_scores[0] if len(valid_scores) > 1 else 0
        arrow = "▲" if delta > 0 else "▼" if delta < 0 else "●"
        print(f"Score    {latest:.3f}  {arrow} {delta:+.3f}  {sparkline(scores)}")

    if valid_latencies:
        latest = valid_latencies[-1]
        delta = valid_latencies[-1] - valid_latencies[0] if len(valid_latencies) > 1 else 0
        arrow = "▼" if delta < 0 else "▲" if delta > 0 else "●"
        print(f"Latency  {latest:.0f}ms  {arrow} {delta:+.0f}ms  {sparkline(latencies)}")

    if valid_tokens:
        latest = valid_tokens[-1]
        delta = valid_tokens[-1] - valid_tokens[0] if len(valid_tokens) > 1 else 0
        arrow = "▼" if delta < 0 else "▲" if delta > 0 else "●"
        print(f"Tokens   {latest:.0f}  {arrow} {delta:+.0f}  {sparkline(tokens)}")

    print(f"\nBest score: {max(valid_scores):.3f}" if valid_scores else "")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    """Apply a candidate's patch to the working tree and tag it."""
    ensure_dirs()
    run_id = args.run_id
    run_dir = RUNS_DIR / run_id
    patch_file = run_dir / "candidate.patch"

    if not patch_file.exists() or patch_file.stat().st_size == 0:
        print(f"Error: No valid patch for {run_id}")
        return 1

    # Check metrics exist
    metrics_file = run_dir / "metrics.json"
    if not metrics_file.exists():
        print(f"Error: No metrics recorded for {run_id}. Run evaluation first.")
        return 1

    try:
        metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error: Invalid metrics.json for {run_id}: {exc}")
        return 1

    git_root = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    if git_root.returncode != 0 or git_root.stdout.strip() != "true":
        print("Error: Promotion requires running inside a git worktree.")
        return 1

    worktree = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
    )
    if worktree.returncode != 0:
        print(f"Error: Unable to inspect git worktree:\n{worktree.stderr}")
        return 1
    if worktree.stdout.strip():
        print("Error: Refusing to promote with a dirty git worktree. Commit or stash tracked changes first.")
        return 1

    tag_name = f"harness-pre-{run_id}"
    tag_check = subprocess.run(
        ["git", "tag", "--list", tag_name],
        capture_output=True,
        text=True,
    )
    if tag_check.returncode != 0:
        print(f"Error: Unable to inspect existing safety tags:\n{tag_check.stderr}")
        return 1
    if tag_check.stdout.strip():
        print(f"Error: Safety tag already exists: {tag_name}")
        return 1

    # Check patch applies cleanly
    check = subprocess.run(
        ["git", "apply", "--check", str(patch_file)],
        capture_output=True, text=True,
    )
    if check.returncode != 0:
        print(f"Error: Patch does not apply cleanly:\n{check.stderr}")
        return 1

    # Create safety tag
    tag_create = subprocess.run(
        ["git", "tag", tag_name, "-m", f"Pre-promotion safety tag for {run_id}"],
        capture_output=True,
        text=True,
    )
    if tag_create.returncode != 0:
        print(f"Error: Unable to create safety tag:\n{tag_create.stderr}")
        return 1

    # Apply patch
    result = subprocess.run(
        ["git", "apply", str(patch_file)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        subprocess.run(
            ["git", "tag", "-d", tag_name],
            capture_output=True,
            text=True,
        )
        print(f"Error applying patch:\n{result.stderr}")
        return 1

    # Update status in frontier
    update_frontier_row(
        run_id,
        status=RUN_STATUS_PROMOTED,
        metrics_schema_version=metrics.get("metrics_schema_version", METRICS_SCHEMA_VERSION),
    )
    metrics["status"] = RUN_STATUS_PROMOTED
    metrics.setdefault("metrics_schema_version", METRICS_SCHEMA_VERSION)
    metrics_file.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    print(f"Promoted {run_id}")
    print(f"Safety tag: {tag_name}")
    print(f"To rollback: git apply -R {patch_file}")
    return 0


def cmd_parallel_run(args: argparse.Namespace) -> int:
    """Reserve N candidate run IDs for parallel evaluation."""
    ensure_dirs()
    count = args.count
    if count < 1:
        print("Error: count must be >= 1")
        return 1
    run_ids = []
    for _ in range(count):
        run_id = next_run_id()
        _reserve_run_dir(run_id, initialize_reserved=True)
        run_ids.append(run_id)
    if args.json:
        print(json.dumps({"run_ids": run_ids, "count": count}))
    else:
        for rid in run_ids:
            print(rid)
    return 0


def cmd_compact_summary(_: argparse.Namespace) -> int:
    """Generate a concise context summary for PostCompact re-injection."""
    rows = read_frontier()
    fr = frontier_rows(rows)
    recent = sorted(rows, key=lambda r: r.get("timestamp", ""), reverse=True)[:3]

    lines = ["[Meta-Harness Context]"]

    if not rows:
        lines.append("No runs recorded yet.")
        print("\n".join(lines))
        return 0

    if fr:
        lines.append("Frontier (non-dominated):")
        for r in fr[:3]:
            lines.append(
                f"  {r.get('run_id','?')}: score={r.get('primary_score','?')} "
                f"latency={r.get('avg_latency_ms','?')}ms "
                f"tokens={r.get('avg_input_tokens','?')} "
                f"risk={r.get('risk','?')}"
            )

    if recent:
        lines.append("Recent:")
        for r in recent:
            lines.append(
                f"  {r.get('run_id','?')}: {r.get('status','?')} "
                f"score={r.get('primary_score','?')} "
                f"note={r.get('note','')}"
            )

    completed = [r for r in rows if r.get("status") in MEASURED_RUN_STATUSES]
    completed.sort(key=lambda r: r.get("timestamp", ""))
    best_so_far = -10**18
    regression_count = 0
    for row in completed:
        score = as_float(row.get("primary_score", "nan"))
        if score != score:
            continue
        if score < best_so_far:
            regression_count += 1
        best_so_far = max(best_so_far, score)

    if regression_count > 0:
        lines.append(f"Regressions detected: {regression_count}")

    lines.append(f"Total runs: {len(rows)}")
    print("\n".join(lines))
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
    s.add_argument("--status", default=RUN_STATUS_COMPLETE, choices=RUN_STATUSES)
    s.add_argument("--consistency", default="")
    s.add_argument("--instruction-adherence", default="")
    s.add_argument("--tool-efficiency", default="")
    s.add_argument("--error-count", default="")
    s.add_argument("--sample-size", default="")
    s.add_argument("--eval-method", default="")
    s.add_argument("--deterministic-score", default="")
    s.add_argument("--llm-judge-score", default="")
    s.add_argument("--evaluation-verdict", default="", choices=("",) + EVALUATION_VERDICTS)
    s.add_argument("--report-verdict", default="", choices=("",) + REPORT_VERDICTS)
    s.add_argument("--benchmark-version", default="")
    s.add_argument("--baseline-run-id", default="")
    s.add_argument("--seed", default="")
    s.set_defaults(func=cmd_record_metrics)

    s = sub.add_parser("regressions")
    s.add_argument("--markdown", action="store_true")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(func=cmd_regressions)

    s = sub.add_parser("validate")
    s.add_argument("path", nargs="?")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("compact-summary")
    s.set_defaults(func=cmd_compact_summary)

    s = sub.add_parser("parallel-run")
    s.add_argument("--count", type=int, default=3)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_parallel_run)

    s = sub.add_parser("promote")
    s.add_argument("run_id")
    s.set_defaults(func=cmd_promote)

    s = sub.add_parser("timeline")
    s.set_defaults(func=cmd_timeline)

    s = sub.add_parser("compare-projects")
    s.set_defaults(func=cmd_compare_projects)

    return p


def main() -> int:
    import sys as _sys
    if hasattr(_sys.stdout, "reconfigure"):
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = parser()
    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
