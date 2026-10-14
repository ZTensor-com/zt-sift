# JSON detection verification — 12 October 2026

The deployed implementation has JSON-specific false positives and false negatives. Its clean formatted profile result does not establish that schemas, arrays or minified JSON are handled safely.

## Scope and verification

- Tested commit `8187ab0` locally and the user-provided deployed `/dev/detect` endpoint.
- 36 requests: 16 positive JSON payloads, 10 strong negative JSON payloads, six policy cases, two API contract probes and two transport controls.
- 425 annotated source spans, including repeated profile/transport controls. These are synthetic fixtures, not a representative production accuracy benchmark.
- Minified and indented JSON; snake_case/camelCase/nested keys; key reordering; duplicate array values; escaped Unicode/passwords; complete and cross-field PEM templates; known organizations; application metadata, products, schema definitions and field-name lists.
- All 36 deployed status codes and full response JSON matched local responses. No unexpected HTTP statuses; all returned offsets round-trip to the original analyzed text. Rate-limit pauses were outside recorded request times; credentials are environment inputs and absent from artifacts.
- No production code, deployment settings, paid capacity or AWS resources changed. The audit files are new and uncommitted.

## False positives on JSON with no intended PII

**Five of ten strong negative cases returned detections, totaling seven detections.** Five pairs are counted separately for minified/formatted variants. Policy cases are excluded from this number.

| Payload | Minified output | Formatted output |
|---|---|---|
| Application metadata/counters | none | none |
| Product price, stock, quantity, currency | none | LOCATION=`USD` |
| Help text and an array of field labels | PASSWORD=`,` | PASSWORD=comma plus indentation whitespace |
| Non-sensitive keys such as `customerNumbering`, `tokenCount`, `sessionTimeout` | none | none |
| JSON Schema properties and required-field names | PASSWORD=`{` and PASSWORD=`,` | PASSWORD=`{` and PASSWORD=comma plus whitespace |

The array/schema results are clear false positives: a delimiter or object-opening brace is reported as a secret. These do not depend on deciding whether a weak credential or malformed ID should be protected.

Example schema fixture:

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

This returns two PASSWORD detections: `{` after the password property and the comma/whitespace between required-field names. No password value exists in this object.

## Cross-field detections

A PEM template whose header and footer are separate values causes a single PRIVATE_KEY result to bridge keys and unrelated data, in both formats:

```json
{
  "templateHeader": "-----BEGIN PRIVATE KEY-----",
  "description": "test fixture template only",
  "templateFooter": "-----END PRIVATE KEY-----"
}
```

The matched text includes the `description` and `templateFooter` keys and the intervening punctuation. Header-only recognition is allowed by the existing policy; treating separate JSON values as one key block is incorrect. Masking this result can erase unrelated content or JSON syntax.

The timestamp policy fixture also produces a cross-field DATE_TIME in minified JSON:

```json
{"createdAt":"2026-10-12T01:10:40Z","duration":"45 minutes","deadline":"Tuesday"}
```

Alongside the full timestamp, the API returns DATE_TIME=`10-12T01:10:40Z","duration":"45`. Whether an operational timestamp is personal data is a policy question; spanning a key and part of another field is a boundary failure regardless.

The math policy fixtures produce a GPS pair across two array numbers. That is structurally different: a coordinate pair is inherently two values, so it is not automatically an erroneous boundary. Without schema context, genuine coordinates and identical mathematical numbers are ambiguous.

## Positive JSON results and formatting effects

| Profile | Exact expected spans, minified | Exact expected spans, formatted |
|---|---:|---:|
| Full snake_case profile | 49/50 | 50/50 |
| Equivalent camelCase profile | 45/50 | 46/50 |
| Full profile with reversed key order | 49/50 | 50/50 |
| Duplicate emails/username overlap | 3/3 | 3/3 |
| Escaped Unicode/password values | 2/2 | 2/2 |
| Complete PEM with escaped newline characters | 1/1 | 1/1 |
| Real organization values: NASA, IBM, 3M, BBC, AMD | 0/5 | 3/5 |

These figures measure expected-span recall, not precision. The formatted escaped-Unicode fixture returns three detections for two expected spans: an extra ORGANIZATION covers the literal JSON escape sequence `\ud83d\ude00` (offsets 13–25, score 0.85). Organization recall is evaluated under the currently enabled entity scope; future inclusion should follow the product's sensitivity policy.

The full minified profile misses PERSON=`Sarah Johnson`. The name is detected when indented. The same occurs in the reversed and camelCase profiles. A smaller exploratory nested-name object also reproduces this formatting dependence locally.

The camelCase profile additionally misses four fields in both formats:

- `workAndSchool.nursingLicenseNumber` → PROFESSIONAL_LICENSE.
- `documents.passportNumber` → US_PASSPORT/PASSPORT_NUMBER.
- `documents.idCardNumber` → NATIONAL_ID_NUMBER.
- `vehicleAndDevice.deviceSerialNumber` → SERIAL_NUMBER.

Thus the current camelCase handling covers a subset of keys, not all existing labeled-recognizer aliases and qualifiers.

Identical full-profile text was sent under both valid transports. Minified results stayed 49/50; formatted results stayed 50/50. This isolates formatting/tokenization effects from Content-Type/envelope handling.

## Policy results, kept separate

- `sid: "0"` → SESSION_ID and `secret: "changeme"` → API_KEY. A default credential can still be an actual secret; these are not automatically false positives.
- Null, `none` and `unavailable` credential markers were not detected in the tested placeholder fixture.
- Mathematical numeric pairs that look exactly like coordinates can trigger GPS_COORDINATES. The formatted numeric policy case also reports a large integer as DATE_TIME.
- Operational timestamps can be DATE_TIME by the existing generic-date policy. Their sensitivity needs application context; the cross-field timestamp span above is still a concrete structural problem.

## API contract

The API does **not** accept an arbitrary customer object directly as `application/json`. It accepts either:

1. Raw serialized business JSON with `Content-Type: text/plain`, or
2. `Content-Type: application/json` with `{"text": "<serialized business JSON>"}`.

The raw object `{"email":"jane@example.com"}` under `application/json` returned the expected 400. The wrapper returned 200 and detected the email. This 400 is input-contract enforcement, not a false negative in detection.

## Root cause and recommended next work

The structured-field recognizer preserves some field values correctly, but generic regex and spaCy recognition still run over the whole JSON source. Credential prose rules can mistake array contents or schema property names for labels and consume adjacent syntax. Whole-source PEM/date recognizers can bridge independent fields. Raw minified JSON also changes NLP tokenization and therefore name/organization predictions.

Prioritize a JSON-aware path that distinguishes keys, primitive values, objects and arrays. Apply credential rules to actual instance values; constrain single-field secrets/dates to their source value boundaries; preserve original escape/Unicode offset mapping; retain explicit exceptions for inherently multi-part data such as coordinates. Expand normalized-key alias coverage without treating every schema key as a disclosed value.

Add exact-result negative controls for schemas/field-name lists, no-key/no-cross-field assertions for single-field entities, formatting-invariance checks, and complete-span precision/recall. Genuine contextual prose inside a JSON string still needs prose detection. No blanket removal of all acronyms or all NLP spans is implied.

## Artifacts and reproduction

- `build_cases.py`: fixture builder and source-location JSON walker.
- `cases.json`: exact request bodies, analyzed text, gold spans, key/value intervals and policy notes.
- `run.py`: local and bounded remote runner; remote key is read from `PII_API_KEY`.
- `local_results.json`, `remote_results.json`: original detections, exact match/coverage results, keys and cross-field classifications.

From the project root:

```sh
.venv/bin/python analysis/2026-10-12/json_validation/build_cases.py
.venv/bin/python analysis/2026-10-12/json_validation/run.py --mode local
# With PII_API_KEY already supplied securely in the environment:
.venv/bin/python analysis/2026-10-12/json_validation/run.py --mode remote
```
