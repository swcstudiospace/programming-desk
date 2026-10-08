# web/verify

Smoke harness for a web URL. Playwright drives `BASE_URL`, axe flags serious and critical violations, and the run writes receipt-shaped JSON plus screenshots. Tauri and Electron files in `desktop/` are type-checked templates. This repository has no desktop app, so those templates are not executed here.

`desk_preview_check` on the Web seat roster finds a preview URL. This harness does not call it. Pass the URL in as `BASE_URL`.

## Install

Node 22. From `web/verify`:

```bash
npm ci
npx playwright install --with-deps chromium
```

Direct dependencies are exact versions in `package.json`. `package-lock.json` pins the tree. The browser download is Playwright's install, run by the command above (`npm ci` also runs Playwright's package postinstall). No other install script is part of this package.

WebKit and Firefox are optional. Install them before setting `VERIFY_BROWSERS`:

```bash
npx playwright install firefox webkit
```

## What a run checks

Each check is its own Playwright test. A failure does not hide the others.

| Check | Fails when |
|---|---|
| `http-status` | The document response is missing, or the status is 400 or above |
| `console-error` | Any console message of type `error` |
| `page-error` | Any uncaught page exception |
| `axe-serious-or-critical` | Any axe violation whose impact is `serious` or `critical` |
| `screenshots` | A desktop (1280×720) or mobile (390×844) screenshot cannot be written |

Moderate and minor axe violations are logged and do not fail the run.

## Output

`out/` (this package does not ship a `.gitignore`; see below):

- `out/verify-result.json` — `{ "commands": [ { "cmd", "exit_code", "duration_s", "output_tail" } ] }`, one entry per check
- `out/screenshots/<route>-desktop.png` and `<route>-mobile.png`
- `out/test-results/` — Playwright trace retained on failure
- `out/playwright-report.json` — raw JSON reporter file

Do not commit `node_modules/` or `out/`.

## Self-test (local fixtures only)

The self-test scripts are fixed to `http://127.0.0.1:4173` and the pages under `fixtures/`. They do not take a URL. Do not point them at a preview or a production host. Example URLs elsewhere in this file have no credentials.

```bash
npm run selftest:fail   # exits non-zero; names the console error and the axe violation
npm run selftest        # exits 0 against fixtures/pass.html
```

`fixtures/fail.html` logs `fixture-console-error: desk-verify-fail` and includes an image with no text alternative (`image-alt`, critical). `fixtures/pass.html` has a title, a language, and a named button.

## A local dev server

Start the server yourself, then:

```bash
BASE_URL=http://127.0.0.1:3000 ROUTES=/ npm run verify
```

`ROUTES` is a comma-separated list of paths. The default is `/`. A path that starts with `/` is resolved from the origin of `BASE_URL` (URL standard). Leave `VERIFY_FIXTURES` unset so the fixture server does not start.

Several routes:

```bash
BASE_URL=http://127.0.0.1:3000 ROUTES=/,/settings npm run verify
```

## A preview URL

```bash
BASE_URL=https://preview.example.com ROUTES=/,/settings npm run verify
```

`BASE_URL` must be an absolute `http` or `https` URL with no username or password. Do not put a token in the query string.

Optional browsers (Chromium is the default, and the only browser the self-test installs):

```bash
VERIFY_BROWSERS=chromium,firefox,webkit BASE_URL=http://127.0.0.1:3000 ROUTES=/ npm run verify
```

## Tauri debug build

`desktop/wdio.tauri.conf.ts` is a WebdriverIO config for `@wdio/tauri-service` (`driverProvider: embedded`). Copy it into the product repo or point `wdio` at it. Install these exact packages in that app (this harness pins `@wdio/types@9.31.2` only, so `tsc --noEmit` can see the config; it does not install the runner):

```bash
npm install --save-dev --save-exact \
  @wdio/cli@9.31.9 \
  @wdio/local-runner@9.31.9 \
  @wdio/mocha-framework@9.31.9 \
  @wdio/spec-reporter@9.31.2 \
  @wdio/tauri-service@1.5.0 \
  webdriverio@9.31.9
```

The app needs `tauri-plugin-wdio-webdriver` for the embedded provider, and `tauri-plugin-wdio` for `browser.tauri.execute()`, IPC mocking, and log capture. Build a debug binary, then:

```bash
TAURI_APP_BINARY=./src-tauri/target/debug/<name> \
TAURI_WDIO_SPEC=./test/specs/tauri.smoke.ts \
npx wdio desktop/wdio.tauri.conf.ts
```

`driverProvider: external` uses plain `tauri-driver`, which covers Windows and Linux. The embedded provider is the one that also covers macOS. This template does not use a paid driver service.

## Electron app

`desktop/electron.smoke.ts` calls Playwright's experimental `_electron.launch`. From a product repo, with the Electron main script or app directory:

```bash
ELECTRON_APP_PATH=/path/to/app \
node --experimental-strip-types desktop/electron.smoke.ts
```

Set `ELECTRON_EXECUTABLE` when launch needs a specific Electron binary. The script writes `out/electron-desktop.png` and exits non-zero when the window title is empty or `ELECTRON_APP_PATH` is unset.

## Typecheck

```bash
npx tsc --noEmit
```

That covers the smoke spec, both scripts, the Playwright config, and both desktop templates.

## Ignore file

`ownership.yaml` gives every file named `.gitignore` to `bot-06-quality-security` (a slash-less pattern matches the basename at any depth, and that rule comes after `web/**`). This package therefore has no `.gitignore`. `node_modules/` and `out/` are local output. Quality owns the root ignore file if those paths should be ignored for the whole repository.
