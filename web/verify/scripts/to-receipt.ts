import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

interface CommandEntry {
  cmd: string;
  exit_code: number;
  duration_s: number;
  output_tail: string;
}

interface ReportSuite {
  title?: string;
  specs?: ReportSpec[];
  suites?: ReportSuite[];
}

interface ReportSpec {
  title?: string;
  tests?: ReportTest[];
}

interface ReportTest {
  projectName?: string;
  results?: ReportResult[];
}

interface ReportResult {
  status?: string;
  duration?: number;
  error?: { message?: string };
  errors?: Array<{ message?: string }>;
  stdout?: unknown;
  stderr?: unknown;
}

const reportPath = resolve('out/playwright-report.json');
const outPath = resolve('out/verify-result.json');

function tail(text: string, max = 500): string {
  const flat = text.replace(/\s+/g, ' ').trim();
  if (flat.length <= max) return flat;
  return flat.slice(flat.length - max);
}

function texts(value: unknown): string[] {
  if (typeof value === 'string') return [value];
  if (!Array.isArray(value)) return [];
  const lines: string[] = [];
  for (const item of value) {
    if (typeof item === 'string') {
      lines.push(item);
    } else if (item && typeof item === 'object' && 'text' in item && typeof item.text === 'string') {
      lines.push(item.text);
    }
  }
  return lines;
}

function walk(suite: ReportSuite, titles: string[], commands: CommandEntry[]): void {
  const next = suite.title ? [...titles, suite.title] : titles;
  for (const spec of suite.specs ?? []) {
    for (const test of spec.tests ?? []) {
      const results = test.results ?? [];
      const last = results[results.length - 1];
      const status = last?.status ?? 'missing';
      const durationMs = results.reduce((sum, result) => sum + (result.duration ?? 0), 0);
      const messages = [
        ...(last?.errors ?? []).map((error) => error.message ?? ''),
        last?.error?.message ?? '',
        ...texts(last?.stdout),
        ...texts(last?.stderr),
      ].filter((line) => line.trim().length > 0);
      const name = [...next, spec.title ?? 'check'].filter((part) => part.length > 0).join(' ');
      const project = test.projectName ?? 'chromium';
      commands.push({
        cmd: `playwright ${project} ${name}`,
        exit_code: status === 'passed' ? 0 : 1,
        duration_s: Math.round(durationMs) / 1000,
        output_tail: tail(messages.join(' | ') || status),
      });
    }
  }
  for (const child of suite.suites ?? []) walk(child, next, commands);
}

let raw: string;
try {
  raw = await readFile(reportPath, 'utf8');
} catch (err) {
  const message = err instanceof Error ? err.message : String(err);
  process.stderr.write(`to-receipt: cannot read ${reportPath}: ${message}\n`);
  process.exit(1);
}

let report: { suites?: ReportSuite[] };
try {
  report = JSON.parse(raw) as { suites?: ReportSuite[] };
} catch (err) {
  const message = err instanceof Error ? err.message : String(err);
  process.stderr.write(`to-receipt: ${reportPath} is not JSON: ${message}\n`);
  process.exit(1);
}

const commands: CommandEntry[] = [];
for (const suite of report.suites ?? []) walk(suite, [], commands);
if (commands.length === 0) {
  process.stderr.write('to-receipt: playwright report has no checks\n');
  process.exit(1);
}

const required = ['cmd', 'exit_code', 'duration_s', 'output_tail'] as const;
for (const entry of commands) {
  for (const key of required) {
    if (entry[key] === undefined || entry[key] === null || entry[key] === '') {
      process.stderr.write(`to-receipt: a check is missing ${key}\n`);
      process.exit(1);
    }
  }
}

await mkdir(dirname(outPath), { recursive: true });
await writeFile(outPath, `${JSON.stringify({ commands }, null, 2)}\n`);

const failed = commands.filter((entry) => entry.exit_code !== 0);
process.stdout.write(`verify-result checks=${commands.length} failed=${failed.length}\n`);
for (const entry of commands) {
  process.stdout.write(`- exit=${entry.exit_code} ${entry.cmd} ${entry.output_tail}\n`);
}
