"""Command-line output that describes what the detector can report."""
import contextlib
import io
import sys
import unittest
from unittest.mock import patch

from pii_detector.detector import main


def run_cli(*args):
    out = io.StringIO()
    with patch.object(sys, "argv", ["pii_detector", *args]), contextlib.redirect_stdout(out):
        status = main()
    return status, out.getvalue()


class ListEntitiesTests(unittest.TestCase):
    def test_names_no_english_model_emits_are_listed_as_aliases_of_the_real_entity(self):
        status, output = run_cli("--list-entities")
        self.assertEqual(status, 0)
        lines = {line.split()[0]: line for line in output.splitlines() if line.startswith("  ")}
        self.assertIn("alias of EMAIL_ADDRESS", lines["EMAIL"])
        self.assertIn("alias of NATIONAL_ID_NUMBER", lines["ID"])
        self.assertNotIn("alias", lines["EMAIL_ADDRESS"])


if __name__ == "__main__":
    unittest.main()
