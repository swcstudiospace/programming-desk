# web/verify

Smoke harness for a web URL. Playwright drives `BASE_URL`, axe flags serious and critical violations, and the run writes receipt-shaped JSON plus screenshots. Tauri and Electron files in `desktop/` are type-checked templates. This repository has no desktop app, so those templates are not executed here.

`desk_preview_check` on the Web seat roster finds a preview URL. This harness does not call it. Pass the URL in as `BASE_URL`.

## Install

Node **22.6.0 or newer** is required: 22.6.0 introduced the `--experimental-strip-types` flag used by the Node scripts. From `web/verify`:

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

The harness observes each page for `VERIFY_STARTUP_MS` milliseconds **after the document's load event** (default `1000`, integer range `0`–`10000`). Console and uncaught page errors during that bounded startup interval fail their respective checks. This is not continuous monitoring: later errors are outside the check. Use a larger interval for applications with slower startup, or `0` to observe only navigation/load events. Axe and screenshots run after the same interval.

```bash
VERIFY_STARTUP_MS=2000 BASE_URL=http://127.0.0.1:3000 ROUTES=/ npm run verify
```

## Output

`out/` (this package does not ship a `.gitignore`; see below):

- `out/verify-result.json` — `{ "run": { "exit_code", "duration_s" }, "commands": [ { "cmd", "exit_code", "duration_s", "output_tail" } ] }`. The first command records the actual Playwright invocation and its exit code; subsequent entries record individual checks. Report-generation/read failures add a nonzero evidence entry.
- `out/screenshots/<project>/<route-slug>-<sha256-of-exact-route>-desktop.png` and `...-mobile.png`. Project directories separate browsers; full route hashes separate paths/query strings with the same readable slug. Names are stable across runs.
- `out/test-results/` — Playwright trace retained on failure
- `out/playwright-report.json` — raw JSON reporter file

Do not commit `node_modules/` or `out/`.

All three run scripts launch Playwright and convert its **current** report even when Playwright fails. They remove the old raw report, result, screenshots, and `out/test-results/` traces before launch; configuration or browser-launch failures cannot reuse previous results or failure artifacts. `run.exit_code` is the actual Playwright exit code (or `1` if it closed without an exit code), including on a negative self-check. Normal `verify` and `selftest` exit nonzero for a failed invocation, failed/missing check, or unusable report. Retries remain disabled.

Run from this package directory. Do not run concurrent invocations against the shared `out/` directory. Invoke `npm run verify`, not `npx playwright test && ...`: the latter bypasses cleanup/evidence generation. Additional Playwright test options may be passed after `--`; overriding the JSON reporter leaves no usable report and therefore fails verification. There is no standalone converter mode, because an old report cannot establish its invocation.

### Cancellation

Signal the native wrapper PID (`node --experimental-strip-types scripts/to-receipt.ts ...`), rather than relying on `npm` to forward signals. On POSIX, the wrapper starts the native Playwright CLI and workers in a separate process group. The first `SIGINT` or `SIGTERM` requests cancellation by forwarding **SIGINT** to that group: this Playwright version's test runner implements graceful cancellation through SIGINT, not SIGTERM. The runner owns the separately grouped Chromium and managed fixture-server processes; its teardown closes those resources. Sending SIGTERM directly to the CLI instead would bypass the runner's awaited teardown.

The wrapper waits for the CLI's `close` event (including closed output pipes), unregisters signal handlers on child error/close, then writes the current evidence. A canceled run adds a nonzero `Canceled by SIGINT`/`SIGTERM` command entry, preserves the actual child exit code, and exits `130`/`143` respectively, even if the report contains passing checks or the mode is `selftest:fail`. Repeated cancellation requests do not interrupt teardown. No wrapper-side timeout or forced-kill escalation is implemented: a stuck Playwright teardown can keep the wrapper waiting. `SIGKILL`, a wrapper crash, or signaling unrelated/externally managed processes is outside this graceful-cleanup guarantee; the harness does not stop a server you started yourself.

Windows has no equivalent POSIX process-group signaling here. The wrapper forwards SIGINT to the child PID and still waits for close/non-passing evidence, but Node may terminate that child rather than perform graceful SIGINT delivery. Windows descendant browser/server cleanup is **not guaranteed and has not been tested**; the cancellation regressions skip Windows. Use a POSIX runner for the process-group cancellation path covered by these regressions.

Each `commands[].cmd` is shell-replayable from this directory. It preserves route, browser/project, fixture port, startup interval, and check selection, and safely quotes shell arguments. The original `BASE_URL` is deliberately **not** written into the command: export it when replaying. Use only credential-free routes and URLs; do not put tokens in query strings or CLI arguments.

For example, after a self-test on port 4199, replay the first individual check (replaying replaces `out/` with that narrower run):

```bash
export BASE_URL=http://127.0.0.1:4199
command=$(node -p 'require("./out/verify-result.json").commands[1].cmd')
sh -c "$command"
```

## Self-test (local fixtures only)

The self-test scripts set their own loopback `BASE_URL` and fixed fixture route; caller-supplied `BASE_URL` and `ROUTES` are ignored. `VERIFY_FIXTURE_PORT` sets both the server port and target URL (default `4173`). Do not point self-tests at a preview or production host. Example URLs elsewhere in this file have no credentials.

```bash
npm run selftest:fail   # exits 0 ONLY when the expected negative failures are observed
npm run selftest        # exits 0 against fixtures/pass.html
VERIFY_FIXTURE_PORT=4199 npm run selftest
VERIFY_FIXTURE_PORT=4199 npm run selftest:fail
```

`selftest:fail` is a harness self-check, not a normal failing verification. It requires exactly five checks in every selected browser: `console-error` must fail with exactly `fixture-console-error: desk-verify-fail`, axe must fail with exactly `image-alt impact=critical`, and HTTP status, page errors, and screenshots must pass. Missing checks, missing expected errors, additional violations, launch/configuration failures, or any unexpected failure make the self-check exit `1`. Its evidence still records the failing Playwright exit (`1`) and the failed checks; exit `0` means the detector worked, not that the fixture passed.

`fixtures/fail.html` logs its console error 100 ms after startup and includes an image with no text alternative. Add `?delayed-page-error` to also throw an uncaught exception after 150 ms. `fixtures/pass.html` has a title, a language, and a named button.

Fresh failure evidence and delayed error capture can be checked with:

```bash
npm run selftest
# Expected exit 1: previous green evidence is replaced by console, page, and axe failures.
VERIFY_FIXTURES=1 VERIFY_FIXTURE_PORT=4199 \
BASE_URL=http://127.0.0.1:4199 ROUTES='/fail.html?delayed-page-error' \
VERIFY_STARTUP_MS=1000 npm run verify
# Expected exit 1 with fresh invocation-failure evidence, not the preceding report.
VERIFY_BROWSERS=unknown-browser npm run selftest
```

The optional behavioral regression suite exercises real delayed errors and isolated child CLI runs: a passing run followed by configuration/browser-launch failures, exact negative self-checks, a missing console error, colliding route screenshot paths, shell replay with a quoted route, and POSIX SIGINT/SIGTERM cancellation in normal and self-check modes. It uses installed Chromium; child outputs are isolated in a temporary directory, removed afterward:

```bash
VERIFY_HARNESS_REGRESSIONS=1 npm run selftest
```

Run only the cancellation reproductions (installed Chromium and Node 22.6+ required; choose an unused outer fixture port):

```bash
VERIFY_FIXTURES=1 VERIFY_HARNESS_REGRESSIONS=1 VERIFY_BROWSERS=chromium \
VERIFY_FIXTURE_PORT=4199 BASE_URL=http://127.0.0.1:4199 \
node --experimental-strip-types scripts/to-receipt.ts verify \
  --grep 'harness regressions cancellation'
```

The tests launch the real native wrapper/Playwright CLI in isolated package copies, wait until a real Chromium page loads the managed fixture server and starts a repeating worker file write, record the CLI/worker/browser PIDs, and signal **only** the wrapper PID. With the old wrapper, SIGTERM exits it immediately while the child keeps running; the same regression fails on wrapper signal exit/missing cancellation evidence. With the fix, each canceled child must exit `130`/`143` without a terminating signal, produce non-passing evidence, leave no running recorded CLI/worker/browser process, immediately release the fixture port for rebinding, and leave both the worker-write counter and result JSON unchanged after close. The outer regression command exits `0` only if those assertions pass; its passing report is evidence about cancellation handling, not a passing canceled child verification. Cleanup in the tests also signals the isolated groups if an assertion fails.

After installing Firefox, confirm separate project and route destinations with:

```bash
VERIFY_FIXTURES=1 VERIFY_FIXTURE_PORT=4199 \
BASE_URL=http://127.0.0.1:4199 VERIFY_BROWSERS=chromium,firefox \
ROUTES='/pass.html?a=b,/pass.html?a/b' npm run verify -- --grep screenshots
```

Both routes have the readable slug `pass.html_a_b`. Expect eight images: two route hashes × desktop/mobile × two project directories. An ensuing run clears the old screenshots.

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

Optional browsers (Chromium is the default; install each browser before running it, including for self-tests):

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

`desktop/electron.smoke.ts` calls Playwright's experimental `_electron.launch`. Copy the template into the **product repo** and install its exact imported dependency there; this harness's `node_modules/` is not used by a copied template. The product must also already provide its Electron app/runtime:

```bash
npm install --save-dev --save-exact playwright@1.64.0

# From the product repo, with its Electron main script or app directory:
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
