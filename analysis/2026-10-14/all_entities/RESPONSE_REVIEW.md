# 125-entry response review

The user-supplied response contains 120 predictions with 107 distinct entity labels. It was compared with the exact formatted `payload.json` using standard-library JSON and the pure JSON scalar lexer. No model, Docker container or API call was run.

## Results

| Field outcome | Count |
|---|---:|
| Whole value with the intended label | 106 |
| LOCATION correctly split into city and country | 1 |
| Expected diagnostic alias (`EMAIL`/`ID`) | 2 |
| Sensible generic classification instead of country-specific label | 7 |
| Incorrect classification, value still covered | 3 |
| No detection | 6 |
| Total input fields | 125 |

There are 118 whole-value matches and one location whose two meaningful components are detected separately. Thus 119 fields have sensitive-value coverage, with 120 predictions because LOCATION produces two results. The comma/space between its components need not be considered undisclosed location content.

Every prediction's text equals the source slice at its offsets. Counts are internally consistent. No prediction includes a JSON key, crosses a value boundary or lies outside a scalar value. The complete private-key block is covered, including source escapes. Its decoded value contains actual newline separators.

## High: six missed values

| Target | Value |
|---|---|
| DE_PLZ | `98788` |
| ES_PASSPORT | `DRS053415` |
| IT_IDENTITY_CARD | `CG21881CN` |
| IT_PASSPORT | `DV9510996` |
| PH_TIN | `555-596-515-000` |
| UK_POSTCODE | `AB10 1XG` |

All six fixtures were marked below the default 0.5 threshold in the historical manifest. Threshold suppression is a plausible explanation, but this response alone does not establish the runtime cause.

## Medium: incorrect classifications

| Intended target | Returned label |
|---|---|
| KR_PASSPORT | US_PASSPORT |
| UK_NHS | PHONE_NUMBER |
| ZA_ID_NUMBER | CREDIT_CARD |

The full values are covered for redaction, but their classifications are wrong. Generic fallback is appropriate for seven other values: German, Indian and UK passports become PASSPORT_NUMBER; Indian GSTIN becomes TAX_ID_NUMBER; Nigerian and Thai national IDs become NATIONAL_ID_NUMBER; Nigerian registration becomes LICENSE_PLATE. These preserve the sensitive category while losing country specificity.

The EMAIL and ID diagnostic rows correctly return EMAIL_ADDRESS and NATIONAL_ID_NUMBER. The selected English models do not emit the registered EMAIL/ID mapping labels.

## Next checks

Repeat with `collapse=false` to see which country-specific candidates exist before priority selection. For each absent case, send its one-entry object using the exact `entities` filter. A lower diagnostic threshold can establish whether its pattern fires; compare against negative controls before changing production confidence rules. Do not lower the global production threshold merely to force a larger total.

No implementation changes were made. Full field-level results are in `response_review.json`.
