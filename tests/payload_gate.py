"""Shared rules for the payload gates (tests/test_complex_payload.py, tests/test_event_stream_payload.py).

A payload ships with a manifest of expectations (written by tools/build_*_payload.py):
  required  a value that must be reported as its type
  decoy     a value that must not be reported at all
  allowed   a value that may be reported as the given type or not at all (never as anything else)
  gap       a value the detector does not report yet; a tripwire fails the day it is, so it gets promoted to required
Nothing else may be reported except the documented KNOWN_NOISE.
"""
import json
import os
import re

from pii_detector import detect, load_analyzer
from pii_detector.structured import json_scalars

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "samples")

# spaCy decides where a name, place, organization or date starts and ends, so for these types the right label on the
# value is what is required, not an exact span (rule-based types must cover every character of the value).
NLP_TYPES = {"PERSON", "ORGANIZATION", "LOCATION", "NRP", "DATE_TIME"}


def alnum(text):
    return re.sub(r"[^0-9A-Za-z]", "", text)


def load(stem):
    with open(os.path.join(SAMPLES, f"{stem}.json"), encoding="utf-8") as handle:
        text = handle.read()
    with open(os.path.join(SAMPLES, f"{stem}.expected.json"), encoding="utf-8") as handle:
        expected = json.load(handle)["expected"]
    return text, expected


def locate(text, leaves, item):
    """Source span of the expected value: an object key, the whole leaf, or a substring of the one named leaf."""
    value, container = item["value"], item.get("within")
    if item.get("in_key"):
        needle = json.dumps(value, ensure_ascii=False)[1:-1]
        at = text.index('"' + needle + '"') + 1
        return at, at + len(needle)
    for leaf in leaves:
        if container is None and leaf.value == value:
            return leaf.spans[0][0], leaf.spans[-1][1]
        if container is not None and leaf.value == container and value in leaf.value:
            i = leaf.value.index(value)
            return leaf.spans[i][0], leaf.spans[i + len(value) - 1][1]
    raise AssertionError(f"{item['where']}: {value!r} not found in the payload")


class GateTests:
    """Mix into a unittest.TestCase and set STEM (and optionally KNOWN_NOISE, EMITTABLE_TYPES)."""
    STEM = None
    KNOWN_NOISE = []
    EMITTABLE_TYPES = 120

    @classmethod
    def setUpClass(cls):
        cls.text, cls.expected = load(cls.STEM)
        cls.leaves = json_scalars(cls.text)
        cls.found = detect(load_analyzer(), cls.text, collapse=True)
        cls.spans = [(item, *locate(cls.text, cls.leaves, item)) for item in cls.expected]

    def hits(self, start, end):
        return [d for d in self.found if d["start"] < end and d["end"] > start]

    def kinds(self, kind):
        for item, start, end in self.spans:
            is_gap, is_allowed = item.get("gap", False), item.get("allowed", False)
            if kind == "required" and item["entity"] and not is_gap and not is_allowed:
                yield item, start, end
            elif kind == "decoy" and item["entity"] is None:
                yield item, start, end
            elif kind == "allowed" and is_allowed:
                yield item, start, end
            elif kind == "gap" and is_gap:
                yield item, start, end

    def test_the_payload_is_valid_json_within_the_api_limit(self):
        self.assertIsNotNone(self.leaves)
        self.assertLessEqual(len(self.text.encode("utf-8")), 20_000)

    def test_every_non_decoy_value_is_reported_as_its_expected_type(self):
        wrong = []
        for item, start, end in self.kinds("required"):
            hits = [d for d in self.hits(start, end) if d["entity"] == item["entity"]]
            covered = alnum("".join(self.text[max(d["start"], start):min(d["end"], end)] for d in hits))
            exact_span_required = item.get("within") is None and item["entity"] not in NLP_TYPES
            if not hits or (exact_span_required and covered != alnum(self.text[start:end])):
                wrong.append((item["entity"], item["where"], item["value"][:30], sorted({d["entity"] for d in self.hits(start, end)})))
        self.assertEqual(wrong, [], f"{len(wrong)} of {sum(1 for _ in self.kinds('required'))}")

    def test_every_emittable_entity_type_appears_in_the_document(self):
        self.assertEqual(len({item["entity"] for item, _, _ in self.kinds("required")}), self.EMITTABLE_TYPES)

    def test_decoys_are_not_reported(self):
        flagged = [(item["where"], item["value"], sorted({d["entity"] for d in self.hits(start, end)}))
                   for item, start, end in self.kinds("decoy") if self.hits(start, end)]
        self.assertEqual(flagged, [])

    def test_allowed_values_are_reported_as_their_type_or_not_at_all(self):
        odd = [(item["where"], item["value"], sorted({d["entity"] for d in self.hits(start, end)}))
               for item, start, end in self.kinds("allowed") if {d["entity"] for d in self.hits(start, end)} - {item["entity"]}]
        self.assertEqual(odd, [])

    def test_nothing_unexplained_is_reported(self):
        explained = [(s, e) for _, s, e in self.kinds("required")] + [(s, e) for _, s, e in self.kinds("allowed")]
        gaps = [(s, e, item["entity"]) for item, s, e in self.kinds("gap")]
        stray = [(d["entity"], d["text"]) for d in self.found
                 if not any(d["start"] < e and d["end"] > s for s, e in explained)
                 and not any(d["start"] < e and d["end"] > s and d["entity"] == entity for s, e, entity in gaps)
                 and not any(d["entity"] == entity and re.fullmatch(pattern, d["text"]) for entity, pattern in self.KNOWN_NOISE)]
        self.assertEqual(stray, [])

    def test_known_gaps_are_still_gaps(self):
        """Tripwire: when the detector learns one of these, this fails and the value is promoted to required."""
        reported = [(item["where"], item["value"], item["entity"]) for item, start, end in self.kinds("gap")
                    if any(d["entity"] == item["entity"] for d in self.hits(start, end))]
        self.assertEqual(reported, [], "a documented gap is now detected: mark it required in the builder and regenerate")

    def test_offsets_round_trip(self):
        for d in self.found:
            self.assertEqual(self.text[d["start"]:d["end"]], d["text"])
