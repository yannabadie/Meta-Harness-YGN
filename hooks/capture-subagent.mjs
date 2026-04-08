#!/usr/bin/env node
/**
 * SubagentStop hook — capture subagent results for trace analysis.
 * Logs the agent type and last message to sessions directory.
 */
import { readFileSync, appendFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const pluginData = process.env.CLAUDE_PLUGIN_DATA || process.env.MH_PLUGIN_DATA || "/tmp/meta-harness-lab";
const sessionsDir = path.join(pluginData, "sessions");

let input = "";
try {
  input = readFileSync(0, "utf-8").trim();
} catch { /* no stdin */ }

if (input) {
  try {
    mkdirSync(sessionsDir, { recursive: true });
    const payload = JSON.parse(input);
    const agentType = payload.agent_type || "unknown";
    const agentId = payload.agent_id || "unknown";
    const lastMsg = (payload.last_assistant_message || "").slice(0, 500);
    const ts = new Date().toISOString();
    const line = `[${ts}] subagent_stop type=${agentType} id=${agentId} msg=${lastMsg}\n`;
    const logFile = path.join(sessionsDir, "subagents.log");
    appendFileSync(logFile, line, "utf-8");
  } catch { /* graceful degradation */ }
}

process.exit(0);
