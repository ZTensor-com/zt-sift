"""Custom Presidio recognizers for PII that Presidio does not cover well out of the box.

Built the way https://presidio.dataprivacystack.org/analyzer/adding_recognizers/ describes:
  * PatternRecognizer (regex Patterns with scores and context words, optional checksum validation) for
    values whose shape identifies them, and
  * a LocalRecognizer subclass (LabeledValueRecognizer) for values that are only recognisable from the label
    in front of them ("password is ...", "CVV 737", "passport number ..."). It returns the span of the value
    only, not the label.

Everything is regex-based: fast (microseconds per recognizer) but heuristic. Scores follow Presidio's usual
scale: a distinctive shape scores 0.85-0.95, a label-plus-value match 0.8-0.9, a weak shape 0.3-0.6 (which
context words from the surrounding text can lift by about 0.35).

    from pii_detector.recognizers import add_custom_recognizers
    add_custom_recognizers(analyzer)        # registers everything in CUSTOM_ENTITIES
"""
import re

from presidio_analyzer import AnalysisExplanation, LocalRecognizer, Pattern, PatternRecognizer, RecognizerResult

# ---------------------------------------------------------------------------- building blocks
US_STATE_CODES = ("AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|PR|GU|VI")
US_STATE_NAMES = ("Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|"
                  "Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|"
                  "North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|"
                  "Washington|West Virginia|Wisconsin|Wyoming|District of Columbia")
CA_PROVINCES = "AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT"
STREET_SUFFIX = ("Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Terrace|Ter|Place|Pl|Circle|Cir|Parkway|Pkwy|Highway|Hwy|Square|Sq|"
                 "Trail|Trl|Alley|Plaza|Plz|Crescent|Cres|Close|Mews|Row|Loop|Pike|Run|Path|Walk|Gardens|Grove|Hill|Park|Cross")
DIRECTION = "N|S|E|W|NE|NW|SE|SW|North|South|East|West"
NAME_WORD = r"[A-Z0-9][A-Za-z0-9.'’\-]*"
# 742 Evergreen Terrace / 1600 Pennsylvania Avenue NW / 221B Baker Street / 5 N Main St Apt 4B
STREET = (rf"\b\d{{1,6}}[A-Za-z]?(?:-\d{{1,4}})?\s+(?:(?:{DIRECTION})\.?\s+)?(?:{NAME_WORD}\s+){{1,5}}?(?i:{STREET_SUFFIX})\b\.?(?:\s+(?:{DIRECTION})\b\.?)?"
          rf"(?:,?\s+(?i:Apt|Apartment|Suite|Ste|Unit|Floor|Fl|Room|Rm)\.?\s*#?[\w-]+|,?\s+#[\w-]+)?")
CITY = r"[A-Z][A-Za-z.'’\-]*(?:\s+[A-Z][A-Za-z.'’\-]*){0,3}"
ZIP = r"\d{5}(?:-\d{4})?"
UK_POSTCODE = r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}"
CA_POSTCODE = r"[A-Z]\d[A-Z]\s?\d[A-Z]\d"
FOREIGN_PREFIX = "Rue|Calle|Via|Viale|Avenida|Paseo|Piazza|Strada|Chaussée|Allée|Plaza|Carrer|Avinguda"
LINK = r"(?:de\s+(?:la\s+|los\s+|las\s+)?|del\s+|dei\s+|di\s+|d['’])?"
FOREIGN_NAME = rf"{LINK}[A-ZÀ-Ý][\wÀ-ÿ'’\-]*(?:\s+[A-ZÀ-Ý][\wÀ-ÿ'’\-]*){{0,3}}"
GERMAN_STREET = r"[A-ZÄÖÜ][\wäöüß\-]*(?:straße|strasse|str\.|weg|allee|platz|gasse|ring|damm|ufer)"


def _pattern(name, regex, score):
    return Pattern(name=name, regex=regex, score=score)


# Words that follow a label without being its value ("password reset", "user is logged in").
FILLER = (r"(?!(?:username|user|userid|password|passwd|pwd|passcode|passphrase|login|handle|screen|token|secret|key|apikey|"
          r"strength|compromised|unavailable|is|was|are|were|the|a|an|and|or|to|of|for|in|on|at|by|from|that|this|these|those|with|without|has|have|had|will|would|can|could|should|must|may|not|no|"
          r"name|id|account|logged|login|log|reset|policy|manager|required|expired|expires|expiry|valid|invalid|incorrect|correct|changed|change|set|used|using|was|been|being|here|there|"
          r"your|my|our|their|his|her|its|new|old|current|please|when|where|which|who|what|how|why|if|then|than|as|so|but|also|only|just|none|null|nil|n/a|na|unknown)\b)")


class LabeledValueRecognizer(LocalRecognizer):
    """Finds VALUE when it follows one of LABELS, e.g. "password: hunter2!", "CVV 737", "passport number is 912803456".

    Between the label and the value it tolerates a qualifier (number, no., #, id, code), JSON-style quotes and
    separators ('": "', ':', '='), and "is". Only the value is reported. FILLER words are rejected so that
    "password reset" or "user is logged in" do not match.
    """
    SEPARATOR = (r"""(?:[\s_\-]*(?:number|no\.?|num\.?|#|id|code|hash))?\s*["'`]?\s*[:=]?\s*["'`]?\s*(?:(?:is|was|are|=)\s+)?(?:actually\s+)?["'`]?""")

    def __init__(self, entity, labels, value, score, name=None, validate=None, context=None, guard_filler=False):
        self.entity = entity
        self.score = score
        self.validate = validate
        ordered = sorted(labels, key=len, reverse=True)
        label = "|".join(re.escape(item).replace(r"\ ", r"[\s_\-]+") for item in ordered)
        # Concatenated/camelCase labels are keys only when followed by an
        # assignment. Preserve the required word boundaries in ordinary prose.
        joined = [re.escape(item.replace(" ", "")) for item in ordered if " " in item]
        if joined:
            label += "|(?:" + "|".join(joined) + r""")(?=[\s"']*[:=])"""
        guard = FILLER if guard_filler else ""
        self.regex = re.compile(rf"(?<![A-Za-z0-9])(?:{label})(?![A-Za-z]){self.SEPARATOR}{guard}(?P<value>{value})", re.IGNORECASE)
        super().__init__(supported_entities=[entity], name=name or f"Labeled{entity.title().replace('_', '')}Recognizer",
                         supported_language="en", context=context)

    def load(self):
        pass

    def analyze(self, text, entities, nlp_artifacts=None):
        if self.entity not in entities:
            return []
        results = []
        for match in self.regex.finditer(text):
            value = match.group("value")
            if self.entity in {"API_KEY", "SESSION_ID"} and len(value) < 16 and not re.search(r"[:=]", text[match.start():match.start("value")]):
                continue
            if self.validate and not self.validate(value):
                continue
            results.append(RecognizerResult(
                entity_type=self.entity, start=match.start("value"), end=match.end("value"), score=self.score,
                analysis_explanation=AnalysisExplanation(recognizer=self.name, original_score=self.score, textual_explanation="value after a label")))
        return results


class CasePatternRecognizer(PatternRecognizer):
    """PatternRecognizer whose regexes are case-sensitive: Presidio's default adds IGNORECASE, which would
    make "must start with a capital letter" rules (street names, key prefixes) meaningless. Use (?i:...)
    inside a pattern where case should not matter."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("global_regex_flags", re.DOTALL | re.MULTILINE)
        super().__init__(*args, **kwargs)


class ValidatedPatternRecognizer(CasePatternRecognizer):
    """PatternRecognizer that drops matches failing a check (checksum or format)."""

    def __init__(self, *args, check, **kwargs):
        super().__init__(*args, **kwargs)
        self.check = check

    def validate_result(self, pattern_text):
        return None if self.check(pattern_text) else False


def luhn_ok(value):
    digits = [int(c) for c in re.sub(r"\D", "", value)]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return bool(digits) and total % 10 == 0


def vin_ok(value):
    """ISO 3779 check digit (position 9); North American VINs satisfy it."""
    if len(value) != 17 or any(c in "IOQ" for c in value.upper()):
        return False
    values = {**{str(i): i for i in range(10)}, **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))), "P": 7, "R": 9,
              **dict(zip("STUVWXYZ", range(2, 10)))}
    weights = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(values[c] * w for c, w in zip(value.upper(), weights))
    check = "X" if total % 11 == 10 else str(total % 11)
    return value[8].upper() == check



def international_phone_ok(value):
    import phonenumbers
    try:
        return phonenumbers.is_valid_number(phonenumbers.parse(value, None))
    except phonenumbers.NumberParseException:
        return False


def coordinates_ok(value):
    latitude, longitude = map(float, value.split(","))
    return abs(latitude) <= 90 and abs(longitude) <= 180


class CredentialRecognizer(LocalRecognizer):
    """Quoted values keep their source escapes; prose passphrases require a quote or field separator."""
    def __init__(self):
        super().__init__(supported_entities=["PASSWORD", "USERNAME"], name="CredentialRecognizer", supported_language="en")
        self.password = re.compile(r"(?<![A-Za-z0-9])(?:password|passwd|pwd|passcode|passphrase|pass[ _-]?phrase)\b[\"']?\s*(?:[:=]\s*|(?:is|was)\s+)?(?:actually\s+)?(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s\"',;]+)", re.I)
        self.login = re.compile(r"\blogin\s*[:=]\s*(?P<user>[\w.@-]+)\s*/\s*(?P<value>[^\s,;]+)", re.I)
        self.user = re.compile(r"\buser\s*=\s*(?P<value>[\w.@-]+)", re.I)

    def load(self):
        pass

    def analyze(self, text, entities, nlp_artifacts=None):
        out = []
        for regex, entity in ((self.password, "PASSWORD"), (self.login, "PASSWORD"), (self.user, "USERNAME")):
            if entity not in entities:
                continue
            for m in regex.finditer(text):
                value = m.group("value")
                prefix = text[m.start():m.start("value")]
                explicit = bool(re.search(r"[:=]", prefix)) or value[:1] in ('"', "'")
                candidate = value[1:-1] if value[:1] in ('"', "'") else value
                if value.startswith('"'):
                    import json
                    try:
                        candidate = json.loads(value)
                    except ValueError:
                        pass
                if candidate.lower() in {"null", "unknown", "n/a", "none", "unavailable", "nil"}:
                    continue
                if not explicit and re.match(FILLER, value, re.I) is None:
                    continue
                if entity == "PASSWORD" and not explicit and (len(value) < 4 or not re.search(r"[A-Za-z0-9]", value) or (not re.search(r"\b(?:is|was)\s+(?:actually\s+)?$", prefix, re.I) and not re.search(r"[\d_!@#$%^&*+?/-]", value))):
                    continue
                a, b = m.span("value")
                if value[:1] in ('"', "'"):
                    a += 1; b -= 1
                if b > a:
                    out.append(RecognizerResult(entity, a, b, .9))
        return out


class StructuredFieldRecognizer(LocalRecognizer):
    """Lex JSON fields without re-encoding values, preserving offsets and escapes.

    Keys may be camelCase, snake_case, nested, or escaped. Only recognized fields
    receive label-based confidence; literals are never normalized.
    """
    FIELDS = {
        "userpassword": "PASSWORD", "password": "PASSWORD", "passwd": "PASSWORD", "pwd": "PASSWORD", "passphrase": "PASSWORD",
        "username": "USERNAME", "user": "USERNAME", "login": "USERNAME",
        "apikey": "API_KEY", "secret": "API_KEY", "token": "API_KEY", "accesstoken": "API_KEY",
        "session": "SESSION_ID", "sessionid": "SESSION_ID", "sid": "SESSION_ID",
        "customerid": "ACCOUNT_ID", "customernumber": "ACCOUNT_ID", "accountid": "ACCOUNT_ID",
        "accountnumber": "US_BANK_NUMBER", "bankaccountnumber": "US_BANK_NUMBER",
        "employeeid": "EMPLOYEE_ID", "studentid": "STUDENT_ID",
        "address": "ADDRESS", "streetnumber": "ADDRESS", "streetname": "ADDRESS", "apartmentnumber": "ADDRESS",
        "dateofbirth": "DATE_OF_BIRTH", "birthdate": "DATE_OF_BIRTH", "dob": "DATE_OF_BIRTH",
        "medicalrecordnumber": "MEDICAL_RECORD_NUMBER", "mrn": "MEDICAL_RECORD_NUMBER", "insurancepolicynumber": "INSURANCE_ID",
        "serialnumber": "SERIAL_NUMBER", "nationalidnumber": "NATIONAL_ID_NUMBER", "driverlicensenumber": "DRIVER_LICENSE_NUMBER",
        "passportnumber": "US_PASSPORT", "idcardnumber": "NATIONAL_ID_NUMBER",
        "nursinglicensenumber": "PROFESSIONAL_LICENSE", "deviceserialnumber": "SERIAL_NUMBER",
        "contactnumber": "PHONE_NUMBER", "age": "AGE",
        "phone": "PHONE_NUMBER", "phonenumber": "PHONE_NUMBER", "mobile": "PHONE_NUMBER", "cell": "PHONE_NUMBER", "tel": "PHONE_NUMBER", "fax": "PHONE_NUMBER",
    }
    # New aliases retain the shape constraints of the existing prose rules.
    ALIAS_SHAPES = {
        "passportnumber": r"(?:[A-Z]\d{8}|\d{9})",
        "idcardnumber": r"(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{5,19}",
        "nursinglicensenumber": r"(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{4,19}",
        "deviceserialnumber": r"(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{5,24}",
    }

    @classmethod
    def valid_alias(cls, key, value):
        pattern = cls.ALIAS_SHAPES.get(key)
        return pattern is None or bool(re.fullmatch(pattern, str(value), re.I))

    FIELD = re.compile(r'(?P<key>"(?:\\.|[^"\\])*")\s*:\s*(?P<value>"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?)(?=\s*[,}\]])')

    def __init__(self):
        super().__init__(supported_entities=sorted(set(self.FIELDS.values())), name="StructuredFieldRecognizer", supported_language="en")

    def load(self):
        pass

    def analyze(self, text, entities, nlp_artifacts=None):
        import json
        out = []
        for m in self.FIELD.finditer(text):
            try:
                key = re.sub(r"[^a-z0-9]", "", json.loads(m.group("key")).lower())
                value = json.loads(m.group("value"))
            except (ValueError, TypeError):
                continue
            entity = self.FIELDS.get(key)
            if not self.valid_alias(key, value):
                continue
            if entity not in entities:
                continue
            raw = m.group("value")
            if value is None or str(value).lower() in {"", "null", "unknown", "n/a", "none", "unavailable", "nil"}:
                continue
            if entity == "AGE" and not (str(value).isdigit() and 0 <= int(value) < 120):
                continue
            if entity == "PHONE_NUMBER" and not (7 <= len(re.sub(r"\D", "", str(value))) <= 15 and re.fullmatch(r"\+?[\d ().-]+", str(value))):
                continue
            a, b = m.span("value")
            if raw.startswith('"'):
                a += 1; b -= 1
            out.append(RecognizerResult(entity, a, b, .9))
        return out

# ---------------------------------------------------------------------------- the recognizers
def build_recognizers():
    recs = []

    # ADDRESS ------------------------------------------------------------------------------------
    address_context = ["address", "lives", "living", "resides", "residence", "located", "location", "mailing", "billing", "shipping", "ship", "deliver", "street", "home", "office", "moved"]
    recs.append(CasePatternRecognizer(supported_entity="ADDRESS", name="UsStreetAddressRecognizer", supported_language="en", context=address_context, patterns=[
        _pattern("street + city + state + zip", rf"(?i:{STREET},?\s+{CITY},?\s+(?:{US_STATE_CODES}|{US_STATE_NAMES})\b,?(?:\s+{ZIP})?)", 0.9),
        _pattern("street + city + zip", rf"{STREET},\s+{CITY},?\s+{ZIP}\b", 0.85),
        _pattern("street + state + zip", rf"{STREET},?\s+(?:{US_STATE_CODES})\s+{ZIP}\b", 0.9),
        _pattern("street, city (comma)", rf"{STREET},\s+{CITY}\b", 0.6),
        _pattern("street only (needs a context word to pass 0.5)", STREET, 0.45),
        _pattern("city, state zip", rf"\b{CITY},\s+(?:{US_STATE_CODES})\s+{ZIP}\b", 0.75),
        _pattern("po box", r"\b(?i:P\.?\s?O\.?\s?Box)\s+\d{1,6}\b(?:,?\s+" + CITY + rf",?\s+(?:{US_STATE_CODES})\s+{ZIP})?", 0.8),
    ]))
    recs.append(CasePatternRecognizer(supported_entity="ADDRESS", name="InternationalAddressRecognizer", supported_language="en", context=address_context, patterns=[
        _pattern("UK street + city + postcode", rf"{STREET},\s*{CITY},?\s+{UK_POSTCODE}\b", 0.9),
        _pattern("Canada street + city + province + postcode", rf"{STREET},?\s+{CITY},?\s+(?:{CA_PROVINCES})\s+{CA_POSTCODE}\b", 0.9),
        _pattern("number-first foreign street", rf"\b\d{{1,6}}[A-Za-z]?\s+(?:{FOREIGN_PREFIX})\s+{FOREIGN_NAME}", 0.6),
        _pattern("number-first German street", rf"\b\d{{1,4}}[a-z]?\s+{GERMAN_STREET}\b", 0.6),
        _pattern("German street + number + postcode + city", rf"\b{GERMAN_STREET}\s+\d{{1,4}}[a-z]?,?\s+(?:\d{{5}}\s+{CITY})?", 0.7),
        _pattern("prefixed foreign street + number", rf"\b(?:{FOREIGN_PREFIX})\s+{FOREIGN_NAME},?\s+\d{{1,4}}\b", 0.6),
    ]))
    recs.append(LabeledValueRecognizer("US_ZIP_CODE", ["zip code", "zipcode", "zip", "postal code", "postcode"], ZIP, 0.85))

    # secrets and credentials -------------------------------------------------------------------
    recs.append(CasePatternRecognizer(supported_entity="API_KEY", name="KnownApiKeyFormatsRecognizer", supported_language="en", context=["key", "token", "secret", "api"], patterns=[
        _pattern("AWS access key id", r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[A-Z0-9]{16}\b", 0.95),
        _pattern("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b", 0.95),
        _pattern("GitHub fine-grained token", r"\bgithub_pat_[A-Za-z0-9_]{22,255}\b", 0.95),
        _pattern("Stripe key", r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b", 0.95),
        _pattern("Slack token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b", 0.95),
        _pattern("Google API key", r"\bAIza[0-9A-Za-z_\-]{35}\b", 0.95),
        _pattern("prefixed api_key_ value", r"\bapi[_-]?key[_-][A-Za-z0-9]{16,}\b", 0.9),
    ]))
    recs.append(CasePatternRecognizer(supported_entity="AUTH_TOKEN", name="JwtRecognizer", supported_language="en", context=["token", "bearer", "authorization", "jwt"], patterns=[
        _pattern("JWT", r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b", 0.95)]))
    recs.append(CasePatternRecognizer(supported_entity="PRIVATE_KEY", name="PrivateKeyRecognizer", supported_language="en", patterns=[
        _pattern("PEM private key block", r"(?i:-----BEGIN (?P<kind>(?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY)-----)(?:[^\x00]*?(?i:-----END (?P=kind)-----)|(?=\s*$))", 0.99),
        _pattern("truncated PEM body", r"(?i:-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----)(?:[ \t]*\r?\n[A-Za-z0-9+/=]+)+", 0.99),
        _pattern("PEM private key header", r"(?i:-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----)", 0.98)]))
    recs.append(LabeledValueRecognizer("API_KEY", ["api key", "apikey", "api_key", "secret key", "secret", "access key", "access token", "auth token", "token", "bearer"],
                                       r"[A-Za-z0-9_\-./+=]+(?![A-Za-z0-9_\-./+=])", 0.8, name="LabeledApiKeyRecognizer", guard_filler=True))
    recs.append(CredentialRecognizer())
    recs.append(LabeledValueRecognizer("USERNAME", ["username", "user name", "login id", "login", "user id", "userid", "account name", "screen name", "handle"],
                                       r"\w[\w._@\-]{0,255}(?![\w.@-])", 0.85, name="LabeledUsernameRecognizer", guard_filler=True))
    recs.append(LabeledValueRecognizer("USERNAME", ["user"], r"(?=[\w._@\-]*[\d._])\w[\w._@\-]{2,39}", 0.7,
                                       name="BareUserLabelRecognizer", guard_filler=True))
    recs.append(CasePatternRecognizer(supported_entity="SOCIAL_HANDLE", name="SocialHandleRecognizer", supported_language="en", context=["twitter", "instagram", "handle", "follow", "social"],
                                  patterns=[_pattern("@handle", r"(?<![\w@.])@\w[\w.]{2,29}(?<!\.)", 0.5)]))

    # card extras ---------------------------------------------------------------------------------
    recs.append(LabeledValueRecognizer("CARD_CVV", ["cvv2", "cvv", "cvc2", "cvc", "cid", "security code", "card verification value", "card verification code"], r"\d{3,4}(?!\d)", 0.88))
    recs.append(LabeledValueRecognizer("CARD_EXPIRY", ["expiry date", "expiry", "expiration date", "expiration", "expires", "exp date", "exp", "valid thru", "valid until", "valid through"],
                                       r"(?:0[1-9]|1[0-2])\s*/\s*(?:\d{4}|\d{2})(?!\d)", 0.88))

    # US identifiers whose own Presidio patterns are too weak to pass 0.5 -------------------------
    recs.append(LabeledValueRecognizer("US_PASSPORT", ["passport"], r"(?:[A-Z]\d{8}|\d{9})(?![\dA-Za-z])", 0.85, name="LabeledUsPassportRecognizer"))
    recs.append(LabeledValueRecognizer("US_BANK_NUMBER", ["bank account", "account number", "acct", "checking account", "savings account", "account no", "account"],
                                       r"\d(?:[ -]?\d){5,16}(?![ -]?\d)", 0.8, name="LabeledUsBankNumberRecognizer"))
    recs.append(LabeledValueRecognizer("US_EIN", ["ein", "employer identification", "federal tax id", "federal tax identification", "tax id", "fein"], r"\d{2}-\d{7}(?!\d)", 0.9))
    recs.append(CasePatternRecognizer(supported_entity="US_EIN", name="EinShapeRecognizer", supported_language="en", context=["ein", "employer", "tax", "irs", "federal"],
                                  patterns=[_pattern("EIN shape", r"(?<![\d-])\d{2}-\d{7}(?![\d-])", 0.3)]))
    recs.append(CasePatternRecognizer(supported_entity="PHONE_NUMBER", name="UsPhoneFormatRecognizer", supported_language="en", context=["phone", "call", "tel", "mobile", "cell", "fax", "contact", "reach"],
                                      patterns=[_pattern("US phone, separated 3-3-4", r"(?<![\d\w])(?:\+?1[\s.\-]?)?\(?[2-9]\d{2}\)?[\s.\-][2-9]\d{2}[\s.\-]\d{4}(?!\d)", 0.6),
                                                _pattern("US phone, bare ten digits", r"(?<![\d\w])(?:\+?1)?[2-9]\d{2}[2-9]\d{2}\d{4}(?!\d)", 0.15)]))

    recs.append(LabeledValueRecognizer("ADDRESS", ["address", "lives at", "ship to", "street"], rf"(?i:{STREET}|[A-Za-z0-9]+,\s+(?:{NAME_WORD}\s+){{1,4}}(?:{STREET_SUFFIX})\b)", 0.85))

    recs.append(ValidatedPatternRecognizer(supported_entity="PHONE_NUMBER", name="InternationalPhoneFormatRecognizer", supported_language="en", check=international_phone_ok,
        patterns=[_pattern("validated +country-code phone", r"(?<![\w+])\+[1-9]\d{0,2}[ ().-]*\d(?:[ ().-]*\d){5,13}(?!\d)", 0.7)]))

    # personal attributes ----------------------------------------------------------------------------
    month = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    date = (rf"(?:\d{{1,2}}[/.\-]\d{{1,2}}[/.\-]\d{{2,4}}|\d{{4}}[/.\-]\d{{1,2}}[/.\-]\d{{1,2}}|\d{{1,2}}(?:st|nd|rd|th)?\s+{month}\.?,?\s+\d{{4}}|{month}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?)")
    recs.append(LabeledValueRecognizer("DATE_OF_BIRTH", ["date of birth", "birth date", "birthdate", "birthday", "d.o.b.", "dob", "born on", "born"], date, 0.9))
    recs.append(LabeledValueRecognizer("AGE", ["age", "aged"], r"\d{1,3}(?!\d|\s*%)", 0.6, name="LabeledAgeRecognizer",
                                       validate=lambda v: 0 <= int(v) < 120))
    recs.append(CasePatternRecognizer(supported_entity="AGE", name="YearsOldRecognizer", supported_language="en",
                                  patterns=[_pattern("N years old", r"\b\d{1,3}(?=[- ]years?[- ]old\b)", 0.8)]))
    recs.append(LabeledValueRecognizer("SALARY", ["salary", "annual salary", "income", "annual income", "earns", "compensation", "wage"],
                                       r"[$€£₹]?\s?\d+(?:,\d{2,3})*(?:\.\d{2})?(?:\s?(?:USD|EUR|GBP|INR|dollars))?(?![\d,])", 0.7))
    recs.append(LabeledValueRecognizer("GENDER", ["gender", "sex"], r"(?:female|male|non[- ]?binary|man|woman|transgender|other)\b", 0.7))
    recs.append(LabeledValueRecognizer("ETHNICITY", ["ethnicity", "ethnic group", "race", "ethnic origin"],
                                       r"(?:Hispanic|Latino|Latina|Latinx|Asian|Black|African[- ]American|White|Caucasian|Native American|Pacific Islander|Middle Eastern|South Asian|East Asian)\b", 0.75))
    recs.append(LabeledValueRecognizer("EMPLOYEE_ID", ["employee id", "employee number", "employee no", "emp id", "staff id", "badge number", "badge id"], r"(?=[A-Z0-9_.-]*\d)[A-Z0-9][A-Z0-9_.-]{2,39}(?![A-Za-z0-9_.-])", 0.8, guard_filler=True))
    recs.append(LabeledValueRecognizer("STUDENT_ID", ["student id", "student number", "student no"], r"(?=[A-Z0-9_.-]*\d)[A-Z0-9][A-Z0-9_.-]{2,39}(?![A-Za-z0-9_.-])", 0.8, guard_filler=True))

    # device, vehicle and location identifiers ------------------------------------------------------------
    recs.append(ValidatedPatternRecognizer(supported_entity="VIN", name="VinRecognizer", supported_language="en", context=["vin", "vehicle", "chassis", "car"], check=vin_ok,
                                           patterns=[_pattern("VIN", r"\b[A-HJ-NPR-Z0-9]{17}\b", 0.8)]))
    recs.append(LabeledValueRecognizer("VIN", ["vin", "vehicle identification number", "chassis number"], r"[A-HJ-NPR-Z0-9]{17}(?![A-Za-z0-9])", 0.85, name="LabeledVinRecognizer"))
    recs.append(ValidatedPatternRecognizer(supported_entity="IMEI", name="ImeiRecognizer", supported_language="en", context=["imei", "device", "phone", "handset"], check=luhn_ok,
                                           patterns=[_pattern("IMEI", r"(?<!\d)\d{15}(?!\d)", 0.4)]))
    recs.append(LabeledValueRecognizer("IMEI", ["imei", "meid"], r"\d{15}(?!\d)", 0.88, name="LabeledImeiRecognizer"))
    recs.append(ValidatedPatternRecognizer(check=coordinates_ok, supported_entity="GPS_COORDINATES", name="GpsRecognizer", supported_language="en", context=["coordinates", "gps", "lat", "lon", "latitude", "longitude", "location", "geo"],
                                  patterns=[_pattern("decimal lat, long", r"(?<![\d.])[-+]?(?:[1-8]?\d|90)\.\d{3,}\s*,\s*[-+]?(?:1[0-7]\d|[1-9]?\d)\.\d{3,}(?!\.?\d)", 0.7)]))
    recs.append(CasePatternRecognizer(supported_entity="UUID", name="UuidRecognizer", supported_language="en", context=["uuid", "guid", "device", "id", "session"],
                                  patterns=[_pattern("UUID", r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b", 0.7)]))
    recs.append(LabeledValueRecognizer("SWIFT_BIC", ["swift bic", "swift code", "swift/bic", "bic/swift", "swift", "bic"], r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b", 0.85, name="LabeledSwiftRecognizer"))

    # ---- identifiers found only by their label (HIPAA / GDPR / online-identifier gaps found by gap_audit.py) ----------
    ident = r"(?=[A-Z0-9\-]*\d)[A-Z0-9][A-Z0-9\-]{%d,%d}(?![A-Za-z0-9])"          # alphanumeric with at least one digit
    recs.append(LabeledValueRecognizer("MEDICAL_RECORD_NUMBER", ["medical record number", "medical record no", "medical record", "health record number", "mrn", "patient id", "patient number", "chart number"], ident % (4, 14), 0.85))
    recs.append(LabeledValueRecognizer("INSURANCE_ID", ["insurance policy number", "insurance policy", "insurance number", "insurance id", "policy number", "policy no", "policy id", "health plan id", "health plan number", "beneficiary id", "subscriber id", "insured id"], ident % (5, 24), 0.8))
    recs.append(LabeledValueRecognizer("ACCOUNT_ID", ["customer id", "customer number", "customer no", "client id", "client number", "account id", "membership number", "membership id", "member id", "member number", "loyalty number", "loyalty id"], ident % (4, 24), 0.75))
    recs.append(LabeledValueRecognizer("LICENSE_PLATE", ["license plate", "licence plate", "number plate", "registration plate", "plate number", "plate no", "plate"],
                                       r"(?-i:(?=[A-Z0-9\- ]*\d)(?=[A-Z0-9\- ]*[A-Z])[A-Z0-9]{2,4}[\- ]?[A-Z0-9]{2,5})(?![A-Za-z0-9])", 0.8))
    recs.append(LabeledValueRecognizer("SERIAL_NUMBER", ["serial number", "serial no", "serial #", "serial", "s/n"], ident % (5, 24), 0.75))
    recs.append(LabeledValueRecognizer("BIOMETRIC_ID", ["fingerprint hash", "fingerprint template", "fingerprint id", "fingerprint", "face template id", "face template", "faceprint", "face id", "voiceprint", "voice print", "iris scan", "retina scan", "biometric id", "biometric template", "biometric hash"],
                                       r"[A-Za-z0-9_\-]{16,64}(?![A-Za-z0-9])", 0.8))
    recs.append(LabeledValueRecognizer("SESSION_ID", ["session id", "session token", "session key", "session cookie", "cookie id", "jsessionid", "phpsessid", "sid", "session"], r"[A-Za-z0-9_\-.%]+(?![A-Za-z0-9_\-.%])", 0.75, guard_filler=True))
    recs.append(LabeledValueRecognizer("PASSPORT_NUMBER", ["passport"], r"(?=[A-Z0-9]*\d)[A-Z0-9]{6,9}(?![A-Za-z0-9])", 0.85))
    recs.append(LabeledValueRecognizer("NATIONAL_ID_NUMBER", ["national identification", "national identity", "national id", "identity card", "id card", "citizen id", "citizen number"], ident % (5, 19), 0.8))
    recs.append(LabeledValueRecognizer("DRIVER_LICENSE_NUMBER", ["driver\u2019s license", "driver's license", "drivers license", "driver license", "driving licence", "driving license", "dl number", "dl no"], ident % (5, 19), 0.8))
    recs.append(LabeledValueRecognizer("PROFESSIONAL_LICENSE", ["professional license", "professional licence", "nursing license", "nursing licence", "medical license", "medical licence", "bar number", "certification number", "certificate number"], ident % (4, 19), 0.8))
    recs.append(LabeledValueRecognizer("TAX_ID_NUMBER", ["taxpayer identification", "taxpayer id", "tax identification", "tax id", "vat number", "vat id", "vat no", "gst number", "gstin", "tin"], r"(?=[A-Z0-9\-.]*\d)[A-Z0-9][A-Z0-9\-.]{6,19}(?![A-Za-z0-9])", 0.8))
    recs.append(LabeledValueRecognizer("US_ALIEN_NUMBER", ["alien registration number", "alien number", "a-number", "a number", "uscis number", "green card number"], r"A?[-\s]?\d{8,9}(?!\d)", 0.85))
    recs.append(CasePatternRecognizer(supported_entity="US_ALIEN_NUMBER", name="AlienNumberShapeRecognizer", supported_language="en", context=["alien", "uscis", "immigration", "green card", "a-number"],
                                      patterns=[_pattern("A-number", r"\bA-?\d{9}\b", 0.4)]))
    recs.append(CasePatternRecognizer(supported_entity="CRYPTO", name="EthereumAddressRecognizer", supported_language="en", context=["ethereum", "eth", "wallet", "address", "crypto"],
                                      patterns=[_pattern("Ethereum address", r"\b0x[a-fA-F0-9]{40}\b", 0.9)]))

    # ---- sensitive attributes and dates -------------------------------------------------------------------------------------
    recs.append(LabeledValueRecognizer("CREDIT_SCORE", ["credit score", "fico score", "fico", "credit rating"], r"[3-8]\d{2}(?!\d)", 0.75))
    recs.append(LabeledValueRecognizer("MARITAL_STATUS", ["marital status", "civil status", "relationship status"], r"(?:single|married|divorced|widowed|widower|widow|separated|domestic partnership|civil partnership|engaged|cohabiting)\b", 0.7))
    recs.append(LabeledValueRecognizer("SEXUAL_ORIENTATION", ["sexual orientation", "orientation"], r"(?:heterosexual|homosexual|straight|gay|lesbian|bisexual|asexual|pansexual|queer)\b", 0.8))
    recs.append(LabeledValueRecognizer("RELIGION", ["religious affiliation", "religious belief", "religion", "faith"],
                                       r"(?:Christian|Catholic|Protestant|Orthodox|Mormon|Evangelical|Muslim|Islam|Sunni|Shia|Hindu|Buddhist|Buddhism|Jewish|Judaism|Sikh|Atheist|Agnostic|Jain|Baha'i|Taoist|Shinto|Pagan)\b", 0.8))
    recs.append(LabeledValueRecognizer("POLITICAL_AFFILIATION", ["political affiliation", "political party", "party affiliation", "political view", "political opinion"],
                                       r"(?:Democrat(?:ic)?|Republican|Libertarian|Green(?: Party)?|Conservative|Liberal(?: Democrat)?|Labou?r|Socialist|Communist|Independent|Progressive|Tory|Nationalist)\b", 0.8))
    recs.append(LabeledValueRecognizer("DATE_OF_DEATH", ["date of death", "death date", "deceased on", "passed away on", "died on", "died"], date, 0.85))
    recs.append(LabeledValueRecognizer("ADMISSION_DATE", ["date of admission", "admission date", "admitted on", "admitted"], date, 0.85))
    recs.append(LabeledValueRecognizer("DISCHARGE_DATE", ["date of discharge", "discharge date", "discharged on", "discharged"], date, 0.85))
    recs.append(StructuredFieldRecognizer())
    recs.append(LabeledValueRecognizer("PHONE_NUMBER", ["phone number", "phone", "mobile", "cell", "tel", "fax"], r"(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]\d{3}[ .-]?\d{4}(?!\d)|\+?\d[\d(). -]{5,}\d(?!\d)", 0.8, validate=lambda v: 7 <= len(re.sub(r"\D", "", v)) <= 15))
    recs.append(LabeledValueRecognizer("GPS_COORDINATES", ["coordinates", "gps"], r"[-+]?\d{1,3}(?:\.\d+)?\s*,\s*[-+]?\d{1,3}(?:\.\d+)?(?![\d.])", 0.85, validate=coordinates_ok))
    return recs


CUSTOM_ENTITIES = sorted({e for r in build_recognizers() for e in r.supported_entities})


def add_custom_recognizers(analyzer):
    """Register every custom recognizer for English; returns how many were added."""
    recognizers = build_recognizers()
    for recognizer in recognizers:
        analyzer.registry.add_recognizer(recognizer)
    # detect(..., collapse=True) ranks these above Presidio's generic rules when results overlap
    analyzer.custom_recognizer_names = {recognizer.name for recognizer in recognizers}
    return len(recognizers)
