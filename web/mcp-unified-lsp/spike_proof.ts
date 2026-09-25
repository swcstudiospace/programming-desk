/**
 * MCP stdio proof for mcp-unified-lsp.
 * Starts the INFRA broker, then drives the adapter over stdin/stdout only.
 */

import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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

function assertClean(payload: Record<string, unknown>): void {
  const text = JSON.stringify(payload);
  expect(!text.includes("/tmp"), text);
  expect(!text.includes("/workspace"), text);
  expect(!text.includes("/home"), text);
  expect(!text.includes("abc123"), text);
  expect(!Object.prototype.hasOwnProperty.call(payload, "stderr"), text);
}

function toolPayload(response: Record<string, unknown>): Record<string, unknown> {
  const result = response.result as { content?: { text: string }[]; isError?: boolean } | undefined;
  expect(!!result?.content?.[0]?.text, `missing tool text: ${JSON.stringify(response)}`);
  const payload = JSON.parse(result.content[0].text) as Record<string, unknown>;
  payload.isError = result.isError === true;
  assertClean(payload);
  return payload;
}

async function main(): Promise<void> {
  expect(!source.includes("createServer("), "MCP adapter must not open a node server");
  expect(!source.includes(".listen("), "MCP adapter must not listen on a port");
  expect(!source.includes("child.stderr"), "MCP adapter must not attach a broker stderr tail");

  const self = spawnSync(process.execPath, ["--experimental-strip-types", server], {
    env: { ...process.env, ULSP_SANITIZE_SELFTEST: "1" },
    encoding: "utf-8",
  });
  expect(self.status === 0, self.stderr || "sanitize self-test failed");
  const sanitized = JSON.parse(self.stdout.trim().split("\n").at(-1) || "{}") as Record<string, unknown>;
  expect(String(sanitized.message).includes("[REDACTED]"), JSON.stringify(sanitized));
  assertClean(sanitized);
  expect(!("stderr" in sanitized), JSON.stringify(sanitized));

  const stateDir = mkdtempSync(path.join(tmpdir(), "ulsp-mcp-"));
  const work = mkdtempSync(path.join(tmpdir(), "ulsp-mcp-work-"));
  cpSync(fixtures, work, { recursive: true });
  writeFileSync(path.join(work, ".env"), "API_KEY=abc123\n");
  writeFileSync(
    path.join(work, "tsjs", "leak.ts"),
    `const leak = 1;\nulsp-diag: API_KEY=abc123 ${"p".repeat(400)}\n`,
  );
  const brokerProc = spawn(
    "python3",
    [broker, "--state-dir", stateDir, "start", "--workspace", work],
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

  const extraDirs: string[] = [];
  try {
    const initMessage = {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "spike", version: "0" } },
    };
    mcp.stdin.write(`null\n${JSON.stringify(initMessage)}\n`);
    const bad = JSON.parse(await nextMcp()) as { error?: { data?: { code?: string } } };
    expect(bad.error?.data?.code === "invalid_arguments", JSON.stringify(bad));
    const init = JSON.parse(await nextMcp()) as Record<string, unknown>;
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

    const secretFile = toolPayload(await mcpCall({
      jsonrpc: "2.0",
      id: 44,
      method: "tools/call",
      params: { name: "lsp_diagnostics", arguments: { language: "tsjs", path: ".env" } },
    }));
    expect(secretFile.isError === true && secretFile.code === "extension_not_allowed", JSON.stringify(secretFile));

    const leaked = toolPayload(await mcpCall({
      jsonrpc: "2.0",
      id: 45,
      method: "tools/call",
      params: { name: "lsp_diagnostics", arguments: { language: "tsjs", path: "tsjs/leak.ts" } },
    }));
    expect(leaked.ok === true, JSON.stringify(leaked));
    const leakMessages = (leaked.diagnostics as { message: string }[]).map((item) => item.message);
    expect(leakMessages.some((item) => item.includes("[REDACTED]")), JSON.stringify(leaked));
    expect(leakMessages.every((item) => item.length <= 240), JSON.stringify(leakMessages));
    expect(!JSON.stringify(leaked).includes("STALE"), JSON.stringify(leaked));

    const frameDir = mkdtempSync(path.join(tmpdir(), "ulsp-mcp-frame-"));
    extraDirs.push(frameDir);
    const frameServer = spawn(process.execPath, ["--experimental-strip-types", server], {
      env: { ...process.env, ULSP_BROKER: broker, ULSP_STATE_DIR: frameDir, ULSP_PYTHON: "python3" },
      stdio: ["pipe", "pipe", "pipe"],
    }) as ChildProcessWithoutNullStreams;
    frameServer.stderr.resume();
    const nextFrame = lineReader(frameServer, 5000);
    frameServer.stdin.write(`${"a".repeat(1_048_577)}`);
    const framed = JSON.parse(await nextFrame()) as { error?: { data?: { code?: string } } };
    expect(framed.error?.data?.code === "invalid_arguments", JSON.stringify(framed));
    frameServer.kill();

    const guard = spawn(process.execPath, ["--experimental-strip-types", server], {
      env: { ...process.env, ULSP_BROKER: broker, ULSP_STATE_DIR: frameDir, ULSP_PYTHON: "python3" },
      stdio: ["pipe", "pipe", "pipe"],
    }) as ChildProcessWithoutNullStreams;
    guard.stderr.resume();
    const nextGuard = lineReader(guard, 5000);
    const ping = (id: number) => JSON.stringify({ jsonrpc: "2.0", id, method: "ping" });
    guard.stdin.write(`${"y".repeat(1_048_577)}\n${ping(70)}\n`);
    const bigLine = JSON.parse(await nextGuard()) as { error?: { data?: { code?: string } } };
    expect(bigLine.error?.data?.code === "invalid_arguments", JSON.stringify(bigLine));
    const afterLine = JSON.parse(await nextGuard()) as { id?: number; result?: unknown };
    expect(afterLine.id === 70 && afterLine.result !== undefined, JSON.stringify(afterLine));
    const declared = 1_048_577;
    const buried = `${ping(99)}\n`;
    const pad = "z".repeat(declared - Buffer.byteLength(buried));
    expect(Buffer.byteLength(buried + pad) === declared, "rejected body length");
    guard.stdin.write(`Content-Length: ${declared}\r\n\r\n${buried}${pad}${ping(72)}\n`);
    const bigHeader = JSON.parse(await nextGuard()) as { id?: number; error?: { data?: { code?: string } } };
    expect(bigHeader.id !== 99 && bigHeader.error?.data?.code === "invalid_arguments", JSON.stringify(bigHeader));
    const afterHeader = JSON.parse(await nextGuard()) as { id?: number; result?: unknown };
    expect(afterHeader.id === 72 && afterHeader.result !== undefined, JSON.stringify(afterHeader));
    guard.stdin.write(`Content-Length: ${declared}\r\n\r\n`);
    const chunked = JSON.parse(await nextGuard()) as { id?: number; error?: { data?: { code?: string } } };
    expect(chunked.id !== 99 && chunked.error?.data?.code === "invalid_arguments", JSON.stringify(chunked));
    guard.stdin.write(buried);
    guard.stdin.write(`${pad}${ping(73)}\n`);
    const afterChunk = JSON.parse(await nextGuard()) as { id?: number; result?: unknown };
    expect(afterChunk.id === 73 && afterChunk.result !== undefined, JSON.stringify(afterChunk));
    const head = `${ping(98)}\n`;
    const tail = `${ping(99)}\n`;
    const mid = "q".repeat(declared - Buffer.byteLength(head + tail));
    const multilineBody = head + mid + tail;
    expect(Buffer.byteLength(multilineBody) === declared, "multiline body length");
    const extra = "Content-Type: application/vscode-jsonrpc; charset=utf-8\r\n";
    guard.stdin.write(`Content-Length: ${declared}\r\n${extra}\r\n${multilineBody}${ping(74)}\n`);
    const multi = JSON.parse(await nextGuard()) as { id?: number; error?: { data?: { code?: string } } };
    expect(multi.id !== 98 && multi.id !== 99 && multi.error?.data?.code === "invalid_arguments", JSON.stringify(multi));
    const afterMulti = JSON.parse(await nextGuard()) as { id?: number; result?: unknown };
    expect(afterMulti.id === 74 && afterMulti.result !== undefined, JSON.stringify(afterMulti));
    guard.stdin.write(`Content-Length: ${declared}\r\n${extra}`);
    await new Promise((resolve) => setTimeout(resolve, 50));
    guard.stdin.write(`\r\n${multilineBody}${ping(75)}\n`);
    const early = JSON.parse(await nextGuard()) as { id?: number; error?: { data?: { code?: string } } };
    expect(early.id !== 98 && early.id !== 99 && early.error?.data?.code === "invalid_arguments", JSON.stringify(early));
    const afterEarly = JSON.parse(await nextGuard()) as { id?: number; result?: unknown };
    expect(afterEarly.id === 75 && afterEarly.result !== undefined, JSON.stringify(afterEarly));
    guard.kill();

    const fat = path.join(frameDir, "fat_broker.py");
    writeFileSync(fat, "import sys\nsys.stdout.write('x' * 4000)\n");
    const limited = spawn(process.execPath, ["--experimental-strip-types", server], {
      env: {
        ...process.env,
        ULSP_BROKER: fat,
        ULSP_STATE_DIR: frameDir,
        ULSP_PYTHON: "python3",
        ULSP_BROKER_MAX_STDOUT: "64",
      },
      stdio: ["pipe", "pipe", "pipe"],
    }) as ChildProcessWithoutNullStreams;
    limited.stderr.resume();
    const nextLimited = lineReader(limited, 5000);
    const limitedCall = async (message: unknown): Promise<Record<string, unknown>> => {
      limited.stdin.write(`${JSON.stringify(message)}\n`);
      return JSON.parse(await nextLimited()) as Record<string, unknown>;
    };
    await limitedCall({
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "spike", version: "0" } },
    });
    const oversized = toolPayload(await limitedCall({
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: { name: "lsp_status", arguments: {} },
    }));
    expect(oversized.isError === true && oversized.code === "response_too_large", JSON.stringify(oversized));
    expect(String(oversized.message).includes("64"), JSON.stringify(oversized));
    limited.kill();
  } finally {
    mcp.stdin.end();
    mcp.kill();
    const stop = spawn("python3", [broker, "--state-dir", stateDir, "stop"], { stdio: "ignore" });
    await new Promise((resolve) => stop.on("exit", resolve));
    if (brokerProc.exitCode === null) {
      brokerProc.kill();
    }
    for (const dir of [stateDir, work, ...extraDirs]) {
      rmSync(dir, { recursive: true, force: true });
    }
  }
  process.stdout.write(
    "MCP_SPIKE_OK stdio-primary languages=tsjs,javascript,python,go ws=unused f2=env f3=redacted f4=nopath sanitize=selftest p2=frame,null,maxbuf,line,clen-hdr\n",
  );
}

main().catch((err) => {
  process.stderr.write(`${String(err instanceof Error ? err.stack : err)}\n`);
  process.exit(1);
});
