"""Synthetic identifiers for every entity type Presidio supports, plus other kinds of personal data.

Everything here is made up. Identifiers are generated from public format rules (and, where a checksum
exists, with a valid checksum), so they look real to a validator but belong to nobody: names are random
pairings from small pools, phone numbers are libphonenumber's documented example numbers, and card, bank
and ID numbers are produced from the format rules rather than copied from anywhere.
"""
import base64
import hashlib
import random
import string

import phonenumbers

DIGITS = string.digits
UPPER = string.ascii_uppercase


# ------------------------------------------------------------------ small helpers
def digits(rng, n):
    return "".join(rng.choice(DIGITS) for _ in range(n))


def upper(rng, n, pool=UPPER):
    return "".join(rng.choice(pool) for _ in range(n))


def luhn_digit(partial):
    """Check digit that makes partial + digit pass the Luhn test."""
    total = 0
    for i, ch in enumerate(reversed(partial)):
        d = int(ch)
        if i % 2 == 0:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return str((10 - total % 10) % 10)


def group(value, size, sep=" "):
    return sep.join(value[i:i + size] for i in range(0, len(value), size))


def base58_encode(data):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = int.from_bytes(data, "big")
    out = ""
    while number:
        number, rem = divmod(number, 58)
        out = alphabet[rem] + out
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + out


def bitcoin_address(rng, version=0):
    payload = bytes([version]) + bytes(rng.randrange(256) for _ in range(20))
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return base58_encode(payload + checksum)


def iban(rng, country, bban_pattern):
    """bban_pattern like 'LLLLDDDDDDDDDDDDDD' (L letter, D digit, A alphanumeric)."""
    bban = "".join({"L": rng.choice(UPPER), "D": rng.choice(DIGITS), "A": rng.choice(UPPER + DIGITS)}[c] for c in bban_pattern)
    moved = bban + country + "00"
    numeric = "".join(str(int(c, 36)) for c in moved)
    check = 98 - int(numeric) % 97
    return f"{country}{check:02d}{bban}"


IBAN_FORMATS = {"GB": "LLLLDDDDDDDDDDDDDD", "DE": "D" * 18, "FR": "D" * 10 + "A" * 11 + "DD", "ES": "D" * 20,
                "IT": "L" + "D" * 10 + "A" * 12, "NL": "LLLL" + "D" * 10, "BE": "D" * 12, "CH": "D" * 5 + "A" * 12,
                "AT": "D" * 16, "PL": "D" * 24, "SE": "D" * 20, "NO": "D" * 11, "DK": "D" * 14, "IE": "LLLL" + "D" * 14,
                "PT": "D" * 21, "FI": "D" * 14}


def example_phone(rng, regions):
    region = rng.choice(regions)
    number = phonenumbers.example_number(region)
    # Vary the example a little so numbers are not all identical across records.
    return phonenumbers.format_number(number, rng.choice([phonenumbers.PhoneNumberFormat.INTERNATIONAL,
                                                          phonenumbers.PhoneNumberFormat.NATIONAL,
                                                          phonenumbers.PhoneNumberFormat.E164]))


PHONE_REGIONS = ["US", "GB", "DE", "FR", "ES", "IT", "NL", "IN", "CA", "BR", "AU", "JP", "KR", "CN", "MX", "ZA", "NG", "SG",
                 "SE", "FI", "PL", "TR", "TH", "PH", "AR", "EG", "ID", "IL", "NZ", "RU", "CH", "IE", "PT", "BE", "AT"]


def ssn(rng):
    return f"{rng.choice([a for a in range(1, 900) if a != 666]):03d}-{rng.randint(1, 99):02d}-{rng.randint(1, 9999):04d}"


def itin(rng):
    return f"9{rng.randint(0, 99):02d}-{rng.choice(list(range(70, 89)) + [90, 91, 92] + list(range(94, 100))):02d}-{rng.randint(0, 9999):04d}"


def aba(rng):
    first = rng.choice(list(range(1, 13)) + list(range(21, 33)))
    d = [int(c) for c in f"{first:02d}" + digits(rng, 6)]
    last = (10 - (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + d[2] + d[5]) % 10) % 10
    return "".join(map(str, d)) + str(last)


def npi(rng):
    body = rng.choice("12") + digits(rng, 8)
    for check in "0123456789":
        total = 0
        for pos, ch in enumerate(reversed("80840" + body + check)):
            d = int(ch)
            if pos % 2:
                d = d * 2 - 9 if d * 2 > 9 else d * 2
            total += d
        if total % 10 == 0:
            return body + check


def mbi(rng):
    letters = "ACDEFGHJKMNPQRTUVWXY"
    return (rng.choice("123456789") + rng.choice(letters) + rng.choice(letters + DIGITS) + rng.choice(DIGITS) + "-" +
            rng.choice(letters) + rng.choice(letters + DIGITS) + rng.choice(DIGITS) + "-" +
            rng.choice(letters) + rng.choice(letters) + rng.choice(DIGITS) + rng.choice(DIGITS))


def dea_number(rng):
    d = [rng.randint(0, 9) for _ in range(6)]
    check = (d[0] + d[2] + d[4] + 2 * (d[1] + d[3] + d[5])) % 10
    return rng.choice("ABFGM") + rng.choice(UPPER) + "".join(map(str, d)) + str(check)


def nhs(rng):
    while True:
        d = [rng.randint(0, 9) for _ in range(9)]
        check = 11 - sum(v * w for v, w in zip(d, range(10, 1, -1))) % 11
        check = 0 if check == 11 else check
        if check != 10:
            full = "".join(map(str, d)) + str(check)
            return f"{full[:3]} {full[3:6]} {full[6:]}"


def nino(rng):
    bad = {"BG", "GB", "NK", "KN", "TN", "NT", "ZZ"}
    while True:
        prefix = rng.choice("ABCEGHJKLMNOPRSTWXYZ") + rng.choice("ABCEGHJKLMNPRSTWXYZ")
        if prefix not in bad:
            return f"{prefix} {digits(rng, 2)} {digits(rng, 2)} {digits(rng, 2)} {rng.choice('ABCD')}"


def uk_postcode(rng):
    return rng.choice(["SW1A 1AA", "EC1A 1BB", "M1 1AE", "B33 8TH", "CR2 6XH", "DN55 1PT", "W1A 0AX", "L1 8JQ", "G1 1XQ", "EH1 1YZ",
                       "LS1 4AP", "BS1 5TR", "NE1 4ST", "CF10 1EP", "BT1 5GS", "AB10 1XG", "OX1 2JD", "CB2 1TN"])


def uk_vrm(rng):
    return f"{upper(rng, 2, 'ABCDEFGHKLMNOPRSTUVWXY')}{rng.choice(['02', '08', '15', '19', '21', '23', '24', '51', '58', '64', '70', '73'])} {upper(rng, 3, 'ABCDEFGHJKLMNOPRSTUVWXYZ')}"


def uk_driving_licence(rng):
    surname = upper(rng, 5)
    decade = rng.choice("5678")
    month = rng.choice(["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "51", "52", "53", "54", "55", "56", "57"])
    return f"{surname}{decade}{month}{rng.randint(1, 28):02d}{rng.choice(DIGITS)}{upper(rng, 2)}9{upper(rng, 2)}"


def es_nif(rng):
    n = rng.randint(10_000_000, 99_999_999)
    return f"{n}{'TRWAGMYFPDXBNJZSQVHLCKE'[n % 23]}"


def es_nie(rng):
    lead = rng.choice("XYZ")
    n = rng.randint(1_000_000, 9_999_999)
    return f"{lead}{n:07d}{'TRWAGMYFPDXBNJZSQVHLCKE'[int(str('XYZ'.index(lead)) + f'{n:07d}') % 23]}"


def it_fiscal_code(rng):
    odd = {**dict(zip("0123456789", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21])),
           **dict(zip(UPPER, [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23]))}
    even = {**{c: i for i, c in enumerate("0123456789")}, **{c: i for i, c in enumerate(UPPER)}}
    body = (upper(rng, 3, "BCDFGHJKLMNPQRSTVWXYZ") + upper(rng, 3, "BCDFGHJKLMNPQRSTVWXYZ") + f"{rng.randint(40, 99):02d}" +
            rng.choice("ABCDEHLMPRST") + f"{rng.randint(1, 28):02d}" + rng.choice("ABCDEFGHILMZ") + digits(rng, 3))
    total = sum((odd if i % 2 == 0 else even)[c] for i, c in enumerate(body))
    return body + UPPER[total % 26]


def it_vat(rng):
    body = digits(rng, 7) + f"{rng.randint(1, 100):03d}"
    return body + luhn_digit(body)


def pesel(rng):
    body = f"{rng.randint(50, 99):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}" + digits(rng, 4)
    check = (10 - sum(int(c) * w for c, w in zip(body, [1, 3, 7, 9, 1, 3, 7, 9, 1, 3])) % 10) % 10
    return body + str(check)


def sg_nric(rng):
    lead = rng.choice("STFG")
    body = digits(rng, 7)
    total = sum(int(c) * w for c, w in zip(body, [2, 7, 6, 5, 4, 3, 2])) + (4 if lead in "TG" else 0)
    table = "JZIHGFEDCBA" if lead in "ST" else "XWUTRQPNMLK"
    return f"{lead}{body}{table[total % 11]}"


def au_abn(rng):
    while True:
        d = [int(c) for c in rng.choice("123456789") + digits(rng, 10)]
        d[0] -= 1
        if sum(v * w for v, w in zip(d, [10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19])) % 89 == 0:
            d[0] += 1
            s = "".join(map(str, d))
            return f"{s[:2]} {s[2:5]} {s[5:8]} {s[8:]}"


def au_acn(rng):
    d = [rng.randint(0, 9) for _ in range(8)]
    check = (10 - sum(v * w for v, w in zip(d, range(8, 0, -1))) % 10) % 10
    s = "".join(map(str, d)) + str(check)
    return f"{s[:3]} {s[3:6]} {s[6:]}"


def au_tfn(rng):
    while True:
        d = [rng.randint(0, 9) for _ in range(9)]
        if d[0] and sum(v * w for v, w in zip(d, [1, 4, 3, 7, 5, 8, 6, 9, 10])) % 11 == 0:
            s = "".join(map(str, d))
            return f"{s[:3]} {s[3:6]} {s[6:]}"


def au_medicare(rng):
    while True:
        d = [rng.randint(2, 6)] + [rng.randint(0, 9) for _ in range(7)]
        check = sum(v * w for v, w in zip(d, [1, 3, 7, 9, 1, 3, 7, 9])) % 10
        s = "".join(map(str, d)) + str(check) + str(rng.randint(1, 9))
        return f"{s[:4]} {s[4:9]} {s[9]}"


def in_pan(rng):
    return upper(rng, 3) + rng.choice("ABCFGHLJPT") + upper(rng, 1) + digits(rng, 4) + upper(rng, 1)


def verhoeff_digit(num):
    d = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
         [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1], [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
         [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
    p = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
         [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1], [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
    inv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = d[c][p[(i + 1) % 8][int(ch)]]
    return str(inv[c])


def aadhaar(rng):
    body = rng.choice("23456789") + digits(rng, 10)
    s = body + verhoeff_digit(body)
    return f"{s[:4]} {s[4:8]} {s[8:]}"


def in_vehicle(rng):
    return f"{rng.choice(['KA', 'MH', 'DL', 'TN', 'UP', 'GJ', 'RJ', 'WB', 'AP', 'KL'])}{rng.randint(1, 60):02d}{upper(rng, 2)}{digits(rng, 4)}"


def in_gstin(rng):
    chars = DIGITS + UPPER
    body = f"{rng.randint(1, 37):02d}{in_pan(rng)}{rng.randint(1, 9)}Z"
    total = 0
    for i, ch in enumerate(body):
        v = chars.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return body + chars[(36 - total % 36) % 36]


def fi_hetu(rng):
    day, month, year = rng.randint(1, 28), rng.randint(1, 12), rng.randint(40, 99)
    individual = rng.randint(2, 899)
    return f"{day:02d}{month:02d}{year:02d}-{individual:03d}{'0123456789ABCDEFHJKLMNPRSTUVWXY'[int(f'{day:02d}{month:02d}{year:02d}{individual:03d}') % 31]}"


def kr_rrn(rng, foreign=False):
    birth = f"{rng.randint(50, 99):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
    gender = rng.choice("5678" if foreign else "1234")
    body = birth + gender + digits(rng, 5)
    check = (11 - sum(int(c) * w for c, w in zip(body, [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5])) % 11) % 10
    return f"{body[:6]}-{body[6:]}{check}"


def kr_brn(rng):
    body = digits(rng, 9)
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    total = sum(int(c) * w for c, w in zip(body, weights)) + (int(body[8]) * 5) // 10
    s = body + str((10 - total % 10) % 10)
    return f"{s[:3]}-{s[3:5]}-{s[5:]}"


def th_tnin(rng):
    province = rng.choice(["10", "11", "30", "40", "13", "20", "21", "50", "51", "60", "61", "70", "71", "80", "81", "90", "91"])
    body = rng.choice("12345678") + province + digits(rng, 9)
    check = (11 - sum(int(c) * (13 - i) for i, c in enumerate(body)) % 11) % 10
    return body + str(check)


def ca_sin(rng):
    body = rng.choice("1234567") + digits(rng, 7)
    s = body + luhn_digit(body)
    return f"{s[:3]} {s[3:6]} {s[6:]}"


def se_personnummer(rng):
    body = f"{rng.randint(50, 99):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}{digits(rng, 3)}"
    return f"{body[:6]}-{body[6:]}{luhn_digit(body)}"


def se_orgnr(rng):
    body = "55" + rng.choice("6789") + digits(rng, 6)
    s = body + luhn_digit(body)
    return f"{s[:6]}-{s[6:]}"


def za_id(rng):
    body = f"{rng.randint(50, 99):02d}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}{digits(rng, 4)}{rng.choice('01')}8"
    return body + luhn_digit(body)


def tr_tckn(rng):
    d = [rng.randint(1, 9)] + [rng.randint(0, 9) for _ in range(8)]
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    d.append(d10)
    d.append(sum(d) % 10)
    return "".join(map(str, d))


def tr_plate(rng):
    return f"{rng.randint(1, 81):02d} {upper(rng, 3, 'ABCDEFGHJKLMNPRSTUVYZ')} {rng.randint(100, 999)}"


def de_tax_id(rng):
    """11 digits: one digit appears 2-3 times in the first ten, the rest at most once; ISO 7064 check digit."""
    while True:
        body = [rng.randint(1, 9)] + [rng.randint(0, 9) for _ in range(9)]
        counts = [body.count(d) for d in set(body)]
        if sorted(counts, reverse=True)[0] in (2, 3) and sum(1 for c in counts if c > 1) == 1 and \
                (body[:3] != body[1:4] and body[:3] != body[2:5] and body[:3] != body[3:6] and body[:3] != body[4:7]):
            product = 10
            for digit in body:
                total = (digit + product) % 10 or 10
                product = (total * 2) % 11
            check = (11 - product) % 10
            return "".join(map(str, body)) + str(check)


def de_social_security(rng):
    area = rng.choice([2, 3, 4, 8, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 28, 29, 38, 39, 40, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 89])
    birth = f"{rng.randint(1, 28):02d}{rng.randint(1, 12):02d}{rng.randint(50, 99):02d}"
    letter = rng.choice(UPPER)
    body = f"{area:02d}{birth}{letter}{rng.randint(0, 99):02d}"
    mapped = f"{area:02d}{birth}{UPPER.index(letter) + 1:02d}{body[-2:]}"
    total = 0
    for ch, w in zip(mapped, [2, 1, 2, 5, 7, 1, 2, 1, 2, 1, 2, 1]):
        p = int(ch) * w
        total += p // 10 + p % 10
    return body + str(total % 10)


def de_health_insurance(rng):
    letter = rng.choice(UPPER)
    body = digits(rng, 8)
    mapped = f"{UPPER.index(letter) + 1:02d}{body}"
    total = 0
    for i, ch in enumerate(mapped):
        p = int(ch) * (1 if i % 2 == 0 else 2)
        total += p // 10 + p % 10
    return f"{letter}{body}{total % 10}"


def kr_driver_license(rng):
    return f"{rng.choice(['11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25', '26'])}-{rng.randint(10, 99)}-{digits(rng, 6)}-{digits(rng, 2)}"


def ng_nin(rng):
    return digits(rng, 11)


def ph_tin(rng):
    s = digits(rng, 9)
    return f"{s[:3]}-{s[3:6]}-{s[6:]}-000"


def us_passport(rng):
    return digits(rng, 9)


def us_driver_license(rng):
    return rng.choice([upper(rng, 1) + digits(rng, 7), upper(rng, 1) + digits(rng, 12), digits(rng, 8), upper(rng, 2) + digits(rng, 6)])


def credit_card(rng):
    """Visa, Mastercard, Amex, Discover or JCB number with a valid Luhn check digit."""
    prefix, length = rng.choice([("4", 16), ("51", 16), ("52", 16), ("53", 16), ("54", 16), ("55", 16), ("34", 15), ("37", 15), ("6011", 16), ("35", 16)])
    body = prefix + digits(rng, length - len(prefix) - 1)
    number = body + luhn_digit(body)
    return group(number, 4) if length == 16 else f"{number[:4]} {number[4:10]} {number[10:]}"


# ------------------------------------------------------------------ one generator per Presidio entity
def ENTITY_GENERATORS():
    return {
        "CREDIT_CARD": credit_card,
        "CRYPTO": lambda r: bitcoin_address(r, r.choice([0, 5])),
        "EMAIL_ADDRESS": None, "DATE_TIME": None, "PERSON": None, "LOCATION": None, "NRP": None,
        "IBAN_CODE": lambda r: (lambda c: group(iban(r, c, IBAN_FORMATS[c]), 4))(r.choice(list(IBAN_FORMATS))),
        "IP_ADDRESS": lambda r: r.choice([f"{r.randint(1, 223)}.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}",
                                          ":".join(f"{r.randint(0, 65535):x}" for _ in range(8))]),
        "MAC_ADDRESS": lambda r: ":".join(f"{r.randint(0, 255):02X}" for _ in range(6)),
        "PHONE_NUMBER": lambda r: example_phone(r, PHONE_REGIONS),
        "MEDICAL_LICENSE": dea_number,
        "URL": lambda r: r.choice(["https://", "http://", "https://www."]) + r.choice(["example.com", "acme.org", "portal.initech.io", "shop.globex.net", "mail.contoso.co.uk"]) + "/" + r.choice(["u", "profile", "account", "orders"]) + "/" + digits(r, 5),
        "US_BANK_NUMBER": lambda r: digits(r, r.randint(8, 17)),
        "US_DRIVER_LICENSE": us_driver_license, "US_ITIN": itin, "US_MBI": mbi, "US_NPI": npi, "US_PASSPORT": us_passport, "US_SSN": ssn,
        "ABA_ROUTING_NUMBER": aba,
        "UK_DRIVING_LICENCE": uk_driving_licence, "UK_NHS": nhs, "UK_NINO": nino,
        "UK_PASSPORT": lambda r: upper(r, 2) + digits(r, 7), "UK_POSTCODE": uk_postcode, "UK_VEHICLE_REGISTRATION": uk_vrm,
        "ES_NIF": es_nif, "ES_NIE": es_nie, "ES_PASSPORT": lambda r: upper(r, 3) + digits(r, 6),
        "IT_FISCAL_CODE": it_fiscal_code, "IT_DRIVER_LICENSE": lambda r: upper(r, 2) + digits(r, 7) + upper(r, 1),
        "IT_VAT_CODE": it_vat, "IT_PASSPORT": lambda r: upper(r, 2) + digits(r, 7), "IT_IDENTITY_CARD": lambda r: "C" + upper(r, 1) + digits(r, 5) + upper(r, 2),
        "PL_PESEL": pesel,
        "SG_NRIC_FIN": sg_nric, "SG_UEN": lambda r: r.choice([digits(r, 8) + upper(r, 1), "20" + digits(r, 2) + digits(r, 5) + upper(r, 1), "T" + digits(r, 2) + "LL" + digits(r, 4) + upper(r, 1)]),
        "AU_ABN": au_abn, "AU_ACN": au_acn, "AU_TFN": au_tfn, "AU_MEDICARE": au_medicare,
        "IN_PAN": in_pan, "IN_AADHAAR": aadhaar, "IN_VEHICLE_REGISTRATION": in_vehicle,
        "IN_VOTER": lambda r: upper(r, 3) + digits(r, 7), "IN_PASSPORT": lambda r: r.choice("ABCDEFGHJKLMNPRSTUVWY") + digits(r, 7), "IN_GSTIN": in_gstin,
        "FI_PERSONAL_IDENTITY_CODE": fi_hetu,
        "KR_DRIVER_LICENSE": kr_driver_license, "KR_FRN": lambda r: kr_rrn(r, True), "KR_PASSPORT": lambda r: r.choice("MSRGD") + digits(r, 8),
        "KR_BRN": kr_brn, "KR_RRN": kr_rrn,
        "TH_TNIN": th_tnin, "NG_NIN": ng_nin, "NG_VEHICLE_REGISTRATION": lambda r: upper(r, 3) + "-" + digits(r, 3) + upper(r, 2),
        "PH_TIN": ph_tin, "CA_SIN": ca_sin, "SE_ORGANISATIONSNUMMER": se_orgnr, "SE_PERSONNUMMER": se_personnummer,
        "ZA_ID_NUMBER": za_id, "TR_NATIONAL_ID": tr_tckn, "TR_LICENSE_PLATE": tr_plate,
        "DE_TAX_ID": de_tax_id, "DE_TAX_NUMBER": lambda r: f"{r.randint(10, 99)}/{digits(r, 3)}/{digits(r, 5)}",
        "DE_PASSPORT": lambda r: r.choice("CFGHJK") + digits(r, 2) + upper(r, 1) + digits(r, 2) + upper(r, 1) + digits(r, 2),
        "DE_ID_CARD": lambda r: r.choice("LMNPRTVWXYZ") + digits(r, 2) + upper(r, 1, "CFGHJKLMNPRTVWXYZ") + digits(r, 2) + upper(r, 1, "CFGHJKLMNPRTVWXYZ") + digits(r, 2),
        "DE_SOCIAL_SECURITY": de_social_security, "DE_HEALTH_INSURANCE": de_health_insurance,
        "DE_KFZ": lambda r: f"{r.choice(['B', 'M', 'HH', 'K', 'F', 'S', 'DD'])}-{upper(r, 2)} {r.randint(1, 9999)}",
        "DE_HANDELSREGISTER": lambda r: f"HR{r.choice('AB')} {r.randint(1000, 99999)}", "DE_PLZ": lambda r: f"{r.randint(10, 99)}{digits(r, 3)}",
    }


# ------------------------------------------------------------------ pools for people, places and free text
FIRST = ["Sarah", "Michael", "Priya", "Daniel", "Aisha", "Wei", "Carlos", "Fatima", "Hiroshi", "Olga", "Kwame", "Sofia", "Liam", "Mei",
         "Ahmed", "Chloe", "Rajesh", "Elena", "Tomasz", "Ingrid", "Mateo", "Yuki", "Amara", "Noah", "Zainab", "Lucas", "Hana", "Ivan",
         "Camila", "Oluwaseun", "Anders", "Leila", "Jin", "Marta", "Dmitri", "Ananya", "Pedro", "Nadia", "Sven", "Kavya", "Emma", "Omar",
         "Grace", "Mikael", "Tariq", "Isabella", "Chen", "Beatriz", "Kofi", "Eleni"]
LAST = ["Johnson", "Chen", "Patel", "O'Connor", "Garcia", "Nguyen", "Kim", "Müller", "Rossi", "Silva", "Okafor", "Ivanov", "Tanaka",
        "Hassan", "Andersson", "Kowalski", "Haddad", "Larsen", "Mendoza", "Sato", "Dubois", "Bianchi", "Singh", "Khan", "Moreau",
        "Papadopoulos", "Fernandez", "Nakamura", "Abdullah", "Costa", "Williams", "Brown", "Jones", "Davis", "Wilson", "Taylor",
        "Mensah", "Petrov", "Lindqvist", "Yilmaz", "Reddy", "Kaur", "Oliveira", "Schmidt", "Novak", "Park", "Lopez", "Walker", "Hall", "Young"]
CITIES = [("Springfield", "IL", "62704", "United States"), ("Austin", "TX", "78701", "United States"), ("Seattle", "WA", "98101", "United States"),
          ("Boston", "MA", "02108", "United States"), ("Denver", "CO", "80202", "United States"), ("London", "", "SW1A 1AA", "United Kingdom"),
          ("Manchester", "", "M1 1AE", "United Kingdom"), ("Berlin", "", "10115", "Germany"), ("Munich", "", "80331", "Germany"),
          ("Madrid", "", "28013", "Spain"), ("Rome", "", "00184", "Italy"), ("Paris", "", "75001", "France"), ("Warsaw", "", "00-001", "Poland"),
          ("Mumbai", "MH", "400001", "India"), ("Bengaluru", "KA", "560001", "India"), ("Sydney", "NSW", "2000", "Australia"),
          ("Toronto", "ON", "M5H 2N2", "Canada"), ("Singapore", "", "049315", "Singapore"), ("Seoul", "", "04524", "South Korea"),
          ("Bangkok", "", "10110", "Thailand"), ("Lagos", "", "101233", "Nigeria"), ("Manila", "", "1000", "Philippines"),
          ("Stockholm", "", "111 22", "Sweden"), ("Helsinki", "", "00100", "Finland"), ("Istanbul", "", "34410", "Turkey"),
          ("Johannesburg", "", "2001", "South Africa"), ("Tokyo", "", "100-0001", "Japan"), ("São Paulo", "SP", "01310-100", "Brazil"),
          ("Mexico City", "", "06000", "Mexico"), ("Cairo", "", "11511", "Egypt")]
STREETS = ["Evergreen Terrace", "Maple Street", "Oak Avenue", "Pennsylvania Avenue NW", "Baker Street", "Elm Road", "Sunset Boulevard", "High Street",
           "Park Lane", "Main Street", "Lakeview Drive", "Hauptstraße", "Calle Mayor", "Via Roma", "Rue de Rivoli", "Nathan Road", "Orchard Road"]
COMPANIES = ["Acme Corp", "Globex Corporation", "Initech", "Umbrella Holdings", "Stark Industries", "Wayne Enterprises", "Soylent Foods", "Hooli Inc",
             "Cyberdyne Systems", "Wonka Industries", "Tyrell Corporation", "Massive Dynamic", "Vandelay Industries", "Oscorp", "Pied Piper"]
NATIONALITIES = ["American", "British", "German", "Spanish", "Italian", "Indian", "Korean", "Nigerian", "Filipino", "Canadian", "Swedish", "Turkish",
                 "South African", "Australian", "Thai", "Polish", "Finnish", "Singaporean", "Brazilian", "Japanese"]
RELIGIONS = ["Catholic", "Muslim", "Hindu", "Buddhist", "Jewish", "Sikh", "Protestant", "Orthodox Christian", "Atheist", "Mormon"]
POLITICAL = ["Democrat", "Republican", "Conservative", "Labour supporter", "Green Party member", "Libertarian", "Socialist", "Liberal Democrat"]
MEDICAL = [("Type 2 diabetes", "metformin"), ("hypertension", "lisinopril"), ("asthma", "albuterol"), ("major depressive disorder", "sertraline"),
           ("hypothyroidism", "levothyroxine"), ("migraine", "sumatriptan"), ("rheumatoid arthritis", "methotrexate"), ("HIV-positive status", "dolutegravir")]
NON_LATIN_NAMES = ["山田 太郎", "김민준", "王小明", "Алексей Иванов", "محمد علي", "राहुल शर्मा", "Νίκος Παπαδόπουλος", "สมชาย ใจดี", "Владимир Петров", "עמית כהן"]


# ------------------------------------------------------------------ personal data beyond Presidio's entity list
def username(rng):
    return rng.choice([rng.choice(FIRST).lower() + "_" + rng.choice(LAST).lower().replace("'", ""), rng.choice(FIRST).lower() + digits(rng, 2),
                       rng.choice(LAST).lower().replace("'", "") + "." + rng.choice(FIRST)[0].lower() + str(rng.randint(70, 99))])


def password(rng):
    return upper(rng, 1) + "".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(4, 7))) + rng.choice("!@#$%&*") + digits(rng, rng.randint(2, 4)) + upper(rng, 1)


def api_key(rng):
    return rng.choice([lambda: "AKIA" + upper(rng, 16, UPPER + DIGITS),
                       lambda: "ghp_" + "".join(rng.choice(string.ascii_letters + DIGITS) for _ in range(36)),
                       lambda: "sk_demo_" + "".join(rng.choice(string.ascii_letters + DIGITS) for _ in range(24)),
                       lambda: "xoxb-" + digits(rng, 11) + "-" + digits(rng, 12) + "-" + "".join(rng.choice(string.ascii_letters + DIGITS) for _ in range(24)),
                       lambda: "api_key_" + "".join(rng.choice("0123456789abcdef") for _ in range(32)),
                       lambda: "AIza" + "".join(rng.choice(string.ascii_letters + DIGITS + "-_") for _ in range(35))])()


def jwt(rng):
    part = lambda n: base64.urlsafe_b64encode(bytes(rng.randrange(256) for _ in range(n))).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.{part(40)}.{part(32)}"


def imei(rng):
    body = digits(rng, 14)
    return body + luhn_digit(body)


def vin(rng):
    return upper(rng, 17, "ABCDEFGHJKLMNPRSTUVWXYZ0123456789")


def us_plate(rng):
    return rng.choice([f"{rng.randint(1, 9)}{upper(rng, 3)}{digits(rng, 3)}", f"{upper(rng, 3)}-{digits(rng, 4)}", f"{upper(rng, 2)}{digits(rng, 2)} {upper(rng, 3)}"])


def uuid_like(rng):
    h = "".join(rng.choice("0123456789abcdef") for _ in range(32))
    return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:]}"


def coordinates(rng):
    return f"{rng.uniform(-60, 65):.5f}, {rng.uniform(-170, 175):.5f}"


def email(rng, first, last, domain=None):
    domain = domain or rng.choice(["example.com", "mail.example.org", "acme.com", "globex.net", "contoso.co.uk", "initech.io", "fastmail.test", "gmail.com", "outlook.com", "proton.me"])
    clean = lambda s: s.lower().replace("'", "").replace(" ", "")
    return rng.choice([f"{clean(first)}.{clean(last)}@{domain}", f"{clean(first)[0]}{clean(last)}@{domain}", f"{clean(first)}{rng.randint(1, 99)}@{domain}"])


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def birth_date(rng):
    y, m, d = rng.randint(1950, 2006), rng.randint(1, 12), rng.randint(1, 28)
    return {"iso": f"{y}-{m:02d}-{d:02d}", "us": f"{m:02d}/{d:02d}/{y}", "long": f"{d} {MONTHS[m - 1]} {y}"}


USER_AGENTS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
               "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
               "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0"]


# ------------------------------------------------------------------ data for the custom recognizers (pii_detector/recognizers.py)
GENDERS = ["female", "male", "non-binary"]
ETHNICITIES = ["Hispanic", "Asian", "Black", "White", "Caucasian", "Native American", "Pacific Islander", "Middle Eastern", "South Asian", "African American"]
MARITAL = ["single", "married", "divorced", "widowed", "separated", "domestic partnership"]
ORIENTATIONS = ["heterosexual", "gay", "lesbian", "bisexual", "asexual", "pansexual", "queer"]
RELIGION_VALUES = ["Catholic", "Muslim", "Hindu", "Buddhist", "Jewish", "Sikh", "Protestant", "Atheist", "Mormon", "Christian"]
POLITICAL_VALUES = ["Democrat", "Republican", "Libertarian", "Green Party", "Conservative", "Socialist", "Independent", "Progressive"]
US_CITIES = [c for c in CITIES if c[3] == "United States"]


def zip5(rng):
    return f"{rng.randint(10000, 99999)}" + (f"-{rng.randint(1000, 9999)}" if rng.random() < 0.3 else "")


def us_address(rng):
    city, state, _, _ = rng.choice(US_CITIES)
    return f"{rng.randint(1, 9999)} {rng.choice(['Maple Street', 'Oak Avenue', 'Elm Road', 'Pennsylvania Avenue NW', 'Evergreen Terrace', 'Sunset Boulevard', 'Lakeview Drive', 'Main St'])}, {city}, {state} {zip5(rng)}"


def ein(rng):
    return f"{rng.randint(10, 99)}-{digits(rng, 7)}"


def date_formats(rng, kind="us"):
    y, m, d = rng.randint(1940, 2024), rng.randint(1, 12), rng.randint(1, 28)
    return {"us": f"{m:02d}/{d:02d}/{y}", "iso": f"{y}-{m:02d}-{d:02d}", "long": f"{MONTHS[m - 1]} {d}, {y}", "day_first": f"{d} {MONTHS[m - 1]} {y}"}[kind]


def mrn(rng):
    return digits(rng, rng.randint(6, 10))


def policy_number(rng):
    return upper(rng, 3) + digits(rng, rng.randint(8, 10))


def customer_id(rng):
    return rng.choice(["CUST-", "C", "M-", "ACC"]) + digits(rng, rng.randint(6, 8))


def professional_license(rng):
    return rng.choice(["RN-", "MD", "BAR-", "CPA-"]) + digits(rng, rng.randint(5, 7))


def session_id(rng):
    return "".join(rng.choice("0123456789abcdef") for _ in range(32))


def fingerprint_hash(rng):
    return "".join(rng.choice("0123456789abcdef") for _ in range(rng.choice([32, 40, 64])))


def passport_generic(rng):
    return rng.choice([upper(rng, 1) + digits(rng, 8), digits(rng, 9), upper(rng, 2) + digits(rng, 7)])


def national_id(rng):
    return digits(rng, rng.choice([8, 10, 12, 13]))


def driver_license_generic(rng):
    return rng.choice([upper(rng, 1) + digits(rng, 7), upper(rng, 2) + digits(rng, 6), digits(rng, 8), upper(rng, 1) + digits(rng, 3) + "-" + digits(rng, 3) + "-" + digits(rng, 3)])


def tax_id_generic(rng):
    return rng.choice(["DE", "FR", "GB", "NL", "ES", "IT", "SE", "PL"]) + digits(rng, rng.randint(9, 11))


def alien_number(rng):
    return "A" + digits(rng, 9)


def ethereum(rng):
    return "0x" + "".join(rng.choice("0123456789abcdefABCDEF") for _ in range(40))


def swift_code(rng):
    return upper(rng, 4) + rng.choice(["US", "GB", "DE", "FR", "IN", "SG", "AU", "CA"]) + upper(rng, 2, UPPER + DIGITS) + (upper(rng, 3, UPPER + DIGITS) if rng.random() < 0.5 else "")


def serial_number(rng):
    return rng.choice(["SN", "S", "SER"]) + digits(rng, rng.randint(7, 10))


def credit_score(rng):
    return str(rng.randint(300, 850))


def us_phone(rng):
    return rng.choice([f"({rng.randint(2, 9)}{digits(rng, 2)}) {rng.randint(2, 9)}{digits(rng, 2)}-{digits(rng, 4)}", f"{rng.randint(2, 9)}{digits(rng, 2)}-{rng.randint(2, 9)}{digits(rng, 2)}-{digits(rng, 4)}"])


def private_key_header(rng):
    return rng.choice(["-----BEGIN RSA PRIVATE KEY-----", "-----BEGIN OPENSSH PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----", "-----BEGIN EC PRIVATE KEY-----"])


def social_handle(rng):
    return "@" + username(rng).replace(".", "_")


def gps(rng):
    return coordinates(rng)


def uuid_value(rng):
    return uuid_like(rng)


# entity -> (context lead used in a test sentence, generator): one row for every custom entity
CUSTOM_EXAMPLES = {
    "ADDRESS": ("home address", us_address), "US_ZIP_CODE": ("ZIP code", zip5), "US_EIN": ("EIN", ein),
    "DATE_OF_BIRTH": ("date of birth", lambda r: date_formats(r, r.choice(["us", "iso", "long", "day_first"]))), "AGE": ("age", lambda r: str(r.randint(18, 95))),
    "SALARY": ("annual salary", lambda r: f"${r.randint(28, 240)},{digits(r, 3)}"), "GENDER": ("gender", lambda r: r.choice(GENDERS)),
    "ETHNICITY": ("ethnicity", lambda r: r.choice(ETHNICITIES)), "MARITAL_STATUS": ("marital status", lambda r: r.choice(MARITAL)),
    "SEXUAL_ORIENTATION": ("sexual orientation", lambda r: r.choice(ORIENTATIONS)), "RELIGION": ("religion", lambda r: r.choice(RELIGION_VALUES)),
    "POLITICAL_AFFILIATION": ("political affiliation", lambda r: r.choice(POLITICAL_VALUES)), "CREDIT_SCORE": ("credit score", credit_score),
    "EMPLOYEE_ID": ("employee ID", lambda r: f"EMP-{digits(r, 6)}"), "STUDENT_ID": ("student ID", lambda r: f"S{digits(r, 8)}"),
    "ACCOUNT_ID": ("customer ID", customer_id), "MEDICAL_RECORD_NUMBER": ("medical record number MRN", mrn),
    "INSURANCE_ID": ("insurance policy number", policy_number), "PROFESSIONAL_LICENSE": ("nursing license number", professional_license),
    "PASSWORD": ("password is", password), "USERNAME": ("username", username), "API_KEY": ("API key", api_key), "AUTH_TOKEN": ("bearer", jwt),
    "PRIVATE_KEY": ("leaked key", private_key_header), "SOCIAL_HANDLE": ("follow", social_handle), "SESSION_ID": ("session ID", session_id),
    "BIOMETRIC_ID": ("fingerprint hash", fingerprint_hash), "CARD_CVV": ("CVV", lambda r: digits(r, r.choice([3, 4]))),
    "CARD_EXPIRY": ("expiry", lambda r: f"{r.randint(1, 12):02d}/{r.randint(27, 33)}"), "PASSPORT_NUMBER": ("passport number", passport_generic),
    "US_PASSPORT": ("passport number", lambda r: r.choice([digits(r, 9), upper(r, 1) + digits(r, 8)])), "NATIONAL_ID_NUMBER": ("national ID number", national_id),
    "DRIVER_LICENSE_NUMBER": ("driver license number", driver_license_generic), "TAX_ID_NUMBER": ("VAT number", tax_id_generic),
    "US_ALIEN_NUMBER": ("alien registration number", alien_number), "US_BANK_NUMBER": ("bank account number", lambda r: digits(r, r.randint(8, 12))),
    "VIN": ("VIN", None), "IMEI": ("IMEI", imei), "GPS_COORDINATES": ("coordinates", gps), "UUID": ("device", uuid_value),
    "SWIFT_BIC": ("SWIFT code", swift_code), "SERIAL_NUMBER": ("serial number", serial_number), "LICENSE_PLATE": ("license plate", us_plate),
    "CRYPTO": ("Ethereum wallet", ethereum), "PHONE_NUMBER": ("phone", us_phone), "DATE_OF_DEATH": ("died on", lambda r: date_formats(r, "us")),
    "ADMISSION_DATE": ("admitted on", lambda r: date_formats(r, "long")), "DISCHARGE_DATE": ("discharge date", lambda r: date_formats(r, "us")),
}


def vin_valid(rng):
    """A VIN whose position-9 check digit is valid."""
    values = {**{str(i): i for i in range(10)}, **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))), "P": 7, "R": 9, **dict(zip("STUVWXYZ", range(2, 10)))}
    weights = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
    chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    body = [rng.choice(chars) for _ in range(17)]
    total = sum(values[c] * w for c, w in zip(body, weights))
    body[8] = "X" if total % 11 == 10 else str(total % 11)
    return "".join(body)


CUSTOM_EXAMPLES["VIN"] = ("VIN", vin_valid)
