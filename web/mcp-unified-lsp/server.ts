/**
 * mcp-unified-lsp — Tier-1 MCP stdio adapter.
 *
 * Primary agent surface: newline-delimited JSON-RPC on stdin/stdout
 * (MCP stdio). This process does not open a socket. It forwards tool
 * calls to the INFRA broker CLI, which owns language-server lifecycle.
 *
 * Spike tool names, chosen this run: lsp_status, lsp_install,
 * lsp_diagnostics, lsp_hover, lsp_definition.
 */

import { spawnSync } from "node:child_process";

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

interface RpcRequest {
  jsonrpc?: string;
  id?: number | string | null;
  method?: string;
  params?: { [key: string]: Json };
}

const TIER1 = ["tsjs", "python", "go"];
const MAX_MCP_FRAME = 1_048_576;
const DEFAULT_BROKER_STDOUT = 8 * 1024 * 1024;

const TOOLS = [
  {
    name: "lsp_status",
    description: "Report broker lifecycle state and Tier-1 session status.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "lsp_install",
    description: "Install a Tier-1 language server on demand. Ids: tsjs, python, go.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["language"],
      properties: { language: { type: "string", enum: TIER1 } },
    },
  },
  {
    name: "lsp_diagnostics",
    description: "Read diagnostics for a workspace-relative path from the broker.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["language", "path"],
      properties: {
        language: { type: "string", enum: TIER1 },
        path: { type: "string" },
      },
    },
  },
  {
    name: "lsp_hover",
    description: "Spike stub for hover. Validates install and workspace path; does not call textDocument/hover.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["language", "path"],
      properties: {
        language: { type: "string", enum: TIER1 },
        path: { type: "string" },
      },
    },
  },
  {
    name: "lsp_definition",
    description: "Spike stub for definition. Validates install and workspace path; does not call textDocument/definition.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["language", "path"],
      properties: {
        language: { type: "string", enum: TIER1 },
        path: { type: "string" },
      },
    },
  },
];

function send(message: Json): void {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

const SECRET_ASSIGN = /(\b(?:api[_-]?key|secret|password|passwd|token|access[_-]?key|client[_-]?secret)\s*[=:]\s*)(\S+)/gi;
const ABS_PATH = /\/(?:tmp|home|workspace|Users|var|private|opt|usr)\/\S+/g;

function sanitizeText(text: string): string {
  const cleaned = text.replace(SECRET_ASSIGN, "$1[REDACTED]").replace(ABS_PATH, "[path]");
  if (cleaned.startsWith("/") && cleaned !== "/") {
    return "[path]";
  }
  return cleaned;
}

function sanitize(value: Json): Json {
  if (typeof value === "string") {
    return sanitizeText(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitize(item));
  }
  if (value && typeof value === "object") {
    const cleaned: { [key: string]: Json } = {};
    for (const [key, item] of Object.entries(value)) {
      if (key === "stderr" || key === "bin" || key === "fixture") {
        continue;
      }
      cleaned[key] = sanitize(item);
    }
    return cleaned;
  }
  return value;
}

function toolText(payload: Json, isError: boolean): Json {
  return {
    content: [{ type: "text", text: JSON.stringify(sanitize(payload)) }],
    isError,
  };
}

function configured(): { python: string; broker: string; stateDir: string } | { error: Json } {
  const broker = process.env.ULSP_BROKER;
  const stateDir = process.env.ULSP_STATE_DIR;
  if (!broker || !stateDir) {
    return {
      error: toolText(
        {
          ok: false,
          code: "broker_not_configured",
          message: "ULSP_BROKER and ULSP_STATE_DIR are required",
        },
        true,
      ),
    };
  }
  return { python: process.env.ULSP_PYTHON || "python3", broker, stateDir };
}

function brokerStdoutCap(): number {
  const raw = Number(process.env.ULSP_BROKER_MAX_STDOUT || DEFAULT_BROKER_STDOUT);
  if (!Number.isFinite(raw) || raw < 1) {
    return DEFAULT_BROKER_STDOUT;
  }
  return raw;
}

function spawnFailureCode(error: Error & { code?: string }): string {
  if (error.name === "TimeoutError") {
    return "diagnostics_timeout";
  }
  if (
    error.code === "ERR_CHILD_PROCESS_STDIO_MAXBUFFER"
    || error.code === "ENOBUFS"
    || /maxBuffer/i.test(error.message)
  ) {
    return "response_too_large";
  }
  return "broker_protocol";
}

function brokerRpc(method: string, params: { [key: string]: Json }): Json {
  const cfg = configured();
  if ("error" in cfg) {
    return cfg.error;
  }
  const child = spawnSync(
    cfg.python,
    [cfg.broker, "--state-dir", cfg.stateDir, "rpc"],
    {
      input: `${JSON.stringify({ id: "mcp", method, params })}\n`,
      encoding: "utf-8",
      timeout: 20000,
      maxBuffer: brokerStdoutCap(),
    },
  );
  if (child.error) {
    const code = spawnFailureCode(child.error as Error & { code?: string });
    const limit = brokerStdoutCap();
    const message = code === "response_too_large"
      ? `broker stdout exceeded ${limit} bytes`
      : child.error.message;
    return toolText({ ok: false, code, message, limit_bytes: limit }, true);
  }
  const line = (child.stdout || "").trim().split("\n").filter(Boolean).at(-1);
  if (!line) {
    return toolText(
      {
        ok: false,
        code: "broker_protocol",
        message: "broker returned no JSON",
      },
      true,
    );
  }
  let parsed: { ok?: boolean; result?: Json; error?: { code?: string; message?: string } };
  try {
    parsed = JSON.parse(line) as typeof parsed;
  } catch {
    return toolText({ ok: false, code: "broker_protocol", message: "broker JSON parse failed" }, true);
  }
  if (!parsed.ok) {
    return toolText(
      {
        ok: false,
        code: parsed.error?.code || "broker_error",
        message: parsed.error?.message || "broker request failed",
      },
      true,
    );
  }
  return toolText({ ok: true, ...(parsed.result as object) }, false);
}

function requireLanguage(args: { [key: string]: Json }): string | Json {
  const language = args.language;
  if (typeof language !== "string" || language.length === 0) {
    return toolText({ ok: false, code: "invalid_arguments", message: "language is required" }, true);
  }
  if (!TIER1.includes(language)) {
    return toolText(
      {
        ok: false,
        code: "language_not_tier1",
        message: `${language} is outside the Tier-1 registry`,
        tier1: TIER1,
      },
      true,
    );
  }
  return language;
}

function requirePath(args: { [key: string]: Json }): string | Json {
  const rel = args.path;
  if (typeof rel !== "string" || rel.length === 0) {
    return toolText({ ok: false, code: "invalid_arguments", message: "path is required" }, true);
  }
  return rel;
}

function callTool(name: string, args: { [key: string]: Json }): Json {
  if (name === "lsp_status") {
    return brokerRpc("health", {});
  }
  if (name === "lsp_install") {
    const language = requireLanguage(args);
    if (typeof language !== "string") {
      return language;
    }
    return brokerRpc("install", { language });
  }
  if (name === "lsp_diagnostics") {
    const language = requireLanguage(args);
    if (typeof language !== "string") {
      return language;
    }
    const rel = requirePath(args);
    if (typeof rel !== "string") {
      return rel;
    }
    return brokerRpc("diagnostics", { language, path: rel });
  }
  if (name === "lsp_hover" || name === "lsp_definition") {
    const language = requireLanguage(args);
    if (typeof language !== "string") {
      return language;
    }
    const rel = requirePath(args);
    if (typeof rel !== "string") {
      return rel;
    }
    const probed = brokerRpc("probe", { language, path: rel });
    const text = JSON.parse(
      ((probed as { content: { text: string }[] }).content[0].text),
    ) as { ok?: boolean; code?: string; message?: string };
    if (!text.ok) {
      return probed;
    }
    const kind = name === "lsp_hover" ? "hover" : "definition";
    return toolText(
      {
        ok: true,
        stub: true,
        kind,
        language,
        path: rel,
        message: `${kind} stub — spike does not call the LSP ${kind} method`,
      },
      false,
    );
  }
  return toolText({ ok: false, code: "unknown_tool", message: `unknown tool ${name}` }, true);
}

function handle(message: RpcRequest): void {
  const method = message.method || "";
  if (!Object.prototype.hasOwnProperty.call(message, "id") || method.startsWith("notifications/")) {
    return;
  }
  const id = message.id ?? null;
  if (method === "initialize") {
    send({
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "mcp-unified-lsp", version: "0.0.1-spike" },
      },
    });
    return;
  }
  if (method === "ping") {
    send({ jsonrpc: "2.0", id, result: {} });
    return;
  }
  if (method === "tools/list") {
    send({ jsonrpc: "2.0", id, result: { tools: TOOLS } });
    return;
  }
  if (method === "tools/call") {
    const params = message.params || {};
    const name = typeof params.name === "string" ? params.name : "";
    const args = (params.arguments && typeof params.arguments === "object" && !Array.isArray(params.arguments))
      ? params.arguments as { [key: string]: Json }
      : {};
    send({ jsonrpc: "2.0", id, result: callTool(name, args) });
    return;
  }
  send({
    jsonrpc: "2.0",
    id,
    error: { code: -32601, message: `method not found: ${method}` },
  });
}

let buffer = Buffer.alloc(0);
let skipBytes = 0;
let resync = false;

function discardDeclaredBody(bodyStart: number, length: number): void {
  const available = Math.max(0, buffer.length - bodyStart);
  const drop = Math.min(available, length);
  const rest = buffer.subarray(bodyStart + drop);
  buffer = rest.length === 0 ? Buffer.alloc(0) : Buffer.from(rest);
  skipBytes = length - drop;
}

function rejectUnsizedBody(): Parsed {
  buffer = Buffer.alloc(0);
  skipBytes = 0;
  resync = true;
  return frameTooBig();
}

function takeRest(start: number): void {
  const rest = buffer.subarray(start);
  buffer = rest.length === 0 ? Buffer.alloc(0) : Buffer.from(rest);
}

function looksLikeContentLength(buf: Buffer): boolean {
  const prefix = "content-length:";
  const head = buf.subarray(0, Math.min(buf.length, prefix.length)).toString("latin1").toLowerCase();
  return prefix.startsWith(head) || head.startsWith(prefix);
}

function applySkip(): boolean {
  if (skipBytes <= 0) {
    return false;
  }
  if (buffer.length === 0) {
    return true;
  }
  const drop = Math.min(buffer.length, skipBytes);
  const rest = buffer.subarray(drop);
  buffer = rest.length === 0 ? Buffer.alloc(0) : Buffer.from(rest);
  skipBytes -= drop;
  return skipBytes > 0;
}

type Parsed =
  | { kind: "need-more" }
  | { kind: "drop" }
  | { kind: "bad"; message: string }
  | { kind: "ok"; message: RpcRequest };

function rejectFrame(message: string): void {
  buffer = Buffer.alloc(0);
  send({
    jsonrpc: "2.0",
    id: null,
    error: {
      code: -32600,
      message,
      data: { code: "invalid_arguments", limit_bytes: MAX_MCP_FRAME },
    },
  });
}

function frameTooBig(): Parsed {
  return { kind: "bad", message: `frame exceeds ${MAX_MCP_FRAME} bytes` };
}

function findHeaderEnd(buf: Buffer): { index: number; length: number } | null {
  const crlf = buf.indexOf("\r\n\r\n");
  const lf = buf.indexOf("\n\n");
  if (crlf < 0 && lf < 0) {
    return null;
  }
  if (lf >= 0 && (crlf < 0 || lf < crlf)) {
    return { index: lf, length: 2 };
  }
  return { index: crlf, length: 4 };
}

function resyncParse(): Parsed {
  if (!looksLikeContentLength(buffer)) {
    const newline = buffer.indexOf(0x0a);
    if (newline < 0) {
      if (buffer.length > MAX_MCP_FRAME) {
        buffer = Buffer.alloc(0);
      }
      return { kind: "need-more" };
    }
    takeRest(newline + 1);
    return { kind: "drop" };
  }
  const headerEnd = findHeaderEnd(buffer);
  if (headerEnd === null) {
    if (buffer.length > MAX_MCP_FRAME) {
      buffer = Buffer.alloc(0);
    }
    return { kind: "need-more" };
  }
  const header = buffer.subarray(0, headerEnd.index).toString("utf-8");
  const match = header.match(/content-length:\s*(\S+)/i);
  const length = match ? Number(match[1]) : NaN;
  if (!Number.isFinite(length) || length < 0) {
    takeRest(headerEnd.index + headerEnd.length);
    return { kind: "drop" };
  }
  resync = false;
  return tryParse();
}

function tryParse(): Parsed {
  if (resync) {
    return resyncParse();
  }
  const textStart = buffer.toString("utf-8");
  if (textStart.startsWith("Content-Length:") || textStart.startsWith("content-length:")) {
    const headerEnd = findHeaderEnd(buffer);
    if (headerEnd === null) {
      if (buffer.length > MAX_MCP_FRAME) {
        buffer = Buffer.alloc(0);
        return frameTooBig();
      }
      return { kind: "need-more" };
    }
    const sep = headerEnd.index;
    const sepLen = headerEnd.length;
    const header = buffer.subarray(0, sep).toString("utf-8");
    const match = header.match(/content-length:\s*(\S+)/i);
    const length = match ? Number(match[1]) : NaN;
    if (!Number.isFinite(length) || length < 0) {
      return rejectUnsizedBody();
    }
    if (length > MAX_MCP_FRAME) {
      discardDeclaredBody(sep + sepLen, length);
      return frameTooBig();
    }
    if (sep > MAX_MCP_FRAME) {
      buffer = Buffer.alloc(0);
      return frameTooBig();
    }
    const start = sep + sepLen;
    if (buffer.length < start + length) {
      if (buffer.length > MAX_MCP_FRAME) {
        buffer = Buffer.alloc(0);
        return frameTooBig();
      }
      return { kind: "need-more" };
    }
    const body = buffer.subarray(start, start + length).toString("utf-8");
    buffer = buffer.subarray(start + length);
    return parseRpcBody(body);
  }
  const newline = buffer.indexOf(0x0a);
  if (newline < 0) {
    if (buffer.length > MAX_MCP_FRAME) {
      buffer = Buffer.alloc(0);
      return frameTooBig();
    }
    return { kind: "need-more" };
  }
  if (newline > MAX_MCP_FRAME) {
    buffer = buffer.subarray(newline + 1);
    return frameTooBig();
  }
  const line = buffer.subarray(0, newline).toString("utf-8").trim();
  buffer = buffer.subarray(newline + 1);
  if (!line) {
    return tryParse();
  }
  return parseRpcBody(line);
}

function parseRpcBody(body: string): Parsed {
  try {
    const parsed = JSON.parse(body) as unknown;
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { kind: "bad", message: "request must be a JSON object" };
    }
    return { kind: "ok", message: parsed as RpcRequest };
  } catch {
    return { kind: "bad", message: "request is not JSON" };
  }
}

function onData(chunk: Buffer): void {
  buffer = Buffer.concat([buffer, chunk]);
  for (;;) {
    if (applySkip()) {
      return;
    }
    const before = buffer.length;
    let parsed: Parsed;
    try {
      parsed = tryParse();
    } catch (err) {
      process.stderr.write(`mcp-unified-lsp parse error: ${String(err)}\n`);
      rejectFrame("request is not JSON");
      return;
    }
    if (parsed.kind === "need-more") {
      return;
    }
    if (parsed.kind === "drop") {
      if (buffer.length >= before) {
        return;
      }
      continue;
    }
    if (parsed.kind === "bad") {
      const consumed = buffer.length < before;
      send({
        jsonrpc: "2.0",
        id: null,
        error: {
          code: -32600,
          message: parsed.message,
          data: { code: "invalid_arguments", limit_bytes: MAX_MCP_FRAME },
        },
      });
      if (!consumed) {
        buffer = Buffer.alloc(0);
        return;
      }
      if (buffer.length === 0) {
        return;
      }
      continue;
    }
    const message = parsed.message;
    try {
      handle(message);
    } catch (err) {
      if (message.id !== undefined && message.id !== null) {
        send({
          jsonrpc: "2.0",
          id: message.id,
          error: { code: -32603, message: String(err) },
        });
      }
    }
    if (buffer.length === before) {
      return;
    }
  }
}

if (process.env.ULSP_SANITIZE_SELFTEST === "1") {
  const sample: Json = {
    path: "/tmp/ulsp/state/broker.sock",
    home: "/home/ubuntu/desk",
    message: "API_KEY=abc123",
    stderr: "tail from /tmp/ulsp/broker",
  };
  process.stdout.write(`${JSON.stringify(sanitize(sample))}\n`);
  process.exit(0);
}

process.stdin.on("data", onData);
process.stdin.on("end", () => {
  process.exit(0);
});
process.stderr.write("mcp-unified-lsp stdio ready\n");
