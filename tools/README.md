# Dev tools: manual test page, coverage checks and sample generators

Run everything from the project root with `.venv/bin/python -m tools.<name>` (the detector itself is `python -m pii_detector`).

## What the detector does

Shows what Presidio detects on its own. **By default every pattern recognizer in the installed Presidio is
switched on** (82 entity types, including all 72 non-medical ones listed at
https://presidio.dataprivacystack.org/supported_entities/). Presidio's stock English registry covers only 23 of them;
the country-specific recognizers (UK, Spain, Italy, Germany, India, Korea, ...) are disabled or registered for other
languages. Use `--english-registry` for the stock 23. The 8 `MEDICAL_*` entities are not included: they need
Presidio's transformers extra and a downloaded model. Context words of non-English recognizers stay in their own
language (for example German "steuer-id"), so those entities score lower in English text without such words. It uses the
project's existing `.venv` (Presidio 2.2.364, spaCy 3.8.16, `en_core_web_lg` 3.8.0), so nothing is downloaded.

## Custom entities (`pii_detector/recognizers.py`)

On by default (`--no-custom` leaves them out). Built the way Presidio's
[adding recognizers](https://presidio.dataprivacystack.org/analyzer/adding_recognizers/) page describes: `PatternRecognizer`
for values recognisable by shape, and a `LocalRecognizer` subclass for values recognisable only from the label in
front of them ("password is ...", `"cvv": "022"`), which reports just the value.

| Entity | What it finds |
|---|---|
| `ADDRESS` | US street addresses (with unit, city, state, ZIP), PO boxes, "City, ST ZIP", UK, Canadian, German, French, Spanish and Italian styles |
| `PASSWORD`, `USERNAME`, `API_KEY`, `AUTH_TOKEN`, `PRIVATE_KEY`, `SESSION_ID`, `SOCIAL_HANDLE` | "password is ...", "username: ...", AWS, GitHub, Stripe, Slack and Google keys, JWTs, PEM headers, session and cookie IDs, `@handles` |
| `CARD_CVV`, `CARD_EXPIRY`, `CREDIT_SCORE`, `SWIFT_BIC`, `CRYPTO` (Ethereum) | value after "CVV", "expiry", "credit score", "SWIFT code"; `0x...` wallets |
| `US_PASSPORT`, `PASSPORT_NUMBER`, `US_BANK_NUMBER`, `US_EIN`, `US_ZIP_CODE`, `US_ALIEN_NUMBER`, `PHONE_NUMBER` (extra rule) | labelled US documents and numbers that Presidio scores below 0.5 or rejects; US-format phones such as `212-555-0187` |
| `NATIONAL_ID_NUMBER`, `DRIVER_LICENSE_NUMBER`, `PROFESSIONAL_LICENSE`, `TAX_ID_NUMBER` | the same idea for any country, found after their labels |
| `DATE_OF_BIRTH`, `DATE_OF_DEATH`, `ADMISSION_DATE`, `DISCHARGE_DATE`, `AGE`, `SALARY` | dates and numbers after labels such as "born on", "died on", "admitted on", "age", "salary" |
| `GENDER`, `ETHNICITY`, `MARITAL_STATUS`, `SEXUAL_ORIENTATION`, `RELIGION`, `POLITICAL_AFFILIATION` | the value after its label ("religion: Buddhist") |
| `EMPLOYEE_ID`, `STUDENT_ID`, `ACCOUNT_ID`, `MEDICAL_RECORD_NUMBER`, `INSURANCE_ID` | internal identifiers after "employee ID", "customer ID", "MRN", "policy number" and similar |
| `VIN`, `IMEI`, `GPS_COORDINATES`, `UUID`, `LICENSE_PLATE`, `SERIAL_NUMBER`, `BIOMETRIC_ID` | check-digit-validated VIN and IMEI, decimal coordinates, UUIDs, plates, serial numbers and fingerprint or face-template hashes |

Heuristics, not magic: an address needs a number, a capitalised name and a street word (a bare "4 Main Street" scores 0.45 and
needs a context word such as "address" or "lives at" to pass 0.5); labelled values are only found when the label is next to
them (`"password": "..."` works, a value several fields away from its label does not, so a nested
`"date_of_birth": {"us": "..."}` is not found while `"dob": "..."` is). Words after a label such as "reset" or "required" are rejected.

```bash
python -m unittest discover -s tests -t .             # 28 tests (21 recognizers + 7 handler)
python -m tools.gap_audit                              # 73 PII categories from HIPAA, GDPR and others
python -m tools.eval_custom                           # recall against the big JSON's known values (about 20 s)
```

Measured on 30-60 people from `world_pii_complete.json`: 100% recall for every one of the 44 custom entities it checks, 100% for
dates of birth in both JSON and narrative form, and every address (people and organizations) found, none outside a known address.
On the five US test documents Presidio now produces a result for 50 of 50 expected items, up from 36 without the custom rules.

### What is still missing

`tools/gap_audit.py` tests 73 kinds of PII drawn from HIPAA's 18 identifiers, GDPR special categories, online identifiers, financial data and
identity documents. Result: **70 of 73 detected**. Without the custom recognizers it was 58. The 3 it cannot find are **health conditions,
medications and criminal records**: they are free-form phrases with no label or shape, so they need a trained model (for example GLiNER),
not rules. Also not covered: names in non-Latin scripts (the English spaCy model), a trade-union membership phrase, biometric or genetic
data that is not text, photos and voice, and any value that sits far from its label. Presidio's 8 `MEDICAL_*` entities need its transformers
extra and a downloaded model and are not enabled.

Paste-ready samples with every custom entity: `samples/us_custom_entities.txt` and `samples/us_custom_entities.json`.

## Try it by hand in the browser

```bash
python -m tools.web        # then open http://127.0.0.1:8765  (Ctrl+C stops it)
```

Paste or type text, press Detect (or Ctrl/Cmd + Enter), and the detections are highlighted in place and
listed in a table with entity, text, start, end, score and the recognizer that found it. "Load sample" fills in
a US test message. The page listens on this machine only and the text is not stored or logged. Set `PORT=9000`
to use a different port.

## The big test files

`samples/world_pii_complete.json` (1.4 MB) and `samples/world_pii_complete.txt` (0.83 MB, one line, no line breaks) cover **every
Presidio entity on the page and every custom entity**: 72 + 44 entity types, each detected at least once in both files. The older
`world_pii_big.json` and `.txt` (Presidio entities only) are kept as they were. The complete files hold
synthetic personal data of every kind:

- an entity catalog with examples of each of the 72 Presidio entity types, each checked against Presidio, plus
  names, places, nationalities, religions, political groups, dates, emails and names in other scripts
- 250 person records in the JSON (names, birth data, contact details, addresses, country-specific government IDs,
  payment cards and bank details, crypto wallets, usernames, passwords, API keys, tokens, IP and MAC addresses, IMEI,
  coordinates, employment, health, vehicle and biometric fields), 50 organizations with business IDs, 250 transactions,
  250 log lines and 50 free-text messages; the text file holds the same material as narrative paragraphs

Everything is made up: identifiers follow public format rules (with valid checksums where the format has one) and
belong to nobody; phone numbers are libphonenumber's documented example numbers. Passwords, API keys and tokens are
random strings in common formats, so a secret scanner may flag the files. Regenerate with
`python -m tools.make_world_pii` (deterministic; `--people N` changes the size, `--probe` checks formats).

```bash
python -m tools.check_world_pii samples/world_pii_complete.json   # per-entity counts; about 5 minutes
python -m tools.check_world_pii samples/world_pii_complete.txt    # about 3 minutes
python -m pii_detector --file samples/world_pii_complete.txt --collapse --threshold 0.5
```

Result: **all 72 entities on the Presidio page are detected in both files**; 61 at the default threshold 0.5 and
11 only below it (`US_BANK_NUMBER`, `US_PASSPORT`, `UK_PASSPORT`, `UK_POSTCODE`, `ES_PASSPORT`, `IT_PASSPORT`,
`IT_IDENTITY_CARD`, `IN_PASSPORT`, `KR_PASSPORT`, `PH_TIN`, `DE_PLZ`). Those are Presidio's own loosest patterns,
which start at a score of 0.05 to 0.1 and cannot reach 0.5 even with a context word. Lowering the threshold to 0.3
finds them but adds a lot of noise (for example `US_DRIVER_LICENSE` 82 to 2,256 hits and `PHONE_NUMBER` 1,253 to
8,000 in the text file). Large inputs are analysed in 100,000-character pieces and take about 2 minutes per
megabyte, so the browser page is slow on these files.

## Command line

```bash
python -m pii_detector "Call Sarah Johnson on (212) 555-0187"     # text as an argument
python -m pii_detector --file samples/sample_us.txt                # a file (stdin also works)
python -m pii_detector --file samples/sample_us.txt --collapse     # best result where results overlap
python -m pii_detector --file samples/sample_us.txt --threshold 0  # show every candidate
python -m pii_detector --list-entities                             # all 23 entity types Presidio knows
python -m tools.check_coverage                                              # expected-vs-found table, 5 US documents
```

Options: `--json`, `--entities PERSON,US_SSN` (restrict types), `--threshold 0-1` (default 0.5).
Add your own test documents in `tools/documents.py`.

## What it found on the five documents (threshold 0.5, 50 expected items)

Speed: about 8 ms per document, against 1-3 s for the GLiNER-based versions.

| Detected correctly, with the right type | Detected only as a different type | Not detected |
|---|---|---|
| names (`PERSON`), emails, SSN, ITIN, driver's license, credit card, crypto wallet, IP, MAC, URL | date of birth (`DATE_TIME`), street address (`LOCATION`, city and state only), routing numbers (`PHONE_NUMBER`, `DATE_TIME`), a bank account number (`UK_NHS`) | passport number, EIN, bank account number, card CVV, username, password, API key, tokens |

Phone numbers were missed in these documents because they use the fictional `555-01xx` range, which
libphonenumber rejects; real numbers are detected. Presidio also reports noise: acronyms such as SSN, EIN and
API as `ORGANIZATION`, and "Monday" or "5 PM" as `DATE_TIME`.
