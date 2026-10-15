"""Tests for pii_detector/recognizers.py and the collapse logic. They call the recognizers directly, so no spaCy model is loaded and the file runs in a second.

    python -m unittest tests.test_recognizers -v   (from the project root)
"""
import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pii_detector import detector  # noqa: E402
from pii_detector import recognizers as C  # noqa: E402

RECOGNIZERS = C.build_recognizers()


def found(text, entity, minimum=0.0):
    """Texts matched as `entity` with a score of at least `minimum`."""
    out = []
    for recognizer in RECOGNIZERS:
        if entity in recognizer.supported_entities:
            out += [text[r.start:r.end] for r in recognizer.analyze(text, [entity], None) if r.score >= minimum]
    return list(dict.fromkeys(out))


class AddressTests(unittest.TestCase):
    def test_us_addresses_in_prose_and_with_units(self):
        for text, expected in [
            ("She lives at 742 Evergreen Terrace, Springfield, IL 62704 and works nearby.", "742 Evergreen Terrace, Springfield, IL 62704"),
            ("Ship to 1600 Pennsylvania Avenue NW, Washington, DC 20500.", "1600 Pennsylvania Avenue NW, Washington, DC 20500"),
            ("Send it to 88 Maple Street, Austin, Texas please", "88 Maple Street, Austin, Texas"),
            ("Bill 5 N Main St Apt 4B, Denver, CO 80202 monthly", "5 N Main St Apt 4B, Denver, CO 80202"),
            ("Mail to P.O. Box 4521, Austin, TX 78701 today", "P.O. Box 4521, Austin, TX 78701"),
            ("Springfield, IL 62704", "Springfield, IL 62704"),
        ]:
            with self.subTest(text=text):
                self.assertIn(expected, found(text, "ADDRESS", 0.5))

    def test_international_addresses(self):
        for text, expected in [
            ("Office: 221B Baker Street, London NW1 6XE", "221B Baker Street, London NW1 6XE"),
            ("Head office 100 King Street West, Toronto ON M5H 2N2", "100 King Street West, Toronto ON M5H 2N2"),
            ("Anschrift: Hauptstraße 12, 10115 Berlin", "Hauptstraße 12"),
            ("12 Rue de Rivoli", "12 Rue de Rivoli"),
            ("Calle Mayor, 5", "Calle Mayor, 5"),
        ]:
            with self.subTest(text=text):
                self.assertTrue(any(expected in hit for hit in found(text, "ADDRESS", 0.5)), found(text, "ADDRESS"))

    def test_ambiguous_street_shape_needs_a_context_word(self):
        # Number + name + street suffix alone scores 0.45, below the default threshold.
        self.assertEqual(found("I bought 4 Main Street food items", "ADDRESS", 0.5), [])
        self.assertEqual(found("5 PM on 3 apples Street food", "ADDRESS"), [])

    def test_ordinary_text_is_not_an_address(self):
        for text in ["Page 12 of 40 in Chapter 5", "Call 12 times at 5 PM", "The meeting is on Main Street", "We have 3 Park places"]:
            with self.subTest(text=text):
                self.assertEqual(found(text, "ADDRESS", 0.5), [])


class LabeledValueTests(unittest.TestCase):
    def test_credentials_in_prose_and_json(self):
        self.assertEqual(found("Her password is Sup3rS3cret!42 today", "PASSWORD"), ["Sup3rS3cret!42"])
        self.assertEqual(found('{"password": "hunter2Bravo!"}', "PASSWORD"), ["hunter2Bravo!"])
        self.assertEqual(found("username: sarah_j89 logged in", "USERNAME"), ["sarah_j89"])
        self.assertEqual(found('{"username": "müller.w88"}', "USERNAME"), ["müller.w88"])
        self.assertEqual(found("user jdoe_42 logged in from 10.0.0.1", "USERNAME"), ["jdoe_42"])
        self.assertEqual(found("Login username sarah_j89, password Sup3rS3cret!42", "USERNAME"), ["sarah_j89"])
        self.assertEqual(found("Login username sarah_j89, password Sup3rS3cret!42", "PASSWORD"), ["Sup3rS3cret!42"])
        self.assertEqual(found('{"api_key": "api_key_7f3a9c2e81b44d6fa0c5e1d92b7a4c38"}', "API_KEY", 0.8)[0], "api_key_7f3a9c2e81b44d6fa0c5e1d92b7a4c38")

    def test_filler_words_after_a_label_are_not_values(self):
        for text in ["Please reset your password and choose a new one", "The password is required", "The user is logged in", "username is invalid", "token expired yesterday"]:
            with self.subTest(text=text):
                for entity in ("PASSWORD", "USERNAME", "API_KEY"):
                    self.assertEqual(found(text, entity), [])

    def test_card_details(self):
        self.assertEqual(found("CVV 737, expiry 08/28", "CARD_CVV"), ["737"])
        self.assertEqual(found("security code: 1234", "CARD_CVV"), ["1234"])
        self.assertEqual(found("CVV 737, expiry 08/28", "CARD_EXPIRY"), ["08/28"])
        self.assertEqual(found('{"expiry": "10/31", "cvv": "022"}', "CARD_EXPIRY"), ["10/31"])
        self.assertEqual(found('{"expiry": "10/31", "cvv": "022"}', "CARD_CVV"), ["022"])
        self.assertEqual(found("The CVV is on the back", "CARD_CVV"), [])

    def test_us_identifiers_that_presidio_scores_below_the_threshold(self):
        self.assertEqual(found("passport number is 075977035", "US_PASSPORT"), ["075977035"])
        self.assertEqual(found("Passport: A12345678", "US_PASSPORT"), ["A12345678"])
        self.assertEqual(found("bank account number 3982583440", "US_BANK_NUMBER"), ["3982583440"])
        self.assertEqual(found('{"bank_account_number": "6548950709"}', "US_BANK_NUMBER"), ["6548950709"])
        self.assertIn("12-3456789", found("Her employer uses EIN 12-3456789", "US_EIN", 0.8))
        self.assertEqual(found("zip code 62704-1234", "US_ZIP_CODE"), ["62704-1234"])

    def test_dates_and_attributes(self):
        for text, expected in [("born on March 14, 1989", "March 14, 1989"), ("DOB: 03/14/1989", "03/14/1989"), ("date of birth 14 March 1989", "14 March 1989"),
                               ('{"date_of_birth": "1989-03-14"}', "1989-03-14"), ("birthday: 3.14.89", "3.14.89")]:
            with self.subTest(text=text):
                self.assertEqual(found(text, "DATE_OF_BIRTH"), [expected])
        self.assertEqual(found("aged 34 and 29-year-old", "AGE"), ["34", "29"])
        self.assertEqual(found("age 340", "AGE"), [])
        self.assertEqual(found("Salary: $85,000", "SALARY"), ["$85,000"])
        self.assertEqual(found('{"annual_salary": "131,000 USD"}', "SALARY"), ["131,000 USD"])
        self.assertEqual(found("Gender: female. Ethnicity: Hispanic", "GENDER"), ["female"])
        self.assertEqual(found("Gender: female. Ethnicity: Hispanic", "ETHNICITY"), ["Hispanic"])
        self.assertEqual(found('{"employee_id": "EMP-016973", "student_id": "S87749056"}', "EMPLOYEE_ID"), ["EMP-016973"])
        self.assertEqual(found('{"employee_id": "EMP-016973", "student_id": "S87749056"}', "STUDENT_ID"), ["S87749056"])


class ShapeTests(unittest.TestCase):
    def test_key_and_token_formats(self):
        self.assertEqual(found("Key AKIAIOSFODNN7EXAMPLE here", "API_KEY"), ["AKIAIOSFODNN7EXAMPLE"])
        self.assertEqual(found("ghp_" + "a1B2c3D4e5" * 3 + "a1B2c3", "API_KEY"), ["ghp_" + "a1B2c3D4e5" * 3 + "a1B2c3"])
        self.assertEqual(len(found("sk_live_" + "A1b2C3d4E5f6G7h8", "API_KEY")), 1)
        self.assertEqual(len(found("xoxb-1234567890-abcdefghij", "API_KEY")), 1)
        self.assertEqual(len(found("AIza" + "A" * 35, "API_KEY")), 1)
        self.assertEqual(len(found("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r", "AUTH_TOKEN")), 1)
        self.assertEqual(len(found("-----BEGIN RSA PRIVATE KEY-----", "PRIVATE_KEY")), 1)
        self.assertEqual(found("akia1234567890abcdef is not a key", "API_KEY"), [])

    def test_checksummed_identifiers(self):
        self.assertTrue(C.vin_ok("1HGCM82633A004352"))
        self.assertFalse(C.vin_ok("1HGCM82633A004353"))
        self.assertEqual(found("VIN 1HGCM82633A004352", "VIN"), ["1HGCM82633A004352"])
        self.assertEqual(found("1HGCM82633A004353", "VIN"), [])
        self.assertTrue(C.luhn_ok("490154203237518"))
        self.assertEqual(found("IMEI 490154203237518", "IMEI", 0.8), ["490154203237518"])
        self.assertEqual(found("number 490154203237519", "IMEI"), [])

    def test_location_and_device_identifiers(self):
        self.assertEqual(found("coordinates 40.71278, -74.00594", "GPS_COORDINATES"), ["40.71278, -74.00594"])
        self.assertEqual(found("last seen at coordinates 40.71278, -74.00594.", "GPS_COORDINATES"), ["40.71278, -74.00594"])
        self.assertEqual(found("version 1.2, 3.4", "GPS_COORDINATES"), [])
        self.assertEqual(found("totals 1.2345, 2.3456.7", "GPS_COORDINATES"), [])
        self.assertEqual(found("device 3f2504e0-4f89-41d3-9a0c-0305e82c3301", "UUID"), ["3f2504e0-4f89-41d3-9a0c-0305e82c3301"])
        self.assertEqual(found("SWIFT code DEUTDEFF500", "SWIFT_BIC", 0.8), ["DEUTDEFF500"])
        self.assertEqual(found("follow @sarah_j89 and email me@example.com", "SOCIAL_HANDLE"), ["@sarah_j89"])
        self.assertEqual(found("(201) 555-0123 or +1 415.555.0132", "PHONE_NUMBER", 0.5), ["(201) 555-0123", "+1 415.555.0132"])
        self.assertEqual(found("you can call me on 212-555-0187. Thanks", "PHONE_NUMBER", 0.5), ["212-555-0187"])
        self.assertEqual(found("ticket 2125550187 opened", "PHONE_NUMBER", 0.5), [])

    def test_registered_entities(self):
        for entity in ("ADDRESS", "PASSWORD", "USERNAME", "API_KEY", "CARD_CVV", "US_EIN", "DATE_OF_BIRTH", "VIN", "GPS_COORDINATES"):
            self.assertIn(entity, C.CUSTOM_ENTITIES)


class GapFillerTests(unittest.TestCase):
    """Recognizers added after gap_audit.py showed what was missing."""

    def test_healthcare_and_account_identifiers(self):
        self.assertEqual(found("Medical record number MRN 00482913 was updated", "MEDICAL_RECORD_NUMBER"), ["00482913"])
        self.assertEqual(found('{"mrn": "A1234567"}', "MEDICAL_RECORD_NUMBER"), ["A1234567"])
        self.assertEqual(found("Her insurance policy number is ZXC123456789.", "INSURANCE_ID"), ["ZXC123456789"])
        self.assertEqual(found("Customer ID CUST-884213 requested a refund", "ACCOUNT_ID"), ["CUST-884213"])
        self.assertEqual(found('{"membership_number": "M-5521973"}', "ACCOUNT_ID"), ["M-5521973"])
        self.assertEqual(found("Nursing license number RN-445566 is active", "PROFESSIONAL_LICENSE"), ["RN-445566"])
        self.assertEqual(found("Pacemaker serial number SN48210937 was logged", "SERIAL_NUMBER"), ["SN48210937"])
        self.assertEqual(found("Fingerprint hash 9f86d081884c7d659a2feaa0c55ad015 was stored", "BIOMETRIC_ID"), ["9f86d081884c7d659a2feaa0c55ad015"])
        self.assertEqual(found('{"fingerprint_template_hash": "9f86d081884c7d659a2feaa0c55ad01512ab"}', "BIOMETRIC_ID"), ["9f86d081884c7d659a2feaa0c55ad01512ab"])

    def test_plates_sessions_and_documents(self):
        self.assertEqual(found("His license plate is 7ABC123.", "LICENSE_PLATE"), ["7ABC123"])
        self.assertEqual(found("Plate number: AB12 CDE", "LICENSE_PLATE"), ["AB12 CDE"])
        self.assertEqual(found("The plate is 12 hours old", "LICENSE_PLATE"), [])
        self.assertEqual(found("Session ID: 3f2a9c1e7b4d8a6f0c2e5b1d9a7f4c3e was reused", "SESSION_ID"), ["3f2a9c1e7b4d8a6f0c2e5b1d9a7f4c3e"])
        self.assertEqual(found("Her UK passport number is 123456789.", "PASSPORT_NUMBER"), ["123456789"])
        self.assertEqual(found("Passport number K12345678 expires soon", "PASSPORT_NUMBER"), ["K12345678"])
        self.assertEqual(found("National ID number 8801015009087 was checked", "NATIONAL_ID_NUMBER"), ["8801015009087"])
        self.assertEqual(found("Driver's license number L8227257 was shown", "DRIVER_LICENSE_NUMBER"), ["L8227257"])
        self.assertEqual(found("DEA medical license number FH6722537", "DRIVER_LICENSE_NUMBER"), [])
        self.assertEqual(found("VAT number DE123456789 is on the invoice", "TAX_ID_NUMBER"), ["DE123456789"])
        self.assertEqual(found("Alien registration number A123456789 was issued", "US_ALIEN_NUMBER", 0.8), ["A123456789"])
        self.assertEqual(found("Send to 0x52908400098527886E0F7030069857D2E4169EE7 now", "CRYPTO"), ["0x52908400098527886E0F7030069857D2E4169EE7"])

    def test_sensitive_attributes_and_dates(self):
        self.assertEqual(found("Credit score: 742", "CREDIT_SCORE"), ["742"])
        self.assertEqual(found("Credit score: 1200", "CREDIT_SCORE"), [])
        self.assertEqual(found("Marital status: divorced", "MARITAL_STATUS"), ["divorced"])
        self.assertEqual(found("Sexual orientation: bisexual", "SEXUAL_ORIENTATION"), ["bisexual"])
        self.assertEqual(found("Her religion is Buddhist.", "RELIGION"), ["Buddhist"])
        self.assertEqual(found("Her political affiliation is Libertarian.", "POLITICAL_AFFILIATION"), ["Libertarian"])
        self.assertEqual(found("He died on 11/02/2023 at home", "DATE_OF_DEATH"), ["11/02/2023"])
        self.assertEqual(found("She was admitted on March 2, 2024 for tests", "ADMISSION_DATE"), ["March 2, 2024"])
        self.assertEqual(found("Discharge date: 03/09/2024", "DISCHARGE_DATE"), ["03/09/2024"])

    def test_labels_inside_underscored_json_keys(self):
        self.assertEqual(found('{"device_serial_number": "SN48210937"}', "SERIAL_NUMBER"), ["SN48210937"])
        self.assertEqual(found('{"user_password": "Sup3rS3cret!42"}', "PASSWORD"), ["Sup3rS3cret!42"])
        self.assertEqual(found('{"employer_ein": "12-3456789"}', "US_EIN", 0.8), ["12-3456789"])
        self.assertEqual(found("anypassword is not a label", "PASSWORD"), [])

    def test_filler_after_new_labels_is_not_a_value(self):
        for text in ["The policy number is required", "Customer ID is missing", "Medical record number unknown", "serial killer stories", "She was admitted to hospital", "He died peacefully"]:
            with self.subTest(text=text):
                for entity in ("INSURANCE_ID", "ACCOUNT_ID", "MEDICAL_RECORD_NUMBER", "SERIAL_NUMBER", "ADMISSION_DATE", "DATE_OF_DEATH"):
                    self.assertEqual(found(text, entity), [])


class CardIssuerTests(unittest.TestCase):
    """Luhn alone accepts any 13-19 digit number with a valid check digit, including national ID numbers."""
    ISSUED = {"Visa": "4111111111111111", "Visa (13 digits)": "4222222222222", "Mastercard": "5555555555554444",
              "Mastercard 2-series": "2223003122003222", "Amex": "378282246310005", "Amex (other prefix)": "340000881360233",
              "Discover": "6011111111111117", "JCB": "3530111333300000", "Diners": "30569309025904", "UnionPay": "6200000000000005"}

    def test_numbers_from_real_issuer_ranges_are_cards(self):
        for brand, number in self.ISSUED.items():
            with self.subTest(brand=brand):
                self.assertTrue(C.luhn_ok(number))
                self.assertTrue(C.card_issuer_ok(number))

    def test_a_luhn_valid_number_outside_every_issuer_range_is_not_a_card(self):
        south_african_id = "6601089934086"
        self.assertTrue(C.luhn_ok(south_african_id))
        self.assertFalse(C.card_issuer_ok(south_african_id))

    def test_length_must_suit_the_issuer(self):
        self.assertFalse(C.card_issuer_ok("41111111111111"))        # Visa prefix, 14 digits
        self.assertFalse(C.card_issuer_ok("37828224631000"))        # Amex prefix, 14 digits
        self.assertFalse(C.card_issuer_ok("55555555555544"))        # Mastercard prefix, 14 digits

    def test_separators_are_ignored(self):
        self.assertTrue(C.card_issuer_ok("4111 1111 1111 1111"))
        self.assertTrue(C.card_issuer_ok("3782-822463-10005"))


class NationalityGuardTests(unittest.TestCase):
    def test_a_us_passport_label_does_not_claim_another_countrys_passport(self):
        self.assertEqual(found("passport: R75075500", "US_PASSPORT"), ["R75075500"])
        for label in ("Korean passport", "German passport", "UK passport", "Indian passport", "south korean passport"):
            with self.subTest(label=label):
                self.assertEqual(found(f"{label}: R75075500", "US_PASSPORT"), [])

    def test_a_nationality_word_elsewhere_in_the_sentence_does_not_block_the_label(self):
        self.assertEqual(found("German tourist, passport: R75075500", "US_PASSPORT"), ["R75075500"])


class CollapseTests(unittest.TestCase):
    def item(self, entity, recognizer, start=0, end=10, score=0.85, text="0123456789"):
        return {"text": text, "entity": entity, "start": start, "end": end, "score": score, "recognizer": recognizer}

    def test_custom_beats_spacy_and_builtin_rules_even_at_a_lower_score(self):
        found = [self.item("DATE_TIME", "SpacyRecognizer"), self.item("DATE_TIME", "DateRecognizer", score=0.95),
                 self.item("US_ZIP_CODE", "LabeledUsZipCodeRecognizer")]
        for order in (found, found[::-1]):
            kept = detector.collapse_overlaps(order, {"LabeledUsZipCodeRecognizer": "label", "DateRecognizer": "rule", "SpacyRecognizer": "nlp"})
            self.assertEqual([k["entity"] for k in kept], ["US_ZIP_CODE"])

    def test_builtin_rule_beats_spacy_and_disjoint_results_survive(self):
        found = [self.item("LOCATION", "SpacyRecognizer"), self.item("PHONE_NUMBER", "PhoneRecognizer", score=0.6),
                 self.item("PERSON", "SpacyRecognizer", start=20, end=30)]
        kept = detector.collapse_overlaps(found)
        self.assertEqual(sorted(k["entity"] for k in kept), ["PERSON", "PHONE_NUMBER"])

    def test_spacy_noise_is_dropped_but_real_organizations_stay(self):
        noisy = [self.item("ORGANIZATION", "SpacyRecognizer", text=t) for t in ("MRN", "API", "Ethereum", "date_of_birth", "A1B2")]
        self.assertTrue(all(detector.spacy_noise(n) for n in noisy))
        self.assertFalse(detector.spacy_noise(self.item("ORGANIZATION", "SpacyRecognizer", text="Acme Corp")))


if __name__ == "__main__":
    unittest.main()
