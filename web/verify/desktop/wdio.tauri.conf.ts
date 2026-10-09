import type { Options } from '@wdio/types';

/**
 * Template for a Tauri v2 debug build. Type-checked here and not executed:
 * programming-desk has no Tauri application.
 *
 * The embedded provider (default) needs tauri-plugin-wdio-webdriver in the app
 * and works on Windows, Linux, and macOS. tauri-plugin-wdio adds
 * browser.tauri.execute(), IPC mocking, and log capture. Plain tauri-driver
 * (driverProvider: 'external') works on Windows and Linux only.
 *
 * Product install, exact versions aligned with @wdio/tauri-service 1.5.0
 * (peer webdriverio ^9) and this package's @wdio/types pin:
 *
 *   @wdio/cli@9.31.9
 *   @wdio/local-runner@9.31.9
 *   @wdio/mocha-framework@9.31.9
 *   @wdio/spec-reporter@9.31.2
 *   @wdio/tauri-service@1.5.0
 *   webdriverio@9.31.9
 *
 *   TAURI_APP_BINARY=./src-tauri/target/debug/<name> \
 *   TAURI_WDIO_SPEC=./test/specs/tauri.smoke.ts \
 *   npx wdio web/verify/desktop/wdio.tauri.conf.ts
 */
const appBinaryPath = process.env.TAURI_APP_BINARY ?? './src-tauri/target/debug/app';
const spec = process.env.TAURI_WDIO_SPEC ?? './test/specs/tauri.smoke.ts';

export const config: Options.Testrunner = {
  runner: 'local',
  specs: [spec],
  maxInstances: 1,
  services: [
    [
      'tauri',
      {
        appBinaryPath,
        driverProvider: 'embedded',
      },
    ],
  ],
  framework: 'mocha',
  reporters: ['spec'],
  mochaOpts: {
    timeout: 60_000,
  },
};
