#!/usr/bin/env python3
"""Audit which kinds of PII the tester detects, against HIPAA's 18 identifiers, GDPR special categories and
other common PII categories. Each row is one test sentence with the value that should be found.

    python -m tools.gap_audit                 # table of found / MISSED
    python -m tools.gap_audit --no-custom     # the same without pii_detector/recognizers.py
    python -m tools.gap_audit --threshold 0.4

Rows marked (needs ML) cannot be matched by rules: they need a trained model such as GLiNER.
"""
import argparse
import sys

from pii_detector.detector import detect, load_analyzer

# (framework, category, text, value that must be detected)
ITEMS = [
    # HIPAA Safe Harbor identifiers
    ("HIPAA 1", "names", "The patient is Emily Rodriguez and she called today.", "Emily Rodriguez"),
    ("HIPAA 2", "street address", "She lives at 742 Evergreen Terrace, Springfield, IL 62704.", "742 Evergreen Terrace, Springfield, IL 62704"),
    ("HIPAA 2", "city / county", "Her clinic is in Cook County near Chicago.", "Chicago"),
    ("HIPAA 2", "ZIP code", "Her ZIP code is 62704-1234.", "62704-1234"),
    ("HIPAA 3", "date of birth", "Her date of birth is 03/14/1989.", "03/14/1989"),
    ("HIPAA 3", "admission date", "She was admitted on March 2, 2024 for tests.", "March 2, 2024"),
    ("HIPAA 3", "discharge date", "Discharge date: 03/09/2024.", "03/09/2024"),
    ("HIPAA 3", "date of death", "He died on 11/02/2023 at home.", "11/02/2023"),
    ("HIPAA 3", "age over 89", "The patient, aged 93, was stable.", "93"),
    ("HIPAA 4", "telephone", "Call (201) 555-0123 after noon.", "(201) 555-0123"),
    ("HIPAA 5", "fax", "Fax: 212-555-0187 for records.", "212-555-0187"),
    ("HIPAA 6", "email", "Write to emily.rodriguez@example.com for results.", "emily.rodriguez@example.com"),
    ("HIPAA 7", "SSN", "Her Social Security Number is 406-06-6975.", "406-06-6975"),
    ("HIPAA 8", "medical record number", "Medical record number MRN 00482913 was updated.", "00482913"),
    ("HIPAA 9", "health plan beneficiary number", "Her insurance policy number is ZXC123456789.", "ZXC123456789"),
    ("HIPAA 9", "Medicare MBI", "Medicare Beneficiary Identifier 1UA3-W06-JR60.", "1UA3-W06-JR60"),
    ("HIPAA 10", "account number", "Bank account number 3982583440 was used.", "3982583440"),
    ("HIPAA 11", "driver's license", "US driver license number L8227257 was shown.", "L8227257"),
    ("HIPAA 11", "professional license", "Nursing license number RN-445566 is active.", "RN-445566"),
    ("HIPAA 11", "DEA number", "DEA medical license number FH6722537.", "FH6722537"),
    ("HIPAA 12", "VIN", "Vehicle VIN 1HGCM82633A004352 was recorded.", "1HGCM82633A004352"),
    ("HIPAA 12", "license plate", "His license plate is 7ABC123.", "7ABC123"),
    ("HIPAA 13", "device serial number", "Pacemaker serial number SN48210937 was logged.", "SN48210937"),
    ("HIPAA 13", "IMEI", "Phone IMEI 490154203237518 was blocked.", "490154203237518"),
    ("HIPAA 14", "URL", "Her profile is https://example.com/u/34050 online.", "https://example.com/u/34050"),
    ("HIPAA 15", "IP address", "Login came from IP address 192.168.10.45 today.", "192.168.10.45"),
    ("HIPAA 16", "biometric identifier", "Fingerprint hash 9f86d081884c7d659a2feaa0c55ad015 was stored.", "9f86d081884c7d659a2feaa0c55ad015"),
    ("HIPAA 18", "customer / account ID", "Customer ID CUST-884213 requested a refund.", "CUST-884213"),
    ("HIPAA", "health condition (needs ML)", "She was diagnosed with type 2 diabetes last year.", "type 2 diabetes"),
    ("HIPAA", "medication (needs ML)", "She takes metformin twice a day.", "metformin"),
    # GDPR special categories and other sensitive attributes
    ("GDPR 9", "racial / ethnic origin", "Ethnicity: Hispanic", "Hispanic"),
    ("GDPR 9", "religion", "Her religion is Buddhist and she attends weekly.", "Buddhist"),
    ("GDPR 9", "political opinion", "Her political affiliation is Libertarian.", "Libertarian"),
    ("GDPR 9", "sexual orientation", "Sexual orientation: bisexual", "bisexual"),
    ("GDPR 9", "trade union membership (needs ML)", "He is a member of the Teamsters union.", "Teamsters"),
    ("Sensitive", "gender", "Gender: female", "female"),
    ("Sensitive", "marital status", "Marital status: divorced", "divorced"),
    ("Sensitive", "nationality", "He is a Canadian citizen.", "Canadian"),
    ("Sensitive", "salary / income", "Her annual salary is $85,000.", "$85,000"),
    ("Sensitive", "credit score", "Credit score: 742", "742"),
    ("Sensitive", "criminal record (needs ML)", "He was convicted of fraud in 2019.", "convicted of fraud"),
    # online and device identifiers
    ("Online", "username", "Username: sarah_j89", "sarah_j89"),
    ("Online", "password", "Her password is Sup3rS3cret!42 today.", "Sup3rS3cret!42"),
    ("Online", "API key (AWS)", "Key AKIAIOSFODNN7EXAMPLE leaked.", "AKIAIOSFODNN7EXAMPLE"),
    ("Online", "OAuth/JWT token", "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r"),
    ("Online", "private key", "-----BEGIN RSA PRIVATE KEY----- was pasted.", "-----BEGIN RSA PRIVATE KEY-----"),
    ("Online", "session / cookie ID", "Session ID: 3f2a9c1e7b4d8a6f0c2e5b1d9a7f4c3e was reused.", "3f2a9c1e7b4d8a6f0c2e5b1d9a7f4c3e"),
    ("Online", "advertising / device UUID", "Advertising ID 3f2504e0-4f89-41d3-9a0c-0305e82c3301 was sent.", "3f2504e0-4f89-41d3-9a0c-0305e82c3301"),
    ("Online", "MAC address", "Device MAC address 5D:D7:33:D3:A3:86 joined.", "5D:D7:33:D3:A3:86"),
    ("Online", "social media handle", "Follow @sarah_j89 for updates.", "@sarah_j89"),
    ("Online", "GPS coordinates", "Last seen at coordinates 40.71278, -74.00594.", "40.71278, -74.00594"),
    # financial
    ("Financial", "credit card", "Card 5287 2984 8533 2152 was charged.", "5287 2984 8533 2152"),
    ("Financial", "card CVV", "CVV 737 was entered.", "737"),
    ("Financial", "card expiry", "Expiry 08/28 was entered.", "08/28"),
    ("Financial", "IBAN", "IBAN DE89 3704 0044 0532 0130 00 received it.", "DE89 3704 0044 0532 0130 00"),
    ("Financial", "SWIFT/BIC", "SWIFT code DEUTDEFF500 was used.", "DEUTDEFF500"),
    ("Financial", "ABA routing number", "ABA routing number 090304619.", "090304619"),
    ("Financial", "Bitcoin wallet", "Wallet 1PQh1kSnnc2PpNgoSaQp73PjiRaHe1YXPM got it.", "1PQh1kSnnc2PpNgoSaQp73PjiRaHe1YXPM"),
    ("Financial", "Ethereum wallet", "Send to 0x52908400098527886E0F7030069857D2E4169EE7 now.", "0x52908400098527886E0F7030069857D2E4169EE7"),
    ("Financial", "EIN", "Employer EIN 12-3456789 is on file.", "12-3456789"),
    ("Financial", "VAT number", "VAT number DE123456789 is on the invoice.", "DE123456789"),
    # identity documents
    ("Documents", "US passport", "Passport number 075977035 expires soon.", "075977035"),
    ("Documents", "non-US passport", "Her UK passport number is 123456789.", "123456789"),
    ("Documents", "national ID card", "National ID number 8801015009087 was checked.", "8801015009087"),
    ("Documents", "alien registration (A-number)", "Alien registration number A123456789 was issued.", "A123456789"),
    ("Documents", "ITIN", "Her ITIN is 928-83-0265.", "928-83-0265"),
    ("Documents", "NPI", "NPI number 1285983403 is valid.", "1285983403"),
    ("Documents", "employee ID", "Employee ID EMP-016973 was used.", "EMP-016973"),
    ("Documents", "student ID", "Student ID S87749056 was used.", "S87749056"),
    # country identifiers (spot checks)
    ("Country", "UK National Insurance number", "National Insurance number AB 12 34 56 C.", "AB 12 34 56 C"),
    ("Country", "Spanish NIF", "Spanish NIF 12345678Z was on the form.", "12345678Z"),
    ("Country", "Aadhaar", "Aadhaar number 2345 6789 0124.", "2345 6789 0124"),
    ("Country", "Canadian SIN", "Social Insurance Number 130 692 544.", "130 692 544"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--no-custom", action="store_true")
    args = parser.parse_args()
    analyzer = load_analyzer(custom=not args.no_custom)
    detect(analyzer, "warm-up")
    found_count = ml_missing = 0
    print(f"{'framework':10} {'category':36} result")
    for framework, category, text, value in ITEMS:
        start = text.index(value)
        end = start + len(value)
        hits = sorted({(d["entity"], d["score"]) for d in detect(analyzer, text, args.threshold)
                       if d["start"] < end and start < d["end"]}, key=lambda h: -h[1])
        needs_ml = "needs ML" in category
        if hits:
            found_count += 1
        elif needs_ml:
            ml_missing += 1
        shown = ", ".join(f"{e} {s:.2f}" for e, s in hits[:3]) if hits else ("MISSED (needs a model)" if needs_ml else "MISSED")
        print(f"{framework:10} {category:36} {shown}")
    total = len(ITEMS)
    print(f"\ndetected {found_count} of {total}; missed {total - found_count - ml_missing} that rules could catch and {ml_missing} that need a model")
    return 0


if __name__ == "__main__":
    sys.exit(main())
