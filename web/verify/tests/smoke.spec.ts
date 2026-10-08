import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { test, type Page, type Response } from '@playwright/test';
import { AxeBuilder } from '@axe-core/playwright';

const screenshotDir = fileURLToPath(new URL('../out/screenshots/', import.meta.url));

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
  const slug = route.replace(/^\/+/, '').replace(/[^A-Za-z0-9._-]+/g, '_');
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

    test('screenshots', async ({ page }) => {
      await mkdir(screenshotDir, { recursive: true });
      const slug = routeSlug(route);
      const desktopPath = `${screenshotDir}${slug}-desktop.png`;
      const mobilePath = `${screenshotDir}${slug}-mobile.png`;
      await page.setViewportSize({ width: 1280, height: 720 });
      await openRoute(page, route);
      await page.screenshot({ path: desktopPath });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.screenshot({ path: mobilePath });
      console.log(`screenshots desktop=${desktopPath} mobile=${mobilePath}`);
    });
  });
}
