"""Gate for samples/complex_payload.json: a nested, messy document with a value for every type the detector can emit
(see tools/build_complex_payload.py and the shared rules in tests/payload_gate.py)."""
import unittest

from tests.payload_gate import GateTests


class ComplexPayloadGate(GateTests, unittest.TestCase):
    STEM = "complex_payload"
    # spaCy tags that are wrong but come from the language model, not from a rule. Listing them keeps the gate honest: a new
    # false positive fails the test, and one that disappears is noticed here.
    KNOWN_NOISE = [
        ("ORGANIZATION", r"Customer"),                       # a capitalised common noun starting a sentence
        ("PERSON", r"Path C:.*"),                            # a Windows file path inside a sentence
    ]


if __name__ == "__main__":
    unittest.main()
