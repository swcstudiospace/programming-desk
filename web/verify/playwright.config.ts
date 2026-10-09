import { defineConfig, devices } from '@playwright/test';

function requireBaseURL(): string {
  const baseURL = process.env.BASE_URL;
  if (!baseURL) {
    throw new Error('BASE_URL is required');
  }
  let parsed: URL;
  try {
    parsed = new URL(baseURL);
  } catch {
    throw new Error('BASE_URL must be an absolute http(s) URL');
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error('BASE_URL must use http or https');
  }
  if (parsed.username !== '' || parsed.password !== '') {
    throw new Error('BASE_URL must not include credentials');
  }
  return baseURL;
}

const catalog = {
  chromium: { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  firefox: { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  webkit: { name: 'webkit', use: { ...devices['Desktop Safari'] } },
};

type BrowserName = keyof typeof catalog;

function browsers(): BrowserName[] {
  const requested = (process.env.VERIFY_BROWSERS ?? 'chromium')
    .split(',')
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
  if (requested.length === 0) {
    throw new Error('VERIFY_BROWSERS is empty');
  }
  const unknown = requested.filter((name) => !(name in catalog));
  if (unknown.length > 0) {
    throw new Error(
      `VERIFY_BROWSERS has unknown browser(s): ${unknown.join(', ')} (use chromium, firefox, webkit)`,
    );
  }
  return requested as BrowserName[];
}

function fixturePort(): string {
  const raw = process.env.VERIFY_FIXTURE_PORT ?? '4173';
  if (!/^[0-9]+$/.test(raw)) {
    throw new Error('VERIFY_FIXTURE_PORT must be an integer');
  }
  const port = Number(raw);
  if (port < 1 || port > 65535) {
    throw new Error('VERIFY_FIXTURE_PORT is out of range');
  }
  return String(port);
}

const baseURL = requireBaseURL();
const port = fixturePort();

export default defineConfig({
  testDir: './tests',
  outputDir: './out/test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 30_000,
  reporter: [
    ['list'],
    ['json', { outputFile: 'out/playwright-report.json' }],
  ],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: browsers().map((name) => catalog[name]),
  ...(process.env.VERIFY_FIXTURES === '1'
    ? {
        webServer: {
          command: 'node --experimental-strip-types scripts/serve-fixtures.ts',
          url: `http://127.0.0.1:${port}/health`,
          reuseExistingServer: false,
          timeout: 30_000,
        },
      }
    : {}),
});
