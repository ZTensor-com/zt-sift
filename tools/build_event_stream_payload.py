#!/usr/bin/env python3
"""Build samples/event_stream_payload.json: a JSON *array* of heterogeneous audit events.

A different shape from samples/complex_payload.json (one nested object grouped by domain):
  * the root is an array; every event has the same envelope (id, type, occurredAt, data) but its own payload shape
  * label-free recall: 44 checksum-validated identifiers sit under generic keys ("number", "ref") with nothing but a sibling
    "docType" next to them, so only their shape and checksum can identify them
  * PascalCase, SCREAMING_SNAKE, camelCase and dotted keys; scalar arrays; numbers where numbers belong
  * text in other formats inside strings: a support thread, double-encoded JSON, YAML, HTML, CSV, a URL with a query string
  * decoys, and event timestamps that may or may not be reported (they are dates, but not personal data)
  * a clearly separate "stretch" event holding shapes the detector does not handle yet (a label in a sibling field, PII used as
    a key, an obfuscated e-mail). They are listed in the manifest as known gaps and checked by a tripwire test.

Values are synthetic, generated with a fixed seed, and checksum-valid where the identifier has a checksum.

    python -m tools.build_event_stream_payload
"""
import base64

from tools.payload_kit import Kit
from tools.world_pii import digits, upper

SEED = 20261016
kit = Kit(SEED)
rng = kit.rng
gen, expect, decoy, gap, allow, valid_for, hexstr, jwt, vin = kit.gen, kit.expect, kit.decoy, kit.gap, kit.allow, kit.valid_for, kit.hexstr, kit.jwt, kit.vin

# (docType, country, entity): identifiers that carry no label at all, only shape and checksum.
LABEL_FREE = [
    ("tax registration", "AU", "AU_ABN"), ("company number", "AU", "AU_ACN"), ("tax file", "AU", "AU_TFN"), ("health card", "AU", "AU_MEDICARE"),
    ("social insurance", "CA", "CA_SIN"), ("commercial register", "DE", "DE_HANDELSREGISTER"), ("health insurance", "DE", "DE_HEALTH_INSURANCE"),
    ("identity card", "DE", "DE_ID_CARD"), ("pension", "DE", "DE_SOCIAL_SECURITY"), ("tax id", "DE", "DE_TAX_ID"),
    ("foreigner id", "ES", "ES_NIE"), ("national id", "ES", "ES_NIF"), ("citizen id", "FI", "FI_PERSONAL_IDENTITY_CODE"),
    ("resident id", "IN", "IN_AADHAAR"), ("gst", "IN", "IN_GSTIN"), ("tax card", "IN", "IN_PAN"), ("fiscal code", "IT", "IT_FISCAL_CODE"),
    ("vat", "IT", "IT_VAT_CODE"), ("business", "KR", "KR_BRN"), ("driving", "KR", "KR_DRIVER_LICENSE"), ("alien card", "KR", "KR_FRN"),
    ("resident", "KR", "KR_RRN"), ("citizen", "PL", "PL_PESEL"), ("company", "SE", "SE_ORGANISATIONSNUMMER"), ("person", "SE", "SE_PERSONNUMMER"),
    ("identity", "SG", "SG_NRIC_FIN"), ("entity", "SG", "SG_UEN"), ("national", "TH", "TH_TNIN"), ("national", "TR", "TR_NATIONAL_ID"),
    ("citizen", "ZA", "ZA_ID_NUMBER"), ("citizen", "NG", "NG_NIN"), ("health service", "GB", "UK_NHS"), ("insurance", "GB", "UK_NINO"),
    ("driving", "GB", "UK_DRIVING_LICENCE"), ("taxpayer", "US", "US_ITIN"), ("benefits", "US", "US_MBI"), ("provider", "US", "US_NPI"),
    ("social", "US", "US_SSN"), ("practitioner", "US", "MEDICAL_LICENSE"),
]
LABEL_FREE_PLATES = [("vehicle", "IN", "IN_VEHICLE_REGISTRATION"), ("vehicle", "NG", "NG_VEHICLE_REGISTRATION"), ("vehicle", "GB", "UK_VEHICLE_REGISTRATION")]


def identifiers(group, entries):
    return [{"docType": doc_type, "country": country, "number": expect(gen(entity), entity, f"{group}[{i}].number", "no label: shape and checksum only")}
            for i, (doc_type, country, entity) in enumerate(entries)]


def build():
    from presidio_analyzer.predefined_recognizers import DeBsnrRecognizer, DeFuehrerscheinRecognizer, DeLanrRecognizer, DeVatIdRecognizer, PhUmidRecognizer

    bsnr = valid_for(DeBsnrRecognizer, "DE_BSNR", lambda r: digits(r, 9))
    lanr = valid_for(DeLanrRecognizer, "DE_LANR", lambda r: digits(r, 9))
    vat = valid_for(DeVatIdRecognizer, "DE_VAT_ID", lambda r: "DE" + digits(r, 9))
    umid = valid_for(PhUmidRecognizer, "PH_UMID", lambda r: f"{digits(r, 4)}-{digits(r, 7)}-{digits(r, 1)}")
    fuehrer = valid_for(DeFuehrerscheinRecognizer, "DE_FUEHRERSCHEIN", lambda r: upper(r, 2) + digits(r, 8) + upper(r, 1))
    stamp = iter(f"2026-10-14T08:{m:02d}:{s:02d}Z" for m in range(10, 40) for s in (7, 41))

    def event(kind, data):
        n = len(events)
        events.append({"id": decoy("evt_" + hexstr(12), f"events[{n}].id"), "type": kind,
                       "occurredAt": allow(next(stamp), "DATE_TIME", f"events[{n}].occurredAt", "a timestamp is a date, not personal data"), "data": data})

    events = []
    pem = "-----BEGIN RSA PRIVATE KEY-----\n" + "\n".join(base64.b64encode(rng.randbytes(48)).decode() for _ in range(3)) + "\n-----END RSA PRIVATE KEY-----"

    # 1 ---------------------------------------------------------------------------------- PascalCase profile
    event("user.signup", {
        "FirstName": expect("Priya", "PERSON", "signup.FirstName"), "LastName": expect("Raghunathan", "PERSON", "signup.LastName"),
        "Email": expect("priya.raghunathan@northwind-traders.com", "EMAIL_ADDRESS", "signup.Email"),
        "MobilePhone": expect("+91 98765 43210", "PHONE_NUMBER", "signup.MobilePhone"),
        "DateOfBirth": expect("1991-03-22", "DATE_OF_BIRTH", "signup.DateOfBirth"), "Age": expect(33, "AGE", "signup.Age", "a JSON number"),
        "Gender": expect("female", "GENDER", "signup.Gender"), "MaritalStatus": expect("married", "MARITAL_STATUS", "signup.MaritalStatus"),
        "Religion": expect("Hindu", "RELIGION", "signup.Religion"), "Ethnicity": expect("Asian", "ETHNICITY", "signup.Ethnicity"),
        "PoliticalAffiliation": expect("Green Party", "POLITICAL_AFFILIATION", "signup.PoliticalAffiliation"),
        "SexualOrientation": expect("straight", "SEXUAL_ORIENTATION", "signup.SexualOrientation"),
        "Nationality": expect("Indian", "NRP", "signup.Nationality"),
        "Address": expect("17 Marigold Court, Leeds, LS6 2AH", "ADDRESS", "signup.Address", "UK style"),
        "MarketingOptIn": True, "Locale": "en-GB", "Tags": ["early-adopter", "newsletter"],
    })

    # 2 ------------------------------------------------------------------------ label-free identifiers (shape only)
    event("kyc.documents", {"submittedBy": "automated-intake", "documents": identifiers("kyc.documents", LABEL_FREE)})
    event("registry.lookup", {"query": decoy("lookup-7731", "registry.query"), "matches": identifiers("registry.matches", LABEL_FREE_PLATES)})

    # 3 ---------------------------------------------------------------------------------------------- payment
    event("payment.authorized", {
        "card": {"holder": "P RAGHUNATHAN", "number": expect(gen("CREDIT_CARD"), "CREDIT_CARD", "payment.card.number"),
                 "cvv": expect("618", "CARD_CVV", "payment.card.cvv"), "expiry": expect("04/29", "CARD_EXPIRY", "payment.card.expiry")},
        "settlement": {"bankRef": expect(gen("ABA_ROUTING_NUMBER"), "ABA_ROUTING_NUMBER", "payment.settlement.bankRef", "no label"),
                       "iban": expect(gen("IBAN_CODE"), "IBAN_CODE", "payment.settlement.iban"), "swiftCode": expect("HDFCINBB", "SWIFT_BIC", "payment.settlement.swiftCode"),
                       "accountNumber": expect(digits(rng, 10), "US_BANK_NUMBER", "payment.settlement.accountNumber"),
                       "customerNumber": expect("CUS-4408213", "ACCOUNT_ID", "payment.settlement.customerNumber")},
        "risk": {"creditScore": expect("745", "CREDIT_SCORE", "payment.risk.creditScore")},
        "payout": {"to": expect("0x" + hexstr(40), "CRYPTO", "payment.payout.to", "no label"), "amount": decoy("1,245.50", "payment.amount"), "currency": "GBP",
                   "reference": decoy("INV-20261014-77", "payment.reference")},
    })

    # 4 ---------------------------------------------------------------------------------- support thread (free text)
    ssn, card = gen("US_SSN"), gen("CREDIT_CARD")
    thread = [
        "Hi, this is Mateo Alvarez. My order never arrived and I am based in Seville.",
        "Please call me on (415) 555-0178 or write to mateo.alvarez@northwind-traders.com. I need an answer by 3 November 2026.",
        f"I live at 88 Cedar Ridge Road, Austin, TX 78704 and my SSN is {ssn} if you need to verify me.",
        "My login is mateo_a and my password is Qw7!pLm#92x, but the portal rejects it.",
        f"The charge on card {card} was made by Northwind Traders, not by me.",
    ]
    event("support.ticket", {"ticketId": decoy("TCK-880412", "support.ticketId"), "channel": "chat",
                             "messages": [{"from": "customer" if i % 2 == 0 else "agent", "text": text} for i, text in enumerate(thread)]})
    for substring, entity, index, note in [
            ("Mateo Alvarez", "PERSON", 0, ""), ("Seville", "LOCATION", 0, ""), ("(415) 555-0178", "PHONE_NUMBER", 1, ""),
            ("mateo.alvarez@northwind-traders.com", "EMAIL_ADDRESS", 1, ""), ("3 November 2026", "DATE_TIME", 1, "a date only spaCy finds"),
            ("88 Cedar Ridge Road, Austin, TX 78704", "ADDRESS", 2, ""), (ssn, "US_SSN", 2, "inside a sentence"),
            ("mateo_a", "USERNAME", 3, "after 'login is'"), ("Qw7!pLm#92x", "PASSWORD", 3, "after 'password is'"),
            (card, "CREDIT_CARD", 4, "inside a sentence"), ("Northwind Traders", "ORGANIZATION", 4, "")]:
        expect(substring, entity, f"support.thread[{index}]", note, within=thread[index])

    # 5 ----------------------------------------------------------------------------------------- HR (camelCase)
    event("hr.onboarding", {"employee": {
        "employeeId": expect("EMP-318274", "EMPLOYEE_ID", "hr.employeeId"), "annualSalary": expect("$91,250", "SALARY", "hr.annualSalary"),
        "companyName": expect("Northwind Traders Ltd", "ORGANIZATION", "hr.companyName"),
        "nursingLicenseNumber": expect("RN-0731942", "PROFESSIONAL_LICENSE", "hr.nursingLicenseNumber"), "studentId": expect("S20931446", "STUDENT_ID", "hr.studentId"),
        "taxId": expect("FR-77-884213", "TAX_ID_NUMBER", "hr.taxId"), "ein": expect("58-1904627", "US_EIN", "hr.ein"),
        "driver": expect(gen("US_DRIVER_LICENSE"), "US_DRIVER_LICENSE", "hr.driver"),
        "driverLicenseNumber": expect("D" + digits(rng, 8), "DRIVER_LICENSE_NUMBER", "hr.driverLicenseNumber"),
        "alienRegistrationNumber": expect("A" + digits(rng, 9), "US_ALIEN_NUMBER", "hr.alienRegistrationNumber"),
        "nationalIdNumber": expect("ID-55903127", "NATIONAL_ID_NUMBER", "hr.nationalIdNumber"),
        "passportNumber": expect(gen("US_PASSPORT"), "US_PASSPORT", "hr.passportNumber"),
        "passport": expect("T" + digits(rng, 7) + "K", "PASSPORT_NUMBER", "hr.passport", "country cannot be named from the shape"),
        "zipCode": expect(78704, "US_ZIP_CODE", "hr.zipCode", "a JSON number"), "social": expect("@mateo_alvarez", "SOCIAL_HANDLE", "hr.social"),
        "directDial": expect("(212) 555-0166", "PHONE_NUMBER", "hr.directDial"),
    }})

    # 6 ------------------------------------------------------------------------------------------------ claim
    event("insurance.claim", {"claim": {
        "medical record number": expect("MRN-8841207", "MEDICAL_RECORD_NUMBER", "claim.mrn"), "insurancePolicyNumber": expect("PLC-6620418-9", "INSURANCE_ID", "claim.policy"),
        "admitted on": expect("March 12, 2026", "ADMISSION_DATE", "claim.admitted"), "discharge date": expect("03/19/2026", "DISCHARGE_DATE", "claim.discharged"),
        "policyholder": {"father": {"died on": expect("11/02/2024", "DATE_OF_DEATH", "claim.father.died")}},
    }})

    # 7 --------------------------------------------------------------------------------------------- vehicles
    event("vehicle.registered", {"vehicle": {"vin": expect(vin(), "VIN", "vehicle.vin"), "license plate": expect("4ABC891", "LICENSE_PLATE", "vehicle.plate"),
                                              "kennzeichen": expect(gen("DE_KFZ"), "DE_KFZ", "vehicle.kennzeichen"), "plaka": expect(gen("TR_LICENSE_PLATE"), "TR_LICENSE_PLATE", "vehicle.plaka")}})

    # 8 -------------------------------------------------------------------------------------------- telemetry
    readings = []
    for i in range(2):
        readings.append({"imei": expect(kit.luhn_number("35", 15), "IMEI", f"telemetry[{i}].imei"), "serial number": expect(f"SN-{digits(rng, 3)}{upper(rng, 2)}{digits(rng, 3)}", "SERIAL_NUMBER", f"telemetry[{i}].serial"),
                         "mac": expect(gen("MAC_ADDRESS"), "MAC_ADDRESS", f"telemetry[{i}].mac", "no label"), "ip": expect(gen("IP_ADDRESS"), "IP_ADDRESS", f"telemetry[{i}].ip", "no label"),
                         "device": expect("%s-%s-4%s-a%s-%s" % (hexstr(8), hexstr(4), hexstr(3), hexstr(3), hexstr(12)), "UUID", f"telemetry[{i}].device"),
                         "coordinates": expect(f"{rng.uniform(-60, 60):.5f}, {rng.uniform(-120, 120):.5f}", "GPS_COORDINATES", f"telemetry[{i}].coordinates"),
                         "fingerprint hash": expect(hexstr(32), "BIOMETRIC_ID", f"telemetry[{i}].fingerprint"), "battery": decoy("87", f"telemetry[{i}].battery")})
    event("device.telemetry", {"readings": readings, "firmware": decoy("v2.8.1-rc3", "telemetry.firmware")})

    # 9 ------------------------------------------------------------------------- security alert (text in other formats)
    alert_ssn, config_key = gen("US_SSN"), "sk_demo_" + hexstr(24)
    raw = '{"email":"alerts@northwind-traders.com","ssn":"%s","password":"Zk4$mQ8!vRt"}' % alert_ssn
    config = "user: svc_billing\npassword: Lm3#nPq7!xV\napi_key: %s" % config_key
    html = '<p>Contact <a href="mailto:help@northwind-traders.com">support</a> or call (303) 555-0119.</p>'
    event("security.alert", {
        "SEVERITY": "high", "ALERT_ID": decoy("ALR-2026-0091", "alert.id"),
        "username": expect("svc.billing", "USERNAME", "alert.username"), "password": expect("Tr0ub4dor&3xQ", "PASSWORD", "alert.password"),
        "apiKey": expect("sk_demo_" + hexstr(24), "API_KEY", "alert.apiKey"), "bearer": expect(jwt(), "AUTH_TOKEN", "alert.bearer"),
        "session ID": expect(hexstr(32), "SESSION_ID", "alert.sessionId"), "privateKey": expect(pem, "PRIVATE_KEY", "alert.privateKey"),
        "raw": raw, "config": config, "html": html, "placeholder": decoy("${VAULT_SECRET}", "alert.placeholder"),
    })
    for substring, entity, container, where, note in [
            ("alerts@northwind-traders.com", "EMAIL_ADDRESS", raw, "alert.raw", "inside double-encoded JSON"), (alert_ssn, "US_SSN", raw, "alert.raw", "inside double-encoded JSON"),
            ("Zk4$mQ8!vRt", "PASSWORD", raw, "alert.raw", "inside double-encoded JSON"),
            ("svc_billing", "USERNAME", config, "alert.config", "inside YAML text"), ("Lm3#nPq7!xV", "PASSWORD", config, "alert.config", "inside YAML text"),
            (config_key, "API_KEY", config, "alert.config", "inside YAML text"),
            ("help@northwind-traders.com", "EMAIL_ADDRESS", html, "alert.html", "inside an HTML snippet"), ("(303) 555-0119", "PHONE_NUMBER", html, "alert.html", "inside an HTML snippet")]:
        expect(substring, entity, where, note, within=container)

    # 10 ------------------------------------------------------------------ foreign records that need their label
    event("gov.international", {
        "de": {"plz": expect(gen("DE_PLZ"), "DE_PLZ", "gov.de.plz"), "steuernummer": expect(gen("DE_TAX_NUMBER"), "DE_TAX_NUMBER", "gov.de.steuernummer"),
               "umsatzsteuer-id": expect(vat, "DE_VAT_ID", "gov.de.vat"), "führerschein": expect(fuehrer, "DE_FUEHRERSCHEIN", "gov.de.fuehrerschein"),
               "bsnr": expect(bsnr, "DE_BSNR", "gov.de.bsnr"), "lanr": expect(lanr, "DE_LANR", "gov.de.lanr"),
               "passport number": expect(gen("DE_PASSPORT"), "DE_PASSPORT", "gov.de.passport")},
        "es": {"pasaporte": expect(gen("ES_PASSPORT"), "ES_PASSPORT", "gov.es.pasaporte")},
        "it": {"patente": expect(gen("IT_DRIVER_LICENSE"), "IT_DRIVER_LICENSE", "gov.it.patente"), "carta": expect(gen("IT_IDENTITY_CARD"), "IT_IDENTITY_CARD", "gov.it.carta"),
               "passaporto": expect(gen("IT_PASSPORT"), "IT_PASSPORT", "gov.it.passaporto")},
        "in": {"voter": expect(gen("IN_VOTER"), "IN_VOTER", "gov.in.voter")},
        "ph": {"bir": expect(gen("PH_TIN"), "PH_TIN", "gov.ph.bir"), "umid": expect(umid, "PH_UMID", "gov.ph.umid")},
        "uk": {"postcode": expect(gen("UK_POSTCODE"), "UK_POSTCODE", "gov.uk.postcode")},
    })

    # 11 ------------------------------------------------------------------------------- CSV and a link in strings
    csv_ssn = gen("US_SSN")
    csv = f"name,ssn,email\nIsabel Ortega,{csv_ssn},isabel.ortega@northwind-traders.com\n"
    link = "https://portal.northwind-traders.com/reset?token=%s&user=isabel" % hexstr(32)
    event("export.batch", {"filename": decoy("customers_2026-10.csv", "export.filename"), "content": csv, "link": expect(link, "URL", "export.link", "the whole URL, token included")})
    for substring, entity in [(csv_ssn, "US_SSN"), ("isabel.ortega@northwind-traders.com", "EMAIL_ADDRESS")]:
        expect(substring, entity, "export.csv", "inside CSV text", within=csv)
    allow("Isabel Ortega", "PERSON", "export.csv", "a name in a bare CSV row: spaCy (sm and lg) is unreliable without a sentence around it", within=csv)

    # 12 ------------------------------------------------- stretch: shapes the detector does not handle yet (known gaps)
    stretch_email = "isabel.ortega@northwind-traders.com"
    event("stretch.known_gaps", {
        "note": "Everything in this event is expected to be missed today; see the tripwire test.",
        "settings": [{"name": "password", "value": gap("Nv5$kTq2!zWm", "PASSWORD", "stretch.settings[0].value", "the label 'password' is in a sibling field")},
                     {"name": "username", "value": gap("isabel.o", "USERNAME", "stretch.settings[1].value", "the label 'username' is in a sibling field")}],
        "accounts": {gap(stretch_email, "EMAIL_ADDRESS", "stretch.accounts key", "personal data used as an object key", in_key=True): {"plan": "pro"}},
        "contact": gap("isabel [at] northwind-traders [dot] com", "EMAIL_ADDRESS", "stretch.contact", "an obfuscated e-mail address"),
    })
    return events


def main():
    doc = build()
    required = {m["entity"] for m in kit.manifest if m["entity"] and not m.get("gap") and not m.get("allowed")}
    import json
    expected = {c["entity"] for c in json.load(open("tests/fixtures/all_entities_expected.json", encoding="utf-8"))} - {"EMAIL", "ID", "IN_PASSPORT", "UK_PASSPORT", "KR_PASSPORT"}
    missing = sorted(expected - required)
    if missing:
        raise SystemExit(f"entity types not covered by the payload: {missing}")
    print(kit.write(doc, "event_stream_payload"))


if __name__ == "__main__":
    main()
