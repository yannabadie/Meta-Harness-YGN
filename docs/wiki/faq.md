# FAQ

Frequently asked questions about Meta-Harness. For setup help, see [Getting Started](getting-started.md). For conceptual background, see [Concepts](concepts.md).

---

## "How is this different from just editing CLAUDE.md manually?"

Manual CLAUDE.md editing has no measurement, no history, and no rollback. You add a rule, it feels better, you move on. Three months later you have 300 lines of instructions and no idea which ones are helping, which ones Claude already follows without being told, and which ones are actively conflicting with each other.

Meta-Harness turns every change into an experiment:

1. **Every change has a hypothesis** — not "I'll add this rule" but "I claim this rule will reduce tool thrashing; here is the evidence from prior runs."
2. **Every change is measured** — 9 deterministic checks plus LLM-judge scoring with a before/after delta, not a vibe check.
3. **Every change is tracked** — the Pareto frontier shows you which candidates actually improved the harness and which ones regressed.
4. **Every change is reversible** — a git patch plus a safety tag. `mh-rollback run-0008` undoes it cleanly.

The ETH Zurich research cited in the README found that LLM-generated context files degrade performance by ~3%. The problem is real: more instructions do not reliably mean better performance. Meta-Harness is the mechanism for finding out what actually helps in your specific project.

---

## "Does this work with Superpowers / other plugins?"

Yes, and Meta-Harness is specifically designed to be aware of other plugins. The `plugin_scan` MCP tool (and the Harvest phase of `/mh:evolve`) reads `~/.claude/plugins/installed_plugins.json` and reports each plugin's skills and MCP tools.

The proposer agent receives this list and can propose harness improvements that reference other plugins. For example:

- A `.claude/rules/` file that triggers `/superpowers:test-driven-development` on certain task types
- A skill that calls Context7's `query-docs` for documentation verification before committing
- A hook that uses Playwright for visual regression checks

The proposer's prompt explicitly includes:

> You may reference other plugins' skills or MCP tools in your proposal. For example, you can propose a rule that triggers `/superpowers:test-driven-development`, or a skill that calls Context7 for doc verification, or a hook that uses Playwright for visual checks.

There are no known conflicts with other plugins. Meta-Harness uses the `/mh:*` namespace exclusively and does not modify any shared configuration files outside the project's own harness surfaces.

---

## "How much does the Stop hook quality gate cost in tokens?"

The Stop hook quality gate is a single Claude Haiku call with a timeout of 30 seconds.

**Approximate cost per session stop where `/mh:evolve` was mentioned:**

- Input tokens: ~150–300 (the hook prompt + the stop event JSON, which includes `last_assistant_message`)
- Output tokens: ~10–30 (`{"ok": true}` or `{"ok": false, "reason": "..."}`)
- Model: Claude Haiku (the cheapest Claude model)

At Haiku pricing, this is under $0.001 per stop event. For a typical session with 2–3 stop events, total quality gate cost is in the sub-cent range.

The gate fires on every stop event, but only acts (returns `ok: false`) when both conditions are met:

1. `stop_hook_active` is false (prevents infinite loops)
2. The `last_assistant_message` mentions `/mh:evolve` but does NOT mention recording metrics or updating the frontier

In normal usage — where every `/mh:evolve` run completes the full pipeline — the gate always returns `{"ok": true}` without blocking.

---

## "Can I use this on a project that isn't a git repo?"

Partially. The eval engine, context harvester, and frontier tracking all work without git. You lose:

- **Git-based context harvesting** — the harvester calls `git log`, `git log --name-only`, and `git diff --stat HEAD~5..HEAD`. On non-git directories, these fail silently and are skipped (the harvester catches exceptions).
- **Rollback** — `mh-rollback` uses `git apply -R`. Without git, you must undo patches manually.
- **Promotion** — `mh-promote` now requires a real git worktree. It refuses to run outside git because promotion creates a safety tag and validates the tracked worktree state first.

Everything else works: skills, hooks, the MCP server, eval tasks, frontier tracking, session logs.

If you need rollback on a non-git project, store a manual backup before running `/mh:evolve`. The `candidate.patch` file in the run directory is a standard unified diff that can be applied and reversed with GNU `patch -R`.

---

## "What happens if the MCP server crashes?"

The plugin degrades gracefully to CLI fallbacks. Every MCP tool has an equivalent CLI command:

| MCP tool | CLI fallback |
|---|---|
| `frontier_read` | `mh-frontier --markdown` |
| `frontier_record` | `mh-record-metrics` |
| `context_harvest` | `mh-context --project . --objective "..."` |
| `eval_run` | `python scripts/eval_runner.py --eval-dir eval-tasks --cwd .` |

The skills and agents are written to use MCP tools where available but fall back to the CLI equivalents. If the MCP server fails to start (missing `mcp` package, port conflict, Python error), the plugin continues to work — you just lose the ability to call tools directly from MCP-aware contexts.

To diagnose a crash:

```bash
python servers/mh_server.py
# Read the traceback
```

Common causes:
1. `mcp` package not installed (`pip install "mcp>=1.12"`)
2. Python version below 3.10
3. `MH_PLUGIN_ROOT` not set correctly when running manually

---

## "How do I rollback a bad change?"

If you promoted a candidate and it degraded your harness, use:

```bash
bin/mh-rollback run-NNNN
```

This:
1. Creates a git safety tag `harness-pre-rollback-run-NNNN`
2. Verifies the patch can be reversed cleanly (`git apply --check -R`)
3. Applies `git apply -R` to reverse the change

If the rollback fails (working tree diverged from the patch's base):

```
Error: Patch cannot be reverse-applied cleanly
The working tree may have changed since the patch was created.
Manual intervention required.
```

In this case, use the safety tag created during promotion:

```bash
git checkout harness-pre-run-NNNN -- CLAUDE.md .claude/rules/
```

Or restore the specific files from the patch manually:

```bash
git show harness-pre-run-NNNN:CLAUDE.md > CLAUDE.md
```

The `candidate.patch` file is always preserved in the run directory, so you can also apply the inverse manually:

```bash
patch -R < /tmp/meta-harness-lab/runs/run-NNNN/candidate.patch
```

---

## "Can Meta-Harness optimize itself?"

Yes. This is documented in the README and actually happened during development (run-0005):

The plugin ran `/mh:evolve` on its own harness and found that 4 eval check types (`patch_not_empty`, `max_files_changed`, `files_in_scope`, and one other) were implemented in `eval_runner.py` but never referenced in any eval task. A proposer could submit an empty or out-of-scope patch and pass all checks.

The fix: added 4 deterministic guards to `eval-tasks/capability/propose-improvement.json`. Guardrail coverage increased from 3 to 7 checks. The 100% eval score was maintained.

To optimize Meta-Harness itself:

```bash
cd Meta-Harness-YGN
claude --plugin-dir .
/mh:evolve "improve eval coverage for candidate validation"
```

The allowed harness surfaces (`CLAUDE.md`, `.claude/**`, `skills/**`, `agents/**`, etc.) are the same surfaces the plugin uses for any project. Meta-Harness is self-applicable.

---

## "What's the minimum Python version?"

**Python 3.10** is the minimum, as declared in `pyproject.toml`:

```toml
requires-python = ">=3.10"
```

The codebase uses:
- `from __future__ import annotations` (3.7+)
- `pathlib.Path` (3.4+)
- `match/case` statements: **not used** — the code uses dict dispatch tables instead, keeping 3.10 as the floor without requiring 3.10-specific syntax
- `dict | dict` union: not used — the code uses `.update()` and `.get()`

The actual minimum-version constraint comes from `mcp>=1.12`, which requires 3.10+. Without the MCP package, the core scripts would likely run on 3.8+, but 3.10 is the supported and tested minimum.

---

## "Does this work on Windows?"

Yes. The plugin is tested on Windows and has explicit Windows compatibility measures:

1. **`mh-python`** resolves `python3` → `python` because on Windows, `python3` often does not exist as an alias.

2. **Hook scripts are Node.js** (`session-start.mjs`, `log-instructions.mjs`, `capture-subagent.mjs`) specifically for cross-platform path handling. `session-start.mjs` quotes the Python path in `execSync` calls.

3. **Python scripts call `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`** at entry points to handle Windows console encoding issues.

4. **`CLAUDE_PLUGIN_DATA`** defaults to `/tmp/meta-harness-lab` (a Unix path). On Windows, set this explicitly:

   ```bash
   # In PowerShell before launching Claude Code:
   $env:CLAUDE_PLUGIN_DATA = "C:\Users\YourName\.meta-harness"
   
   # In Git Bash / WSL:
   export CLAUDE_PLUGIN_DATA="$USERPROFILE/.meta-harness"
   ```

5. **`mh-rollback` and git commands** require Git for Windows. Install from https://git-scm.com/download/win and ensure `git` is in PATH.

Known limitation on Windows: the `bin/` scripts are bash scripts. They run correctly under Git Bash, WSL, or any POSIX shell, but not in CMD or PowerShell directly. Claude Code runs hooks via its own shell layer, so this is not a problem for hooks — only for direct CLI invocation from a Windows terminal.

---

## "How do I add custom eval checks?"

Three approaches, in order of complexity:

### Approach 1: `command_output` with a custom script

No code changes required. Write a script that prints a recognizable string on success:

```json
{
  "type": "command_output",
  "command": "python scripts/check_my_constraint.py",
  "pattern": "CONSTRAINT_SATISFIED",
  "weight": 2.0
}
```

```python
# scripts/check_my_constraint.py
import sys, pathlib
if pathlib.Path("CLAUDE.md").read_text().count("##") >= 3:
    print("CONSTRAINT_SATISFIED")
    sys.exit(0)
else:
    sys.exit(1)
```

### Approach 2: `exit_code` with a test

Any test framework works:

```json
{
  "type": "exit_code",
  "command": "python -m pytest tests/harness_constraints/ -q --tb=short",
  "expected": 0,
  "weight": 3.0
}
```

### Approach 3: Extend `eval_runner.py`

Add a handler to the `_CHECK_HANDLERS` dict in `scripts/eval_runner.py`:

```python
def _check_my_custom_type(check: dict, cwd: str) -> dict:
    # check is the JSON object from the eval task
    # cwd is the working directory for resolving relative paths
    result = do_your_check(check, cwd)
    return {
        "type": "my_custom_type",
        "passed": result.ok,
        "weight": check.get("weight", 1.0),
        "evidence": result.description,
    }

_CHECK_HANDLERS["my_custom_type"] = _check_my_custom_type
```

Then use it in any eval task:

```json
{
  "type": "my_custom_type",
  "my_param": "value",
  "weight": 1.5
}
```

The handler receives the full check JSON object, so you can add any fields you need (`my_param`, etc.). See [Eval Tasks Guide](eval-tasks-guide.md) for the full check type reference and [Architecture](architecture.md) for the eval engine implementation details.

---

See [Getting Started](getting-started.md) for installation help, [Commands Reference](commands-reference.md) for CLI syntax, and [Architecture](architecture.md) for implementation details.
