import { createHash } from 'node:crypto';
import { spawn, type ChildProcess } from 'node:child_process';
import { cp, mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createServer } from 'node:net';
import { test, expect, type Page, type Response } from '@playwright/test';
import { AxeBuilder } from '@axe-core/playwright';

const screenshotDir = fileURLToPath(new URL('../out/screenshots/', import.meta.url));
const startupMs = Number(process.env.VERIFY_STARTUP_MS ?? '1000');
if (!Number.isInteger(startupMs) || startupMs < 0 || startupMs > 10_000) {
  throw new Error('VERIFY_STARTUP_MS must be an integer from 0 through 10000');
}

function routesFromEnv(): string[] {
  const routes = (process.env.ROUTES ?? '/')
    .split(',')
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .map((route) => (route.startsWith('/') ? route : `/${route}`));
  if (routes.length === 0) {
    throw new Error('ROUTES is empty');
  }
  return routes;
}

function routeSlug(route: string): string {
  if (route === '/') return 'root';
  const slug = route.replace(/^\/+/, '').replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 80);
  return slug.length > 0 ? slug : 'root';
}

interface Opened {
  response: Response | null;
  consoleErrors: string[];
  pageErrors: string[];
}

async function openRoute(page: Page, route: string): Promise<Opened> {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => {
    pageErrors.push(err.message);
  });
  const response = await page.goto(route, { waitUntil: 'load' });
  // Loading the document does not finish asynchronous application startup.
  await page.waitForTimeout(startupMs);
  return { response, consoleErrors, pageErrors };
}

for (const route of routesFromEnv()) {
  test.describe(`route ${route}`, () => {
    test('http-status', async ({ page }) => {
      const { response } = await openRoute(page, route);
      if (response === null) {
        throw new Error(`http-status: no response for ${route}`);
      }
      const status = response.status();
      if (status >= 400) {
        throw new Error(`http-status: ${status} for ${route}`);
      }
      console.log(`http-status: ${status} for ${route}`);
    });

    test('console-error', async ({ page }) => {
      const { consoleErrors } = await openRoute(page, route);
      if (consoleErrors.length > 0) {
        throw new Error(`console-error: ${consoleErrors.join(' | ')}`);
      }
      console.log(`console-error: none for ${route}`);
    });

    test('page-error', async ({ page }) => {
      const { pageErrors } = await openRoute(page, route);
      if (pageErrors.length > 0) {
        throw new Error(`page-error: ${pageErrors.join(' | ')}`);
      }
      console.log(`page-error: none for ${route}`);
    });

    test('axe-serious-or-critical', async ({ page }) => {
      await openRoute(page, route);
      const results = await new AxeBuilder({ page }).analyze();
      const blocking = results.violations.filter(
        (violation) => violation.impact === 'serious' || violation.impact === 'critical',
      );
      const noted = results.violations.filter(
        (violation) => violation.impact !== 'serious' && violation.impact !== 'critical',
      );
      if (noted.length > 0) {
        console.log(
          `axe below fail threshold: ${noted
            .map((violation) => `${violation.id} impact=${violation.impact ?? 'null'}`)
            .join('; ')}`,
        );
      }
      if (blocking.length > 0) {
        throw new Error(
          `axe violation: ${blocking
            .map((violation) => `${violation.id} impact=${violation.impact ?? 'unknown'}`)
            .join('; ')}`,
        );
      }
      console.log(`axe-serious-or-critical: none for ${route}`);
    });

    test('screenshots', async ({ page }, testInfo) => {
      const projectDir = join(screenshotDir, testInfo.project.name);
      await mkdir(projectDir, { recursive: true });
      const routeId = createHash('sha256').update(route).digest('hex');
      const slug = `${routeSlug(route)}-${routeId}`;
      const desktopPath = join(projectDir, `${slug}-desktop.png`);
      const mobilePath = join(projectDir, `${slug}-mobile.png`);
      await page.setViewportSize({ width: 1280, height: 720 });
      await openRoute(page, route);
      await page.screenshot({ path: desktopPath });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.screenshot({ path: mobilePath });
      console.log(`screenshots desktop=${desktopPath} mobile=${mobilePath}`);
    });
  });
}

// Opt-in consumer regressions use real browsers and the real CLI, with child
// runs isolated from the outer invocation's report and screenshot directory.
if (process.env.VERIFY_FIXTURES === '1' && process.env.VERIFY_HARNESS_REGRESSIONS === '1') {
  test.describe('harness regressions', () => {
    test('captures delayed console and page startup errors', async ({ page }) => {
      const opened = await openRoute(page, '/fail.html?delayed-page-error');
      expect(opened.consoleErrors).toEqual(['fixture-console-error: desk-verify-fail']);
      expect(opened.pageErrors).toEqual(['fixture-page-error: desk-verify-fail']);
    });

    for (const [mode, signal] of [
      ['verify', 'SIGINT'], ['verify', 'SIGTERM'], ['selftest', 'SIGTERM'], ['selftest:fail', 'SIGTERM'],
    ] as const) {
      test(`cancellation ${mode} ${signal} waits for browser and fixture cleanup`, async () => {
        test.skip(process.platform === 'win32', 'POSIX signal/process-group regression; Windows tree cleanup is not guaranteed');
        test.setTimeout(60_000);
        const sandbox = await mkdtemp(join(tmpdir(), 'web-verify-cancellation-'));
        const packageRoot = fileURLToPath(new URL('../', import.meta.url));
        let child: ChildProcess | undefined;
        let cliPid: number | undefined;
        let closed = false;
        try {
          for (const name of ['package.json', 'playwright.config.ts', 'scripts', 'fixtures']) {
            await cp(join(packageRoot, name), join(sandbox, name), { recursive: true });
          }
          await symlink(join(packageRoot, 'node_modules'), join(sandbox, 'node_modules'), 'dir');
          await mkdir(join(sandbox, 'tests'));
          // This is a real Playwright test, not a substitute CLI. Readiness is
          // emitted only after Chromium loads the actual managed fixture server.
          await writeFile(join(sandbox, 'tests/cancellation.spec.ts'), `
import { test } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import { writeFileSync } from 'node:fs';
test('cancellation target', async ({ page, browser }) => {
  await page.goto('/pass.html');
  const cdp = await browser.newBrowserCDPSession();
  const { processInfo } = await cdp.send('SystemInfo.getProcessInfo');
  const browserProcess = processInfo.find((entry) => entry.type === 'browser');
  if (!browserProcess) throw new Error('Chromium process identity unavailable');
  let writes = 0;
  writeFileSync('worker-writes.txt', String(writes));
  setInterval(() => writeFileSync('worker-writes.txt', String(++writes)), 50);
  await writeFile('ready.json', JSON.stringify({
    workerPid: process.pid, cliPid: process.ppid, browserPids: processInfo.map((entry) => entry.id),
  }));
  await page.waitForTimeout(25_000);
});
`);
          const portServer = createServer();
          await new Promise<void>((resolvePort) => portServer.listen(0, '127.0.0.1', resolvePort));
          const address = portServer.address();
          if (!address || typeof address === 'string') throw new Error('No fixture port allocated');
          const port = address.port;
          await new Promise<void>((resolvePort, reject) => portServer.close((error) => error ? reject(error) : resolvePort()));
          child = spawn(process.execPath, ['--experimental-strip-types', 'scripts/to-receipt.ts', mode], {
            cwd: sandbox, detached: true, stdio: ['ignore', 'pipe', 'pipe'],
            env: {
              ...process.env, VERIFY_FIXTURES: '1', VERIFY_HARNESS_REGRESSIONS: '0',
              VERIFY_BROWSERS: 'chromium', VERIFY_FIXTURE_PORT: String(port),
              BASE_URL: `http://127.0.0.1:${port}`,
            },
          });
          let output = '';
          child.stdout?.on('data', (chunk: Buffer) => { output = (output + chunk.toString()).slice(-8000); });
          child.stderr?.on('data', (chunk: Buffer) => { output = (output + chunk.toString()).slice(-8000); });
          let launchError: Error | undefined;
          const exited = new Promise<{ code: number | null; signal: NodeJS.Signals | null }>((resolveExit) => {
            child!.once('error', (error) => { launchError = error; });
            child!.once('close', (code, exitSignal) => {
              closed = true;
              resolveExit({ code, signal: exitSignal });
            });
          });
          await expect.poll(async () => {
            if (launchError) throw launchError;
            try { return await readFile(join(sandbox, 'ready.json'), 'utf8'); }
            catch (error) {
              if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
              if (closed) throw new Error(`Wrapper exited before Chromium readiness: ${output}`);
              return '';
            }
          }, { timeout: 20_000 }).not.toBe('');
          const ready = JSON.parse(await readFile(join(sandbox, 'ready.json'), 'utf8')) as {
            workerPid: number; cliPid: number; browserPids: number[];
          };
          cliPid = ready.cliPid;
          expect(child.kill(signal)).toBe(true); // Signal only the wrapper PID.
          await expect.poll(() => closed, { timeout: 20_000 }).toBe(true);
          const exit = await exited;
          expect(exit.signal, output).toBeNull();
          expect(exit.code, output).toBe(signal === 'SIGINT' ? 130 : 143);
          const receiptText = await readFile(join(sandbox, 'out/verify-result.json'), 'utf8');
          const receipt = JSON.parse(receiptText) as {
            run: { exit_code: number };
            commands: Array<{ exit_code: number; output_tail: string }>;
          };
          expect(receipt.run.exit_code, output).not.toBe(0);
          expect(receipt.commands.some((entry) =>
            entry.exit_code !== 0 && entry.output_tail.includes(`Canceled by ${signal}`),
          )).toBe(true);
          // Detached browsers and web servers are not covered by the CLI group:
          // assert Playwright's own teardown actually stopped them before close.
          for (const pid of [ready.cliPid, ready.workerPid, ...ready.browserPids]) {
            let alive = true;
            try {
              process.kill(pid, 0);
              if (process.platform === 'linux') {
                const stat = await readFile(`/proc/${pid}/stat`, 'utf8');
                alive = stat.slice(stat.lastIndexOf(')') + 2).split(' ')[0] !== 'Z';
              }
            } catch (error) {
              if (!['ESRCH', 'ENOENT'].includes((error as NodeJS.ErrnoException).code ?? '')) throw error;
              alive = false;
            }
            expect(alive, `Process ${pid} survived wrapper close: ${output}`).toBe(false);
          }
          const rebound = createServer();
          await new Promise<void>((resolvePort, reject) => {
            rebound.once('error', reject);
            rebound.listen(port, '127.0.0.1', resolvePort);
          });
          await new Promise<void>((resolvePort, reject) => rebound.close((error) => error ? reject(error) : resolvePort()));
          const workerWrites = await readFile(join(sandbox, 'worker-writes.txt'), 'utf8');
          await new Promise<void>((resolveWait) => setTimeout(resolveWait, 250));
          expect(await readFile(join(sandbox, 'worker-writes.txt'), 'utf8')).toBe(workerWrites);
          expect(await readFile(join(sandbox, 'out/verify-result.json'), 'utf8')).toBe(receiptText);
        } finally {
          // Also clean a pre-fix reproduction's orphaned CLI group on failure.
          for (const pid of [cliPid, child?.pid]) {
            if (!pid) continue;
            try { process.kill(-pid, 'SIGINT'); }
            catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error; }
          }
          if (child && !closed) {
            await new Promise<void>((resolveClose) => child!.once('close', () => resolveClose()));
          }
          await rm(sandbox, { recursive: true, force: true });
        }
      });
    }

    test('writes current failure evidence, checks negative failures, and replays unique screenshots', async () => {
      test.setTimeout(120_000);
      const sandbox = await mkdtemp(join(tmpdir(), 'web-verify-regression-'));
      const packageRoot = fileURLToPath(new URL('../', import.meta.url));
      try {
        for (const name of ['package.json', 'playwright.config.ts', 'scripts', 'tests', 'fixtures']) {
          await cp(join(packageRoot, name), join(sandbox, name), { recursive: true });
        }
        await symlink(join(packageRoot, 'node_modules'), join(sandbox, 'node_modules'), 'dir');
        const portServer = createServer();
        await new Promise<void>((resolvePort) => portServer.listen(0, '127.0.0.1', resolvePort));
        const address = portServer.address();
        if (!address || typeof address === 'string') throw new Error('No fixture port allocated');
        const port = String(address.port);
        await new Promise<void>((resolvePort, reject) => portServer.close((error) => error ? reject(error) : resolvePort()));
        const childEnv = {
          ...process.env,
          VERIFY_HARNESS_REGRESSIONS: '0',
          VERIFY_BROWSERS: 'chromium',
          VERIFY_FIXTURE_PORT: port,
          VERIFY_STARTUP_MS: '1000',
          BASE_URL: `http://127.0.0.1:${port}`,
        };
        interface Receipt {
          run: { exit_code: number };
          commands: Array<{ cmd: string; exit_code: number; output_tail: string }>;
        }
        async function invoke(mode: string, extraEnv: NodeJS.ProcessEnv = {}, args: string[] = []): Promise<{ exit: number; receipt: Receipt }> {
          const exit = await new Promise<number>((resolveExit, reject) => {
            const child = spawn(process.execPath, ['--experimental-strip-types', 'scripts/to-receipt.ts', mode, ...args], {
              cwd: sandbox, env: { ...childEnv, ...extraEnv }, stdio: 'ignore',
            });
            child.on('error', reject);
            child.on('close', (code) => resolveExit(code ?? 1));
          });
          const receipt = JSON.parse(await readFile(join(sandbox, 'out/verify-result.json'), 'utf8')) as Receipt;
          return { exit, receipt };
        }

        const green = await invoke('selftest');
        expect(green.exit).toBe(0);
        expect(green.receipt.commands.every((entry) => entry.exit_code === 0)).toBe(true);
        const configFailure = await invoke('selftest', { VERIFY_BROWSERS: 'unknown-browser' });
        expect(configFailure.exit).not.toBe(0);
        expect(configFailure.receipt.run.exit_code).not.toBe(0);
        expect(configFailure.receipt.commands.every((entry) => entry.exit_code !== 0)).toBe(true);
        const launchFailure = await invoke('selftest', { PLAYWRIGHT_BROWSERS_PATH: join(sandbox, 'no-browsers') }, ['--grep', 'http-status']);
        expect(launchFailure.exit).not.toBe(0);
        expect(launchFailure.receipt.commands.every((entry) => entry.exit_code !== 0)).toBe(true);
        const negative = await invoke('selftest:fail');
        expect(negative.exit).toBe(0);
        expect(negative.receipt.run.exit_code).toBe(1);
        expect(negative.receipt.commands.filter((entry) => entry.exit_code !== 0)).toHaveLength(3);
        const failureFiles = await readdir(join(sandbox, 'out/test-results'), { recursive: true });
        expect(failureFiles.some((name) => name.endsWith('trace.zip'))).toBe(true);
        const failureThenConfigError = await invoke('selftest', { VERIFY_BROWSERS: 'unknown-browser' });
        expect(failureThenConfigError.exit).toBe(1);
        await expect(readdir(join(sandbox, 'out/test-results'))).rejects.toMatchObject({ code: 'ENOENT' });
        const fixturePath = join(sandbox, 'fixtures/fail.html');
        const fixture = await readFile(fixturePath, 'utf8');
        await writeFile(fixturePath, fixture.replace('console.error(', 'console.info('));
        const missingConsoleFailure = await invoke('selftest:fail');
        expect(missingConsoleFailure.exit).toBe(1);
        expect(missingConsoleFailure.receipt.run.exit_code).toBe(1);
        await writeFile(fixturePath, fixture);

        const routes = ["/pass.html?a='b", '/pass.html?a=/b'];
        const screenshots = await invoke('verify', { VERIFY_FIXTURES: '1', ROUTES: routes.join(',') }, ['--grep', 'screenshots']);
        expect(screenshots.exit).toBe(0);
        const files = await readdir(join(sandbox, 'out/screenshots/chromium'));
        expect(files).toHaveLength(4);
        for (const route of routes) {
          const id = createHash('sha256').update(route).digest('hex');
          expect(files).toContain(`pass.html_a_b-${id}-desktop.png`);
          expect(files).toContain(`pass.html_a_b-${id}-mobile.png`);
        }
        const command = screenshots.receipt.commands[1].cmd;
        const replayExit = await new Promise<number>((resolveExit, reject) => {
          const child = spawn('/bin/sh', ['-c', command], { cwd: sandbox, env: childEnv, stdio: 'ignore' });
          child.on('error', reject);
          child.on('close', (code) => resolveExit(code ?? 1));
        });
        expect(replayExit).toBe(0);
        expect(await readdir(join(sandbox, 'out/screenshots/chromium'))).toHaveLength(2);
      } finally {
        await rm(sandbox, { recursive: true, force: true });
      }
    });
  });
}
