import { pathToFileURL } from 'node:url';
import { _electron as electron, type ElectronApplication, type Page } from 'playwright';

/**
 * Template for an Electron app. Playwright marks _electron.launch experimental.
 * Type-checked here and not executed: programming-desk has no Electron app.
 *
 *   ELECTRON_APP_PATH=/path/to/app \
 *   ELECTRON_EXECUTABLE=/path/to/electron \
 *   node --experimental-strip-types web/verify/desktop/electron.smoke.ts
 *
 * ELECTRON_EXECUTABLE is optional when the app can be launched from args alone.
 */

export interface ElectronSmokeOptions {
  appPath: string;
  screenshotPath: string;
  executablePath?: string;
}

export async function smokeElectron(options: ElectronSmokeOptions): Promise<{ title: string }> {
  const app: ElectronApplication = await electron.launch({
    args: [options.appPath],
    ...(options.executablePath ? { executablePath: options.executablePath } : {}),
  });
  try {
    const window: Page = await app.firstWindow();
    const title = await window.title();
    if (title.length === 0) {
      throw new Error('electron window title is empty');
    }
    await window.screenshot({ path: options.screenshotPath });
    return { title };
  } finally {
    await app.close();
  }
}

function isDirectRun(): boolean {
  const entry = process.argv[1];
  if (!entry) return false;
  return import.meta.url === pathToFileURL(entry).href;
}

if (isDirectRun()) {
  const appPath = process.env.ELECTRON_APP_PATH;
  if (!appPath) {
    process.stderr.write('ELECTRON_APP_PATH is required to run the Electron template\n');
    process.exit(1);
  }
  const executablePath = process.env.ELECTRON_EXECUTABLE;
  smokeElectron({
    appPath,
    screenshotPath: 'out/electron-desktop.png',
    ...(executablePath ? { executablePath } : {}),
  }).then(
    (result) => {
      process.stdout.write(`electron title: ${result.title}\n`);
    },
    (err: unknown) => {
      const message = err instanceof Error ? err.message : String(err);
      process.stderr.write(`${message}\n`);
      process.exit(1);
    },
  );
}
