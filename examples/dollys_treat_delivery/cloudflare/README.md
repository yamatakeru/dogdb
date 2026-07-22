# Cloudflare static deployment

This subproject deploys Dolly's First Shift as Cloudflare Workers Static
Assets. It does not run a Worker or consume Worker CPU for tutorial requests.

The build runs the shared tutorial scenario with the real DogDB and in-memory
SQLite, then writes each deterministic result to `dist/api/acts/<act>.json`.
The hosted UI replays those build-generated traces. The local Flask tutorial
uses the same scenario, response shape, and frontend, but executes DogDB again
for every act request.

## Local runtime

```console
npm install
npm run dev
```

Run the command from this directory. `npm run build` uses the repository's uv
environment to generate the traces before Wrangler serves the resulting static
site. Run `npm install` once before the first invocation to install the pinned
Wrangler version.

## Deployment checks

```console
npm run deploy:dry-run
npm run deploy
```

The deployment is ready when all three generated traces match `run_act()`, the
static site builds without a Worker entrypoint, and the browser completes all
three acts.

## Why this is static

Measured on 2026-07-22 with `workers-py==1.15.0`, Wrangler 4.112.0, and the
Cloudflare NRT location:

| Check | Result |
|---|---|
| Pyodide dependency resolution | PASS |
| Compressed Worker size | PASS: 651.58 KiB |
| Existing test suite | PASS: 306 tests |
| CPython parity | PASS: 3 serial and 60 concurrent local requests |
| Deployed three-act browser flow | PASS |
| Static assets bypass Worker execution | PASS |
| Worker startup report | WARN: 1,584-2,615 ms; deployments were accepted |
| Free plan CPU budget | FAIL: median 13 ms, p95 85 ms, max 111 ms |
| Wrangler dependency audit | WARN: 3 high findings in the dev-only Sharp chain |

The deployed API returned all expected results, including 20 concurrent remote
requests, but 36 of 57 observed invocations exceeded the Free plan's 10 ms CPU
budget. Cloudflare permits occasional overruns, so successful responses do not
make this workload reliably Free-plan compatible.

Wrangler 4.113.0 shipped a `workerd` binary that failed local macOS signature
validation during the live-Worker evaluation, so the subproject pins 4.112.0. Its Miniflare
dependency includes the reported Sharp advisories; the affected image-processing
path is not used by this deployment, but the pin and advisories should be
revisited during the next Wrangler upgrade.

The live Python Worker is technically viable on Workers Paid, but it is not
reliably compatible with the Free plan's CPU budget. Static Assets preserve the
tutorial's visible behavior and generate every displayed result with the real
DogDB implementation while moving that execution to deployment time.
