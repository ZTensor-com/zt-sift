# All registered entity types: JSON probe

`payload.json` contains one labeled example for each of the 125 registered entity names. `minified.json` has identical JSON values with compact formatting. Both are below the API's 20,000-byte input limit.

These are synthetic detection fixtures. Identifier checksums and shapes do not establish real-world issuance or ownership. The key header/JWT/API-key examples are test strings, not usable credentials.

## Send to Lambda

Use the contents of `payload.json` directly as the request body and set **Content-Type: text/plain**, alongside your existing API key. Repeat with `minified.json`. For `application/json`, serialize this object into a string inside the existing `{"text":"..."}` envelope. Do not send the business object directly under `application/json`.

Compare results to `manifest.json`: each row identifies the target type, source JSON path, literal value, historical confidence information and known possible alternative classifications. Entity-name keys themselves should not be reported as data.

## 125 examples do not imply 125 exact predictions

- `EMAIL` and `ID` are registered NLP mapping labels but are not emitted by the configured English spaCy model. Their diagnostic values should instead yield `EMAIL_ADDRESS` and `NATIONAL_ID_NUMBER`. These two labels cannot be promised as reachable.
- Country identifiers share formats with generic identifiers. Default collapse can retain `TAX_ID_NUMBER` instead of `IN_GSTIN`, for example. Other unlisted collisions may occur as well.
- Some built-in examples historically scored below the default 0.5 threshold. Their low-score status is marked in the manifest. Context and the deployed model may change this result.
- To investigate an exact entity individually, send its one-entry object with `?entities=ENTITY_NAME&collapse=false`. For a below-threshold recognizer, use `&threshold=0.1` diagnostically; do not use lowered thresholds to declare production accuracy.
- Validate source coverage, classification and unexpected detections separately. One value can produce several nested/overlapping detections when collapse is disabled.

## Verification performed

Only lightweight standard-library checks ran: valid JSON, exactly 125 unique entries, identical formatted/minified values and UTF-8 byte counts. The older sample catalog supplied most synthetic identifiers and historical scores. Five new country recognizers were checked against installed source formats; LANR and German VAT checksums were generated using the source algorithms. **No spaCy model, Docker container or deployed API was run for this fixture.**

Rebuild with `python3 analysis/2026-10-14/all_entities/build_payload.py` from the repository root. No detector configuration or production code is modified.
