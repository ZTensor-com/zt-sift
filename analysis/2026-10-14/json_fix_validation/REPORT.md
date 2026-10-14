# Structured JSON fix verification — 14 October 2026

The local implementation now uses field-aware JSON value boundaries. The implementation and regression tests are saved in commit `49d174e` (`fix: analyze structured JSON values with source offsets`); the previous implementation is commit `8187ab0`. No AWS deployment, model, memory, provisioned concurrency or API contract changes were made.

## Implementation

- Valid object/array JSON within the existing 100,000-character chunk limit is scanned into scalar source intervals. String escapes are decoded for recognition and each decoded character maps back to its original interval, including surrogate pairs.
- Pattern recognizers scan a joined corpus once; candidates outside a single value are rejected before per-value context enhancement. NLP is batched for values requiring it. Explicit name/company labels and full-value typed matches avoid unnecessary NER, subject to the requested entity filter.
- First/last/middle/full names and company-name fields receive contextual classifications. Generic `name` is label-classified only under person-related parents.
- Missing passport, ID-card, nursing-license, device-serial and contact-number aliases are recognized. The new identifier aliases retain the existing prose rules' shape constraints.
- Escaped lone surrogates no longer fail NLP. Numeric ages in exponent/decimal notation are classified as complete values when integral and within bounds; fractional/out-of-bounds ages are rejected.
- Malformed and oversized JSON retain the previous text/chunk path. The HTTP envelope remains `{"text":"..."}` for `application/json`; business JSON may also be submitted as `text/plain`.

## Independent baseline and final candidate

| Check | Baseline | Fixed candidate |
|---|---:|---:|
| Existing JSON audit, expected source spans | 404/425 | 425/425 |
| Strong JSON negatives, total false detections across ten cases | 7 | 0 |
| JSON detections overlapping keys | Present | 0 |
| JSON detections crossing value boundaries | Present | 0 |
| Earlier 128-case audit, exact expected spans | 191/195 | 191/195 |
| Image minified, personal values excluding company | 6/14 | 14/14 |
| Image formatted, personal values excluding company | 11/14 | 14/14 |
| Image company | Missed | Detected in both formats |
| New positive payload, minified | 6/12 | 12/12 |
| New positive payload, formatted | 8/12 | 12/12 |
| New negative payload, minified/formatted false detections | 2 / 3 | 0 / 0 |

The final candidate has no unmatched detections in the JSON positive fixtures. Policy cases still return the legitimate ISO timestamp, `sid=0` and `secret=changeme`; those are not counted as strong-negative failures. Source offsets are valid throughout both audit suites. API statuses are unchanged from the baseline, including rejection of empty entity filters; one historical fixture still expects the outdated HTTP 200 for that request.

The original four misses in the 128-case audit remain unchanged: complete Indian-address coverage, unlabeled Hindi name recognition in English prose, terminal punctuation in an unquoted prose password, and a platform-specific hyphenated social handle. This fix does not resolve every PII format or language.

## Tests and review

- 44 unit tests pass in the local project environment.
- The same 44 tests pass in the existing Python 3.12 Linux/amd64 Lambda-compatible image with the final workspace mounted read-only, UID/GID 1051, and networking disabled. This checks code/runtime compatibility; a new deployable image still needs to be built.
- 14 independent holdout variants pass: Unicode-escaped names, labeled Hindi names, emoji and punctuation secrets, duplicate values, embedded prose, nested JSON strings and contextual phone/address recognition. Entity-filter, threshold and scalar-type negative controls also pass.
- Review identified and verified fixes for lone-surrogate crashes, partial exponent ages, requested-PERSON detection in credential fields, and malformed phone fields containing prose.
- `git diff --check` passes.

## Local runtime observations

Three sequential runs per workload, measured on this machine; these are not Lambda benchmarks and should not be interpreted as production percentiles.

| Workload | Text bytes | Baseline median | Fixed median |
|---|---:|---:|---:|
| 190 person records | 15,212 | 352.29 ms | 391.65 ms |
| 300 metadata records | 14,410 | 289.08 ms | 439.08 ms |

The person workload now detects 760 values versus 380 previously, recovering the missing names. The new path adds modest absolute latency in these samples; it does not demonstrate a speed improvement over the baseline. An abandoned per-value pattern scan took tens of seconds and was replaced with one corpus scan before delivery.

## Remaining limits and deployment

Field aliases target primitive leaves, including array elements. A nested wrapper such as `{"passportNumber":{"number":"..."}}` does not automatically inherit passport semantics. Generic text recognition, organization sensitivity, ignored string sentinels such as `none`/`null`, and unknown schemas still follow existing policy or heuristics. All consumers should redact the union of returned source intervals.

The deployed API still runs its prior image. Build/deploy the fixed source and rerun the live six-case test before asserting production verification. The baseline and candidate responses, timing samples and independent runner are saved next to this report; credentials are not saved.
