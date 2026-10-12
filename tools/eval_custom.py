#!/usr/bin/env python3
"""Measure the custom recognizers against the known values in samples/world_pii_complete.json.

Takes the first N person records and organizations from the big file, writes them out as JSON text, runs the
detector at threshold 0.5, and checks for each known field whether the intended entity was found on its value.
Also counts ADDRESS detections that do not overlap any known address (possible false positives).

    python -m tools.eval_custom            # 40 people
    python -m tools.eval_custom --people 100
"""
import argparse
import json
import sys
import time
from collections import Counter, defaultdict

from pii_detector.detector import detect, load_analyzer

# (path into a person record, entity expected on that value)
FIELDS = [
    (("contact", "address", "street"), "ADDRESS"), (("date_of_birth",), "DATE_OF_BIRTH"),
    (("financial", "credit_card", "cvv"), "CARD_CVV"), (("financial", "credit_card", "expiry"), "CARD_EXPIRY"),
    (("digital", "username"), "USERNAME"), (("digital", "password"), "PASSWORD"), (("digital", "api_key"), "API_KEY"),
    (("digital", "access_token"), "AUTH_TOKEN"), (("digital", "imei"), "IMEI"), (("digital", "device_id"), "UUID"),
    (("digital", "geolocation"), "GPS_COORDINATES"), (("digital", "social_handle"), "SOCIAL_HANDLE"),
    (("employment", "employee_id"), "EMPLOYEE_ID"), (("education", "student_id"), "STUDENT_ID"),
    (("financial", "annual_salary"), "SALARY"), (("demographics", "gender"), "GENDER"),
    (("contact", "address", "zip_code"), "US_ZIP_CODE"), (("financial", "bank_account_number"), "US_BANK_NUMBER"),
    (("demographics", "age"), "AGE"), (("demographics", "ethnicity"), "ETHNICITY"), (("demographics", "marital_status"), "MARITAL_STATUS"),
    (("demographics", "sexual_orientation"), "SEXUAL_ORIENTATION"), (("demographics", "credit_score"), "CREDIT_SCORE"),
    (("demographics", "religion"), "RELIGION"), (("demographics", "political_affiliation"), "POLITICAL_AFFILIATION"),
    (("documents", "passport_number"), "PASSPORT_NUMBER"), (("documents", "national_id_number"), "NATIONAL_ID_NUMBER"),
    (("documents", "driver_license_number"), "DRIVER_LICENSE_NUMBER"), (("documents", "tax_id_number"), "TAX_ID_NUMBER"),
    (("documents", "professional_license_number"), "PROFESSIONAL_LICENSE"), (("employment", "ein"), "US_EIN"),
    (("accounts", "customer_id"), "ACCOUNT_ID"), (("accounts", "device_serial_number"), "SERIAL_NUMBER"),
    (("health", "medical_record_number"), "MEDICAL_RECORD_NUMBER"), (("health", "insurance_policy_number"), "INSURANCE_ID"),
    (("health", "admission_date"), "ADMISSION_DATE"), (("health", "discharge_date"), "DISCHARGE_DATE"),
    (("digital", "session_id"), "SESSION_ID"), (("financial", "ethereum_wallet"), "CRYPTO"), (("financial", "swift_bic"), "SWIFT_BIC"),
    (("vehicle", "vin"), "VIN"), (("vehicle", "license_plate"), "LICENSE_PLATE"), (("biometrics", "fingerprint_template_hash"), "BIOMETRIC_ID"),
    (("contact", "mobile_us"), "PHONE_NUMBER"),
]


def dig(record, path):
    for key in path:
        record = record[key]
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--people", type=int, default=40)
    parser.add_argument("--no-custom", action="store_true", help="measure Presidio without the custom recognizers")
    args = parser.parse_args()
    with open("samples/world_pii_complete.json", encoding="utf-8") as handle:
        source = json.load(handle)
    people = source["people"][: args.people]
    subset = {"people": people, "organizations": source["organizations"][: max(5, args.people // 5)],
              "free_text_messages": source["free_text_messages"][: min(len(people), len(source["free_text_messages"]))]}
    text = json.dumps(subset, ensure_ascii=False, indent=1)
    analyzer = load_analyzer(custom=not args.no_custom)
    detect(analyzer, "warm-up")
    started = time.time()
    found = detect(analyzer, text, 0.5)
    seconds = time.time() - started
    print(f"{len(people)} people + {len(subset['organizations'])} organizations = {len(text):,} characters; {len(found):,} detections in {seconds:.1f} s\n")

    hits, totals, misses = Counter(), Counter(), defaultdict(list)
    anchors = [text.index(f'"record_id": "{p["record_id"]}"') for p in people] + [len(text)]
    for i, person in enumerate(people):
        block_start, block_end = anchors[i], anchors[i + 1]
        for path, entity in FIELDS:
            try:
                raw = dig(person, path)
            except KeyError:
                continue                       # US-only or optional fields are absent from some records
            value = str(raw)
            encoded = json.dumps(raw, ensure_ascii=False)          # numbers stay unquoted in the file
            needle = f'"{path[-1]}": {encoded}'
            at = text.find(needle, block_start, block_end)
            totals[entity] += 1
            if at < 0:
                continue
            start = at + len(needle) - len(encoded) + (1 if isinstance(raw, str) else 0)
            end = start + len(value)
            if any(d["entity"] == entity and d["start"] < end and start < d["end"] for d in found):
                hits[entity] += 1
            elif len(misses[entity]) < 3:
                seen = sorted({d["entity"] for d in found if d["start"] < end and start < d["end"]})
                misses[entity].append(f"{value!r} (found as {seen or 'nothing'})")
    # Dates of birth appear inside the narrative messages ("born on 5 August 2005 (08/05/2005)").
    for message, person in zip(subset["free_text_messages"], people):
        long_date = person["birth"]["date_of_birth"]["long"]
        base = text.find(message[:60])
        start = base + message.index("born on " + long_date) + len("born on ")
        end = start + len(long_date)
        totals["DATE_OF_BIRTH"] += 1
        if any(d["entity"] == "DATE_OF_BIRTH" and d["start"] < end and start < d["end"] for d in found):
            hits["DATE_OF_BIRTH"] += 1
        elif len(misses["DATE_OF_BIRTH"]) < 3:
            misses["DATE_OF_BIRTH"].append(repr(long_date))
    print(f"{'entity':18} found  of  recall")
    for entity in sorted(totals):
        print(f"{entity:18} {hits[entity]:5} {totals[entity]:3}  {hits[entity] / totals[entity]:5.0%}   " + ("; ".join(misses[entity][:2]) if misses[entity] else ""))

    addresses = [(text.find(str(dig(p, ("contact", "address", "street")))), str(dig(p, ("contact", "address", "street")))) for p in people]
    addresses += [(text.find(o["address"]), o["address"]) for o in subset["organizations"]]
    known = [(i, i + len(v)) for i, v in addresses if i >= 0]
    for message, person in zip(subset["free_text_messages"], people):        # addresses written out in the narratives
        street = person["contact"]["address"]["street"]
        base = text.find(message[:60])
        if base >= 0 and street in message:
            known.append((base + message.index(street), base + message.index(street) + len(street)))
    org_hit = sum(1 for o in subset["organizations"] if any(d["entity"] == "ADDRESS" and d["start"] < text.find(o["address"]) + len(o["address"]) and text.find(o["address"]) < d["end"] for d in found))
    stray = [d for d in found if d["entity"] == "ADDRESS" and not any(d["start"] < b and a < d["end"] for a, b in known)]
    print(f"\norganization addresses found: {org_hit} of {len(subset['organizations'])}")
    print(f"ADDRESS detections outside any known address: {len(stray)} of {sum(1 for d in found if d['entity'] == 'ADDRESS')}")
    for d in stray[:8]:
        print("   ", d["score"], repr(d["text"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
