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
const mhPython = path.join(pluginRoot, "bin", "mh-python");

// Try mh-python (plugin's resolver), fallback to python3, then python
function findPython() {
  for (const cmd of [mhPython, "python3", "python"]) {
    try {
      execSync(`"${cmd}" --version`, { encoding: "utf-8", timeout: 5000, stdio: "pipe" });
      return cmd;
    } catch { /* try next */ }
  }
  return null;
}

const py = findPython();
if (!py) process.exit(0); // No Python — degrade gracefully

let summaryOutput = "";

try {
  execSync(`"${py}" "${script}" init`, { encoding: "utf-8", timeout: 10000, stdio: "pipe" });
} catch { /* degrade gracefully */ }

try {
  summaryOutput = execSync(`"${py}" "${script}" compact-summary`, {
    encoding: "utf-8",
    timeout: 10000,
    stdio: ["pipe", "pipe", "pipe"],
  }).trim();
} catch {
  summaryOutput = "";
}

if (summaryOutput) {
  process.stdout.write(JSON.stringify({ additionalContext: summaryOutput }));
}

process.exit(0);
