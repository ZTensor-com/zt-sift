# PII detection audit — 12 October 2026

The supplied sample passes all 50 expected typed spans at the API defaults. Accuracy deteriorates on changes in formatting, labels, locale and secret length. The largest measured speed bottleneck is scanning phone numbers separately for all 245 regions.

No production code, deployment settings or AWS resources were changed. Added only audit fixtures, scripts, results and a code graph. Service credentials are environment inputs, absent from these artifacts.

## What was checked

- Pipeline: `handler → detect → AnalyzerEngine → spaCy + recognizers → overlap removal → response`.
- 132 registered recognizers, 125 advertised entity types, including 48 project-defined entity types. Advertised types do not guarantee a capable recognizer/model.
- All 28 existing unit tests pass. Handler tests use the actual local analyzer. Those tests do not cover the failing cases below.
- 128 main fixtures exercised locally and against the supplied deployed endpoint: 48 isolated custom positives, the supplied sample with/without collapse, 34 harder variants, 19 negative/policy fixtures, 10 stock positives and 15 request-validation cases.
- 136 independently seeded stock-format probes across 68 types, locally isolated and then in four deployed batches. The generators come from this project, but values were NOT selected by detector output. They are format-coverage diagnostics, not externally certified government IDs.
- Ten additional local registry diagnostics cover the remaining advertised types, including generic NER labels and newer country recognizers. Thus every advertised type received a fixture or diagnostic; this is not exhaustive testing of every possible format or condition.
- Initial fast remote passes hit HTTP 429. A later completion pass retried only throttle gaps at three-second spacing. All 128 final main responses have the expected HTTP status and match local response JSON exactly.
- Seven latency workloads and a local profiler; optimization experiments modify only a fresh in-memory analyzer.
- Local runtime is macOS ARM/Python 3.14; deployed image declares Linux x86_64/Python 3.12. Local speedups are directional evidence, not measured deployed speedups.

## Accuracy results

Exact typed match requires the entire expected character interval and an accepted entity type. For US passports, US_PASSPORT and PASSPORT_NUMBER are explicitly accepted aliases. Mere overlap is reported separately. Nested city/ZIP detections inside an already labeled full address are not separate expected spans in the supplied sample.

| Suite | Expected spans | Exact typed hits |
|---|---:|---:|
| Supplied sample, default collapse | 50 | 50 |
| Isolated custom positives | 48 | 48 |
| Ten stock positives | 10 | 10 |
| Harder variants | 37 | 7 |
| Four broad stock batches | 136 | 86 |

The hard variants deliberately emphasize likely failures; 7/37 is NOT an estimate of production recall. Stock batch results are influenced by shared context, label conflicts and overlapping country formats. The canonical custom suite produced 49 detections for 48 target spans: `US` in a passport label also becomes LOCATION, so these examples are not an exhaustive precision oracle.

Twelve of the 19 negative/policy fixtures returned at least one detection, totaling 13 detections. Some invalid-format cases are policy choices: a privacy detector may intentionally mask a malformed identifier. The unequivocal unrelated-prose failure is `Page 12 of 40` → TR_LICENSE_PLATE (`12 of 40`, score 1.0).

## Critical

No confirmed critical vulnerability or irreversible data change established in this review.

## High

1. **Secret spans can be incomplete.** A complete `BEGIN PRIVATE KEY ... END PRIVATE KEY` block returns only its header; a 240-character labeled API key returns only the first 200 characters; a 140-character session ID returns only 128 characters. Escaped JSON password text returns `pass\` rather than the full value. A consumer masking only these results could leave sensitive characters visible. Detect the complete token/block, support escaped structured strings, and avoid silently truncating overlength values. The sample contains only a key header, so it cannot expose this failure. [pii_detector/recognizers.py:173](pii_detector/recognizers.py:173)

2. **A shorter custom span can suppress a validated full span.** With `username: ` followed by 45 `a` characters and `@example.com`, raw results contain a full EMAIL_ADDRESS and a 40-character USERNAME. Collapse retains the truncated USERNAME and the domain URL, discarding the full email. Prefer containment-aware selection; preserve the union of sensitive intervals for redaction independently of primary classification. Do not rank every custom result ahead of every validated built-in result. Local reproducer: `spot_checks.json`. [pii_detector/detector.py:106](pii_detector/detector.py:106)

3. **Label-based credential recognition misses common real values.** `password: abc`, `password: secret`, and a quoted multiword passphrase produce no PASSWORD. `password is actually Sup3rS3cret!42` returns PASSWORD=`actually`, missing the actual secret. Strong quoted/key-value structure should outweigh password-strength heuristics; prose needs controlled label-to-value extraction. [pii_detector/recognizers.py:63](pii_detector/recognizers.py:63), [pii_detector/recognizers.py:179](pii_detector/recognizers.py:179)

4. **Global phone scanning dominates request cost.** Every input is passed through libphonenumber for 245 regions. A profiled sample spent approximately 89% of instrumented cumulative time in PhoneRecognizer; profiling overhead means this percentage is diagnostic, not a production SLA. Route national numbers using a configured/requested region and handle international `+` numbers separately. This has much greater measured value than optimizing overlap sorting first. [pii_detector/detector.py:47](pii_detector/detector.py:47)

## Medium

5. **All-country registration creates false positives and competing labels.** A Turkish plate recognizer accepts `12 of 40` in ordinary prose at score 1.0. Re-registering every country recognizer for English also retains foreign-language context and does not make weak patterns reliable. Use explicit jurisdiction/entity profiles. Supply locale in a request or client configuration; unqualified numeric IDs cannot reliably reveal their country. [pii_detector/detector.py:47](pii_detector/detector.py:47)

6. **Formatting and locale coverage is narrow.** Lowercase US addresses lose ADDRESS; an Indian address returns only `12 MG Road, Bengaluru`, omitting its flat, state and postal code. `salary: 85000`, `salary: ₹12,50,000`, spaced bank accounts, `STU-123456`, alphanumeric employee IDs, camelCase JSON labels, short usernames, Hindi names and modern UUIDv7 are missed. These are regex/schema/model limitations, not fixes that a lower global threshold will solve. Preserve source offsets when normalizing labels or input. English-only NLP needs language routing for non-English names. [pii_detector/recognizers.py:140](pii_detector/recognizers.py:140), [pii_detector/recognizers.py:207](pii_detector/recognizers.py:207), [pii_detector/recognizers.py:225](pii_detector/recognizers.py:225)

7. **Validation policy is inconsistent across recognizers.** The labeled VIN path accepts an invalid North American check digit while the shape path rejects it. `DOB: 99/99/9999`, `February 30, 2024`, and `999 years old` pass. GPS accepts `90.12345` latitude yet misses valid integer/two-decimal coordinates and longitude 180. Apply real date/range checks consistently; distinguish “looks sensitive” from “valid issued identifier.” Country-specific VIN/credit-score rules should be explicit policy, not universal assumptions. [pii_detector/recognizers.py:202](pii_detector/recognizers.py:202), [pii_detector/recognizers.py:219](pii_detector/recognizers.py:219)

8. **Noise filtering discards real organizations.** Raw spaCy results recognize NASA, IBM and 3M; default collapse removes all three because they are short uppercase names or contain digits. Replace blanket acronym/digit exclusions with evidence-sensitive filtering or a narrow tested denylist. [pii_detector/detector.py:96](pii_detector/detector.py:96)

9. **Current evaluation can overstate correctness.** `check_coverage` counts any overlapping entity; `eval_custom` accepts partial typed overlap and runs with collapse=False, unlike the deployed default. The sample generator selects candidates already detected above threshold, introducing circular selection bias. Keep independently annotated holdout fixtures, compare default API behavior, and report exact typed precision/recall, sensitive-character coverage and false positives per entity/locale. [tools/check_coverage.py:42](tools/check_coverage.py:42), [tools/eval_custom.py:64](tools/eval_custom.py:64), [tools/make_world_pii.py:58](tools/make_world_pii.py:58)

10. **Emoji shift the web tester's highlights.** API offsets count Python Unicode code points; `tools/web.py` passes them directly to JavaScript `text.slice`, which indexes UTF-16 code units. API spans for the emoji fixture are correct, but displayed highlights shift after a non-BMP character. Convert offsets or slice a code-point array, and document the offset contract. [tools/web.py:89](tools/web.py:89)

11. **Operational observability misses handled failures.** Detection exceptions become HTTP 500 rather than Lambda invocation errors, so the Lambda Errors alarm misses those failures. The API alarm requires five 5XX responses in five minutes. Emit an application failure metric and track per-stage latency, init duration, input size, active recognizers and throttling without logging input text. [handler.py:84](handler.py:84), [template.yaml:160](template.yaml:160)

## Low and scope-dependent

- An explicitly empty `entities` filter becomes all entities. Reject it as a 400 or define/document this behavior. [handler.py:55](handler.py:55), [pii_detector/detector.py:141](pii_detector/detector.py:141)
- Base64 decoding is outside guarded error handling; a malformed direct Lambda event can raise uncaught `binascii.Error`. Gateway normally generates this field, so this is event hardening. Existing `\xff` test uses valid Unicode `ÿ`, not malformed UTF-8. [handler.py:76](handler.py:76)
- CLI/file analysis cuts at 100,000 characters without overlap. A local boundary fixture loses a password when its label and value land in different chunks. The 20,000-byte API limit avoids this exact boundary. Use context overlap and offset-aware deduplication. [pii_detector/detector.py:135](pii_detector/detector.py:135)
- Collapse compares each candidate to every kept span: quadratic in dense results. This matters for larger files, but phone scanning is the demonstrated priority on current API-sized requests. [pii_detector/detector.py:122](pii_detector/detector.py:122)
- The registry advertises EMAIL and ID through generic NLP mappings although this English spaCy model has no EMAIL or ID output labels. Separate advertised mappings from actually supported model labels.
- API Gateway uses API-key gating with AuthorizationType NONE. If this becomes a multi-client production service, add an identity/authorization boundary. This audit did not test unauthorized access. [AWS guidance](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html).

## Speed results

Local medians use five sequential warm calls, except optimization comparisons which use three calls. Remote medians below use only HTTP 200 timings from the slower pass; 429 response times are excluded. Client round trips include network and API Gateway. Small counts are descriptive, not p95/p99 or load-test estimates.

| Workload | Local median | Deployed successful-response median | Successful remote runs |
|---|---:|---:|---:|
| short | 32.4 ms | 135.9 ms | 3/5 |
| user_sample | 260.5 ms | 781.9 ms | 4/5 |
| 20k_benign | 1057.8 ms | unmeasured: all throttled | 0/5 |
| 20k_dense | 2266.7 ms | 6289.7 ms | 2/5 |
| 20k_numeric | 3803.8 ms | 8451.8 ms | 5/5 |
| email_only | 28.7 ms | 173.8 ms | 1/5 |
| no_collapse | 260.6 ms | 746.5 ms | 3/5 |

The first supplied-sample request was 5.43 seconds; subsequent successful sample calls were around 0.78 seconds. A cold start is plausible but cannot be confirmed without Lambda init telemetry. Provisioned concurrency defaults to zero in the template. Actual deployed parameter overrides were not inspected.

In-memory optimization experiment:

| Workload | 245 regions | US/IN/GB/CA | Four regions + parser disabled |
|---|---:|---:|---:|
| user_sample | 261.9 ms | 70.2 ms | 65.1 ms |
| 20k_dense | 2271.1 ms | 636.2 ms | 576.8 ms |
| 20k_numeric | 3754.3 ms | 360.6 ms | 343.7 ms |

All main collapsed detection outputs stayed the same in this experiment; raw uncollapsed sample candidates changed. Four regions preserved tested international `+91`, `+44`, `+49`, `+33` numbers, but lost the national German `030 901820`. Therefore this is evidence for locale routing, not justification to permanently remove other countries. Parser disabling preserved this finite suite and provided a smaller additional gain. Context enhancement still needs tagger/lemmatizer; do not disable those without separate checks. [spaCy component guidance](https://spacy.io/usage/processing-pipelines).

## Suggested implementation order

1. Make this fixture suite a regression gate. Separate exact typing from redaction coverage, and explicitly settle policy-dependent cases such as malformed identifiers, hyphenated social handles, incomplete birth dates and punctuation in passwords.
2. Fix secret boundaries and containment-aware overlap handling. Support full PEM blocks, quoted/multiword secrets, escaped structured fields and long values.
3. Add locale/entity profiles and region-aware phone recognition. Re-run country-specific national and international phone cases; preserve a configurable broad mode.
4. Add structured-key normalization (snake/kebab/camelCase), better address coverage, salary formats and consistent validators. Expand UUID versions to the current RFC and test UUIDv6/v7/v8. [UUID standard](https://www.rfc-editor.org/rfc/rfc9562.html).
5. Tune per-entity thresholds on a holdout set and inspect decision explanations. A single global score is not calibrated across custom heuristics, checksums and spaCy. Keep context requirements for weak numeric shapes. [Presidio decision process](https://microsoft.github.io/presidio/analyzer/decision_process/).
6. Reduce unnecessary NLP components after corpus validation. Compare smaller models only if name/location recall stays within a chosen budget. Add a trained span-model fallback only for measured residual free-text misses; do not assume a larger model fixes regex truncation.
7. Tune Lambda memory and paid warm capacity after fixing the hot path, using real init/duration metrics. Align client throttling with measured deployed limits; do not treat 429 as a detector error.

## Reproduce and artifacts

Run from the project root:

```sh
.venv/bin/python -m unittest discover -s tests -t .
.venv/bin/python analysis/2026-10-12/build_cases.py
.venv/bin/python analysis/2026-10-12/evaluate.py --mode local
.venv/bin/python analysis/2026-10-12/stock_probe.py
.venv/bin/python analysis/2026-10-12/optimization_probe.py
```

For remote runs, provide PII_API_KEY through your environment and run `evaluate.py --mode remote`. Deployed throttles may be stricter than template defaults; the completion runner records bounded retries. Raw response data here contains only synthetic fixtures. The optimization script changes no source/config and its restricted-region setting is not a proposed production default.

- `cases.json`: hand-annotated main fixtures and accepted aliases.
- `local_results.json`, `remote_complete.json`: actual responses, offsets and exact/overlap scoring.
- `remote_initial_throttled.json`, `remote_results.json`: original attempts, including 429s.
- `stock_results.json`, `stock_cases.json`: independently seeded format probes and batch inputs.
- `extra_registry_results.json`: local diagnostics for remaining advertised types.
- `profile.txt`, `optimization_results.json`, `spot_checks.json`: runtime evidence and focused reproductions.
- `coverage.csv`: entity inventory and which diagnostics exercised each type.
- `../../graphify-out/graph.html`, `graph.json`, `GRAPH_REPORT.md`: code/document relationships. Large generated document inspection was bounded; extraction token usage is unavailable. Graph results are navigation aids; source and API measurements establish the findings above.

## Failing variant inventory

| Fixture | Expected value/type | Actual detections |
|---|---|---|
| lower_address | 742 evergreen terrace, springfield, il 62704 (ADDRESS) | springfield (LOCATION) |
| india_address | Flat 4B, 12 MG Road, Bengaluru, Karnataka 560001 (ADDRESS) | 12 MG Road, Bengaluru (ADDRESS); Karnataka (LOCATION); 560001 (DATE_TIME) |
| hindi_name | आरव शर्मा (PERSON) | none |
| short_password | abc (PASSWORD) | abc (ORGANIZATION) |
| dictionary_password | secret (PASSWORD) | none |
| quoted_passphrase | correct horse battery staple (PASSWORD) | none |
| punctuation_password | hunter2! (PASSWORD) | hunter2!. (PASSWORD) |
| escaped_password | pass\"word123! (PASSWORD) | pass\ (PASSWORD) |
| short_username | jo (USERNAME) | jo (PERSON) |
| hyphenated_social | @sarah-j89 (SOCIAL_HANDLE) | @sarah (SOCIAL_HANDLE) |
| plain_salary | 85000 (SALARY) | none |
| indian_salary | ₹12,50,000 (SALARY) | none |
| spaced_bank | 1234 5678 9012 (US_BANK_NUMBER) | 9012 (DATE_TIME) |
| hyphen_student | STU-123456 (STUDENT_ID) | none |
| alphanumeric_employee | E9AB12345 (EMPLOYEE_ID) | none |
| json_camel_birth | 1989-03-14 (DATE_OF_BIRTH) | 1989-03-14 (DATE_TIME) |
| json_camel_medical | MRN-00482913 (MEDICAL_RECORD_NUMBER) | none |
| polite_label | Sup3rS3cret!42 (PASSWORD) | actually (PASSWORD) |
| incomplete_dob | March 14 (DATE_OF_BIRTH) | March 14 (DATE_TIME) |
| uuid_v7 | 01890f3e-7c4a-7cc0-98c4-dc0c0c07398f (UUID) | none |
| integer_gps | 40, -74 (GPS_COORDINATES) | none |
| antimeridian_gps | 45.00000, 180.00000 (GPS_COORDINATES) | none |
| two_decimal_gps | 40.71, -74.00 (GPS_COORDINATES) | none |
| full_private_key | -----BEGIN PRIVATE KEY-----
QUJDREVGRw==
-----END PRIVATE KEY---- (PRIVATE_KEY) | -----BEGIN PRIVATE KEY----- (PRIVATE_KEY) |
| long_api_key | aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa (API_KEY) | aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa (API_KEY) |
| long_session | bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb (SESSION_ID) | bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb (SESSION_ID) |
| real_short_organizations | NASA (ORGANIZATION); IBM (ORGANIZATION); 3M (ORGANIZATION) | none |
| newborn_age | 0 (AGE) | none |
