# PII detection

Send a message in the request body; get back every detection with `text`, `entity`, `start`, `end` and `score`, plus a total `count` and per-entity `counts`.
Presidio with spaCy `en_core_web_lg` and 48 custom recognizers. There is no neural span model, so it runs on a small Lambda in a few hundred milliseconds.

## Layout

```
pii_detector/    the code that ships: detector.py (load_analyzer, detect, collapse_overlaps), recognizers.py (the 48 custom recognizers)
handler.py       Lambda entry point behind API Gateway
Dockerfile       Lambda image, installed offline from wheels/
template.yaml    CloudFormation: Lambda, API Gateway, API key, usage plan, alarms (stack pii-detection-presidio, ap-south-1)
requirements.txt direct dependencies of the image; requirements.lock pins all 52 packages
requirements-dev.txt  extra packages for tools/ (web page)
wheels/          offline cache of those 52 Linux / Python 3.12 wheels (gitignored)
scripts/         deploy.sh (--validate | --build | --deploy); build_lock.py regenerates requirements.lock offline from wheels/
tests/           28 unit tests (recognizers, collapse logic, Lambda handler)
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
