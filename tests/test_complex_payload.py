"""Gate for samples/complex_payload.json: a nested, messy document with a value for every type the detector can emit.

The expected-results manifest is written by tools/build_complex_payload.py. A value must be reported as its expected
type; decoys must not be reported at all; and nothing else may be reported except the documented KNOWN_NOISE below.
"""
import json
import os
import re
import unittest

from pii_detector import detect, load_analyzer
from pii_detector.structured import json_scalars

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "samples")

# spaCy tags that are wrong but come from the language model, not from a rule. Listing them keeps the gate honest: a new
# false positive fails the test, and one that disappears is noticed here.
KNOWN_NOISE = [
    ("ORGANIZATION", r"Customer"),                       # a capitalised common noun starting a sentence
    ("PERSON", r"Path C:.*"),                            # a Windows file path inside a sentence
]
# spaCy decides where a name, place, organization or date starts and ends, so for these types the right label on the
# value is what is required, not an exact span (rule-based types must cover every character of the value).
NLP_TYPES = {"PERSON", "ORGANIZATION", "LOCATION", "NRP", "DATE_TIME"}


def load():
    with open(os.path.join(SAMPLES, "complex_payload.json"), encoding="utf-8") as handle:
        text = handle.read()
    with open(os.path.join(SAMPLES, "complex_payload.expected.json"), encoding="utf-8") as handle:
        expected = json.load(handle)["expected"]
    return text, expected


def locate(leaves, item):
    """Source span of the expected value: the whole leaf, or a substring of the one named leaf."""
    value, container = item["value"], item.get("within")
    for leaf in leaves:
        if container is None and leaf.value == value:
            return leaf.spans[0][0], leaf.spans[-1][1]
        if container is not None and leaf.value == container and value in leaf.value:
            i = leaf.value.index(value)
            return leaf.spans[i][0], leaf.spans[i + len(value) - 1][1]
    raise AssertionError(f"{item['where']}: {value!r} not found in the payload")


def alnum(text):
    return re.sub(r"[^0-9A-Za-z]", "", text)


class ComplexPayloadGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text, cls.expected = load()
        cls.leaves = json_scalars(cls.text)
        cls.found = detect(load_analyzer(), cls.text, collapse=True)
        cls.spans = [(item, *locate(cls.leaves, item)) for item in cls.expected]

    def hits(self, start, end):
        return [d for d in self.found if d["start"] < end and d["end"] > start]

    def test_the_payload_is_valid_json_within_the_api_limit(self):
        self.assertIsNotNone(self.leaves)
        self.assertLessEqual(len(self.text.encode("utf-8")), 20_000)

    def test_every_non_decoy_value_is_reported_as_its_expected_type(self):
        wrong = []
        for item, start, end in self.spans:
            if item["entity"] is None:
                continue
            hits = [d for d in self.hits(start, end) if d["entity"] == item["entity"]]
            covered = alnum("".join(self.text[max(d["start"], start):min(d["end"], end)] for d in hits))
            exact_span_required = item.get("within") is None and item["entity"] not in NLP_TYPES
            if not hits or (exact_span_required and covered != alnum(self.text[start:end])):
                wrong.append((item["entity"], item["where"], item["value"][:30], sorted({d["entity"] for d in self.hits(start, end)})))
        self.assertEqual(wrong, [], f"{len(wrong)} of {sum(1 for i in self.expected if i['entity'])}")

    def test_every_emittable_entity_type_appears_in_the_document(self):
        self.assertEqual(len({i["entity"] for i in self.expected if i["entity"]}), 120)

    def test_decoys_are_not_reported(self):
        flagged = [(item["where"], item["value"], sorted({d["entity"] for d in self.hits(start, end)}))
                   for item, start, end in self.spans if item["entity"] is None and self.hits(start, end)]
        self.assertEqual(flagged, [])

    def test_nothing_unexplained_is_reported(self):
        stray = [(d["entity"], d["text"]) for d in self.found
                 if not any(d["start"] < end and d["end"] > start for item, start, end in self.spans if item["entity"])
                 and not any(d["entity"] == entity and re.fullmatch(pattern, d["text"]) for entity, pattern in KNOWN_NOISE)]
        self.assertEqual(stray, [])

    def test_offsets_round_trip(self):
        for d in self.found:
            self.assertEqual(self.text[d["start"]:d["end"]], d["text"])


if __name__ == "__main__":
    unittest.main()
