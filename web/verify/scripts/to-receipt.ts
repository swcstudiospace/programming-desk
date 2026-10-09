import { spawn } from 'node:child_process';
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';

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

interface Check {
  route: string;
  title: string;
  project: string;
  status: string;
  errorMessage: string;
  command: CommandEntry;
}

const reportPath = resolve('out/playwright-report.json');
const outPath = resolve('out/verify-result.json');
const [mode, ...args] = process.argv.slice(2);
const env = { ...process.env };
if (mode === 'selftest' || mode === 'selftest:fail') {
  env.VERIFY_FIXTURES = '1';
  env.BASE_URL = `http://127.0.0.1:${env.VERIFY_FIXTURE_PORT ?? '4173'}`;
  env.ROUTES = mode === 'selftest' ? '/pass.html' : '/fail.html';
}

function tail(text: string, max = 500): string {
  const flat = text.replace(/\s+/g, ' ').trim();
  return flat.length <= max ? flat : flat.slice(flat.length - max);
}

function quote(value: string): string {
  return `'${value.replace(/'/g, `'"'"'`)}'`;
}

function replay(extra: string[] = [], route?: string, project?: string): string {
  const settings = ['BASE_URL="${BASE_URL:?Set BASE_URL to the original target URL}"'];
  // Keep secrets out of commands. BASE_URL is supplied by the operator at replay time.
  for (const [name, value] of Object.entries({
    ROUTES: route || env.ROUTES || '/',
    VERIFY_BROWSERS: project ?? env.VERIFY_BROWSERS ?? 'chromium',
    VERIFY_STARTUP_MS: env.VERIFY_STARTUP_MS ?? '1000',
    VERIFY_FIXTURES: env.VERIFY_FIXTURES ?? '0',
    VERIFY_FIXTURE_PORT: env.VERIFY_FIXTURE_PORT ?? '4173',
    VERIFY_HARNESS_REGRESSIONS: env.VERIFY_HARNESS_REGRESSIONS ?? '0',
  })) {
    settings.push(`${name}=${quote(value)}`);
  }
  return `${settings.join(' ')} node --experimental-strip-types scripts/to-receipt.ts verify${extra.map((arg) => ` ${quote(arg)}`).join('')}`;
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

function walk(suite: ReportSuite, route: string, checks: Check[]): void {
  const nextRoute = suite.title?.startsWith('route ') ? suite.title.slice(6) : route;
  for (const spec of suite.specs ?? []) {
    for (const test of spec.tests ?? []) {
      const results = test.results ?? [];
      const last = results[results.length - 1];
      const status = last?.status ?? 'missing';
      const messages = [
        ...(last?.errors ?? []).map((error) => error.message ?? ''),
        last?.error?.message ?? '',
        ...texts(last?.stdout),
        ...texts(last?.stderr),
      ].filter((line) => line.trim().length > 0).join(' | ');
      const title = spec.title ?? 'check';
      const project = test.projectName ?? 'chromium';
      const escapedTitle = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      checks.push({
        route: nextRoute,
        title,
        project,
        status,
        errorMessage: last?.error?.message ?? '',
        command: {
          cmd: replay(['--project', project, '--grep', `(?:^| )${escapedTitle}$`], nextRoute, project),
          exit_code: status === 'passed' ? 0 : 1,
          duration_s: Math.round(results.reduce((sum, result) => sum + (result.duration ?? 0), 0)) / 1000,
          output_tail: tail(messages || status),
        },
      });
    }
  }
  for (const child of suite.suites ?? []) walk(child, nextRoute, checks);
}

// Delete prior evidence before launching, even if configuration or browser launch fails.
// A standalone converter cannot establish which invocation an existing report belongs to.
await mkdir(dirname(outPath), { recursive: true });
await Promise.all([
  rm(reportPath, { force: true }),
  rm(outPath, { force: true }),
  rm(resolve('out/screenshots'), { force: true, recursive: true }),
  rm(resolve('out/test-results'), { force: true, recursive: true }),
]);
const started = performance.now();
let runExit = 1;
let runOutput = '';
try {
  if (!['verify', 'selftest', 'selftest:fail'].includes(mode ?? '')) {
    throw new Error('usage: to-receipt.ts verify|selftest|selftest:fail [Playwright test options]');
  }
  const require = createRequire(import.meta.url);
  const cli = join(dirname(require.resolve('playwright/package.json')), 'cli.js');
  runExit = await new Promise<number>((resolveExit, reject) => {
    const child = spawn(process.execPath, [cli, 'test', ...args], { env, stdio: ['inherit', 'pipe', 'pipe'] });
    child.stdout.on('data', (chunk: Buffer) => {
      runOutput = (runOutput + chunk.toString()).slice(-4000);
      process.stdout.write(chunk);
    });
    child.stderr.on('data', (chunk: Buffer) => {
      runOutput = (runOutput + chunk.toString()).slice(-4000);
      process.stderr.write(chunk);
    });
    child.on('error', reject);
    child.on('close', (code, signal) => {
      if (signal) runOutput += ` Playwright terminated by ${signal}`;
      resolveExit(code ?? 1);
    });
  });
} catch (error) {
  runOutput += error instanceof Error ? error.message : String(error);
}
const duration = Math.round(performance.now() - started) / 1000;
const checks: Check[] = [];
let reportError = '';
try {
  const report = JSON.parse(await readFile(reportPath, 'utf8')) as {
    suites?: ReportSuite[];
    errors?: Array<{ message?: string }>;
  };
  for (const suite of report.suites ?? []) walk(suite, '', checks);
  reportError = (report.errors ?? []).map((error) => error.message ?? 'Playwright report error').join(' | ');
  if (checks.length === 0) reportError ||= 'Playwright report has no checks';
} catch (error) {
  reportError = `No usable report from this invocation: ${error instanceof Error ? error.message : String(error)}`;
}
const commands: CommandEntry[] = [{
  cmd: replay(args),
  exit_code: runExit,
  duration_s: duration,
  output_tail: tail(runOutput || `Playwright exit=${runExit}`),
}, ...checks.map((check) => check.command)];
if (reportError) {
  commands.push({
    cmd: replay(args),
    exit_code: 1,
    duration_s: 0,
    output_tail: tail(reportError),
  });
}
await writeFile(outPath, `${JSON.stringify({ run: { exit_code: runExit, duration_s: duration }, commands }, null, 2)}\n`);
const failed = commands.filter((entry) => entry.exit_code !== 0);
process.stdout.write(`verify-result checks=${checks.length} failed=${failed.length} run_exit=${runExit}\n`);

if (mode === 'selftest:fail') {
  const projects = (env.VERIFY_BROWSERS ?? 'chromium').split(',').map((name) => name.trim()).filter(Boolean);
  const expected = ['http-status', 'console-error', 'page-error', 'axe-serious-or-critical', 'screenshots'];
  const correct = runExit === 1 && !reportError && checks.length === projects.length * expected.length &&
    projects.every((project) => expected.every((title) => {
      const matching = checks.filter((check) => check.project === project && check.route === '/fail.html' && check.title === title);
      if (matching.length !== 1) return false;
      const check = matching[0];
      if (title === 'console-error') {
        return check.status === 'failed' && check.errorMessage === 'Error: console-error: fixture-console-error: desk-verify-fail';
      }
      if (title === 'axe-serious-or-critical') {
        return check.status === 'failed' && check.errorMessage === 'Error: axe violation: image-alt impact=critical';
      }
      return check.status === 'passed';
    }));
  process.stdout.write(correct
    ? 'selftest:fail: observed exactly the expected console-error and image-alt failures in every project\n'
    : 'selftest:fail: missing expected failures or encountered an unexpected failure; see current report\n');
  process.exitCode = correct ? 0 : 1;
} else {
  process.exitCode = runExit || (failed.length > 0 ? 1 : 0);
}
