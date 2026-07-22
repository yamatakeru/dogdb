# Cloudflare deployment spike

This subproject checks whether Dolly's First Shift can run within the
Cloudflare Workers Free limits without changing DogDB's published runtime
dependencies.

The build copies the shared tutorial scenario and DogDB source into ignored
Wrangler build directories. The local Flask tutorial remains the reference
development entrypoint.

## Local runtime

```console
npm install
npm run dev
```

Run the command from this directory. Static requests are served by Workers
Static Assets; only `/api/acts/<act>` falls through to the Python Worker.
Run `npm install` once before the first invocation to install the pinned
Wrangler version. The npm scripts synchronize Python dependencies before they
copy DogDB and the shared tutorial sources into the deployment bundle.

## Deployment checks

```console
npm run deploy:dry-run
npm run deploy
```

The spike passes only when the compressed Worker is below 3 MB, all three acts
match the CPython behavior, static assets bypass Worker execution, and deployed
invocations stay comfortably below the Free plan's 10 ms CPU limit.

## Result

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
validation during this spike, so the subproject pins 4.112.0. Its Miniflare
dependency includes the reported Sharp advisories; the affected image-processing
path is not used by this deployment, but the pin should be revisited before this
spike becomes maintained production configuration.

The live Python Worker is therefore technically viable on Workers Paid, but it
should not become the README's primary hosted demo while zero-cost operation is
a requirement. A static build-generated trace would be the next zero-cost
option; it was not implemented by this spike.
