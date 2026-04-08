#!/usr/bin/env node
/**
 * SessionStart hook for Meta-Harness.
 * Initializes persistent storage and injects frontier summary as additionalContext.
 * Written in Node.js for cross-platform compatibility (Windows path handling).
 */
import { execSync } from "node:child_process";
import path from "node:path";

const pluginRoot = process.env.CLAUDE_PLUGIN_ROOT || process.env.MH_PLUGIN_ROOT || ".";
const script = path.join(pluginRoot, "scripts", "meta_harness.py");

let summaryOutput = "";

try {
  // Initialize persistent storage
  execSync(`mh-python "${script}" init`, {
    encoding: "utf-8",
    timeout: 10000,
  });
} catch {
  // Python not available — degrade gracefully
}

try {
  // Generate compact summary for context injection
  summaryOutput = execSync(`mh-python "${script}" compact-summary`, {
    encoding: "utf-8",
    timeout: 10000,
  }).trim();
} catch {
  summaryOutput = "";
}

// Output additionalContext if we have a summary
if (summaryOutput) {
  const result = { additionalContext: summaryOutput };
  process.stdout.write(JSON.stringify(result));
}

process.exit(0);
