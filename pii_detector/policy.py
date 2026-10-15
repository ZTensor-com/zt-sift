"""Rules shared by the plain-text and JSON paths: which candidates are accepted, and how entity names relate.

Kept apart from the detector so the rules can be read, tested and changed without loading a model.
"""
import re

DEFAULT_THRESHOLD = 0.5

# --------------------------------------------------------------------------------------- weak country patterns
# These Presidio recognizers match only the *shape* of a country-specific identifier (a 5-digit German postcode,
# a Spanish passport number, ...). Their own score starts at 0.01-0.1, so by itself a match is meaningless. A
# nearby context word ("plz", "pasaporte", "postcode") lifts it to 0.4-0.45, which is below the default 0.5
# threshold, so the value used to be dropped even when its label sat right next to it.
#
# A match is accepted below the threshold only when ALL of these hold: the entity is listed here, a context word
# was actually found next to it, and the score reached WEAK_FLOOR (the minimum Presidio gives after a context boost).
# The list is deliberately explicit: a global lower threshold also admits shapes such as ticket numbers that happen
# to resemble a voter ID.
WEAK_FLOOR = 0.4
WEAK_CONTEXT_ENTITIES = frozenset({"DE_PLZ", "ES_PASSPORT", "IT_IDENTITY_CARD", "IT_PASSPORT", "PH_TIN", "UK_POSTCODE"})
# Not listed on purpose: IN_PASSPORT, UK_PASSPORT and KR_PASSPORT. Their shapes (one or two letters plus 7-8 digits) cannot
# tell the issuing country apart from each other or from a US passport, so next to the word "passport" the honest answer
# is the generic PASSPORT_NUMBER, which the label-based recognizer already reports.


def candidate_floor(threshold):
    """Lowest score worth collecting from the analyzer; accepts() makes the final decision."""
    return min(threshold, WEAK_FLOOR)


def accepts(entity, score, has_context, threshold):
    """True when a candidate clears the caller's threshold, or is a context-supported weak country pattern.

    A caller who raises the threshold above the default asks for stricter output, so the weak-pattern allowance
    only applies at the default threshold or below.
    """
    if score >= threshold:
        return True
    return (entity in WEAK_CONTEXT_ENTITIES and has_context and score >= WEAK_FLOOR
            and threshold <= DEFAULT_THRESHOLD)


# --------------------------------------------------------------------------------------------- registered aliases
# Presidio's SpacyRecognizer advertises these names, but neither English spaCy model has such a label, so they can
# never be produced. They are accepted in the `entities` filter and mapped to the entity that is actually emitted.
ENTITY_ALIASES = {"EMAIL": "EMAIL_ADDRESS", "ID": "NATIONAL_ID_NUMBER"}


def resolve_entities(entities):
    """Map alias names to real entities, keeping order and dropping duplicates. None stays None (all entities)."""
    if entities is None:
        return None
    return list(dict.fromkeys(ENTITY_ALIASES.get(name, name) for name in entities))


# ---------------------------------------------------------------------------------- generic vs country-specific
# A label such as "passport" or "tax id" proves what kind of identifier follows but not which country issued it.
# The label-based recognizers therefore report a generic type (PASSPORT_NUMBER, TAX_ID_NUMBER, ...). When a
# validated country-specific recognizer fires on exactly the same value and belongs to the family the label
# selected, the specific type is more informative and replaces the generic one. Only validated results (checksum or
# distinctive format, score >= REFINE_MIN_SCORE) qualify: a weak shape match is a guess, and the generic type is the
# honest answer then.
REFINE_MIN_SCORE = 0.8
FAMILIES = {
    "PASSPORT_NUMBER": frozenset({"US_PASSPORT", "DE_PASSPORT", "ES_PASSPORT", "IN_PASSPORT", "IT_PASSPORT", "KR_PASSPORT", "UK_PASSPORT"}),
    "NATIONAL_ID_NUMBER": frozenset({
        "DE_ID_CARD", "ES_NIE", "ES_NIF", "FI_PERSONAL_IDENTITY_CODE", "IN_AADHAAR", "IN_VOTER", "IT_IDENTITY_CARD", "KR_FRN",
        "KR_RRN", "NG_NIN", "PH_UMID", "PL_PESEL", "SE_PERSONNUMMER", "SG_NRIC_FIN", "TH_TNIN", "TR_NATIONAL_ID", "UK_NINO",
        "ZA_ID_NUMBER"}),
    "TAX_ID_NUMBER": frozenset({
        "AU_ABN", "AU_ACN", "AU_TFN", "DE_TAX_ID", "DE_TAX_NUMBER", "DE_VAT_ID", "IN_GSTIN", "IN_PAN", "IT_FISCAL_CODE",
        "IT_VAT_CODE", "KR_BRN", "PH_TIN", "SE_ORGANISATIONSNUMMER", "SG_UEN", "US_EIN", "US_ITIN"}),
    "LICENSE_PLATE": frozenset({"DE_KFZ", "IN_VEHICLE_REGISTRATION", "NG_VEHICLE_REGISTRATION", "TR_LICENSE_PLATE", "UK_VEHICLE_REGISTRATION"}),
    "DRIVER_LICENSE_NUMBER": frozenset({"DE_FUEHRERSCHEIN", "IT_DRIVER_LICENSE", "KR_DRIVER_LICENSE", "UK_DRIVING_LICENCE", "US_DRIVER_LICENSE"}),
    "PROFESSIONAL_LICENSE": frozenset({"MEDICAL_LICENSE"}),
    "API_KEY": frozenset({"AUTH_TOKEN"}),
}


# ------------------------------------------------------------------------------------------------- placeholders
# A masked or templated value stands in for a secret; it is not one. Reporting "********" as a password or
# "${DB_PASSWORD}" as an API key only produces noise for the consumer.
_PLACEHOLDER = re.compile(r"""\A(?:[*\u2022\u25cf#xX_.\-]{4,}|\[?\s*redacted\s*\]?|<[^<>\s][^<>]*>|\$\{[^{}]*\}|\{\{[^{}]*\}\}|%[A-Za-z0-9_]+%)\Z""", re.IGNORECASE)


def is_placeholder(value):
    """True for a mask (****, xxxx, ####), [REDACTED], <name>, ${VAR}, {{ var }} or %VAR%."""
    return bool(_PLACEHOLDER.match(value.strip()))
