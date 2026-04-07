#!/usr/bin/env node
/**
 * InstructionsLoaded hook — audit which instruction files are loaded.
 * Logs to sessions directory for observability.
 */
import { readFileSync, appendFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const pluginData = process.env.CLAUDE_PLUGIN_DATA || process.env.MH_PLUGIN_DATA || "/tmp/meta-harness";
const sessionsDir = path.join(pluginData, "sessions");

let input = "";
try {
  input = readFileSync(0, "utf-8").trim();
} catch { /* no stdin */ }

if (input) {
  try {
    mkdirSync(sessionsDir, { recursive: true });
    const payload = JSON.parse(input);
    const filePath = payload.file_path || "unknown";
    const reason = payload.load_reason || "unknown";
    const ts = new Date().toISOString();
    const line = `[${ts}] instructions_loaded path=${filePath} reason=${reason}\n`;
    const logFile = path.join(sessionsDir, "instructions.log");
    appendFileSync(logFile, line, "utf-8");
  } catch { /* graceful degradation */ }
}

process.exit(0);
