import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const fixturesRoot = fileURLToPath(new URL('../fixtures/', import.meta.url));
const host = '127.0.0.1';

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
};

function fixturePort(): number {
  const raw = process.env.VERIFY_FIXTURE_PORT ?? '4173';
  if (!/^[0-9]+$/.test(raw)) {
    process.stderr.write('VERIFY_FIXTURE_PORT must be an integer\n');
    process.exit(1);
  }
  const port = Number(raw);
  if (port < 1 || port > 65535) {
    process.stderr.write('VERIFY_FIXTURE_PORT is out of range\n');
    process.exit(1);
  }
  return port;
}

function send(res: ServerResponse, status: number, body: string, type = 'text/plain; charset=utf-8'): void {
  res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store' });
  res.end(body);
}

function resolveFixture(pathname: string): string | null {
  let decoded: string;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  if (decoded.includes('\0')) return null;
  const relative = decoded.replace(/^\/+/, '');
  if (relative === '' || relative.includes('\0')) return null;
  const full = join(fixturesRoot, relative);
  const rootWithSep = fixturesRoot.endsWith(sep) ? fixturesRoot : fixturesRoot + sep;
  if (!full.startsWith(rootWithSep)) return null;
  return full;
}

const port = fixturePort();
const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
  const pathname = (req.url ?? '/').split('?')[0] ?? '/';
  if (pathname === '/health') {
    send(res, 200, 'ok');
    return;
  }
  const file = resolveFixture(pathname);
  if (!file) {
    send(res, 404, 'not found');
    return;
  }
  try {
    const body = await readFile(file);
    const type = MIME[extname(file)] ?? 'application/octet-stream';
    res.writeHead(200, { 'content-type': type, 'cache-control': 'no-store' });
    res.end(body);
  } catch {
    send(res, 404, 'not found');
  }
});

server.on('error', (err: NodeJS.ErrnoException) => {
  process.stderr.write(`fixture server: ${err.message}\n`);
  process.exit(1);
});

server.listen(port, host, () => {
  process.stdout.write(`fixture server http://${host}:${port}\n`);
});
