---
name: dashboard
description: Full Meta-Harness status view — Pareto frontier, recent runs, regressions, eval health, installed plugins.
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash(python3 *) Bash(mh-*) Bash(git *)
---

# Meta-Harness Dashboard

## Pareto Frontier
```!
mh-frontier --markdown 2>/dev/null || echo "No frontier data"
```

## Recent Regressions
```!
mh-regressions --markdown 2>/dev/null || echo "No regressions"
```

## Eval Suite Health
```!
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/eval_runner.py --eval-dir ${CLAUDE_PLUGIN_ROOT}/eval-tasks --cwd . 2>&1 || echo "Eval runner unavailable"
```

## Incomplete Runs
```!
python3 -c "
from scripts.meta_harness import detect_incomplete_runs
r = detect_incomplete_runs()
if r: print(f'Incomplete: {r[\"run_id\"]} phase={r[\"phase\"]} turn={r[\"turn\"]}')
else: print('No incomplete runs')
" 2>/dev/null || echo "Check unavailable"
```

## Plugin Surfaces
```!
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.claude' / 'plugins' / 'installed_plugins.json'
if p.exists():
    d = json.loads(p.read_text())
    for k in list(d.get('plugins', {}))[:10]:
        name = k.split('@')[0]
        print(f'  {name}')
else:
    print('No plugins')
" 2>/dev/null || echo "Plugin scan unavailable"
```

## Instructions

Present the dashboard using the Meta-Harness output style:

```
◉ DASHBOARD ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Synthesize the data above into a clear status view]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Highlight:
1. Best frontier candidate and its scores
2. Any active regressions with suspected causes
3. Eval suite pass rate
4. Any incomplete runs that need attention
5. Recommendations for next evolution target
