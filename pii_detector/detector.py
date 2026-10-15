#!/usr/bin/env python3
"""Presidio + spaCy (en_core_web_sm by default, opt-in en_core_web_lg; no GLiNER).

By default every pattern recognizer in the installed Presidio is switched on (72 entity types plus a few
extras): Presidio's default English registry covers only 23 of them, and the country-specific ones
(UK, Spain, Italy, Germany, India, Korea and so on) are disabled or registered for other languages. Pass
--english-registry to get Presidio's stock behaviour instead. Not included: the 8 MEDICAL_* entities, which
need Presidio's transformers extra and a downloaded model. On top of that come the project's own recognizers from pii_detector/recognizers.py (ADDRESS, PASSWORD, USERNAME,
API_KEY, CARD_CVV, US_EIN and about 20 more; pass --no-custom to leave them out). Two small changes keep it offline and broad:
email validation uses tldextract's bundled suffix list, and phone detection uses configured regions
(US by default; international +country-code numbers remain supported). Context words of non-English recognizers stay in their own language, so those
entities can score lower in English text.

    python -m pii_detector "Call Sarah on (415) 555-0132"       # text as an argument
    python -m pii_detector --file samples/sample_us.txt         # a file
    echo "..." | python -m pii_detector --json                  # stdin, JSON output
    python -m pii_detector --list-entities                      # everything Presidio can detect
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter

from . import policy

SPACY_MODEL = "en_core_web_sm"
SPACY_MODELS = (SPACY_MODEL, "en_core_web_lg")


def configured_spacy_model():
    """Select a bundled model explicitly; never accept a path or download URL."""
    model = os.environ.get("PII_SPACY_MODEL", SPACY_MODEL)
    if model not in SPACY_MODELS:
        raise ValueError("PII_SPACY_MODEL must be en_core_web_sm or en_core_web_lg")
    return model


def create_nlp_engine(model):
    from presidio_analyzer.nlp_engine import SpacyNlpEngine

    class CompactSpacyNlpEngine(SpacyNlpEngine):
        def load(self):
            import spacy
            self._enable_gpu()
            # Exclude at load time: disable would retain the unused weights in RAM.
            # NER, tagger and lemmatizer remain for recognition/context enhancement.
            self.nlp = {"en": spacy.load(model, exclude=["parser", "senter"])}

    engine = CompactSpacyNlpEngine(models=[{"lang_code": "en", "model_name": model}])
    engine.load()
    return engine


# Recognizers that need extra packages, a model download or an external service; they are not pattern rules.
SKIP_CLASSES = ("Azure", "Stanza", "Transformers", "GLiNER", "HuggingFace", "LangExtract", "MedicalNER", "Spacy")


def load_analyzer(everything=True, custom=True, phone_regions=None):
    model = configured_spacy_model()
    from presidio_analyzer import AnalyzerEngine
    analyzer = AnalyzerEngine(nlp_engine=create_nlp_engine(model), supported_languages=["en"])
    use_bundled_suffix_list(analyzer)
    use_issuer_aware_cards(analyzer)
    configure_phone_regions(analyzer, phone_regions)
    if everything:
        enable_all_pattern_recognizers(analyzer)
    if custom:
        from .recognizers import add_custom_recognizers
        add_custom_recognizers(analyzer)
    analyzer.recognizer_kinds = recognizer_kinds(analyzer)
    return analyzer


def recognizer_kinds(analyzer):
    """Map each registered recognizer's name to how much its evidence is worth when results overlap.

    label: found because a label sits right before the value (the strongest evidence for what the value is)
    rule:  matched by a pattern, often with a checksum (built-in and project shape rules)
    nlp:   spaCy's entity tagger (a flat 0.85 for everything it tags, so it ranks last)
    """
    from .recognizers import CredentialRecognizer, LabeledValueRecognizer, StructuredFieldRecognizer
    labelled = (LabeledValueRecognizer, CredentialRecognizer, StructuredFieldRecognizer)
    return {r.name: "nlp" if r.name == "SpacyRecognizer" else "label" if isinstance(r, labelled) else "rule"
            for r in analyzer.registry.recognizers}


def use_issuer_aware_cards(analyzer):
    """Replace Presidio's card recognizer with one that also requires a known issuer range."""
    from presidio_analyzer.predefined_recognizers import CreditCardRecognizer
    from .recognizers import IssuerAwareCreditCardRecognizer
    for original in list(analyzer.registry.recognizers):
        if isinstance(original, CreditCardRecognizer):
            analyzer.registry.remove_recognizer(original.name, language=original.supported_language)
            analyzer.registry.add_recognizer(IssuerAwareCreditCardRecognizer(
                patterns=original.patterns, context=original.context, supported_language=original.supported_language,
                supported_entity=original.supported_entities[0], name=original.name))


def configure_phone_regions(analyzer, regions=None):
    """US national format by default; +country-code numbers still work worldwide."""
    import phonenumbers
    from presidio_analyzer.predefined_recognizers import PhoneRecognizer
    if regions is None:
        regions = os.environ.get("PII_PHONE_REGIONS", "US").split(",")
    regions = sorted({r.strip().upper() for r in regions if r.strip()})
    if not regions or set(regions) - phonenumbers.SUPPORTED_REGIONS:
        raise ValueError("PII_PHONE_REGIONS must contain valid comma-separated region codes")
    for original in list(analyzer.registry.recognizers):
        if isinstance(original, PhoneRecognizer):
            analyzer.registry.remove_recognizer(original.name, language=original.supported_language)
    analyzer.registry.add_recognizer(PhoneRecognizer(supported_regions=regions, supported_language="en", context=["phone", "call", "telephone", "mobile", "cell", "fax", "tel", "contact"]))


def enable_all_pattern_recognizers(analyzer):
    """Register every predefined pattern recognizer for English."""
    import inspect
    import presidio_analyzer.predefined_recognizers as predefined
    from presidio_analyzer import EntityRecognizer
    from presidio_analyzer.predefined_recognizers import PhoneRecognizer
    registry = analyzer.registry
    present = {entity for recognizer in registry.recognizers for entity in recognizer.supported_entities}
    for name, cls in sorted(inspect.getmembers(predefined, inspect.isclass)):
        if not issubclass(cls, EntityRecognizer) or not name.endswith("Recognizer") or any(k in name for k in SKIP_CLASSES):
            continue
        try:
            recognizer = cls(supported_language="en")
        except Exception:
            continue
        if recognizer.supported_entities[0] not in present:
            registry.add_recognizer(recognizer)
            present.update(recognizer.supported_entities)


def use_bundled_suffix_list(analyzer):
    """Presidio's email check downloads the public-suffix list; use the copy bundled with tldextract."""
    from presidio_analyzer.predefined_recognizers import EmailRecognizer
    from tldextract import TLDExtract
    extractor = TLDExtract(suffix_list_urls=(), cache_dir=None, fallback_to_snapshot=True)

    class OfflineEmailRecognizer(EmailRecognizer):
        def validate_result(self, pattern_text):
            return extractor(pattern_text).fqdn != ""

    for original in list(analyzer.registry.recognizers):
        if isinstance(original, EmailRecognizer):
            analyzer.registry.remove_recognizer(original.name, language=original.supported_language)
            analyzer.registry.add_recognizer(OfflineEmailRecognizer(
                patterns=original.patterns, context=original.context, supported_language=original.supported_language,
                supported_entity=original.supported_entities[0], name=original.name))


CHUNK_CHARS = 100_000   # spaCy refuses inputs over 1,000,000 characters; analyse big inputs in pieces


# Narrow PII field labels and crypto terms that otherwise become spurious NER entities.
NOT_ORGANIZATIONS = {"ethereum", "bitcoin", "litecoin", "solana", "ripple", "dogecoin", "swift", "iban", "ssn", "cvv", "pin", "otp", "ein", "itin", "mrn", "api", "a1b2"}


def spacy_noise(item):
    """True for spaCy-only results that are almost certainly wrong: acronyms, crypto names, JSON/snake_case keys."""
    text = item["text"].strip()
    if "_" in text:
        return True
    if item["entity"] == "ORGANIZATION":
        return text.lower() in NOT_ORGANIZATIONS
    if item["entity"] == "NRP":
        return text.lower() in NOT_ORGANIZATIONS
    return False


KIND_RANK = {"label": 2, "rule": 1, "nlp": 0}
# How far a context word may sit from the value it supports and still count as that value's label (Presidio looks 5 tokens back).
CONTEXT_REACH = 64


def kind_of(item, kinds):
    default = "nlp" if item["recognizer"] == "SpacyRecognizer" else "rule"
    return kinds.get(item["recognizer"], default) if kinds else default


def same_span(a, b):
    return a["start"] == b["start"] and a["end"] == b["end"]


def refine_generic(found, kinds):
    """Let a validated country-specific result replace the generic type chosen by a label.

    "passport: J36C20G26" yields PASSPORT_NUMBER from the label and DE_PASSPORT from a checksum-validated German
    rule on exactly the same value. The label says it is a passport, so the German passport rule is the better
    answer. The label also settles which family the value belongs to, so rival rules from other families on the
    same value (here DE_ID_CARD, which has the same shape) are discarded whatever their score.

    Only a validated specific result (score >= policy.REFINE_MIN_SCORE) is used. A weak shape match cannot name the
    country, so the generic type stays.
    """
    dropped = set()
    for generic in sorted((d for d in found if d["entity"] in policy.FAMILIES and kind_of(d, kinds) == "label"),
                          key=lambda d: (d["start"], d["end"], d["entity"])):
        family = policy.FAMILIES[generic["entity"]]
        specifics = [d for d in found if d["entity"] in family and same_span(d, generic) and d["score"] >= policy.REFINE_MIN_SCORE]
        if not specifics:
            continue
        dropped.add(id(generic))
        for rival in found:
            if same_span(rival, generic) and rival["entity"] not in family and kind_of(rival, kinds) != "label":
                dropped.add(id(rival))
    return [d for d in found if id(d) not in dropped]


def drop_nlp_noise(found, kinds=None):
    """Remove spaCy tags that only restate or decorate a typed result.

    spaCy tags field labels and values as organizations, dates and places ("CVV 737", "employee ID EMP-016973",
    "45 years old", the word "Bank" in "Bank account number", "VIN" in "VIN: 1HGCM..."). Three cases are certain noise:
      * the tag lies inside a labelled phrase (from the start of the label to the end of its value),
      * the tag contains a typed result, so the typed result already names the value, or
      * the tag is exactly the context word that supported a typed result right beside it (CONTEXT_REACH characters).
    PERSON is exempt: a name legitimately extends a typed fragment ("user=Sarah Johnson" types only "Sarah").
    """
    typed = [d for d in found if kind_of(d, kinds) != "nlp"]
    phrases = [(d["label_start"], d["end"]) for d in typed if d.get("label_start") is not None]
    kept = []
    for d in found:
        if kind_of(d, kinds) == "nlp" and d["entity"] != "PERSON":
            if any(a <= d["start"] and d["end"] <= b for a, b in phrases):
                continue
            if any(d["start"] <= t["start"] and t["end"] <= d["end"] for t in typed):
                continue
            tag = d["text"].strip().lower()
            if any(t.get("context_word") and t["context_word"].lower() == tag
                   and max(t["start"] - d["end"], d["start"] - t["end"], 0) <= CONTEXT_REACH for t in typed):
                continue
        kept.append(d)
    return kept


def collapse_overlaps(found, kinds=None):
    """Keep one result per overlapping group, preferring the strongest evidence, and report extensions.

    Ranking, strongest first: a value found after its label ("label"), then pattern/checksum rules ("rule"), then
    spaCy's tagger ("nlp", which gives every tag a flat 0.85 and so used to win ties against precise rules).
    Inside a rank a result whose own context word sits beside the value (and that is accepted on its own score) beats
    one that matched by chance, e.g. "bsnr: 337700093" is a DE_BSNR even though the digits also satisfy the DE_LANR
    checksum. After that the higher score wins, then the longer span, a US_-prefixed entity, and finally the entity
    name, so the outcome never depends on recognizer registration order.

    A generic label result first yields to a validated country-specific result (see refine_generic). A span that lies
    inside a kept span is redundant. A span that extends beyond a kept one is kept as well, so a consumer masking the
    union of intervals loses no sensitive character; a non-spaCy span that fully contains smaller kept spans replaces them.
    Results are copied, never modified in place. Two results for the same entity and span merge, keeping the higher score.
    """
    found = refine_generic(found, kinds)
    rank = lambda d: KIND_RANK[kind_of(d, kinds)]
    kept = []
    supported = lambda d: d.get("context", False) and d["score"] >= policy.DEFAULT_THRESHOLD
    for item in sorted(found, key=lambda d: (-rank(d), -supported(d), -d["score"], -(d["end"] - d["start"]),
                                             not d["entity"].startswith("US_"), d["entity"], d["start"])):
        overlapping = [k for k in kept if item["start"] < k["end"] and item["end"] > k["start"]]
        if not overlapping:
            kept.append(dict(item))
        elif any(item["start"] < k["start"] or item["end"] > k["end"] for k in overlapping):
            contained = [k for k in overlapping if item["start"] <= k["start"] and item["end"] >= k["end"]]
            if len(contained) == len(overlapping) and (rank(item) > 0 or all(rank(k) == 0 for k in contained)):
                for k in contained:
                    kept.remove(k)
            kept.append(dict(item))
        else:
            # Redundant. If it names the same entity on the same value, two recognizers agree: keep the
            # winner's evidence but never lose the stronger score (a checksum-validated 1.0 must not drop to a label's 0.85).
            twin = next((k for k in overlapping if k["entity"] == item["entity"] and same_span(k, item)), None)
            if twin:
                twin["score"] = max(twin["score"], item["score"])
                twin["context"] = twin.get("context", False) or item.get("context", False)
    return kept


def inside_identifier(text, start, end):
    """True when the span is only a fragment of a hyphen/underscore-joined identifier: REQ-2026-10-15-000481, report_2024-03-01_final.

    It must touch '-' or '_' on a side and the identifier must contain a letter, so date ranges ("2020-01-01-2020-12-31")
    and ISO timestamps ("2024-03-01T10:22:31Z") are not mistaken for identifiers.
    """
    touches = re.search(r"[A-Za-z0-9][-_]\Z", text[max(0, start - 2):start]) or re.match(r"[-_][A-Za-z0-9]", text[end:end + 2])
    if not touches:
        return False
    left, right = start, end
    while left > 0 and re.match(r"[A-Za-z0-9_-]", text[left - 1]):
        left -= 1
    while right < len(text) and re.match(r"[A-Za-z0-9_-]", text[right]):
        right += 1
    return bool(re.search(r"[A-Za-z]", text[left:right].replace("-", " ").replace("_", " "))) and (left, right) != (start, end)


def cut_mid_word(text, end):
    """True when a span stops in the middle of a word: the next character continues it (letter, digit, '_', or '-' + alphanumeric).

    Presidio's URL pattern lists top-level domains without a closing boundary, so the identifier user.signup matches as
    "user.si" (Slovenia). A genuine domain or URL is followed by whitespace, punctuation or the end of the text.
    """
    return bool(re.match(r"\w|-\w", text[end:end + 2]))


_MONTH_OR_DAY =re.compile(r"(?i)\A(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|mon|tue|wed|thu|fri|sat|sun)")


def identifier_shaped(text):
    """True for a letters-first identifier with digits and at least two - or _ joints (REQ-2026-10-15-000481).

    Month and weekday prefixes (Oct-15-2026, Mon-Fri) and digits-first timestamps (2024-03-01T10:22:31Z) are dates.
    """
    return bool(re.fullmatch(r"[A-Za-z]{2,}[-_][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*", text) and len(re.findall(r"[-_]", text)) >= 2
                and not _MONTH_OR_DAY.match(text))


def candidate(piece, offset, r):
    """One analyzer result as a dict with offsets into the whole text."""
    explanation = r.analysis_explanation
    metadata = r.recognition_metadata or {}
    word = (explanation.supportive_context_word if explanation else "") or ""
    item = {"text": piece[r.start:r.end], "entity": r.entity_type, "start": offset + r.start, "end": offset + r.end,
            "score": round(float(r.score), 3), "recognizer": metadata.get("recognizer_name", ""),
            "context": bool(word), "context_word": word}
    if metadata.get("label_start") is not None:
        item["label_start"] = offset + metadata["label_start"]
    return item


def detect(analyzer, text, threshold=0.5, entities=None, collapse=False):
    """Return Presidio's detections as dicts sorted by position.

    A candidate is reported when its score reaches the threshold, or when it is a context-supported weak country
    pattern (policy.accepts). collapse removes redundant candidates while preserving extending coverage (see
    collapse_overlaps). `entities` may use the alias names in policy.ENTITY_ALIASES.

    Inputs longer than CHUNK_CHARS use overlapping pieces (512 characters of context).
    Entities longer than that overlap can still straddle a cut; API requests are limited to 20 KB.
    """
    from .structured import json_scalars, analyze_json
    entities = policy.resolve_entities(entities)
    leaves = json_scalars(text) if len(text) <= CHUNK_CHARS else None
    found = analyze_json(analyzer, text, leaves, threshold, entities) if leaves is not None else []
    start = 0
    while leaves is None and start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        if end < len(text):
            cut = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
            end = cut + 1 if cut > start else end
        piece = text[start:end]
        for r in analyzer.analyze(text=piece, language="en", entities=entities or None, score_threshold=policy.candidate_floor(threshold),
                                  return_decision_process=True):
            item = candidate(piece, start, r)
            if policy.accepts(item["entity"], item["score"], item["context"], threshold):
                found.append(item)
        if end == len(text):
            break
        start = max(start + 1, end - min(512, CHUNK_CHARS // 4))
    unique = {(d["start"], d["end"], d["entity"], d["recognizer"]): d for d in found}
    found = list(unique.values())
    cleaned = []
    for item in found:
        if policy.is_placeholder(item["text"]):
            continue
        if item["entity"] == "DATE_TIME" and (identifier_shaped(item["text"]) or inside_identifier(text, item["start"], item["end"])):
            continue
        if item["entity"] == "URL" and cut_mid_word(text, item["end"]):
            continue
        if item["entity"] == "EMAIL_ADDRESS":
            assignment = re.match(r"(?i)(?:email|emailaddress|email_address|mail)=", item["text"])
            if assignment:
                item["start"] += assignment.end()
                item["text"] = text[item["start"]:item["end"]]
        if item["entity"] == "TR_LICENSE_PLATE":
            surrounding = text[max(0, item["start"] - 32):min(len(text), item["end"] + 32)]
            if not re.search(r"(?i)\b(?:plate|plaka|vehicle|registration|car)\b", surrounding):
                continue
        if item["recognizer"] == "SpacyRecognizer":
            if spacy_noise(item):
                continue
            context = text[max(0, item["start"] - 48):item["start"]]
            sensitive_date = re.search(r"(?i)birth|born|dob|admi|discharg|died|death", context)
            if item["entity"] == "DATE_TIME" and not sensitive_date and re.fullmatch(r"(?i)(?:yesterday|today|tomorrow|(?:last |next )?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|\d+ (?:minutes?|hours?)|end of day)", item["text"]):
                continue
            if item["entity"] == "PERSON" and item["text"].lower() in {"reach", "call", "contact", "email"}:
                continue
        cleaned.append(item)
    found = cleaned
    if collapse:
        kinds = getattr(analyzer, "recognizer_kinds", None)
        found = collapse_overlaps(drop_nlp_noise(found, kinds), kinds)
    return sorted(found, key=lambda d: (d["start"], d["end"], d["entity"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("text", nargs="?", help="text to analyse; default: stdin")
    source.add_argument("--file", help="UTF-8 file to analyse")
    source.add_argument("--list-entities", action="store_true", help="print every entity Presidio can detect and exit")
    parser.add_argument("--threshold", type=float, default=0.5, help="minimum score, 0-1 (default 0.5; try 0 to see everything)")
    parser.add_argument("--entities", help="comma-separated entity types to look for (default: all)")
    parser.add_argument("--collapse", action="store_true", help="remove redundant candidates while preserving extending sensitive spans")
    parser.add_argument("--english-registry", action="store_true", help="Presidio's stock English registry only (23 entity types)")
    parser.add_argument("--no-custom", action="store_true", help="leave out the project's own recognizers (pii_detector/recognizers.py)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")

    started = time.time()
    analyzer = load_analyzer(everything=not args.english_registry, custom=not args.no_custom)
    load_seconds = time.time() - started
    if args.list_entities:
        by_recognizer = {}
        for recognizer in analyzer.registry.get_recognizers(language="en", all_fields=True):
            for entity in recognizer.supported_entities:
                by_recognizer.setdefault(entity, set()).add(recognizer.name)
        scope = "Presidio's stock English registry" if args.english_registry else "the registry with every pattern recognizer enabled"
        scope += "" if args.no_custom else " plus the custom recognizers"
        print(f"{len(by_recognizer)} entity types in {scope}:\n")
        for entity in sorted(by_recognizer):
            owners = (f"alias of {policy.ENTITY_ALIASES[entity]} (no English model emits {entity})" if entity in policy.ENTITY_ALIASES
                      else ", ".join(sorted(by_recognizer[entity])))
            print(f"  {entity:28} {owners}")
        return 0

    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            text = handle.read()
    else:
        text = args.text if args.text is not None else sys.stdin.read()
    if not text.strip():
        parser.error("no text provided")
    wanted = [e.strip() for e in args.entities.split(",") if e.strip()] if args.entities else None

    detect(analyzer, "warm-up", args.threshold)   # first call has one-off costs; keep them out of the timing
    started = time.time()
    found = detect(analyzer, text, args.threshold, wanted, args.collapse)
    seconds = time.time() - started

    if args.json:
        print(json.dumps({"detections": found, "seconds": round(seconds, 3)}, indent=2, ensure_ascii=False))
        return 0
    if not found:
        print("No detections.")
    else:
        print(f"{'start':>5} {'end':>5}  {'entity':26} {'score':>5}  {'recognizer':28} text")
        for d in found:
            print(f"{d['start']:5} {d['end']:5}  {d['entity']:26} {d['score']:5.2f}  {d['recognizer']:28} {d['text']!r}")
        counts = Counter(d["entity"] for d in found)
        print("\n" + ", ".join(f"{entity} x{n}" for entity, n in counts.most_common()))
    print(f"\n{len(found)} detections in {seconds * 1000:.0f} ms ({len(text)} chars; model {configured_spacy_model()}, load {load_seconds:.1f} s, threshold {args.threshold})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
