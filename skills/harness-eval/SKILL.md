---
name: eval
description: Run the evaluation suite on the current harness or a specific candidate run. Reports deterministic check results and LLM-judge assessment.
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash(python3 *) Bash(git *)
---

# Harness Evaluation

Run the evaluation suite to measure harness quality.

## Deterministic checks
```!
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/eval_runner.py --eval-dir ${CLAUDE_PLUGIN_ROOT}/eval-tasks --cwd . 2>&1 || echo "Eval runner not available"
```

## Instructions

1. Review the deterministic check results above.
2. For each eval task that has `llm_judge` criteria, evaluate the criteria manually:
   - Read the relevant files
   - Assess whether each criteria is met
   - Record evidence for your judgment
3. Compute the final score: 0.6 * deterministic + 0.4 * llm_judge
4. Present results using the Meta-Harness output format.

If a specific run_id was provided as $ARGUMENTS, evaluate that candidate's artifacts in runs/{run_id}/.
Otherwise, evaluate the current harness state.
