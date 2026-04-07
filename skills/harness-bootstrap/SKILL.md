---
name: bootstrap
description: Analyze the current project and generate initial eval tasks for harness optimization. Creates regression and capability eval tasks based on project structure.
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash(python3 *) Bash(git *) Bash(ls *) Write
---

# Harness Bootstrap

Analyze this project and generate appropriate eval tasks for harness optimization.

## Current project state
```!
ls -la
```

## Current harness surfaces
```!
ls .claude/rules/ 2>/dev/null || echo "No rules directory"
ls .claude/skills/*/SKILL.md 2>/dev/null || echo "No project skills"
ls .claude/agents/*.md 2>/dev/null || echo "No project agents"
cat CLAUDE.md 2>/dev/null | head -50 || echo "No CLAUDE.md"
```

## Current eval tasks
```!
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/eval_runner.py --eval-dir ${CLAUDE_PLUGIN_ROOT}/eval-tasks --cwd . 2>&1 || echo "No eval runner"
```

## Instructions

Generate eval tasks for this project:

1. **Regression tasks** (eval-tasks/regression/): Easy checks that should ALWAYS pass.
   - Harness files are valid JSON/YAML
   - CLAUDE.md exists and has required sections
   - Skills have valid frontmatter
   - mh-validate passes

2. **Capability tasks** (eval-tasks/capability/): Harder checks measuring improvement.
   - Based on the project's actual domain and coding patterns
   - Based on recent git history (what kind of tasks are common)
   - Based on CLAUDE.md constraints (are they being followed?)

Write each task as a JSON file following the schema in eval-tasks/_schema.json.
Each task must have: name, type, difficulty, description, checks (deterministic + llm_judge).
Use only check types: exit_code, file_exists, file_contains, file_not_contains, json_valid, command_output.
