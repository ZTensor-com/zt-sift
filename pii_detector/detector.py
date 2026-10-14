#!/usr/bin/env python3
"""Presidio + spaCy (en_core_web_lg by default, opt-in en_core_web_sm; no GLiNER).

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

SPACY_MODEL = "en_core_web_lg"
SPACY_MODELS = (SPACY_MODEL, "en_core_web_sm")


def configured_spacy_model():
    """Select a bundled model explicitly; never accept a path or download URL."""
    model = os.environ.get("PII_SPACY_MODEL", SPACY_MODEL)
    if model not in SPACY_MODELS:
        raise ValueError("PII_SPACY_MODEL must be en_core_web_lg or en_core_web_sm")
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
    configure_phone_regions(analyzer, phone_regions)
    if everything:
        enable_all_pattern_recognizers(analyzer)
    if custom:
        from .recognizers import add_custom_recognizers
        add_custom_recognizers(analyzer)
    return analyzer


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


def collapse_overlaps(found, custom_names=()):
    """Prefer a typed result for equal/contained spans, retaining extensions for complete coverage.

    Ranking: the project's own recognizers beat Presidio's built-in rules, which beat spaCy's name/place/date tagging
    (spaCy gives every tag a flat 0.85, so it used to win ties against precise rules). Within a tier the higher score,
    then the longer span, then a US_-prefixed entity (the more specific name), then the entity name wins, so the outcome never depends on recognizer registration order.
    spaCy-only results that look like noise are dropped first.
    """
    def tier(item):
        if item["recognizer"] == "SpacyRecognizer":
            return 0
        return 2 if item["recognizer"] in custom_names else 1

    kept = []
    candidates = [item for item in found if not (tier(item) == 0 and spacy_noise(item))]
    for item in sorted(candidates, key=lambda d: (-tier(d), -d["score"], -(d["end"] - d["start"]), not d["entity"].startswith("US_"), d["entity"], d["start"])):
        overlapping = [k for k in kept if item["start"] < k["end"] and item["end"] > k["start"]]
        if not overlapping:
            kept.append(item)
        elif any(item["start"] < k["start"] or item["end"] > k["end"] for k in overlapping):
            # Coverage takes precedence over tier for strict containment. Partial
            # overlaps retain both results so masking can union their intervals.
            contained = [k for k in overlapping if item["start"] <= k["start"] and item["end"] >= k["end"]]
            if len(contained) == len(overlapping) and (tier(item) > 0 or all(tier(item) >= tier(k) for k in contained)):
                for k in contained:
                    kept.remove(k)
            kept.append(item)
    return kept


def detect(analyzer, text, threshold=0.5, entities=None, collapse=False):
    """Return Presidio's detections as dicts sorted by position. collapse removes redundant spans while preserving extending coverage (see collapse_overlaps).

    Inputs longer than CHUNK_CHARS use overlapping pieces (512 characters of context).
    Entities longer than that overlap can still straddle a cut; API requests are limited to 20 KB.
    """
    from .structured import json_scalars, analyze_json
    leaves = json_scalars(text) if len(text) <= CHUNK_CHARS else None
    found = analyze_json(analyzer, text, leaves, threshold, entities) if leaves is not None else []
    start = 0
    while leaves is None and start < len(text):
        end = min(start + CHUNK_CHARS, len(text))
        if end < len(text):
            cut = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
            end = cut + 1 if cut > start else end
        piece = text[start:end]
        for r in analyzer.analyze(text=piece, language="en", entities=entities or None, score_threshold=threshold):
            found.append({"text": piece[r.start:r.end], "entity": r.entity_type, "start": start + r.start,
                          "end": start + r.end, "score": round(float(r.score), 3),
                          "recognizer": (r.recognition_metadata or {}).get("recognizer_name", "")})
        if end == len(text):
            break
        start = max(start + 1, end - min(512, CHUNK_CHARS // 4))
    unique = {(d["start"], d["end"], d["entity"], d["recognizer"]): d for d in found}
    found = list(unique.values())
    cleaned = []
    for item in found:
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
        found = collapse_overlaps(found, getattr(analyzer, "custom_recognizer_names", ()))
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
            print(f"  {entity:28} {', '.join(sorted(by_recognizer[entity]))}")
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
