#!/usr/bin/env python3
"""Run Presidio over a big test file and report, per entity type, how many detections it produced.

    python -m tools.check_world_pii samples/world_pii_complete.json
    python -m tools.check_world_pii samples/world_pii_complete.txt --out report.json

The page https://presidio.dataprivacystack.org/supported_entities/ lists 72 pattern/NER entities (plus 8
medical-NER ones that need a model download and are not covered here). The table marks each one, shows counts at the
default threshold 0.5 and at 0.3 (Presidio's loosest patterns cannot reach 0.5 even with context), and flags any
that were never detected.
"""
import argparse
import json
import sys
import time
from collections import Counter

from pii_detector.recognizers import CUSTOM_ENTITIES
from pii_detector.detector import detect, load_analyzer

PAGE_ENTITIES = """CREDIT_CARD CRYPTO DATE_TIME EMAIL_ADDRESS IBAN_CODE IP_ADDRESS MAC_ADDRESS NRP LOCATION PERSON PHONE_NUMBER MEDICAL_LICENSE URL
US_BANK_NUMBER US_DRIVER_LICENSE US_ITIN US_MBI US_NPI US_PASSPORT US_SSN UK_DRIVING_LICENCE UK_NHS UK_NINO UK_PASSPORT UK_POSTCODE
UK_VEHICLE_REGISTRATION ES_NIF ES_NIE ES_PASSPORT IT_FISCAL_CODE IT_DRIVER_LICENSE IT_VAT_CODE IT_PASSPORT IT_IDENTITY_CARD PL_PESEL SG_NRIC_FIN
SG_UEN AU_ABN AU_ACN AU_TFN AU_MEDICARE IN_PAN IN_AADHAAR IN_VEHICLE_REGISTRATION IN_VOTER IN_PASSPORT IN_GSTIN FI_PERSONAL_IDENTITY_CODE
KR_DRIVER_LICENSE KR_FRN KR_PASSPORT KR_BRN KR_RRN TH_TNIN NG_NIN NG_VEHICLE_REGISTRATION PH_TIN CA_SIN SE_ORGANISATIONSNUMMER SE_PERSONNUMMER
ZA_ID_NUMBER TR_NATIONAL_ID TR_LICENSE_PLATE DE_TAX_ID DE_TAX_NUMBER DE_PASSPORT DE_ID_CARD DE_SOCIAL_SECURITY DE_HEALTH_INSURANCE DE_KFZ
DE_HANDELSREGISTER DE_PLZ""".split()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file")
    parser.add_argument("--out", help="also write the detections and counts to this JSON file")
    args = parser.parse_args()
    with open(args.file, encoding="utf-8") as handle:
        text = handle.read()
    print(f"{args.file}: {len(text):,} characters", flush=True)
    analyzer = load_analyzer()
    detect(analyzer, "warm-up", 0.5)
    started = time.time()
    found = detect(analyzer, text, 0.3)
    seconds = time.time() - started
    at05 = Counter(d["entity"] for d in found if d["score"] >= 0.5)
    at03 = Counter(d["entity"] for d in found)
    print(f"{len(found):,} detections at >= 0.3 ({sum(at05.values()):,} at >= 0.5) in {seconds:.0f} s\n")
    print(f"{'entity (from the Presidio page)':34} {'>= 0.5':>8} {'>= 0.3':>8}")
    missing = []
    for entity in PAGE_ENTITIES:
        flag = "" if at03[entity] else "   <-- NEVER DETECTED"
        if not at03[entity]:
            missing.append(entity)
        print(f"{entity:34} {at05[entity]:8} {at03[entity]:8}{flag}")
    custom_only = [e for e in CUSTOM_ENTITIES if e not in PAGE_ENTITIES]
    print(f"\n{'custom entity (pii_detector/recognizers.py)':34} {'>= 0.5':>8} {'>= 0.3':>8}")
    for entity in custom_only:
        flag = "" if at03[entity] else "   <-- NEVER DETECTED"
        if not at03[entity]:
            missing.append(entity)
        print(f"{entity:34} {at05[entity]:8} {at03[entity]:8}{flag}")
    shared = [e for e in CUSTOM_ENTITIES if e in PAGE_ENTITIES]
    print("(custom rules for entities Presidio also has, so counted above:", ", ".join(shared) + ")")
    known = set(PAGE_ENTITIES) | set(CUSTOM_ENTITIES)
    extras = {e: n for e, n in at03.items() if e not in known}
    print("\nOther entity types reported:", ", ".join(f"{e} {n}" for e, n in sorted(extras.items(), key=lambda kv: -kv[1])))
    total = len(PAGE_ENTITIES) + len(custom_only)
    print(f"\n{total - len(missing)} of {total} entities ({len(PAGE_ENTITIES)} from the Presidio page, {len(custom_only)} custom) were detected at least once; "
          f"{sum(1 for e in PAGE_ENTITIES + custom_only if at05[e])} of them at the default threshold 0.5.")
    if missing:
        print("Never detected:", ", ".join(missing))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump({"counts_0_5": at05, "counts_0_3": at03, "detections": found}, handle, ensure_ascii=False)
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
