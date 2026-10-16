# Security scan report

Date: 2026-10-16

## Executive summary

The read-only scan found **one High vulnerability**, **one Medium authentication design gap**, and **two Low issues in the local development tester**. No Critical findings were identified. The High finding is a reproducible regex denial of service in the production detector, triggered by a 306-character input.

The scan covered 17 tracked files, local development tools, selected tests, and Python dependency pins. No deployed AWS resources or live endpoints were accessed. No application code was changed.

## Critical

None identified within the scope of this scan.

## High

### SEC-001 — Crafted whitespace causes excessive regex backtracking

**Locations:** `pii_detector/recognizers.py:69`, `pii_detector/recognizers.py:85`, `pii_detector/recognizers.py:96`; phone recognizer registration at `pii_detector/recognizers.py:452`.

`LabeledValueRecognizer.SEPARATOR` combines multiple unbounded `\s*` expressions separated by optional delimiters. A supported label followed by spaces and an invalid value causes Python's regular-expression engine to explore many equivalent whitespace partitions before failing. `analyze()` runs this expression without a time limit.

**Evidence from bounded local reproductions:**

- The isolated phone recognizer took approximately 0.403 seconds for `"phone" + " " * 100 + "!"`.
- Inputs with 300 and 1,000 spaces each exceeded an 8-second subprocess deadline and were terminated.
- After model initialization, the full `handler.handler()` path with default detection and 300 spaces exceeded an audit-imposed 3-second signal deadline. The injected timeout was caught by the handler, returning a generic 500 after 3.008 seconds. This deadline was part of the audit harness; production has no equivalent 3-second cancellation. The default Lambda timeout is 60 seconds.

**Impact and preconditions:** An API-key holder, or an attacker with the shared key, can consume Lambda execution time and concurrency with small requests, degrading availability and increasing cost. The payload is well below the 20,000-byte production body limit. The local tester calls the same detector synchronously and can also have its event loop blocked.

**Recommended fix:** Replace the ambiguous separator with deterministic parsing or a regex that consumes each whitespace region once. Bound the distance between label and value where supported formats permit. Consider timeout-capable matching as additional protection, ensuring it applies to custom recognizers. Add adversarial whitespace regression tests that use an external process deadline so a regression cannot hang the suite.

## Medium

### SEC-002 — Public API relies solely on a shared API Gateway key

**Locations:** `template.yaml:107`, `template.yaml:108`, `template.yaml:138` through `template.yaml:149`.

The REST method sets `AuthorizationType: NONE` and `ApiKeyRequired: true`. One generated key is attached to the usage plan. The supplied template has no IAM, Cognito, or Lambda authorizer.

**Impact and preconditions:** Anyone holding the shared key can invoke the detector and consume the shared quota. There is no caller identity or per-client authorization. Compromise of a client's key gives the same access as other key holders and increases exposure to SEC-001. AWS recommends using an authorization mechanism in addition to API keys; usage-plan quotas and throttles are best effort. See [AWS API Gateway usage-plan guidance](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html).

**Caveat:** The shared-key design is documented. The API analyzes caller-submitted data; no stored customer-record retrieval was found. This is an authentication design gap, not an API-key bypass or demonstrated cross-customer PII disclosure.

**Recommended fix:** Use IAM authorization for service clients or a suitable authorizer for application users. Retain API keys for metering if useful, and separate and rotate client credentials.

## Low

### SEC-003 — Local tester accepts arbitrary Host/Origin and non-JSON content types

**Locations:** `tools/web.py:119` through `tools/web.py:130`, `tools/web.py:142`.

The loopback tester has no allowed-host or origin validation. `request.json()` also parses JSON submitted as `text/plain`.

**Evidence:** An in-process ASGI request to `/detect` using `Host: attacker.example`, `Origin: http://attacker.example`, and `Content-Type: text/plain` returned 200. Detection was replaced with an empty-result stub to isolate request validation.

**Impact and preconditions:** A browser able to reach the local service may trigger computation through a cross-origin simple request, even when it cannot read the response. DNS rebinding may permit additional access in susceptible browser/environments. This can expose the tester to SEC-001.

**Caveat:** This tool is gitignored, local-only, and excluded from the Lambda image. No complete browser or DNS-rebinding exploit was performed. No stored PII retrieval was found.

**Recommended fix:** Allow only intended loopback hostnames, validate browser origins, require the intended JSON content type, and consider a local session token.

### SEC-004 — Local tester reads the full body before enforcing its limit

**Locations:** `tools/web.py:121`, `tools/web.py:127` through `tools/web.py:130`.

The tester calls `await request.json()` before checking the text field size. Large JSON bodies and unused fields are received and decoded before rejection. Its 3,000,000-character text limit also permits more detector work than the production API. Synchronous detection blocks its async event loop.

**Evidence:** A synthetic request with 3,000,001 text characters was fully read by the request receiver before the tester returned 413. No memory-exhaustion test was performed.

**Impact and preconditions:** A process or browser request able to reach the tester can consume memory and monopolize its single-worker event loop.

**Recommended fix:** Enforce a byte limit while streaming the body, before JSON decoding. Limit relevant fields and request concurrency, and isolate expensive detection from the ASGI event loop.

## Validation and positive controls

- Reviewed handler parsing, error handling, response headers, model selection, recognizers, structured JSON scanning, IAM/API Gateway configuration, Docker build context, dependency locking, and deployment scripts. Consulted the existing graph map and verified findings against current source.
- No executable `eval`, unsafe pickle/YAML deserialization, user-directed outbound URL fetching, or shell-interpolated request input was found in the production request path.
- The handler enforces a 20,000-byte decoded-body limit, validates thresholds and entity filters, sets `Cache-Control: no-store`, and avoids logging submitted payloads or exception messages.
- API Gateway payload tracing is disabled. Function logs have seven-day retention. The Lambda role uses its basic logging policy; API invocation permission is restricted to the API and method.
- Model selection is allowlisted, email suffix handling is offline, and Docker uses an allowlisted build context with a local wheel cache.
- A focused secret-format scan of all 17 tracked files found zero high-confidence matches for AWS access keys, GitHub tokens, Slack tokens, Stripe live secrets, or private-key headers. No secret values were printed.
- A direct HTTPS query to the [OSV vulnerability API](https://google.github.io/osv.dev/api/) on the scan date checked 52 production lock pins and 2 development pins. All 54 queries returned empty vulnerability lists. An empty result can also mean missing database coverage; it does not prove a package is safe.
- `.venv/bin/python -m unittest tests.test_handler tests.test_structured tests.test_policy tests.test_model_config -q`: **55 tests passed**.
- Bounded adversarial tests reproduced SEC-001 without accessing AWS or leaving servers running.

## Limits and next action

Bandit, pip-audit, Semgrep, Gitleaks, and Trivy were unavailable; no scanner packages were installed. The secret check was a focused source-pattern scan, not a full entropy or Git-history audit. Dependency checks do not inspect wheel contents, provenance, model assets, or the container base image. No deployed AWS state, authorization bypass, full browser exploit, production load test, or penetration test was assessed. No dedicated skill reference covered bare Lambda or Starlette.

Address SEC-001 first, then assess whether the documented shared-key deployment needs identity-based authorization. Treat SEC-003 and SEC-004 as local-tool issues, separate from the deployed Lambda. Fixes have not been applied.
