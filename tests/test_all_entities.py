"""Gate: one value for every registered entity type, each next to its own descriptive key.

The payload is label-rich on purpose: it proves every recognizer is reachable and ranked correctly. It is NOT an
estimate of recall on text without labels (see test_label_free_values for that).
"""
import json
import os
import re
import unittest

from pii_detector import detect, load_analyzer

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
# Registered names that no English model emits; the API reports the real entity instead.
ALIASES = {"EMAIL": "EMAIL_ADDRESS", "ID": "NATIONAL_ID_NUMBER"}
# Next to the word "passport", these three shapes (one or two letters plus 7-8 digits) cannot be told apart from each
# other or from a US passport. Reporting the generic type is the correct answer, not a miss (see policy.WEAK_CONTEXT_ENTITIES).
GENERIC_BY_DESIGN = {"IN_PASSPORT": "PASSPORT_NUMBER", "UK_PASSPORT": "PASSPORT_NUMBER", "KR_PASSPORT": "PASSPORT_NUMBER"}


def load_cases():
    with open(os.path.join(FIXTURES, "all_entities_payload.json"), encoding="utf-8") as handle:
        text = handle.read()
    with open(os.path.join(FIXTURES, "all_entities_expected.json"), encoding="utf-8") as handle:
        cases = json.load(handle)
    located = []
    for case in cases:
        key_at = text.index(json.dumps(case["entity"]))
        label_at = text.index(json.dumps(case["label"], ensure_ascii=False), key_at)
        literal = json.dumps(case["value"], ensure_ascii=False)
        start = text.index(literal, label_at)
        end = start + len(literal)
        if isinstance(case["value"], str):          # the span excludes the quotes
            start, end = start + 1, end - 1
        located.append({**case, "start": start, "end": end, "expected": ALIASES.get(case["entity"]) or GENERIC_BY_DESIGN.get(case["entity"], case["entity"])})
    return text, located


def visible(text):
    return re.sub(r"[^0-9A-Za-z]", "", text)


class AllEntitiesGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = load_analyzer()
        cls.text, cls.cases = load_cases()
        cls.found = detect(cls.analyzer, cls.text, collapse=True)

    def overlapping(self, case):
        return [d for d in self.found if d["start"] < case["end"] and d["end"] > case["start"]]

    def test_every_value_is_reported_under_its_own_entity_type(self):
        wrong = []
        for case in self.cases:
            hits = self.overlapping(case)
            types = {d["entity"] for d in hits}
            covered = visible("".join(self.text[max(d["start"], case["start"]):min(d["end"], case["end"])] for d in hits))
            if types != {case["expected"]} or covered != visible(self.text[case["start"]:case["end"]]):
                wrong.append((case["entity"], self.text[case["start"]:case["end"]][:30], sorted(types)))
        self.assertEqual(wrong, [], f"{len(wrong)} of {len(self.cases)} values")

    def test_nothing_is_reported_outside_the_values(self):
        stray = [(d["entity"], d["text"]) for d in self.found
                 if not any(d["start"] < c["end"] and d["end"] > c["start"] for c in self.cases)]
        self.assertEqual(stray, [])

    def test_offsets_round_trip(self):
        for d in self.found:
            self.assertEqual(self.text[d["start"]:d["end"]], d["text"])

    def test_the_two_alias_names_are_resolved_not_dropped(self):
        for alias, real in ALIASES.items():
            got = detect(self.analyzer, self.text, entities=[alias], collapse=True)
            self.assertTrue(got, alias)
            self.assertEqual({d["entity"] for d in got}, {real}, alias)


if __name__ == "__main__":
    unittest.main()
