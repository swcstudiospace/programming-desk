/**
 * MCP stdio proof for mcp-unified-lsp.
 * Starts the INFRA broker, then drives the adapter over stdin/stdout only.
 */

import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { readFileSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../..");
const broker = path.join(repo, "infra/unified-lsp-broker/broker.py");
const fixtures = path.join(repo, "infra/unified-lsp-broker/fixtures");
const server = path.join(here, "server.ts");
const source = readFileSync(server, "utf-8");

function expect(cond: boolean, message: string): void {
  if (!cond) {
    throw new Error(message);
  }
}

function lineReader(child: ChildProcessWithoutNullStreams, timeoutMs: number): () => Promise<string> {
  let buf = "";
  const waiters: Array<(line: string) => void> = [];
  child.stdout.on("data", (chunk: Buffer) => {
    buf += chunk.toString("utf-8");
    drain();
  });
  function drain(): void {
    let idx = buf.indexOf("\n");
    while (idx >= 0 && waiters.length > 0) {
      const line = buf.slice(0, idx);
      buf = buf.slice(idx + 1);
      const waiter = waiters.shift();
      if (waiter) {
        waiter(line);
      }
      idx = buf.indexOf("\n");
    }
  }
  return () => {
    const idx = buf.indexOf("\n");
    if (idx >= 0) {
      const line = buf.slice(0, idx);
      buf = buf.slice(idx + 1);
      return Promise.resolve(line);
    }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`timeout waiting for output; so far ${buf.slice(0, 300)}`));
      }, timeoutMs);
      waiters.push((line) => {
        clearTimeout(timer);
        resolve(line);
      });
    });
  };
}

function toolPayload(response: Record<string, unknown>): Record<string, unknown> {
  const result = response.result as { content?: { text: string }[]; isError?: boolean } | undefined;
  expect(!!result?.content?.[0]?.text, `missing tool text: ${JSON.stringify(response)}`);
  const payload = JSON.parse(result.content[0].text) as Record<string, unknown>;
  payload.isError = result.isError === true;
  return payload;
}

async function main(): Promise<void> {
  expect(!source.includes("createServer("), "MCP adapter must not open a node server");
  expect(!source.includes(".listen("), "MCP adapter must not listen on a port");

  const stateDir = mkdtempSync(path.join(tmpdir(), "ulsp-mcp-"));
  const brokerProc = spawn(
    "python3",
    [broker, "--state-dir", stateDir, "start", "--workspace", fixtures],
    { env: { ...process.env, PYTHONUNBUFFERED: "1" }, stdio: ["ignore", "pipe", "pipe"] },
  ) as ChildProcessWithoutNullStreams;
  brokerProc.stderr.resume();
  const brokerNext = lineReader(brokerProc, 5000);
  const listening = JSON.parse(await brokerNext()) as { state: string; ws: unknown };
  expect(listening.state === "ready", JSON.stringify(listening));
  expect(listening.ws === null, "MCP proof broker must not require websocket");

  const mcp = spawn(process.execPath, ["--experimental-strip-types", server], {
    env: {
      ...process.env,
      ULSP_BROKER: broker,
      ULSP_STATE_DIR: stateDir,
      ULSP_PYTHON: "python3",
    },
    stdio: ["pipe", "pipe", "pipe"],
  }) as ChildProcessWithoutNullStreams;
  mcp.stderr.resume();
  const nextMcp = lineReader(mcp, 20000);
  const mcpCall = async (message: unknown): Promise<Record<string, unknown>> => {
    mcp.stdin.write(`${JSON.stringify(message)}\n`);
    const line = await nextMcp();
    return JSON.parse(line) as Record<string, unknown>;
  };

  try {
    const init = await mcpCall({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "spike", version: "0" } },
    });
    const initResult = init.result as { serverInfo?: { name?: string } };
    expect(initResult.serverInfo?.name === "mcp-unified-lsp", JSON.stringify(init));
    mcp.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" })}\n`);

    const listed = await mcpCall({ jsonrpc: "2.0", id: 2, method: "tools/list" });
    const names = ((listed.result as { tools: { name: string }[] }).tools).map((tool) => tool.name);
    for (const name of ["lsp_status", "lsp_install", "lsp_diagnostics", "lsp_hover", "lsp_definition"]) {
      expect(names.includes(name), `missing tool ${name}: ${names.join(",")}`);
    }

    const missing = toolPayload(await mcpCall({
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: { name: "lsp_diagnostics", arguments: { language: "python", path: "python/sample.py" } },
    }));
    expect(missing.isError === true && missing.code === "language_server_missing", JSON.stringify(missing));

    const cases: { language: string; path: string; needle: string }[] = [
      { language: "tsjs", path: "tsjs/sample.ts", needle: "intentional spike diagnostic for tsjs" },
      { language: "tsjs", path: "tsjs/sample.js", needle: "intentional spike diagnostic for javascript" },
      { language: "python", path: "python/sample.py", needle: "intentional spike diagnostic for python" },
      { language: "go", path: "go/sample.go", needle: "intentional spike diagnostic for go" },
    ];
    let id = 10;
    for (const item of cases) {
      const installed = toolPayload(await mcpCall({
        jsonrpc: "2.0",
        id: id++,
        method: "tools/call",
        params: { name: "lsp_install", arguments: { language: item.language } },
      }));
      expect(installed.ok === true && installed.isError === false, JSON.stringify(installed));
      const diags = toolPayload(await mcpCall({
        jsonrpc: "2.0",
        id: id++,
        method: "tools/call",
        params: { name: "lsp_diagnostics", arguments: { language: item.language, path: item.path } },
      }));
      expect(diags.ok === true && diags.isError === false, JSON.stringify(diags));
      const list = diags.diagnostics as { message: string }[];
      expect(list.some((diag) => String(diag.message).includes(item.needle)), JSON.stringify(diags));
    }

    const hover = toolPayload(await mcpCall({
      jsonrpc: "2.0",
      id: 40,
      method: "tools/call",
      params: { name: "lsp_hover", arguments: { language: "go", path: "go/sample.go" } },
    }));
    expect(hover.stub === true && hover.kind === "hover", JSON.stringify(hover));
    const definition = toolPayload(await mcpCall({
      jsonrpc: "2.0",
      id: 41,
      method: "tools/call",
      params: { name: "lsp_definition", arguments: { language: "go", path: "go/sample.go" } },
    }));
    expect(definition.stub === true && definition.kind === "definition", JSON.stringify(definition));

    const outside = toolPayload(await mcpCall({
      jsonrpc: "2.0",
      id: 42,
      method: "tools/call",
      params: { name: "lsp_install", arguments: { language: "rust" } },
    }));
    expect(outside.isError === true && outside.code === "language_not_tier1", JSON.stringify(outside));

    const status = toolPayload(await mcpCall({
      jsonrpc: "2.0",
      id: 43,
      method: "tools/call",
      params: { name: "lsp_status", arguments: {} },
    }));
    expect(status.state === "serving", JSON.stringify(status));
    expect(status.primary_surface === "mcp-stdio", JSON.stringify(status));
  } finally {
    mcp.stdin.end();
    mcp.kill();
    const stop = spawn("python3", [broker, "--state-dir", stateDir, "stop"], { stdio: "ignore" });
    await new Promise((resolve) => stop.on("exit", resolve));
    if (brokerProc.exitCode === null) {
      brokerProc.kill();
    }
  }
  process.stdout.write("MCP_SPIKE_OK stdio-primary languages=tsjs,javascript,python,go ws=unused\n");
}

main().catch((err) => {
  process.stderr.write(`${String(err instanceof Error ? err.stack : err)}\n`);
  process.exit(1);
});
