# PII detection

Send a message in the request body; get back every detection with `text`, `entity`, `start`, `end` and `score`, plus a total `count` and per-entity `counts`.
Presidio with spaCy `en_core_web_lg` and 61 custom recognizers covering 48 custom entity types. There is no additional neural span model.

## Layout

```
pii_detector/    the code that ships: detector.py (load_analyzer, detect, collapse_overlaps), recognizers.py (custom recognizers)
handler.py       Lambda entry point behind API Gateway
Dockerfile       Lambda image, installed offline from wheels/
template.yaml    CloudFormation: Lambda, API Gateway, API key, usage plan, alarms (stack pii-detection-presidio, ap-south-1)
requirements.txt direct dependencies of the image; requirements.lock pins all 52 packages
requirements-dev.txt  extra packages for tools/ (web page)
wheels/          offline cache of those 52 Linux / Python 3.12 wheels (gitignored)
scripts/         deploy.sh (--validate | --build | --deploy); build_lock.py regenerates requirements.lock offline from wheels/
tests/           unit and regression tests (recognizers, real analyzer, collapse logic, Lambda handler)
tools/           dev only, never shipped: web test page, coverage and evaluation scripts, sample generators (see tools/README.md)
samples/         test inputs, from small US samples to large generated files
```

## Use

```bash
python -m pii_detector "Call Sarah on (415) 555-0132"       # the detector from the command line (--file, --json, --collapse, --threshold)
python -m tools.web                                          # manual test page at http://127.0.0.1:8765
python -m unittest discover -s tests -t .                    # unit tests

scripts/deploy.sh --validate    # tests + cfn-lint, no Docker or AWS
scripts/deploy.sh --build       # local image pii-presidio-lambda:local
scripts/deploy.sh --deploy      # creates or updates the billable AWS resources
```

## API

`POST /detect` with header `x-api-key`. Body: plain text, or JSON `{"text": "..."}` (at most 20,000 bytes). Optional query parameters:
`threshold` (default 0.5), `entities` (comma-separated, default all), `collapse` (default `true`: keep one result per overlapping group).

```json
{"count": 2, "counts": {"EMAIL_ADDRESS": 1, "US_SSN": 1}, "detections": [{"text": "jane@example.com", "entity": "EMAIL_ADDRESS", "start": 14, "end": 30, "score": 1.0}, ...]}
```

When results overlap, the project's own recognizers win over Presidio's built-in rules, which win over spaCy's name, place and date tags; spaCy-only acronyms and
JSON-style keys are dropped. Entity names are Presidio's own (`EMAIL_ADDRESS`, `US_SSN`, `CREDIT_CARD`, `ADDRESS`, ...).

## Try the image locally

`--user 1051:1051` reproduces Lambda's unprivileged file permissions.

```bash
docker run --rm --platform linux/amd64 --user 1051:1051 --memory=2048m -p 9000:8080 pii-presidio-lambda:local
curl -XPOST http://localhost:9000/2015-03-31/functions/function/invocations \
  -d '{"httpMethod":"POST","headers":{"Content-Type":"text/plain"},"body":"Email Jane at jane@example.com"}'
```

Measured in the emulator at a 2,048 MB limit: 695 MB image, about 2.4 s init (Lambda allows 10 s), 0.3-0.4 s per request for 1-1.5 KB of text, about 835 MiB of memory.

## Notes

- Published Lambda versions are frozen snapshots, so the template's version description includes the image, memory and timeout; changing any of them publishes a new version.
- Every file in the image must be world-readable because Lambda runs as an unprivileged user; the Dockerfile checks this.
- To refresh `wheels/`, see the `pip download` command at the top of `scripts/build_lock.py`.

### Accuracy and latency controls

`PII_PHONE_REGIONS=US` is the default. Set comma-separated region codes (for
example `US,IN,GB,DE`) to include national-format numbers from those countries.
International `+country-code` numbers still use libphonenumber validation.
Explicit phone fields additionally detect plausible 7–15 digit numbers, even
when a numbering plan rejects them. This protects malformed sensitive values;
it does not assert that the phone is usable. More regions increase request time.
The spaCy parser is disabled; NER, tagging and lemmatization remain enabled.
No provisioned concurrency, periodic warming, memory or model changes are needed.

Known JSON field names are normalized for camelCase/snake_case recognition;
values retain their original source spelling, escapes and offsets. Returned offsets
are Unicode code-point indices, not JavaScript UTF-16 indices. Passwords may be
short when explicitly assigned; quoted passwords/passphrases include all source
characters between the quotes. Unquoted prose passwords end at whitespace or a
field delimiter: use quotes for multiword passphrases. Source escapes remain part
of the sensitive span and must be masked too. Complete PEM blocks include their
bodies; a header-only fragment is still reported as a warning signal.

Collapse removes redundant contained results but retains partial overlap and
higher-confidence typed results when a larger spaCy span extends them. Consumers
should redact the **union of all intervals**, not assume results never overlap.
`collapse=false` is useful for inspecting candidates. Validate both exact entity
typing and full sensitive-span coverage, with the production default threshold
0.5 and collapse behavior. Score thresholds change recall/precision, and an
explicit entity filter limits what can be protected.

Label-based rules prioritize privacy coverage: malformed labeled dates and IDs
can still be sensitive, so checksum validity is not a universal reason to discard
them. GPS coordinates do require latitude/longitude bounds. Turkish plate patterns
require nearby vehicle/plate context to avoid timestamp and page-number matches.
Conversational spaCy dates are suppressed without birth/medical/death context;
real names with particles and acronyms such as NASA/IBM/3M are not blanket-filtered.
English NLP remains heuristic: Hindi names and complete Indian addresses require
additional language/locale support. Social-handle syntax remains platform-dependent.

API requests are limited to 20 KB. CLI inputs use overlapping 100,000-character
chunks with 512 characters of overlap; unusually long entities crossing chunk
boundaries may still be partial. Prefer document sections or suitably larger
chunks for very long PEM blocks. No library guarantees all PII formats are found.

`PII_EMIT_METRICS=1` optionally emits fixed-name CloudWatch embedded metrics for
successful detection duration and detection failures. It defaults to disabled;
enabling custom metrics can incur CloudWatch charges. Metrics never include text,
entity values, request identifiers or exception messages. Existing privacy-safe
failure logging remains enabled.

Run `python -m unittest discover -v` in the project environment to exercise direct
recognizers, real analyzer behavior, source offsets, negative controls and API
validation. The immutable pre-change audit is under `analysis/2026-10-12/`.

The existing API Gateway 5XX alarm now triggers on a single server error in its
configured evaluation period, including handled Lambda failures. No new alarm or
custom metric resource is created. The separate unhandled Lambda error alarm remains.
