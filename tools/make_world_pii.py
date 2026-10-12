#!/usr/bin/env python3
"""Build two big synthetic test files containing every kind of PII Presidio knows, plus many it does not.

    python -m tools.make_world_pii --probe     # check each identifier format against Presidio and report
    python -m tools.make_world_pii             # write samples/world_pii_complete.json and samples/world_pii_big.txt

Every value is generated (see world_pii.py) and then checked: it is kept only if Presidio, given a sentence
with the recognizer's own context words, detects it as the intended entity. Output is deterministic.
"""
import argparse
import json
import random
import sys
import time

from pii_detector.detector import detect, load_analyzer
from tools import world_pii as W
from tools.world_pii import ENTITY_GENERATORS

PER_ENTITY = 6
TRIES = 600


def context_phrases(analyzer, entity):
    for recognizer in analyzer.registry.recognizers:
        if entity in recognizer.supported_entities and getattr(recognizer, "context", None):
            return [c for c in recognizer.context if c.replace(" ", "").replace("-", "").replace("_", "").isalpha()][:6] or ["id"]
    return ["id"]


def verify(analyzer, entity, value, lead, threshold=0.5):
    """Score Presidio gives this value, as the intended entity, inside a sentence with a context lead."""
    sentence = f"Please note the {lead} {value} for the record."
    start = sentence.index(value)
    best = 0.0
    for d in detect(analyzer, sentence, 0.0, [entity]):
        if d["entity"] == entity and d["start"] <= start + 1 and d["end"] >= start + len(value) - 1:
            best = max(best, d["score"])
    return best


def build_catalog(analyzer, rng, per_entity=PER_ENTITY, entities=None):
    catalog, report = {}, {}
    generators = ENTITY_GENERATORS()
    for entity, generate in generators.items():
        if generate is None or (entities and entity not in entities):
            continue
        leads = context_phrases(analyzer, entity)
        scored = []                                  # (score, value, lead) for every distinct candidate
        for attempt in range(TRIES):
            try:
                value = generate(rng)
            except Exception:
                continue
            if not value or any(value == v for _, v, _ in scored):
                continue
            lead = leads[len(scored) % len(leads)]
            scored.append((verify(analyzer, entity, value, lead), value, lead))
            strong = [x for x in scored if x[0] >= 0.5]
            if len(strong) >= per_entity:
                break
            # Presidio's loosest patterns (US passport, bank account, ...) cannot reach 0.5 even with context;
            # stop searching early and keep the best candidates, marked weak.
            if attempt >= 60 and not strong and len([x for x in scored if x[0] >= 0.3]) >= per_entity:
                break
        strong = sorted([x for x in scored if x[0] >= 0.5], key=lambda x: -x[0])[:per_entity]
        weak = not strong
        pool = strong or sorted([x for x in scored if x[0] >= 0.3], key=lambda x: -x[0])[:per_entity] or sorted(scored, key=lambda x: -x[0])[:1]
        good = [(v, lead, score) for score, v, lead in pool]
        catalog[entity] = good
        report[entity] = {"found": len(good), "best": round(max([g[2] for g in good] or [0]), 2), "weak": weak, "tries": attempt + 1}
    return catalog, report


LABELS = {
    "CREDIT_CARD": "credit card number", "CRYPTO": "Bitcoin wallet address", "IBAN_CODE": "IBAN", "IP_ADDRESS": "IP address",
    "MAC_ADDRESS": "MAC address", "PHONE_NUMBER": "phone number", "MEDICAL_LICENSE": "DEA medical license number", "URL": "profile URL",
    "US_BANK_NUMBER": "US bank account number", "US_DRIVER_LICENSE": "US driver license number", "US_ITIN": "ITIN", "US_MBI": "Medicare Beneficiary Identifier",
    "US_NPI": "National Provider Identifier (NPI)", "US_PASSPORT": "US passport number", "US_SSN": "Social Security Number (SSN)",
    "ABA_ROUTING_NUMBER": "ABA routing number", "UK_DRIVING_LICENCE": "UK driving licence number", "UK_NHS": "NHS number",
    "UK_NINO": "National Insurance number", "UK_PASSPORT": "UK passport number", "UK_POSTCODE": "postcode",
    "UK_VEHICLE_REGISTRATION": "UK vehicle registration", "ES_NIF": "Spanish NIF", "ES_NIE": "Spanish NIE", "ES_PASSPORT": "Spanish passport number",
    "IT_FISCAL_CODE": "codice fiscale", "IT_DRIVER_LICENSE": "Italian driver license", "IT_VAT_CODE": "partita IVA", "IT_PASSPORT": "Italian passport number",
    "IT_IDENTITY_CARD": "Italian identity card number", "PL_PESEL": "PESEL", "SG_NRIC_FIN": "NRIC", "SG_UEN": "Singapore UEN",
    "AU_ABN": "Australian Business Number (ABN)", "AU_ACN": "Australian Company Number (ACN)", "AU_TFN": "tax file number (TFN)",
    "AU_MEDICARE": "Australian Medicare number", "IN_PAN": "PAN", "IN_AADHAAR": "Aadhaar number", "IN_VEHICLE_REGISTRATION": "Indian vehicle registration",
    "IN_VOTER": "voter ID (EPIC)", "IN_PASSPORT": "Indian passport number", "IN_GSTIN": "GSTIN", "FI_PERSONAL_IDENTITY_CODE": "henkilötunnus",
    "KR_DRIVER_LICENSE": "Korean driver license number", "KR_FRN": "foreigner registration number", "KR_PASSPORT": "Korean passport number",
    "KR_BRN": "business registration number", "KR_RRN": "resident registration number", "TH_TNIN": "Thai national ID (TNIN)",
    "NG_NIN": "NIN", "NG_VEHICLE_REGISTRATION": "Nigerian vehicle registration", "PH_TIN": "Philippine TIN", "CA_SIN": "Social Insurance Number (SIN)",
    "SE_ORGANISATIONSNUMMER": "organisationsnummer", "SE_PERSONNUMMER": "personnummer", "ZA_ID_NUMBER": "South African ID number",
    "TR_NATIONAL_ID": "Turkish national ID (TCKN)", "TR_LICENSE_PLATE": "Turkish license plate", "DE_TAX_ID": "Steuer-ID", "DE_TAX_NUMBER": "Steuernummer",
    "DE_PASSPORT": "German passport number", "DE_ID_CARD": "Personalausweis number", "DE_SOCIAL_SECURITY": "Rentenversicherungsnummer",
    "DE_HEALTH_INSURANCE": "Krankenversicherungsnummer", "DE_KFZ": "Kfz-Kennzeichen", "DE_HANDELSREGISTER": "Handelsregister number", "DE_PLZ": "PLZ",
}
COUNTRY_IDS = {
    "United States": ["US_SSN", "US_PASSPORT", "US_DRIVER_LICENSE", "US_BANK_NUMBER", "ABA_ROUTING_NUMBER", "US_ITIN", "US_MBI", "US_NPI", "MEDICAL_LICENSE"],
    "United Kingdom": ["UK_NINO", "UK_NHS", "UK_PASSPORT", "UK_DRIVING_LICENCE", "UK_VEHICLE_REGISTRATION", "UK_POSTCODE"],
    "Germany": ["DE_TAX_ID", "DE_SOCIAL_SECURITY", "DE_HEALTH_INSURANCE", "DE_PASSPORT", "DE_ID_CARD", "DE_KFZ", "DE_PLZ", "DE_TAX_NUMBER"],
    "Spain": ["ES_NIF", "ES_NIE", "ES_PASSPORT"], "Italy": ["IT_FISCAL_CODE", "IT_DRIVER_LICENSE", "IT_PASSPORT", "IT_IDENTITY_CARD"],
    "Poland": ["PL_PESEL"], "India": ["IN_PAN", "IN_AADHAAR", "IN_VOTER", "IN_PASSPORT", "IN_VEHICLE_REGISTRATION"],
    "Australia": ["AU_TFN", "AU_MEDICARE"], "Canada": ["CA_SIN"], "Singapore": ["SG_NRIC_FIN"],
    "South Korea": ["KR_RRN", "KR_DRIVER_LICENSE", "KR_PASSPORT"], "Thailand": ["TH_TNIN"], "Nigeria": ["NG_NIN", "NG_VEHICLE_REGISTRATION"],
    "Philippines": ["PH_TIN"], "Sweden": ["SE_PERSONNUMMER"], "Finland": ["FI_PERSONAL_IDENTITY_CODE"],
    "Turkey": ["TR_NATIONAL_ID", "TR_LICENSE_PLATE"], "South Africa": ["ZA_ID_NUMBER"],
}
LABELS["FI_PERSONAL_IDENTITY_CODE"] = "henkilötunnus (Finnish personal identity code)"
ORG_IDS = ["AU_ABN", "AU_ACN", "IN_GSTIN", "IT_VAT_CODE", "SG_UEN", "SE_ORGANISATIONSNUMMER", "KR_BRN", "DE_HANDELSREGISTER"]


def person(rng, gens, index):
    first, last = rng.choice(W.FIRST), rng.choice(W.LAST)
    city, region, postcode, country = rng.choice(W.CITIES)
    dob = W.birth_date(rng)
    street = f"{rng.randint(1, 999)} {rng.choice(W.STREETS)}"
    ids = {entity: gens[entity](rng) for entity in COUNTRY_IDS.get(country, []) if gens.get(entity)}
    medical = rng.choice(W.MEDICAL)
    exp = f"{rng.randint(1, 12):02d}/{rng.randint(27, 33)}"
    record = {
        "record_id": f"P{index:05d}", "name": {"first": first, "last": last, "full": f"{first} {last}", "native_script_example": rng.choice(W.NON_LATIN_NAMES)},
        "birth": {"date_of_birth": dob, "place_of_birth": rng.choice(W.CITIES)[0]},
        "demographics": {"nationality": rng.choice(W.NATIONALITIES), "religion": rng.choice(W.RELIGIONS),
                         "political_affiliation": rng.choice(W.POLITICAL), "gender": rng.choice(["female", "male", "non-binary"])},
        "contact": {"emails": [W.email(rng, first, last), W.email(rng, first, last, "acme.com")], "phones": [gens["PHONE_NUMBER"](rng), gens["PHONE_NUMBER"](rng)],
                    "address": {"street": street, "city": city, "region": region, "postcode": postcode, "country": country}},
        "government_ids": {LABELS[e]: v for e, v in ids.items()},
        "financial": {"credit_card": {"number": gens["CREDIT_CARD"](rng), "expiry": exp, "cvv": W.digits(rng, 3)}, "iban": gens["IBAN_CODE"](rng),
                      "bank_account_number": W.digits(rng, 10), "routing_number": gens["ABA_ROUTING_NUMBER"](rng), "bitcoin_wallet": gens["CRYPTO"](rng),
                      "annual_salary": f"{rng.randint(28, 240) * 1000:,} USD", "card_pin": W.digits(rng, 4)},
        "digital": {"username": W.username(rng), "password": W.password(rng), "api_key": W.api_key(rng), "access_token": W.jwt(rng),
                    "ip_address": gens["IP_ADDRESS"](rng), "mac_address": gens["MAC_ADDRESS"](rng), "profile_url": gens["URL"](rng),
                    "imei": W.imei(rng), "device_id": W.uuid_like(rng), "social_handle": "@" + W.username(rng), "user_agent": rng.choice(W.USER_AGENTS),
                    "geolocation": W.coordinates(rng), "last_login": f"2026-{rng.randint(1, 9):02d}-{rng.randint(1, 28):02d} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}"},
        "employment": {"employer": rng.choice(W.COMPANIES), "employee_id": f"EMP-{W.digits(rng, 6)}", "work_email": W.email(rng, first, last, "acme.com")},
        "education": {"student_id": f"S{W.digits(rng, 8)}"},
        "health": {"condition": medical[0], "medication": medical[1], "blood_type": rng.choice(["A+", "O-", "B+", "AB-", "O+"]),
                   "insurance_member_id": f"{W.upper(rng, 3)}{W.digits(rng, 9)}"},
        "vehicle": {"license_plate": W.us_plate(rng), "vin": W.vin(rng)},
        "biometrics": {"fingerprint_template_hash": "".join(rng.choice("0123456789abcdef") for _ in range(40)), "face_template_id": W.uuid_like(rng)},
    }
    add_custom_fields(rng, record, country)
    return record, ids


def add_custom_fields(rng, record, country):
    """Fields for the custom recognizers, written the way real records label them (direct keys, one value each)."""
    record["date_of_birth"] = W.date_formats(rng, "us")
    d = record["demographics"]
    d.update({"age": rng.randint(18, 95), "ethnicity": rng.choice(W.ETHNICITIES), "marital_status": rng.choice(W.MARITAL),
              "sexual_orientation": rng.choice(W.ORIENTATIONS), "credit_score": rng.randint(300, 850)})
    address = record["contact"]["address"]
    if country == "United States":
        address["zip_code"] = W.zip5(rng)
        address["alien_registration_number"] = W.alien_number(rng)
    record["contact"]["mobile_us"] = W.us_phone(rng)
    record["documents"] = {"passport_number": W.passport_generic(rng), "national_id_number": W.national_id(rng),
                           "driver_license_number": W.driver_license_generic(rng), "tax_id_number": W.tax_id_generic(rng),
                           "professional_license_number": W.professional_license(rng)}
    record["financial"].update({"swift_bic": W.swift_code(rng), "ethereum_wallet": W.ethereum(rng)})
    record["digital"].update({"session_id": W.session_id(rng), "advertising_id": W.uuid_like(rng)})
    if rng.random() < 0.3:
        record["digital"]["ssh_private_key_header"] = W.private_key_header(rng)
    record["employment"]["ein"] = W.ein(rng)
    record["accounts"] = {"customer_id": W.customer_id(rng), "device_serial_number": W.serial_number(rng)}
    h = record["health"]
    h.update({"medical_record_number": W.mrn(rng), "insurance_policy_number": W.policy_number(rng),
              "admission_date": W.date_formats(rng, "long"), "discharge_date": W.date_formats(rng, "us")})
    if rng.random() < 0.1:
        h["date_of_death"] = W.date_formats(rng, "us")
    record["vehicle"]["vin"] = W.vin_valid(rng)


def narrative_extra(p):
    """Labelled sentences covering the custom entities, appended to each person's paragraph."""
    d, doc, f, g, h, e = p["demographics"], p["documents"], p["financial"], p["digital"], p["health"], p["employment"]
    a = p["contact"]["address"]
    parts = [f"Profile: age {d['age']}, gender: {d['gender']}, ethnicity: {d['ethnicity']}, marital status: {d['marital_status']}, sexual orientation: {d['sexual_orientation']}, "
             f"religion: {d['religion']}, political affiliation: {d['political_affiliation']}, credit score: {d['credit_score']}, born on {p['date_of_birth']}."]
    extra_ids = [f"passport number {doc['passport_number']}", f"national ID number {doc['national_id_number']}", f"driver license number {doc['driver_license_number']}",
                 f"tax ID {doc['tax_id_number']}", f"professional license number {doc['professional_license_number']}", f"EIN {e['ein']}"]
    if "zip_code" in a:
        extra_ids += [f"ZIP code {a['zip_code']}", f"alien registration number {a['alien_registration_number']}"]
    parts.append("More documents: " + "; ".join(extra_ids) + f"; US mobile {p['contact']['mobile_us']}; SWIFT code {f['swift_bic']}; Ethereum wallet {f['ethereum_wallet']}.")
    parts.append(f"Records: customer ID {p['accounts']['customer_id']}, serial number {p['accounts']['device_serial_number']}, session ID {g['session_id']}, advertising id {g['advertising_id']}, "
                 f"medical record number {h['medical_record_number']}, insurance policy number {h['insurance_policy_number']}, admitted on {h['admission_date']}, discharge date {h['discharge_date']}"
                 + (f", died on {h['date_of_death']}" if "date_of_death" in h else "") + ".")
    if "ssh_private_key_header" in g:
        parts.append(f"A leaked file begins with {g['ssh_private_key_header']}.")
    return " ".join(parts)


def narrative(rng, p, ids):
    n, c, a, f, d, e, h = p["name"], p["contact"], p["contact"]["address"], p["financial"], p["digital"], p["employment"], p["health"]
    dob = p["birth"]["date_of_birth"]
    pronoun = {"female": "She", "male": "He"}.get(p["demographics"]["gender"], "They")
    parts = [f"{n['full']} (also written {n['native_script_example']}) was born on {dob['long']} ({dob['us']}) in {p['birth']['place_of_birth']}; "
             f"{pronoun.lower()} is a {p['demographics']['nationality']} {p['demographics']['religion']} and a {p['demographics']['political_affiliation']}.",
             f"{pronoun} lives at {a['street']}, {a['city']}{', ' + a['region'] if a['region'] else ''} {a['postcode']}, {a['country']}, and can be reached on {c['phones'][0]}, "
             f"{c['phones'][1]}, {c['emails'][0]} or {c['emails'][1]}."]
    if ids:
        parts.append("Identity documents: " + "; ".join(f"{LABELS[e]} {v}" for e, v in ids.items()) + ".")
    parts.append(f"Payment details: card {f['credit_card']['number']} with expiry {f['credit_card']['expiry']} and CVV {f['credit_card']['cvv']} and PIN {f['card_pin']}, "
                 f"IBAN {f['iban']}, bank account number {f['bank_account_number']} with ABA routing number {f['routing_number']}, Bitcoin wallet {f['bitcoin_wallet']}, salary {f['annual_salary']}.")
    parts.append(f"Online: username {d['username']}, password {d['password']}, API key {d['api_key']}, token {d['access_token']}, last seen on {d['last_login']} "
                 f"from IP {d['ip_address']} on a device with MAC {d['mac_address']} and IMEI {d['imei']} (device id {d['device_id']}), handle {d['social_handle']}, "
                 f"profile {d['profile_url']}, near coordinates {d['geolocation']}.")
    parts.append(f"{pronoun} works at {e['employer']} (employee ID {e['employee_id']}, {e['work_email']}), student number {p['education']['student_id']}, drives a car with plate "
                 f"{p['vehicle']['license_plate']} and VIN {p['vehicle']['vin']}, and has been diagnosed with {h['condition']}, taking {h['medication']}; blood type {h['blood_type']}, "
                 f"insurance member ID {h['insurance_member_id']}. Biometric template hash {p['biometrics']['fingerprint_template_hash']}.")
    parts.append(narrative_extra(p))
    return " ".join(parts)


def organization(rng, gens, index):
    city, region, postcode, country = rng.choice(W.CITIES)
    name = rng.choice(W.COMPANIES) + " " + rng.choice(["Ltd", "GmbH", "Pty Ltd", "LLC", "AB", "Oy", "S.p.A.", "Inc."])
    ids = {LABELS[e]: gens[e](rng) for e in rng.sample(ORG_IDS, 4)}
    return {"organization_id": f"O{index:04d}", "name": name, "registered_ids": ids, "ein": W.ein(rng),
            "address": f"{rng.randint(1, 500)} {rng.choice(W.STREETS)}, {city} {postcode}, {country}", "contact_email": f"info@{name.split()[0].lower()}.example.com",
            "phone": gens["PHONE_NUMBER"](rng), "website": gens["URL"](rng), "iban": gens["IBAN_CODE"](rng), "swift_bic": W.upper(rng, 4) + rng.choice(["GB", "DE", "US", "FR", "IN"]) + W.upper(rng, 2)}


def transaction(rng, gens, index, people):
    a, b = rng.sample(people, 2)
    return {"transaction_id": f"T{index:06d}", "timestamp": f"2026-{rng.randint(1, 9):02d}-{rng.randint(1, 28):02d}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}Z",
            "from": {"name": a["name"]["full"], "iban": a["financial"]["iban"], "card": a["financial"]["credit_card"]["number"], "ip": a["digital"]["ip_address"]},
            "to": {"name": b["name"]["full"], "iban": b["financial"]["iban"], "bitcoin_wallet": b["financial"]["bitcoin_wallet"], "email": b["contact"]["emails"][0]},
            "amount": f"{rng.randint(5, 9000)}.{rng.randint(0, 99):02d} {rng.choice(['USD', 'EUR', 'GBP', 'INR'])}", "memo": f"Invoice paid by {a['name']['full']} on behalf of {b['name']['full']}, call {a['contact']['phones'][0]}"}


def access_log_line(rng, p):
    d = p["digital"]
    return (f"{d['last_login']} INFO login ok user={d['username']} password={d['password']} ip={d['ip_address']} mac={d['mac_address']} "
            f"email={p['contact']['emails'][0]} token={d['access_token'][:60]} agent=\"{d['user_agent'][:40]}\" geo={d['geolocation']}")


def build_custom_catalog(analyzer, rng, per_entity=PER_ENTITY):
    """Verified examples for every custom entity: each is kept only if the analyzer finds it as that entity."""
    catalog, report = {}, {}
    for entity, (lead, generate) in W.CUSTOM_EXAMPLES.items():
        good = []
        for _ in range(300):
            value = str(generate(rng))
            if any(value == g[0] for g in good):
                continue
            score = verify(analyzer, entity, value, lead)
            if score >= 0.5:
                good.append((value, lead, score))
                if len(good) == per_entity:
                    break
        catalog[entity] = good
        report[entity] = {"found": len(good), "weak": not good}
    return catalog, report


def build_files(analyzer, rng, people_count):
    gens = ENTITY_GENERATORS()
    started = time.time()
    catalog, report = build_catalog(analyzer, rng)
    print(f"  verified {len(report)} identifier formats in {time.time() - started:.0f} s", flush=True)
    custom_catalog, custom_report = build_custom_catalog(analyzer, rng)
    unverified = sorted(e for e, r in custom_report.items() if r["weak"])
    print(f"  verified {len(custom_report) - len(unverified)} of {len(custom_report)} custom entity formats; not detectable: {unverified}", flush=True)
    gens = {k: v for k, v in gens.items() if v}
    people, ids_by_person = [], []
    for i in range(1, people_count + 1):
        record, ids = person(rng, gens, i)
        people.append(record)
        ids_by_person.append(ids)
    orgs = [organization(rng, gens, i) for i in range(1, max(10, people_count // 5) + 1)]
    transactions = [transaction(rng, gens, i, people) for i in range(1, people_count + 1)]
    log = [access_log_line(rng, rng.choice(people)) for _ in range(people_count)]
    messages = [narrative(rng, p, ids) for p, ids in zip(people, ids_by_person)]
    entity_catalog = {}
    for entity, items in catalog.items():
        entity_catalog[entity] = {"description": LABELS.get(entity, entity), "reachable_at_default_threshold_0_5": not report[entity]["weak"],
                                  "best_presidio_score_seen": report[entity]["best"],
                                  "examples": [{"value": v, "in_a_sentence": f"Please note the {lead} {v} for the record."} for v, lead, _ in items]}
    generic = {"PERSON": [f"{rng.choice(W.FIRST)} {rng.choice(W.LAST)}" for _ in range(12)], "LOCATION": [f"{c[0]}, {c[3]}" for c in W.CITIES],
               "NRP": W.NATIONALITIES + W.RELIGIONS + W.POLITICAL, "EMAIL_ADDRESS": [W.email(rng, rng.choice(W.FIRST), rng.choice(W.LAST)) for _ in range(12)],
               "DATE_TIME": [f"{W.birth_date(rng)['long']}" for _ in range(6)] + ["Monday at 5 PM", "next Tuesday morning", "in 3 weeks", "at 14:30 on 1 June 2026", "the 4th of July"],
               "NON_LATIN_NAMES": W.NON_LATIN_NAMES}
    for entity, items in custom_catalog.items():
        entity_catalog[f"{entity} (custom)"] = {"description": "custom recognizer from pii_detector/recognizers.py (value found by its label or shape)",
                                               "reachable_at_default_threshold_0_5": bool(items),
                                               "examples": [{"value": v, "in_a_sentence": f"Please note the {lead} {v} for the record."} for v, lead, _ in items]}
    for key, values in generic.items():
        entity_catalog[key] = {"description": "found by spaCy (names, places, groups, dates) or by Presidio's email recognizer" if key != "NON_LATIN_NAMES" else "names in other scripts; the English spaCy model is not expected to find these",
                               "reachable_at_default_threshold_0_5": key not in ("NON_LATIN_NAMES",), "examples": [{"value": v} for v in values]}
    document = {
        "_meta": {"title": "Synthetic PII test file: every Presidio entity type and every custom entity, plus other personal data", "synthetic": True,
                  "notice": "All people, organisations and identifiers are generated. Identifiers follow public format rules (with valid checksums where the format has one) and belong to nobody. Passwords, API keys and tokens are random strings in common formats.",
                  "generator": "tools/make_world_pii.py (seeded, deterministic)", "people": len(people), "organizations": len(orgs), "transactions": len(transactions),
                  "presidio_entity_types_in_catalog": len(report), "custom_entity_types_in_catalog": len(custom_report),
                  "custom_entities_without_a_detectable_example": unverified,
                  "weak_in_presidio_cannot_reach_0_5_even_with_context": sorted(e for e, r in report.items() if r["weak"])},
        "entity_catalog": entity_catalog, "people": people, "organizations": orgs, "transactions": transactions, "access_log": log,
        "free_text_messages": messages[: max(20, people_count // 5)],
    }
    sections = ["=== ENTITY CATALOG ==="]
    for entity, info in entity_catalog.items():
        sections.append(f"{info['description']} ({entity}): " + " | ".join(
            ex["in_a_sentence"] if "in_a_sentence" in ex else ex["value"] for ex in info["examples"]))
    sections.append("=== PEOPLE ===")
    sections += messages
    sections.append("=== ORGANIZATIONS ===")
    sections += [f"{o['name']} is registered with " + "; ".join(f"{k} {v}" for k, v in o["registered_ids"].items()) +
                 f", EIN {o['ein']}, based at {o['address']}, email {o['contact_email']}, phone {o['phone']}, website {o['website']}, IBAN {o['iban']}, SWIFT/BIC {o['swift_bic']}." for o in orgs]
    sections.append("=== TRANSACTIONS AND LOGS ===")
    sections += [f"Transfer {t['transaction_id']} at {t['timestamp']}: {t['from']['name']} (IBAN {t['from']['iban']}, card {t['from']['card']}, from IP {t['from']['ip']}) "
                 f"paid {t['amount']} to {t['to']['name']} (IBAN {t['to']['iban']}, wallet {t['to']['bitcoin_wallet']}, {t['to']['email']}); memo: {t['memo']}." for t in transactions]
    sections += log
    one_line = " ".join(" ".join(sections).split())
    return document, one_line, report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probe", action="store_true", help="only check identifier formats and print a report")
    parser.add_argument("--entities", help="comma-separated entities to probe")
    parser.add_argument("--people", type=int, default=250, help="number of person records (default 250)")
    args = parser.parse_args()
    analyzer = load_analyzer()
    rng = random.Random(20260801)
    started = time.time()
    wanted = set(args.entities.split(",")) if args.entities else None
    catalog, report = build_catalog(analyzer, rng, entities=wanted) if args.probe else ({}, {})
    if args.probe:
        print(f"{'entity':28} kept  best  example")
        for entity, info in report.items():
            note = "  <- weak: Presidio cannot reach 0.5" if info["weak"] else ""
            print(f"{entity:28} {info['found']:3}  {info['best']:5.2f}  {catalog[entity][0][0]!r}{note}")
        print(f"\n{len(report)} entities checked in {time.time() - started:.0f} s")
        return 0
    document, one_line, report = build_files(analyzer, random.Random(20260801), args.people)
    import os
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "samples")
    with open(os.path.join(out, "world_pii_complete.json"), "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "world_pii_complete.txt"), "w", encoding="utf-8") as handle:
        handle.write(one_line)
    for name in ("world_pii_complete.json", "world_pii_complete.txt"):
        size = os.path.getsize(os.path.join(out, name))
        print(f"wrote samples/{name}: {size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
