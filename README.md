# zt-sift

Find sensitive data. Know your exposure.

Send a message in the request body; get back every detection with `text`, `entity`, `start`, `end` and `score`, plus a total `count` and per-entity `counts`.
Presidio with spaCy `en_core_web_sm` (the only model in the image) and 61 custom recognizers covering 48 custom entity types. There is no additional neural span model.

## Layout

```
pii_detector/    the code that ships: detector.py (load_analyzer, detect, collapse_overlaps), recognizers.py (custom recognizers),
                 policy.py (score acceptance, entity aliases, generic-to-specific families), structured.py (JSON values with source offsets)
handler.py       Lambda entry point behind API Gateway
Dockerfile       Lambda image, installed offline from wheels/
template.yaml    CloudFormation: Lambda, API Gateway, API key, usage plan, alarms (stack pii-detection-presidio, us-west-2)
requirements.txt direct dependencies of the image; requirements.lock pins all 52 packages
wheels/          offline cache of those 52 Linux / Python 3.12 wheels (gitignored)
scripts/         deploy.sh (--validate | --build | --deploy); build_lock.py regenerates requirements.lock offline from wheels/
```

## Use

```bash
python -m pii_detector "Call Sarah on (415) 555-0132"       # the detector from the command line (--file, --json, --collapse, --threshold)

scripts/deploy.sh --validate    # compile check, tests (when a tests/ folder is present) and cfn-lint; no Docker or AWS
scripts/deploy.sh --build       # local image pii-presidio-lambda:local
scripts/deploy.sh --deploy      # creates or updates the billable AWS resources
scripts/deploy.sh --deploy-existing-image  # upload an already-built image; no build or local detection
```

## API

`POST /detect` with header `x-api-key`. Body: plain text, or JSON `{"text": "..."}` (at most 20,000 bytes). Optional query parameters:
`threshold` (default 0.5), `entities` (comma-separated, default all; `EMAIL` and `ID` are accepted as aliases for `EMAIL_ADDRESS` and `NATIONAL_ID_NUMBER`),
`collapse` (default `true`: remove redundant candidates, see "How a value's type is chosen").

```json
{"count": 2, "counts": {"EMAIL_ADDRESS": 1, "US_SSN": 1}, "detections": [{"text": "jane@example.com", "entity": "EMAIL_ADDRESS", "start": 14, "end": 30, "score": 1.0}, ...]}
```

When results overlap, the project's own recognizers win over Presidio's built-in rules, which win over spaCy's name, place and date tags; spaCy-only acronyms and
JSON-style keys are dropped. Entity names are Presidio's own (`EMAIL_ADDRESS`, `US_SSN`, `CREDIT_CARD`, `ADDRESS`, ...).

## How a value's type is chosen

Every recognizer proposes candidates; `detect(..., collapse=True)` then settles overlaps with these rules (`pii_detector/policy.py`, `detector.py`):

1. **Evidence ranking.** A value found right after its label (`passport: ...`, `IMEI: ...`) outranks a pattern/checksum rule, which outranks spaCy's tagger.
   Inside a rank the higher score wins, then a context-supported match, the longer span, and finally the entity name, so output never depends on registration order.
2. **Specific over generic.** A label such as `passport` or `tax id` proves the kind of identifier but not the country, so the label-based recognizers report a generic type
   (`PASSPORT_NUMBER`, `TAX_ID_NUMBER`, `NATIONAL_ID_NUMBER`, `LICENSE_PLATE`, ...). If a *validated* country-specific rule (score >= 0.8) fires on exactly the same value and belongs to that
   family, the specific type is reported instead (`DE_PASSPORT`, `IN_GSTIN`, `NG_NIN`, ...), and rivals from other families on that value are discarded. A weak shape match never replaces the
   generic type: `IN_PASSPORT`, `UK_PASSPORT` and `KR_PASSPORT` share one-or-two-letters-plus-digits shapes that cannot name the country, so those come back as `PASSPORT_NUMBER`.
3. **Weak country patterns.** `DE_PLZ`, `ES_PASSPORT`, `IT_IDENTITY_CARD`, `IT_PASSPORT`, `PH_TIN` and `UK_POSTCODE` match only a shape, so alone they score 0.01-0.1. They are reported at the default
   threshold only when a context word (`plz`, `pasaporte`, `postcode`, ...) sits next to the value. Raising `threshold` above 0.5 removes this allowance.
4. **Credit cards need a real issuer range** (Visa, Mastercard, Amex, Discover, JCB, Diners, UnionPay, Maestro, Mir, Verve, InstaPayment) in addition to the Luhn check, so a 13-digit
   national ID such as a South African ID is no longer called a card.
5. **spaCy noise.** A spaCy tag is dropped when it lies inside a labelled phrase, contains a typed result, or is exactly the context word beside a typed value (`VIN` in `VIN: ...`).
   `PERSON` is exempt, because a name can extend a typed fragment (`user=Sarah Johnson`).
6. **Extensions are kept.** A span that extends beyond another is reported too, so a consumer masking the union of intervals hides every sensitive character. A non-spaCy span that fully
   contains smaller ones replaces them.

`EMAIL` and `ID` are advertised by Presidio but no English model emits them; they are accepted as `entities` filters and mapped to `EMAIL_ADDRESS` and `NATIONAL_ID_NUMBER`.

## Try the image locally

`--user 1051:1051` reproduces Lambda's unprivileged file permissions.

```bash
docker run --rm --platform linux/amd64 --user 1051:1051 --memory=2048m -p 9000:8080 pii-presidio-lambda:local
curl -XPOST http://localhost:9000/2015-03-31/functions/function/invocations \
  -d '{"httpMethod":"POST","headers":{"Content-Type":"text/plain"},"body":"Email Jane at jane@example.com"}'
```

Measured in the emulator at a 2,048 MB limit: 695 MB image, about 2.4 s init (Lambda allows 10 s), 0.3-0.4 s per request for 1-1.5 KB of text, about 835 MiB of memory.

## Notes

- Published Lambda versions are frozen snapshots, so the template's version description includes the image, model, memory and timeout; changing any of them publishes a new version.
- Every file in the image must be world-readable because Lambda runs as an unprivileged user; the Dockerfile checks this.
- To refresh `wheels/`, see the `pip download` command at the top of `scripts/build_lock.py`.

### Accuracy and latency controls

`PII_PHONE_REGIONS=US` is the default. Set comma-separated region codes (for
example `US,IN,GB,DE`) to include national-format numbers from those countries.
International `+country-code` numbers still use libphonenumber validation.
Explicit phone fields additionally detect plausible 7–15 digit numbers, even
when a numbering plan rejects them. This protects malformed sensitive values;
it does not assert that the phone is usable. More regions increase request time.
The spaCy parser and sentence recognizer are excluded during loading; their unused
weights are not retained in memory. NER, tagging and lemmatization remain enabled.
No provisioned concurrency or periodic warming is needed.

### The spaCy model

The image bundles only `en_core_web_sm`. It supplies spaCy's tags for names, organizations and locations in free text;
every other entity comes from Presidio's and this project's recognizers. The small model tags more field labels as
organizations; the noise rules below remove those. Measure missed values and false positives on your own text.

```bash
python -m pii_detector --file message.txt --collapse
scripts/deploy.sh --build
docker run --rm --platform linux/amd64 --user 1051:1051 --memory=3008m -p 9000:8080 pii-presidio-lambda:local
```

For isolated AWS testing, explicitly use a separate stack. This command creates
billable test resources and prints a separate endpoint; it leaves the existing
stack alone. Start at the existing memory allocation to compare accuracy and
latency, then test 512 MB only after measuring startup and maximum-input peaks.
The deployment script accepts `MEMORY_SIZE=512`, but it does not change the 3008 MB
default. Container memory limits do not reproduce Lambda's reduced CPU allocation.

```bash
STACK_NAME=pii-detection-sm-test ECR_REPOSITORY_NAME=pii-detection-sm-test \
  MEMORY_SIZE=3008 PROVISIONED_CONCURRENCY=0 scripts/deploy.sh --deploy
```

A deployment publishes a new Lambda version and updates the live alias. AWS settings change only when you explicitly run a deployment command.

If `pii-presidio-lambda:model-test` has already been built, upload that image to
test directly in Lambda. Docker Desktop only needs to be running for the upload;
this mode does not build an image or execute detection locally. Use the same
stack/memory variables with `--deploy-existing-image`. It uses the saved
image's code, so later source changes require a new image. To avoid Docker on
the Mac entirely, build and publish the image on a separate machine or CI runner.

Known JSON field names are normalized for camelCase/snake_case recognition;
values retain their original source spelling, escapes and offsets. Returned offsets
are Unicode code-point indices, not JavaScript UTF-16 indices. Passwords may be
short when explicitly assigned; quoted passwords/passphrases include all source
characters between the quotes. Unquoted prose passwords end at whitespace or a
field delimiter: use quotes for multiword passphrases. Source escapes remain part
of the sensitive span and must be masked too. Complete PEM blocks include their
bodies; a header-only fragment is still reported as a warning signal.

When the analyzed text is a valid JSON object or array of at most 100,000 characters, detection operates on its
scalar values with their field names as context. Keys and JSON separators cannot
be included in a result, and each result stays within one value. Escaped characters
are decoded for recognition and mapped back to their original source intervals.
Explicit first/last/full name fields and company-name fields use their labels;
generic `name` fields use person-related parent context. Malformed JSON retains
the ordinary text detection path. This does not change the HTTP contract: an
`application/json` request still requires `{"text":"<serialized JSON or prose>"}`;
raw business JSON can also be submitted as `text/plain`.
Larger CLI documents use the existing text chunking path. Label aliases apply to
primitive values (including array elements); a wrapper such as
`{"passportNumber":{"number":"..."}}` needs a recognized leaf label or a
recognizable value format. Recognition of unfamiliar schemas remains heuristic.

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

The existing API Gateway 5XX alarm now triggers on a single server error in its
configured evaluation period, including handled Lambda failures. No new alarm or
custom metric resource is created. The separate unhandled Lambda error alarm remains.
