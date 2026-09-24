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

function toolText(payload: Json, isError: boolean): Json {
  return {
    content: [{ type: "text", text: JSON.stringify(payload) }],
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
    },
  );
  if (child.error) {
    const code = child.error.name === "TimeoutError" ? "diagnostics_timeout" : "broker_protocol";
    return toolText({ ok: false, code, message: child.error.message }, true);
  }
  const line = (child.stdout || "").trim().split("\n").filter(Boolean).at(-1);
  if (!line) {
    return toolText(
      {
        ok: false,
        code: "broker_protocol",
        message: "broker returned no JSON",
        stderr: (child.stderr || "").slice(-400),
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

function tryParse(): RpcRequest | undefined {
  const textStart = buffer.toString("utf-8");
  if (textStart.startsWith("Content-Length:") || textStart.startsWith("content-length:")) {
    const sep = buffer.indexOf("\r\n\r\n");
    if (sep < 0) {
      return undefined;
    }
    const header = buffer.subarray(0, sep).toString("utf-8");
    const match = header.match(/content-length:\s*(\d+)/i);
    if (!match) {
      buffer = Buffer.alloc(0);
      return undefined;
    }
    const length = Number(match[1]);
    const start = sep + 4;
    if (buffer.length < start + length) {
      return undefined;
    }
    const body = buffer.subarray(start, start + length).toString("utf-8");
    buffer = buffer.subarray(start + length);
    return JSON.parse(body) as RpcRequest;
  }
  const newline = buffer.indexOf(0x0a);
  if (newline < 0) {
    return undefined;
  }
  const line = buffer.subarray(0, newline).toString("utf-8").trim();
  buffer = buffer.subarray(newline + 1);
  if (!line) {
    return tryParse();
  }
  return JSON.parse(line) as RpcRequest;
}

function onData(chunk: Buffer): void {
  buffer = Buffer.concat([buffer, chunk]);
  for (;;) {
    const before = buffer.length;
    let message: RpcRequest | undefined;
    try {
      message = tryParse();
    } catch (err) {
      process.stderr.write(`mcp-unified-lsp parse error: ${String(err)}\n`);
      return;
    }
    if (!message) {
      return;
    }
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

process.stdin.on("data", onData);
process.stdin.on("end", () => {
  process.exit(0);
});
process.stderr.write("mcp-unified-lsp stdio ready\n");
