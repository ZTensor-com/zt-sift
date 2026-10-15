"""Gate for samples/event_stream_payload.json: a top-level array of heterogeneous audit events (see tools/build_event_stream_payload.py)."""
import unittest

from tests.payload_gate import GateTests


class EventStreamPayloadGate(GateTests, unittest.TestCase):
    STEM = "event_stream_payload"
    # Bare enumeration values that spaCy's NER tags: ISO country codes ("US", "GB", "SE", ...) as places, organisations or even
    # people (the exact tag differs between the small and large model), and a document-type name. They carry no context to decide on.
    KNOWN_NOISE = [(entity, r"[A-Z]{2}") for entity in ("LOCATION", "ORGANIZATION", "PERSON")] + [("ORGANIZATION", r"national id")]



if __name__ == "__main__":
    unittest.main()
