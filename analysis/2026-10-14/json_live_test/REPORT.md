# Live structured JSON test — 14 October 2026

Six requests were sent to the existing deployed `/dev/detect` endpoint. Each used `application/json` with the current supported envelope `{"text":"<serialized business JSON>"}`. The image was manually transcribed into a valid JSON object; this tests detection on its contents, not OCR. The spelling `Newyork` was preserved. Default query settings were used. No production code, deployment or AWS configuration was changed.

## Image payload

| Target | Minified | Formatted |
|---|---:|---:|
| Eight first/last name values | 0/8 | 5/8 |
| Four ages | 4/4 | 4/4 |
| Address | 1/1 | 1/1 |
| Phone | 1/1 | 1/1 |
| Total for these 14 target values | 6/14 | 11/14 |
| Company organization (separate scope) | Missed | Missed |

The formatted response finds John, Mary, Smith, Sally and Jim. It misses Doe, Green and Galley. Both variants miss ORGANIZATION for True Value Corporation. No unrelated extra detections were observed in these two responses.

The first response took 17,064.65 ms end to end; the second took 190.77 ms. A cold start is possible, but cannot be established without Lambda telemetry.

## Independent positive payload

The synthetic nested profile has 12 target values: first name, last name, age, email, phone, passport, national ID, nursing license, device serial, username, password and session ID.

- Minified: 6/12 exact target values detected.
- Formatted: 8/12 detected.
- Both miss passportNumber, idCardNumber, nursingLicenseNumber and deviceSerialNumber.
- Minified also misses Sarah and Johnson; formatted detects both.
- Both detect the punctuation-leading password `,{Sup3rSecret!}` correctly, supporting the need to preserve legitimate punctuation in secrets.
- No unrelated extra detections were observed in these responses.

## Independent negative payload

The payload describes a schema and ordinary product metadata, with no disclosed credentials.

- Minified: two false PASSWORD detections, covering `{` and `,`.
- Formatted: three false detections: PASSWORD covering `{`, PASSWORD covering comma plus indentation, and LOCATION covering `USD`.

All six requests returned HTTP 200. Every returned source span matches the analyzed text at its reported offsets. The five subsequent requests took 165.06–193.34 ms end to end. This is a small sequential sample, not a latency percentile benchmark or an estimate of general accuracy.

## Conclusion

The deployment detects several labeled JSON values, but name recognition still depends heavily on serialization and camelCase aliases remain incomplete. JSON syntax is still misinterpreted as credential content. These results support value-aware JSON handling with normalized field aliases and source boundary checks before relying on the service for predominantly structured input.

The input variants, full responses and a reproducible runner are stored alongside this report. The runner reads its API key from an environment variable; no key is saved in artifacts.
