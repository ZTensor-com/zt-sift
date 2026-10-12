# Fix validation — 12 October 2026

Baseline commit: `bd43970`. Fixes are a separate commit. No AWS deployment was performed. Provisioned concurrency remains zero; no paid warm-up was added; memory and models are unchanged.

## Verified outcomes

| Fixture group | Expected | Exact before | Exact after | Full coverage after |
|---|---:|---:|---:|---:|
| sample | 50 | 50 | 50 | 50 |
| canonical | 48 | 48 | 48 | 48 |
| stock | 10 | 10 | 10 | 10 |
| variant | 37 | 7 | 33 | 34 |

All 128 fixture requests returned their expected status under the updated contract, and returned spans round-trip to original input text. An empty explicit entities filter now deliberately returns 400. Original audit artifacts are unchanged.

36 unit/regression tests pass locally and in the Linux x86_64/Python 3.12 Lambda image as UID1051 with networking disabled. CloudFormation lint and compile checks pass. A Node harness verified Unicode code-point indexing and union highlighting of overlapping intervals. The local container image was built from cached wheels, with no AWS calls.

## Local warm timing comparison

| Input | Baseline median | Fixed median | Speedup |
|---|---:|---:|---:|
| user_sample | 260.5 ms | 73.0 ms | 3.6x |
| 20k_dense | 2266.7 ms | 597.0 ms | 3.8x |
| 20k_numeric | 3803.8 ms | 298.1 ms | 12.8x |

Five sequential calls per workload on local hardware. These are descriptive timings, not a deployed latency guarantee or a load test.

## Implemented behavior

- Complete and truncated PEM bodies, long tokens, short/quoted/escaped passwords, login pairs and log assignments. Ordinary password/authentication prose is excluded.
- Source-aware JSON keys and values, camelCase log assignments, original Unicode offsets, address components and plausible explicitly labeled phone values.
- US-default phone scanning, configurable national regions and validated worldwide +country-code numbers; unused spaCy parser disabled.
- Better numeric salaries, spaced bank accounts, identifiers, newborn ages, newer UUID versions and bounded GPS coordinates.
- Containment/partial overlap preserve sensitive coverage; real organization acronyms remain; conversational dates retain birth/medical context.
- Malformed base64 and empty filters return 400; optional custom metrics remain disabled. Existing server-error alarm threshold is now 1.

## Remaining limitations and policy

- Hindi names and complete Indian addresses need additional locale/language support. English spaCy remains heuristic.
- Unquoted trailing password punctuation is kept for coverage rather than guessed away; quote the intended value for an exact boundary.
- Social-handle syntax remains platform-dependent; the hyphenated handle fixture is only partially detected.
- Explicitly labeled malformed IDs/dates may still be reported for privacy coverage. This is not a certificate of identifier validity.
- CLI documents use 512-character chunk overlap; longer entities crossing those boundaries can remain partial. API requests are bounded to 20 KB.
- Consumers should mask the union of intervals; collapse can retain extending overlapping classifications.
- graphify-out preserves the pre-fix code graph; refresh it before relying on changed source locations.

## Rollback

Use `git log --oneline` to find the fix commit and `git revert <fix-commit>` to undo it without rewriting history. The baseline is retained as `bd43970`. These commits are local; reverting code does not change the running AWS deployment.
