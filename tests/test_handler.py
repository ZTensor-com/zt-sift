import base64
import json
import os
import sys
import unittest
from pathlib import Path

os.environ["PII_EAGER_INIT"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import handler  # noqa: E402
from pii_detector import load_analyzer  # noqa: E402


def event(body, content_type="text/plain", query=None, encoded=False):
    if encoded:
        body = base64.b64encode(body.encode()).decode()
    return {"headers": {"Content-Type": content_type}, "body": body, "queryStringParameters": query,
            "isBase64Encoded": encoded}


class HandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler.analyzer = load_analyzer(everything=True, custom=True)

    def call(self, *args, **kwargs):
        result = handler.handler(event(*args, **kwargs), None)
        return result["statusCode"], json.loads(result["body"])

    def test_plain_text_returns_the_five_fields(self):
        text = "Contact jane@example.com about card 4111 1111 1111 1111"
        code, body = self.call(text)
        self.assertEqual(code, 200)
        found = {d["entity"]: d for d in body["detections"]}
        self.assertEqual(set(found["EMAIL_ADDRESS"]), {"text", "entity", "start", "end", "score"})
        email = found["EMAIL_ADDRESS"]
        self.assertEqual(text[email["start"]:email["end"]], email["text"])
        self.assertIn("CREDIT_CARD", found)
        self.assertEqual(body["count"], len(body["detections"]))
        self.assertEqual(body["counts"], {e: sum(d["entity"] == e for d in body["detections"]) for e in found})

    def test_json_and_base64_bodies(self):
        code, body = self.call(json.dumps({"text": "SSN 219-09-9999"}), "application/json", encoded=True)
        self.assertEqual(code, 200)
        self.assertIn("US_SSN", {d["entity"] for d in body["detections"]})

    def test_custom_entities_are_active(self):
        code, body = self.call("Ship to 742 Evergreen Terrace, Springfield, IL 62704. Password: hunter2xyz!")
        entities = {d["entity"] for d in body["detections"]}
        self.assertLessEqual({"ADDRESS", "PASSWORD"}, entities)

    def test_entities_filter_and_threshold(self):
        text = "jane@example.com 123-45-6789"
        _, body = self.call(text, query={"entities": "email_address"})
        self.assertEqual({d["entity"] for d in body["detections"]}, {"EMAIL_ADDRESS"})
        _, body = self.call(text, query={"threshold": "1.01"})
        self.assertFalse(body.get("detections"))

    def test_bad_requests(self):
        for args, kwargs in ((("  ",), {}), (("x",), {"query": {"threshold": "high"}}), (("x",), {"query": {"entities": "NOPE"}}),
                             (("x",), {"query": {"collapse": "maybe"}}), (("{}", "application/json"), {}), (("\xff",), {})):
            with self.subTest(args=args, kwargs=kwargs):
                self.assertEqual(self.call(*args, **kwargs)[0], 400 if args != ("\xff",) else 200)

    def test_oversized_body_refused(self):
        self.assertEqual(self.call("a" * (handler.MAX_BYTES + 1))[0], 413)

    def test_failures_do_not_leak_the_message(self):
        original = handler.detect
        handler.detect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret 123-45-6789"))
        try:
            code, body = self.call("hello")
        finally:
            handler.detect = original
        self.assertEqual((code, body), (500, {"error": "Detection failed"}))


if __name__ == "__main__":
    unittest.main()
