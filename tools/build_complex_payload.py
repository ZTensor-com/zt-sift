#!/usr/bin/env python3
"""Build samples/complex_payload.json: one nested, messy JSON document that holds a value for every registered entity type.

Unlike tests/fixtures/all_entities_payload.json (one flat {"ENTITY": {"label": "value"}} pair per type), this document
looks like a real CRM/KYC export:
  * five levels of nesting, arrays of objects, repeated entity types, numbers where numbers belong
  * snake_case, camelCase, kebab-case, "Title Case" and abbreviated keys; some values under keys that say nothing
  * free-text fields (notes, transcripts) with personal data written into sentences
  * escaped quotes, newlines, backslashes and accented characters
  * decoys that look sensitive but are not (order numbers, hashes, versions, placeholders)

Values are generated with a fixed seed (checksum-valid where the identifier has a checksum) and are synthetic.
A second file, samples/complex_payload.expected.json, lists what each value should be reported as.

    python -m tools.build_complex_payload            # writes both files
"""
import base64

from tools.payload_kit import Kit
from tools.world_pii import digits, group, upper

SEED = 20261015
kit = Kit(SEED)
rng, manifest = kit.rng, kit.manifest
gen, expect, decoy, valid_for = kit.gen, kit.expect, kit.decoy, kit.valid_for
hexstr, luhn_number, vin, jwt = kit.hexstr, kit.luhn_number, kit.vin, kit.jwt


def build():
    from presidio_analyzer.predefined_recognizers import DeBsnrRecognizer, DeFuehrerscheinRecognizer, DeLanrRecognizer, DeVatIdRecognizer, PhUmidRecognizer

    bsnr = valid_for(DeBsnrRecognizer, "DE_BSNR", lambda r: digits(r, 9))
    lanr = valid_for(DeLanrRecognizer, "DE_LANR", lambda r: digits(r, 9))
    vat = valid_for(DeVatIdRecognizer, "DE_VAT_ID", lambda r: "DE" + digits(r, 9))
    umid = valid_for(PhUmidRecognizer, "PH_UMID", lambda r: f"{digits(r, 4)}-{digits(r, 7)}-{digits(r, 1)}")
    fuehrer = valid_for(DeFuehrerscheinRecognizer, "DE_FUEHRERSCHEIN", lambda r: upper(r, 2) + digits(r, 8) + upper(r, 1))

    card = expect(gen("CREDIT_CARD"), "CREDIT_CARD", "financial.cards[0].number")
    backup_card = expect(gen("CREDIT_CARD"), "CREDIT_CARD", "financial.cards[1].pan")
    pem_body = "\n".join(base64.b64encode(rng.randbytes(48)).decode() for _ in range(3))
    pem = f"-----BEGIN PRIVATE KEY-----\n{pem_body}\n-----END PRIVATE KEY-----"
    ssn = expect(gen("US_SSN"), "US_SSN", "taxes.federal.ssn")
    email = expect("daniel.okafor@brightwater-analytics.com", "EMAIL_ADDRESS", "applicant.contact.emails[0]")
    other_email = expect("d.okafor@personalmail.com", "EMAIL_ADDRESS", "applicant.contact.emails[1]")
    office_phone = expect("(720) 555-0143", "PHONE_NUMBER", "applicant.contact.phones[1].number")
    phone = expect("+1-303-555-0187", "PHONE_NUMBER", "applicant.contact.phones[0].number")

    notes = [
        "Called (720) 555-0143 on 21 September 2026. Customer confirmed the card 4111 1111 1111 1111 and said the CVV 912 was on the back.",
        "Escalated to compliance. The customer wrote: \"my password is Zx9!kLm#4q and my username is okafor_d\" in the chat.",
        "Wire to account 000123456789 at routing number 021000021; contact backup@brightwater-analytics.com before Friday.",
        "Mail returned from 912 Birch Lane, Portland, OR 97205 (resident since 2019).\nForwarded to the new office.",
        "Zoe Müller and Pablo García agreed to meet in Zürich. Path C:\\\\users\\\\dokafor\\\\notes.txt was attached.",
    ]
    doc = {
        "meta": {
            "requestId": decoy("REQ-2026-10-15-000481", "meta.requestId"),
            "schemaVersion": decoy("3.14.2", "meta.schemaVersion"),
            "source": "crm-sync",
            "checksum": decoy("9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08", "meta.checksum"),
            "flags": {"dryRun": False, "retries": 3, "notes": None, "reviewer": "", "comment": "N/A"},
        },
        "applicant": {
            "identity": {
                "fullName": expect("Daniel Okafor", "PERSON", "applicant.identity.fullName"),
                "dateOfBirth": expect("July 9, 1987", "DATE_OF_BIRTH", "applicant.identity.dateOfBirth"),
                "age": expect(38, "AGE", "applicant.identity.age", "a JSON number, not a string"),
                "gender": expect("male", "GENDER", "applicant.identity.gender"),
                "marital-status": expect("divorced", "MARITAL_STATUS", "applicant.identity['marital-status']"),
                "Ethnicity": expect("Black", "ETHNICITY", "applicant.identity.Ethnicity"),
                "religion": expect("Buddhist", "RELIGION", "applicant.identity.religion"),
                "political affiliation": expect("Libertarian", "POLITICAL_AFFILIATION", "applicant.identity['political affiliation']"),
                "sexual_orientation": expect("gay", "SEXUAL_ORIENTATION", "applicant.identity.sexual_orientation"),
                "nationality": expect("Nigerian", "NRP", "applicant.identity.nationality"),
                "placeOfBirth": expect("Lagos, Nigeria", "LOCATION", "applicant.identity.placeOfBirth"),
                "deceased": False,
                "dateOfDeath": None,
            },
            "contact": {
                "emails": [email, other_email],
                "phones": [{"type": "mobile", "number": phone}, {"type": "office", "number": office_phone}],
                "homeAddress": expect("4821 Willow Creek Drive, Denver, CO 80203", "ADDRESS", "applicant.contact.homeAddress"),
                "zipCode": expect(80203, "US_ZIP_CODE", "applicant.contact.zipCode", "a JSON number"),
                "social": expect("@d_okafor", "SOCIAL_HANDLE", "applicant.contact.social"),
                "website": expect(gen("URL"), "URL", "applicant.contact.website"),
            },
            "employment": {
                "companyName": expect("Brightwater Analytics Ltd", "ORGANIZATION", "applicant.employment.companyName"),
                "employee id": expect("EMP-204815", "EMPLOYEE_ID", "applicant.employment.['employee id']"),
                "annualSalary": expect("$118,500", "SALARY", "applicant.employment.annualSalary"),
                "nursingLicenseNumber": expect("RN-0417733", "PROFESSIONAL_LICENSE", "applicant.employment.nursingLicenseNumber"),
                "studentId": expect("S10458723", "STUDENT_ID", "applicant.employment.studentId"),
            },
        },
        "financial": {
            "banking": {
                "abaRoutingNumber": expect(gen("ABA_ROUTING_NUMBER"), "ABA_ROUTING_NUMBER", "financial.banking.abaRoutingNumber"),
                "accountNumber": expect(digits(rng, 11), "US_BANK_NUMBER", "financial.banking.accountNumber"),
                "iban": expect(gen("IBAN_CODE"), "IBAN_CODE", "financial.banking.iban"),
                "swiftCode": expect("BARCGB22", "SWIFT_BIC", "financial.banking.swiftCode"),
                "customerNumber": expect("CUS-7712904", "ACCOUNT_ID", "financial.banking.customerNumber"),
                "creditScore": expect("712", "CREDIT_SCORE", "financial.banking.creditScore"),
            },
            "cards": [
                {"holder": "D OKAFOR", "number": card, "cvv": expect("481", "CARD_CVV", "financial.cards[0].cvv"),
                 "expiry": expect("11/28", "CARD_EXPIRY", "financial.cards[0].expiry")},
                {"holder": "D OKAFOR", "pan": backup_card},
            ],
            "wallets": [{"chain": "ethereum", "address": expect("0x" + hexstr(40), "CRYPTO", "financial.wallets[0].address")}],
        },
        "taxes": {"federal": {"ssn": ssn, "ein": expect("47-2918356", "US_EIN", "taxes.federal.ein"),
                              "itin": expect(gen("US_ITIN"), "US_ITIN", "taxes.federal.itin"),
                              "taxId": expect("GB-99-123456", "TAX_ID_NUMBER", "taxes.federal.taxId")}},
        "government": {
            "us": {"passportNumber": expect(gen("US_PASSPORT"), "US_PASSPORT", "government.us.passportNumber"),
                   "driver": expect(gen("US_DRIVER_LICENSE"), "US_DRIVER_LICENSE", "government.us.driver"),
                   "driverLicenseNumber": expect("D" + digits(rng, 8), "DRIVER_LICENSE_NUMBER", "government.us.driverLicenseNumber"),
                   "alienRegistrationNumber": expect("A208841537", "US_ALIEN_NUMBER", "government.us.alienRegistrationNumber"),
                   "nationalIdNumber": expect("ID-77412093", "NATIONAL_ID_NUMBER", "government.us.nationalIdNumber")},
            "uk": {"nino": expect(gen("UK_NINO"), "UK_NINO", "government.uk.nino"),
                   "postcode": expect(gen("UK_POSTCODE"), "UK_POSTCODE", "government.uk.postcode"),
                   "dvla": expect(gen("UK_DRIVING_LICENCE"), "UK_DRIVING_LICENCE", "government.uk.dvla")},
            "de": {"plz": expect(digits(rng, 5), "DE_PLZ", "government.de.plz"),
                   "steueridentifikationsnummer": expect(gen("DE_TAX_ID"), "DE_TAX_ID", "government.de.steueridentifikationsnummer"),
                   "steuernummer": expect(gen("DE_TAX_NUMBER"), "DE_TAX_NUMBER", "government.de.steuernummer"),
                   "umsatzsteuer-id": expect(vat, "DE_VAT_ID", "government.de['umsatzsteuer-id']"),
                   "rentenversicherungsnummer": expect(gen("DE_SOCIAL_SECURITY"), "DE_SOCIAL_SECURITY", "government.de.rentenversicherungsnummer"),
                   "krankenversicherungsnummer": expect(gen("DE_HEALTH_INSURANCE"), "DE_HEALTH_INSURANCE", "government.de.krankenversicherungsnummer"),
                   "dokumentennummer": expect(gen("DE_ID_CARD"), "DE_ID_CARD", "government.de.dokumentennummer"),
                   "passport number": expect(gen("DE_PASSPORT"), "DE_PASSPORT", "government.de['passport number']"),
                   "führerschein": expect(fuehrer, "DE_FUEHRERSCHEIN", "government.de.führerschein"),
                   "handelsregister": expect(gen("DE_HANDELSREGISTER"), "DE_HANDELSREGISTER", "government.de.handelsregister"),
                   "bsnr": expect(bsnr, "DE_BSNR", "government.de.bsnr"), "lanr": expect(lanr, "DE_LANR", "government.de.lanr")},
            "es": {"documento nacional de identidad": expect(gen("ES_NIF"), "ES_NIF", "government.es.dni"),
                   "número de identificación de extranjero": expect(gen("ES_NIE"), "ES_NIE", "government.es.nie"),
                   "pasaporte": expect(gen("ES_PASSPORT"), "ES_PASSPORT", "government.es.pasaporte")},
            "it": {"codice fiscale": expect(gen("IT_FISCAL_CODE"), "IT_FISCAL_CODE", "government.it.codiceFiscale"),
                   "piva": expect(gen("IT_VAT_CODE"), "IT_VAT_CODE", "government.it.piva"),
                   "patente": expect(gen("IT_DRIVER_LICENSE"), "IT_DRIVER_LICENSE", "government.it.patente"),
                   "carta": expect(gen("IT_IDENTITY_CARD"), "IT_IDENTITY_CARD", "government.it.carta"),
                   "passaporto": expect(gen("IT_PASSPORT"), "IT_PASSPORT", "government.it.passaporto")},
            "in": {"aadhaar": expect(gen("IN_AADHAAR"), "IN_AADHAAR", "government.in.aadhaar"),
                   "pan": expect(gen("IN_PAN"), "IN_PAN", "government.in.pan"),
                   "gstin": expect(gen("IN_GSTIN"), "IN_GSTIN", "government.in.gstin"),
                   "voter": expect(gen("IN_VOTER"), "IN_VOTER", "government.in.voter"),
                   "RTO": expect(gen("IN_VEHICLE_REGISTRATION"), "IN_VEHICLE_REGISTRATION", "government.in.rto"),
                   "passport": expect(gen("IN_PASSPORT"), "PASSPORT_NUMBER", "government.in.passport", "country cannot be named from the shape; reported as the generic type")},
            "kr": {"주민등록번호": expect(gen("KR_RRN"), "KR_RRN", "government.kr.rrn"),
                   "외국인등록번호": expect(gen("KR_FRN"), "KR_FRN", "government.kr.frn"),
                   "사업자등록번호": expect(gen("KR_BRN"), "KR_BRN", "government.kr.brn"),
                   "운전면허": expect(gen("KR_DRIVER_LICENSE"), "KR_DRIVER_LICENSE", "government.kr.driverLicense"),
                   "Korean passport": expect(gen("KR_PASSPORT"), "PASSPORT_NUMBER", "government.kr.passport", "reported as the generic type")},
            "au": {"australian business number": expect(gen("AU_ABN"), "AU_ABN", "government.au.abn"),
                   "australian company number": expect(gen("AU_ACN"), "AU_ACN", "government.au.acn"),
                   "tax file number": expect(gen("AU_TFN"), "AU_TFN", "government.au.tfn"),
                   "medicare": expect(gen("AU_MEDICARE"), "AU_MEDICARE", "government.au.medicare")},
            "ca": {"sin": expect(gen("CA_SIN"), "CA_SIN", "government.ca.sin")},
            "se": {"personnummer": expect(gen("SE_PERSONNUMMER"), "SE_PERSONNUMMER", "government.se.personnummer"),
                   "organisationsnummer": expect(gen("SE_ORGANISATIONSNUMMER"), "SE_ORGANISATIONSNUMMER", "government.se.organisationsnummer")},
            "fi": {"hetu": expect(gen("FI_PERSONAL_IDENTITY_CODE"), "FI_PERSONAL_IDENTITY_CODE", "government.fi.hetu")},
            "pl": {"PESEL": expect(gen("PL_PESEL"), "PL_PESEL", "government.pl.pesel")},
            "sg": {"fin": expect(gen("SG_NRIC_FIN"), "SG_NRIC_FIN", "government.sg.fin"),
                   "uen": expect(gen("SG_UEN", tries=1500), "SG_UEN", "government.sg.uen")},
            "th": {"Thai National ID": expect(gen("TH_TNIN"), "TH_TNIN", "government.th.tnin")},
            "tr": {"tc kimlik": expect(gen("TR_NATIONAL_ID"), "TR_NATIONAL_ID", "government.tr.tckn"),
                   "plaka": expect(gen("TR_LICENSE_PLATE"), "TR_LICENSE_PLATE", "government.tr.plaka")},
            "za": {"id": expect(gen("ZA_ID_NUMBER"), "ZA_ID_NUMBER", "government.za.id")},
            "ng": {"national identity": expect(gen("NG_NIN"), "NG_NIN", "government.ng.nin"),
                   "plate number": expect(gen("NG_VEHICLE_REGISTRATION"), "NG_VEHICLE_REGISTRATION", "government.ng.vehicle")},
            "ph": {"bir": expect(gen("PH_TIN"), "PH_TIN", "government.ph.tin"), "umid": expect(umid, "PH_UMID", "government.ph.umid")},
            "uk-health": {"national health service": expect(gen("UK_NHS"), "UK_NHS", "government.ukHealth.nhs")},
            "uk-passport": {"passport": expect(gen("UK_PASSPORT"), "PASSPORT_NUMBER", "government.ukPassport", "reported as the generic type")},
        },
        "healthcare": {
            "records": [{
                "medicalRecordNumber": expect("MRN-5527341", "MEDICAL_RECORD_NUMBER", "healthcare.records[0].medicalRecordNumber"),
                "insurancePolicyNumber": expect("FNO3391847265", "INSURANCE_ID", "healthcare.records[0].insurancePolicyNumber"),
                "admitted on": expect("April 3, 2024", "ADMISSION_DATE", "healthcare.records[0]['admitted on']"),
                "discharge date": expect("04/11/2024", "DISCHARGE_DATE", "healthcare.records[0]['discharge date']"),
                "npi": expect(gen("US_NPI"), "US_NPI", "healthcare.records[0].npi"),
                "medicare": expect(gen("US_MBI"), "US_MBI", "healthcare.records[0].medicare"),
                "medical": expect(gen("MEDICAL_LICENSE"), "MEDICAL_LICENSE", "healthcare.records[0].medical"),
            }],
            "familyHistory": {"father": {"died on": expect("12/30/2023", "DATE_OF_DEATH", "healthcare.familyHistory.father['died on']")}},
        },
        "vehicles": [
            {"vin": expect(vin(), "VIN", "vehicles[0].vin"), "license plate": expect("7XYZ482", "LICENSE_PLATE", "vehicles[0]['license plate']")},
            {"kennzeichen": expect(gen("DE_KFZ"), "DE_KFZ", "vehicles[1].kennzeichen"),
             "vehicle": expect(gen("UK_VEHICLE_REGISTRATION"), "UK_VEHICLE_REGISTRATION", "vehicles[1].vehicle")},
        ],
        "devices": [{
            "imei": expect(luhn_number("35", 15), "IMEI", "devices[0].imei"),
            "serial number": expect("SN7740291A", "SERIAL_NUMBER", "devices[0]['serial number']"),
            "mac": expect(gen("MAC_ADDRESS"), "MAC_ADDRESS", "devices[0].mac"),
            "ip": expect(gen("IP_ADDRESS"), "IP_ADDRESS", "devices[0].ip"),
            "device": expect("%s-%s-4%s-a%s-%s" % (hexstr(8), hexstr(4), hexstr(3), hexstr(3), hexstr(12)), "UUID", "devices[0].device"),
            "coordinates": expect("37.77493, -122.41942", "GPS_COORDINATES", "devices[0].coordinates"),
        }],
        "digital": {
            "username": expect("d.okafor92", "USERNAME", "digital.username"),
            "password": expect("Tr1ck$ter#2026", "PASSWORD", "digital.password"),
            "apiKey": expect("sk_demo_" + hexstr(24), "API_KEY", "digital.apiKey"),
            "bearer": expect(jwt(), "AUTH_TOKEN", "digital.bearer"),
            "session ID": expect(hexstr(32), "SESSION_ID", "digital.sessionId"),
            "fingerprint hash": expect(hexstr(32), "BIOMETRIC_ID", "digital.fingerprintHash"),
            "privateKey": expect(pem, "PRIVATE_KEY", "digital.privateKey", "a whole PEM block with escaped newlines"),
        },
        "notes": notes,
        "decoys": {
            "orderNumber": decoy("884213", "decoys.orderNumber"), "page": decoy("Page 12 of 40", "decoys.page"),
            "sku": decoy("AB-12345-XL", "decoys.sku"), "build": decoy("20261015", "decoys.build"),
            "tracking": decoy("1Z999AA10123456784", "decoys.tracking"), "status": "Active", "percent": decoy("12%", "decoys.percent"),
            "placeholderPassword": decoy("********", "decoys.placeholderPassword"), "emptyEmail": "", "version": decoy("v3.14.2", "decoys.version"),
        },
    }
    # Personal data written into the free-text notes (a substring of a longer string)
    for substring, entity, where, note, container in [
            ("(720) 555-0143", "PHONE_NUMBER", "notes[0]", "in a sentence", notes[0]),
            ("21 September 2026", "DATE_TIME", "notes[0]", "a date only spaCy finds", notes[0]),
            ("4111 1111 1111 1111", "CREDIT_CARD", "notes[0]", "in a sentence", notes[0]),
            ("912", "CARD_CVV", "notes[0]", "after the word 'CVV'", notes[0]),
            ("Zx9!kLm#4q", "PASSWORD", "notes[1]", "inside an escaped quote", notes[1]),
            ("okafor_d", "USERNAME", "notes[1]", "inside an escaped quote", notes[1]),
            ("000123456789", "US_BANK_NUMBER", "notes[2]", "after 'account'", notes[2]),
            ("021000021", "ABA_ROUTING_NUMBER", "notes[2]", "after 'routing number'", notes[2]),
            ("backup@brightwater-analytics.com", "EMAIL_ADDRESS", "notes[2]", "", notes[2]),
            ("912 Birch Lane, Portland, OR 97205", "ADDRESS", "notes[3]", "inside a multi-line string", notes[3]),
            ("2019", "DATE_TIME", "notes[3]", "a year only spaCy finds", notes[3]),
            ("Zoe Müller", "PERSON", "notes[4]", "accented surname", notes[4]),
            ("Pablo García", "PERSON", "notes[4]", "accented surname", notes[4]),
            ("Zürich", "LOCATION", "notes[4]", "accented place name", notes[4])]:
        expect(substring, entity, where, note, within=container)
    return doc


def main():
    print(kit.write(build(), "complex_payload"))


if __name__ == "__main__":
    main()
