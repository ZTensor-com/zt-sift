# PII detection: consolidated accuracy, JSON correctness and performance report

**Report date:** 12 October 2026  
**Implementation under review:** `8187ab0`  
**Pre-fix baseline:** `bd43970`  
**Scope:** Claude’s post-deployment verification, Codex’s subsequent verification of its findings, and the dedicated local/deployed JSON audit.  
**Change status:** This report introduces no implementation changes, deployment changes, commits or paid infrastructure.

## 1. Executive assessment

The fixes improved detection coverage and warm request speed. The original 50-value prose example still has all expected values detected, harder variant recall improved from 7/37 to 33/37 exact typed spans, and Claude measured approximately 3–5× lower warm round-trip latency for typical deployed requests.

Those gains are real, but they do not establish acceptable precision or complete JSON support:

1. The prose example now returns **53 detections for 50 expected spans**. Three extra spaCy organization predictions were independently confirmed.
2. **Five of ten strong negative JSON fixtures returned false positives**, totaling seven detections. These include object braces and commas classified as passwords.
3. Single-field entities can span **unrelated JSON keys and values**, including a private-key template and a timestamp.
4. Equivalent minified and formatted JSON produce different name and organization recognition. The full profile is **49/50 when minified and 50/50 when formatted**.
5. CamelCase support is incomplete: the corresponding profile is **45/50 minified and 46/50 formatted**.
6. Cold initialization remains an operational concern despite faster warm inference. Claude observed approximately 18 seconds after deployment, including an initialization retry.

The next work should prioritize **JSON field boundaries, complete value coverage and precision checks**, while retaining the faster phone path. Blanket acronym filtering or blanket rejection of extending spaCy spans would introduce new misses.

**Provisioned concurrency remains excluded by the user’s cost constraint.** This report does not recommend enabling it or adding a scheduled warmer as a default.

## 2. Evidence and provenance

| Evidence | What it establishes | Verification boundary |
|---|---|---|
| User-provided Claude verification report | A/B results; deployment inspection; 128-fixture and 24-input live/local parity; five-run latency comparisons; CloudWatch observations | Deployment identifiers, historical timings and telemetry are Claude-reported. Codex did not independently query AWS configuration/logs during the follow-up reviews. |
| Codex follow-up of Claude’s findings | The 53-result prose output, overlap mechanism, field-label noise, age/date duplication, short session/default-secret behavior; counterexamples to blanket filters | Independently checked from saved results, current source and targeted local detections. |
| Dedicated JSON audit | Exact typing, full coverage, negative controls, key/cross-field detections, formatting and transport effects | **36/36 deployed statuses and full response JSON matched local output.** All returned offsets matched their source substrings. |
| Earlier fix validation | 36 tests; target image validation; Unicode/overlap highlighting; pre/post local timings | Performed during implementation. Claude explicitly did not independently verify the Docker, Node or CLI checks. |

Primary local artifacts:

- [Claude’s supplied verification](<~/.codex/attachments/18fd6884-c854-4919-b14c-833d0a464500/Pasted text.txt>).
- [Original implementation audit](analysis/2026-10-12/REPORT.md).
- [Fix validation](analysis/2026-10-12/POST_FIX.md).
- [Saved post-fix responses](analysis/2026-10-12/post_fix_results.json).
- [Dedicated JSON report](analysis/2026-10-12/json_validation/REPORT.md).
- [JSON fixtures](analysis/2026-10-12/json_validation/cases.json), [local results](analysis/2026-10-12/json_validation/local_results.json), and [deployed results](analysis/2026-10-12/json_validation/remote_results.json).

These datasets overlap in subject matter and contain repeated format variants. Their counts must not be combined into a single estimate of production accuracy.

## 3. Implementation and deployment context

The application uses Presidio, spaCy `en_core_web_lg`, built-in recognizers and project-specific recognizers. The phone scan defaults to US national formats, with validated international `+country-code` recognition and configurable additional national regions. The unused spaCy parser is disabled for inference.

The detector analyzes text, collects candidate spans, applies noise rules and optionally collapses redundant detections. The structured-field recognizer adds exact source spans for some known JSON fields, but **generic regex and NLP recognition still analyze the complete serialized JSON text**. This distinction explains several remaining failures.

Deployment state reported by Claude:

| Item | Reported value |
|---|---|
| Stack | `pii-detection-presidio`, `UPDATE_COMPLETE` |
| Stack update time | 12 October 2026, 09:32 UTC / 15:02 IST |
| Alias/version | `live` → version 5 |
| Image tag | `20261012T092938Z-2cbba3d6` |
| Memory | 3,008 MB |
| Function timeout | 60 seconds |
| Provisioned concurrency | 0 |
| Alarm thresholds | Both reported as 1 |

This table records Claude’s inspection, not a fresh AWS inspection performed for this consolidated report.

## 4. Test methodology and limitations

### 4.1 Claude’s verification

Claude reported side-by-side execution of baseline and fixed code on:

- All 128 original audit fixtures.
- The 50-value long prose example.
- A 24-input battery containing JSON, logs, support, medical and HR records, configuration, phones, emoji and ordinary text.
- 34 short phrases targeting label rules.
- Live execution of the 128 fixtures, prose example and 24-input battery.

Claude’s report therefore did include JSON. The dedicated follow-up expands its JSON-specific negative controls and structural checks; it does not replace a prose-only verification.

### 4.2 Dedicated JSON audit

The JSON audit contained 36 requests:

| Group | Payloads | Purpose |
|---|---:|---|
| Positive JSON | 16 | Full profiles, camelCase, reordered keys, duplicates, escapes, PEM and organization values |
| Strong negative JSON | 10 | Five no-PII objects, each minified and formatted |
| Policy cases | 6 | Coordinates versus math, timestamps, missing-value markers and weak/default credentials |
| API contract | 2 | Raw domain-object rejection and valid `text` envelope |
| Transport controls | 2 | Hold analyzed text constant while changing the accepted transport |

There are **425 annotated source spans**, including repetitions across profile variants and transport controls. These are not 425 distinct personal values or independent real-world observations.

Every expected span is indexed against the serialized JSON being analyzed, not its outer API wrapper. String escapes remain part of the source representation. Key and primitive-value intervals are recorded separately to identify detections that consume syntax or unrelated fields.

### 4.3 What the measurements mean

- **Exact typed match:** correct start, end and an accepted entity type. The US passport fixtures explicitly accept US_PASSPORT or PASSPORT_NUMBER.
- **Complete sensitive coverage:** the union of returned intervals covers the full annotated value, even if typing differs.
- **Orphan detection:** overlaps no expected span. This catches some extras but misses false classifications that overlap real PII.
- **Incorrect overlapping prediction:** may cover a real value but include an invalid type, field label, neighboring value or excess syntax.
- **Strong negative:** fixture with no intended PII and an exhaustive empty gold set.
- **Policy case:** sensitivity depends on application context; detections are not automatically counted as false positives.

All 36 JSON responses matched locally and remotely, and all returned offsets were internally consistent. **A substring can have correct offsets and still be the wrong detection.** The false password brace and cross-field private key demonstrate this.

The suites are deliberately diagnostic. The negative-case incidence and hard-case recall are not estimates of production prevalence, and paired minified/formatted cases are not independent samples.

## 5. Verified improvements retained from the fix

The combined evidence supports retaining these changes:

- Much smaller phone-region scan, while supporting validated international numbers.
- Complete full PEM blocks and tested truncated base64 bodies; longer tokens and sessions.
- Explicit short, quoted and escaped passwords; login pairs and log-style labels.
- Correct handling of `password is actually …` and known email assignments.
- Some nested/camelCase JSON fields, address components and plausible labeled phone values.
- Better salary, bank-account, identifier, newborn-age, UUID and GPS formats.
- Removal of demonstrated page/timestamp plate noise and selected conversational date noise.
- Input guards for malformed base64 and empty entity filters.
- Unicode code-point highlighting and merged highlight coverage.
- Existing API server-error alarm sensitivity improved without adding paid warm capacity.

Passing the earlier 36 tests establishes these tested behaviors. It does not establish the absence of extras on arbitrary prose, JSON schemas or all field aliases.

## 6. Consolidated accuracy results

### 6.1 Original fixtures, as reported by Claude

| Group | Expected spans | Exact before | Exact after | Detections before → after | Orphan detections before → after |
|---|---:|---:|---:|---:|---:|
| Prose sample, default collapse | 50 | 50 | 50 | 50 → 53 | 0 → 1 |
| Same sample, raw candidates | 50 | 50 | 50 | 81 → 72 | 4 → 1 |
| Isolated custom positives | 48 | 48 | 48 | 49 → 50 | 1 → 2 |
| Stock positives | 10 | 10 | 10 | 11 → 12 | 1 → 1 |
| Hard variants | 37 | 7 | 33 | 25 → 39 | 3 → 1 |

The prose sample illustrates the metric gap. Its three incorrect organization results are:

| Incorrect result | Relationship to expected PII |
|---|---|
| `EIN 12-3456789` as ORGANIZATION | Overlaps the correctly detected US_EIN value |
| `CVV 737` as ORGANIZATION | Overlaps the correctly detected CARD_CVV value |
| `IMEI` as ORGANIZATION | A separate field-label prediction |

Only the last is an orphan. Counting orphans alone therefore reports one extra while there are three incorrect classifications. Under this curated sample’s exact gold contract, exact typed precision is **50/53 ≈ 94.3%**, while recall is **50/50 = 100%**. This is a sample-specific calculation, not production precision.

Claude reported the original negative/policy fixtures returning detections in 12/19 cases before and 10/19 after. That suite mixes unrelated prose with malformed-identifier policy cases, so its incidence should not be presented as a pure false-positive rate.

### 6.2 Positive JSON, independently reproduced on deployment

| Profile | Minified exact matches | Formatted exact matches |
|---|---:|---:|
| Full snake_case profile | 49/50 | 50/50 |
| Equivalent camelCase profile | 45/50 | 46/50 |
| Full profile with reversed key order | 49/50 | 50/50 |
| Duplicate emails and username overlap | 3/3 | 3/3 |
| Escaped Unicode/password values | 2/2 | 2/2 |
| Complete PEM with JSON-escaped newlines | 1/1 | 1/1 |
| Organization values: NASA, IBM, 3M, BBC, AMD | 0/5 | 3/5 |

These figures measure expected-span recall, not precision. The formatted escaped-Unicode fixture returns three detections for two expected spans: the extra ORGANIZATION result covers the literal JSON escape sequence `\ud83d\ude00` (offsets 13–25, score 0.85). This is a false positive despite the 2/2 expected-span result.

The formatted organization fixture detects NASA, IBM and BBC, while missing 3M and AMD. The organization behavior depends on the whole input context; preserving an acronym in a prose example does not ensure recognition in JSON. Organization recall gates describe the currently enabled entity scope; requiring organization reporting in future releases depends on the product's sensitivity policy.

### 6.3 Strong negative JSON

**Five of ten fixtures returned seven false-positive detections.** The ten fixtures are five payloads serialized in two formats.

| Payload | Minified result | Formatted result |
|---|---|---|
| Application metadata and counters | none | none |
| Product metadata | none | LOCATION=`USD` |
| Help text and field-name array | PASSWORD=comma | PASSWORD=comma plus indentation |
| Non-sensitive suffix keys | none | none |
| JSON Schema | PASSWORD=object brace and comma | PASSWORD=object brace and comma/indentation |

The policy fixtures are excluded from this count.

## 7. Findings grouped by severity

Severity reflects the demonstrated failure and likely effect. Actual downstream redaction or business-data corruption was not tested; its impact is identified as a consequence a consumer could encounter.

### Critical

No critical issue was established by these functional detection and performance investigations.

### High

#### H1. Minified JSON misses names that formatted JSON detects

**Evidence:** The full, reordered and camelCase minified profiles miss `person.name = "Sarah Johnson"`. Their formatted equivalents detect it. Equivalent-content transport controls retain the same difference.

**Impact:** The identity remains uncovered, rather than merely assigned a generic alternate type. Detection depends on presentation whitespace.

**Mechanism:** NLP still receives the entire serialized source. Punctuation and token adjacency alter tokenization and entity predictions. A structured recognizer handles some fields but does not supply a general person-name path.

**Recommended correction:** Analyze relevant string values with field/path context, retaining a map back to original source intervals. Preserve prose detection within values. Avoid blindly treating every field named `name` as a person: application, product and service names need different context.

**Acceptance:** The three minified name fixtures recover their full PERSON span; formatted and minified representations have equivalent value-level results. Negative metadata/product name cases must remain protected from invented person classifications.

Source: [load/detect pipeline](pii_detector/detector.py:156).

#### H2. CamelCase alias coverage omits recognized PII fields

The following fields are missed in both camelCase formats:

| Field path | Expected type |
|---|---|
| `workAndSchool.nursingLicenseNumber` | PROFESSIONAL_LICENSE |
| `documents.passportNumber` | US_PASSPORT / PASSPORT_NUMBER |
| `documents.idCardNumber` | NATIONAL_ID_NUMBER |
| `vehicleAndDevice.deviceSerialNumber` | SERIAL_NUMBER |

**Impact:** Sensitive values that work under existing snake_case labels are uncovered under common JSON keys.

**Mechanism:** The structured map contains a subset of aliases. Generic label matching joins some multiword labels only at assignments, but does not consistently handle appended qualifiers or field prefixes.

**Recommended correction:** Maintain one explicit normalized alias registry shared by structured and labeled recognition, including approved qualifiers and prefixes. Preserve boundaries so `customerNumbering` does not become `customerNumber`.

**Acceptance:** Both camelCase profiles recover all four values without additional detections in the suffix-key negative fixtures. All pre-existing snake_case and log assignments remain correct.

Sources: [structured aliases](pii_detector/recognizers.py:204), [label construction](pii_detector/recognizers.py:65).

### Medium

#### M1. JSON syntax and schema field names are classified as passwords

Reproducer fixture:

```json
{
  "properties": {
    "password": {"type": "string"},
    "email": {"type": "string"},
    "customerId": {"description": "generated identifier"}
  },
  "required": ["password", "email"],
  "additionalProperties": false
}
```

**Actual:** PASSWORD=`{` and PASSWORD=comma/whitespace. The field-name array fixture independently produces a comma password.

**Impact:** False alerts and unnecessary masking of structural syntax. A consumer replacing such spans could damage JSON structure.

**Mechanism:** Credential prose matching operates over raw JSON and treats adjacent quoting or `:` as assignment evidence without checking whether the apparent value is an object, array member or actual credential primitive.

**Recommended correction:** Use JSON token/path context to distinguish instance values from schema descriptors and required-field lists. Restrict single-field credential spans to appropriate value locations. Do not globally ban braces or punctuation as password characters: `password: ab{cd}ef` and a genuine string value containing braces must retain complete coverage.

**Acceptance:** Both schema and field-name-list variants return no PASSWORD detections. Existing explicit short, quoted, escaped and brace-containing password positives remain complete.

Source: [CredentialRecognizer](pii_detector/recognizers.py:157).

#### M2. Private-key and date recognizers bridge unrelated JSON fields

PEM template reproducer:

```json
{
  "templateHeader": "-----BEGIN PRIVATE KEY-----",
  "description": "test fixture template only",
  "templateFooter": "-----END PRIVATE KEY-----"
}
```

**Actual:** One PRIVATE_KEY span runs from the header through both intervening keys and unrelated text to the footer. It occurs in both formats. Header-only recognition remains allowed by existing policy; the separate values are not a single key block.

Timestamp reproducer:

```json
{"createdAt":"2026-10-12T01:10:40Z","duration":"45 minutes","deadline":"Tuesday"}
```

**Actual:** Alongside the full timestamp, minified JSON produces DATE_TIME=`10-12T01:10:40Z","duration":"45`.

**Impact:** Incorrect entity boundaries, inaccurate classifications and potential masking of unrelated data or syntax.

**Recommended correction:** Confine single-field entities to their primitive source value, with decoded-to-source mapping when needed. Maintain complete key blocks inside one value, including escaped newlines. Handle true multi-part entities explicitly; a GPS pair spanning two numeric array elements is not automatically an error.

**Acceptance:** Template fragments do not bridge fields. Full and tested truncated keys in actual value strings remain covered. The timestamp fixture has no DATE_TIME containing a key or neighboring field fragment.

Source: [recognizer definitions](pii_detector/recognizers.py).

#### M3. Extending spaCy predictions add wrong organization/date classifications

**Evidence:** The prose sample’s three extra organization results; local `45 years old` and `999 years old` returning both AGE and DATE_TIME; local `token=expired` returning ORGANIZATION=`token=`. Claude also observed longer log spans and other labels in its battery.

**Mechanism:** A wider spaCy span can be retained merely because it extends an already correct result. The exact-text noise blocklist does not match composite text such as `EIN 12-3456789`.

**Recommended correction:** Suppress known label-plus-typed-value organization predictions and contextual field-label predictions; suppress redundant age-duration date predictions. Preserve independently meaningful names and organizations.

**Why not blanket rejection:**

```text
user=Sarah Johnson
```

Currently returns USERNAME=`Sarah` and PERSON=`Sarah Johnson`. Discarding every extending spaCy span can leave `Johnson` uncovered. A NASA/IBM/3M-only acronym allow-list would also discard independently verified TCS, BBC and AMD predictions.

**Acceptance:** The curated prose sample returns its 50 intended detections with no spurious EIN/CVV/IMEI organizations. Full-name coverage, legitimate acronym positives, true addresses and complete validated identifier spans must remain intact.

Sources: [overlap handling](pii_detector/detector.py:126), [noise filtering](pii_detector/detector.py:114).

#### M4. JSON metadata can receive incorrect or context-dependent NLP labels

**Evidence:** Formatted product metadata returns LOCATION=`USD`; organization values return 0/5 minified versus 3/5 formatted; operational and numeric metadata receive generic date predictions in some contexts.

**Recommended correction:** Give NLP a suitable value representation and field/path context. Separate known non-personal metadata from personal or free-text fields. Do not use a blanket rule that all uppercase words, digit-containing names or generic dates are irrelevant.

**Acceptance:** Product and application metadata negatives remain clear, while personal fields, employer names and contextual dates retain recognition. Formatting changes must not create metadata-only predictions.

#### M5. Consumers cannot assume collapsed responses are non-overlapping

**Evidence:** The prose sample contains overlapping EIN/organization and CVV/organization pairs. The behavior is documented but differs from the earlier one-result-per-overlap expectation.

**Impact:** Consumers selecting one candidate rather than merging coverage can miss characters; consumers masking overly broad candidates can remove unrelated content.

**Recommended correction:** First reduce incorrect candidates. Continue documenting union masking for genuine overlaps, and consider an explicit optional merged-redaction view if consumers need it. Keep classifications and masking intervals conceptually separate; do not silently change response or offset semantics.

**Acceptance:** Overlap tests preserve every sensitive character, retain full names/complete emails, and avoid erasing typed detections because of a larger hallucinated NLP span. JSON single-field masking excludes structural keys and delimiters.

#### M6. Validation reports emphasize recall without fully measuring precision

The positive regression helper checks that an expected result exists, and the earlier post-fix summary reports exact hits and union coverage. Both can pass when incorrect additional detections exist.

**Required metrics:** Exact typed precision/recall with defined alias and duplicate matching; orphan and overlapping wrong predictions; false positives by entity and fixture category; complete sensitive-character coverage; key/syntax intersections; cross-field spans; formatting invariance; correct HTTP contract.

**Acceptance:** Positive successes must not hide extras. Strong negative JSON fixtures require exact empty results. Policy cases have separate expected behavior and are excluded from categorical false-positive totals.

Sources: [regression assertions](tests/test_regressions.py), [post-fix metrics](analysis/2026-10-12/post_fix_check.py:21).

#### M7. Cold initialization can dominate otherwise fast requests

Claude observed one post-deployment cold request at roughly 18 seconds: initialization reached its initial 10-second limit, then retried during the invocation; reported function duration was approximately 8.3 seconds. It cited a 29-second gateway window. This is an observation from one request, not an established cold-start distribution or proof of behavior after every idle period.

**Recommended work within the cost constraint:** Inspect initialization versus invocation timing; measure model loading, registry setup and warm-up; investigate excluding unused components at load time; reduce unnecessary initialization work. Compare smaller models only against accuracy gates. Keep current memory until an end-to-end memory benchmark includes cold starts, large inputs and cost per completed request.

A peak of 1,334 MB in observed traffic does not by itself make 1,769 MB the best configuration. CPU allocation and runtime can change with memory. Warm-up pings are best-effort and still create recurring requests; no warmer or provisioned concurrency is proposed as a default. [AWS memory guidance](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html), [initialization lifecycle](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html).

Source: [eager initialization and warm-up](handler.py:30).

### Low / policy or scope decisions

| Topic | Current observation | Treatment |
|---|---|---|
| Missing-value markers | Tested null/none/unavailable markers were excluded | Retain consistent placeholder behavior without assuming all weak credentials are placeholders |
| Short/default credentials | `sid=0`, `secret: changeme`, admin/guest usernames can be flagged | Define policy; `changeme` may be an actual default secret |
| Malformed labeled IDs/dates | Invalid DOB, VIN or IMEI may still be flagged | Privacy coverage and identifier validity are different questions |
| Numeric pairs | Math arrays can match GPS signatures | Decide using path/schema context; identical numbers are otherwise ambiguous |
| Generic dates and organizations | Correct entity recognition does not always imply personal sensitivity | Define intended entity scope and context, rather than labeling every such result a model bug |
| Non-US national phones | Default US scan misses some local formats | Configure supported national regions; international `+` coverage is a separate path |
| English-only NLP | Hindi names and complete Indian addresses remain limitations | Outside the current English/US-first scope; additional locale work requires separate validation |
| Password punctuation | Unquoted trailing punctuation may be included | Retain coverage rather than guess away a legitimate password character; quotes clarify boundaries |
| Hyphenated handles | `@sarah-j89` currently returns only `@sarah` | Platform-dependent syntax requires an explicit contract |
| Large CLI entities | 512-character overlap may not preserve longer boundary-crossing entities | Documented limitation; the API’s 20 KB cap avoids its 100,000-character chunk boundary |

## 8. API contract and offsets

The current endpoint accepts:

```http
Content-Type: text/plain

{"email":"jane@example.com"}
```

or a JSON envelope whose `text` value contains the serialized business JSON:

```json
{"text":"{\"email\":\"jane@example.com\"}"}
```

An arbitrary domain object sent directly under `Content-Type: application/json` returns 400 because the endpoint expects a string `text` field. That response is correct under the current contract, not a detection miss. Decide explicitly whether future raw-object support is needed; do not silently reinterpret existing callers’ inputs.

Offsets refer to the analyzed text, not the outer envelope, and use Unicode code points. JSON source escapes belong to the analyzed representation. A future decoded-value path must map detections back to those original intervals. Correctly indexed results must also be checked for semantic and structural correctness.

## 9. Performance evidence

### 9.1 Claude-reported deployed warm round trips

Five runs per workload, 1.1 seconds apart; curl times exclude deliberate rate-limit pauses but include network and API Gateway.

| Input | Before | After |
|---|---:|---:|
| 47 bytes | not measured | 0.14 s |
| 1.5 KB prose | 0.97 s | 0.21 s |
| 1.8 KB JSON | 0.95 s | 0.22 s |
| 1.2 KB customer payload | 0.48 s | 0.17 s |
| Near-20,000-byte input | not measured | 1.6–1.7 s |

These results support a substantial warm-speed improvement. They do not establish p95/p99, throughput, load behavior or cold-start reliability.

### 9.2 Local comparisons from separate investigations

| Investigation / workload | Baseline | Fixed | Speedup |
|---|---:|---:|---:|
| Codex saved sample | 260.5 ms | 73.0 ms | 3.6× |
| Codex 20 KB dense | 2,266.7 ms | 597.0 ms | 3.8× |
| Codex 20 KB numeric | 3,803.8 ms | 298.1 ms | 12.8× |
| Claude 1.5 KB prose | 234 ms | 36 ms | 6.5× |
| Claude 1.8 KB JSON | 252 ms | 56 ms | 4.5× |
| Claude short input | 26 ms | 3 ms | 8.7× |
| Claude 20 KB dense | 1,919 ms | 626 ms | 3.1× |
| Claude 20 KB numeric | 7,445 ms | 1,406 ms | 5.3× |

The workloads and measurement conditions differ. Both show improvement; the numeric-heavy results must not be treated as measurements of one identical input. Local macOS ARM/Python 3.14 timings are not directly interchangeable with deployed Linux x86_64/Python 3.12 timings.

Claude’s CloudWatch sample covered 415 invocations over four hours, including prior audit traffic, with median duration 12 ms, p90 116 ms and peak memory 1,334 MB. This mixed sample is not an isolated post-fix latency distribution. The dedicated 36-case JSON audit establishes behavior and parity, not a repeated warm-latency benchmark.

## 10. Prioritized remediation plan

| Order | Work | Completion gate |
|---|---|---|
| 1 | Extend the regression gate with precise negative and structural assertions | Reproduce every confirmed failure; evaluate extras as well as expected hits |
| 2 | Introduce JSON value/path-aware analysis and source-offset mapping | No schema/array delimiters as secrets; no single-field entity bridges; escaped secrets remain complete |
| 3 | Complete approved key aliases and stable value recognition | All four omitted camelCase values recovered; full profile names invariant to formatting; suffix negatives stay clear |
| 4 | Apply contextual NLP suppression | Curated prose sample has 50 intended detections; full names and genuine organization controls remain intact |
| 5 | Resolve consumer and sensitivity policy | Explicit overlap/redaction contract, entity scope, placeholders, malformed-value and locale rules |
| 6 | Investigate cold initialization without paid warm capacity | Measured initialization profile; accuracy-preserving changes; benchmark memory only if justified |

### Proposed JSON analysis design

1. Preserve the analyzed source string and its offset contract.
2. Detect and walk valid JSON using real object/array/scalar structure, recording paths and source boundaries. Treat malformed JSON-like prose under an explicit fallback policy.
3. Use approved normalized field aliases and path context for structured identity/credential values.
4. Apply relevant format recognizers within individual values. Run NLP on appropriate textual values or a controlled representation, batching where possible rather than invoking the full pipeline separately for every numeric scalar.
5. Map decoded-text predictions back to original escaped source characters.
6. Handle declared composite entities such as coordinate arrays through explicit rules, not arbitrary source bridging.
7. Keep classification reconciliation separate from union coverage and reject structurally impossible candidates.

This is a proposed design, not an implementation already present. It must be benchmarked: naive per-field analyzer calls could lose the current latency gains.

## 11. Acceptance matrix for the next patch

| Test | Required behavior |
|---|---|
| Original prose sample | Retain 50/50 exact values; remove its three spurious organizations |
| Name extension | `user=Sarah Johnson` retains coverage of both words |
| Organizations | Retain meaningful NASA, IBM, 3M, TCS, BBC and AMD controls without a tiny global allow-list |
| Age expression | Correct AGE without an unwanted overlapping age-duration DATE_TIME |
| Snake_case JSON profile | Recover all 50 values in both formats, with no unrelated extra predictions |
| CamelCase profile | Recover omitted aliases and the full name in both formats |
| Schema and required-field arrays | No object brace, comma, indentation or field name interpreted as a credential instance |
| Product/application metadata | No fabricated location/person/credential classifications in the curated negatives |
| Full PEM in one JSON value | Complete source span, including escaped newlines |
| PEM template split across fields | No span bridges keys or unrelated values; header-only policy remains explicit |
| Timestamp/duration fields | No DATE_TIME crossing a key or neighboring value |
| Real punctuation passwords | Braces/quotes/escapes remain covered when they are actual string content |
| Duplicate values | Each occurrence has the correct source position; no global `str.index` assumptions |
| Unicode and escapes | Original code-point spans round-trip; frontend highlights equivalent characters |
| Transport controls | Same analyzed content yields identical output through both accepted transports |
| API errors | Deliberate 400 cases stay correct and do not masquerade as detector misses |
| Performance | Preserve demonstrated speed gains; investigate any material regression on representative small, dense and numeric inputs |

Numerical production SLAs, allowed false-positive rates and cold-start targets have not been agreed. The curated zero-extra gates above are fixture-level requirements, not a promise of universal perfect detection.

## 12. Reproduction, deployment and rollback

From the project root, existing regression and JSON checks can be reproduced with:

```sh
.venv/bin/python -m unittest discover -s tests -t .
.venv/bin/python analysis/2026-10-12/json_validation/build_cases.py
.venv/bin/python analysis/2026-10-12/json_validation/run.py --mode local
```

For another bounded live pass, supply the API key securely in `PII_API_KEY`, then run:

```sh
.venv/bin/python analysis/2026-10-12/json_validation/run.py --mode remote
```

The saved JSON response files already preserve the original run; rerunning the runner replaces its result file. Archive existing result files first if comparing a future implementation. This report includes no credentials.

No code fixes are applied by creating this report. For future changes, preserve the current deployed state in a separate commit and make each reviewed correction rollback-friendly. `git revert 8187ab0` undoes the earlier fix in source; the running deployment changes only after deployment. A future patch should have its own revert target, rather than using the baseline to discard all verified improvements.

## 13. Coverage not established

The investigations do not establish production-corpus accuracy, complete language/country coverage, load/concurrency behavior, unauthorized-access behavior, client-side redaction correctness across all consumers or a distribution of cold-start latency. The pre-fix graph under `graphify-out` is historical and should not supply current source locations without verification.

The immediate evidence-based objective is a JSON-aware, precision-tested detector that preserves complete sensitive values and the existing warm-speed improvements, without paid provisioned concurrency.
