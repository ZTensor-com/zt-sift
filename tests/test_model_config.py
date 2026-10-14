"""Model selection and component exclusion without loading model weights."""
import os
import unittest
from unittest.mock import patch, sentinel

from pii_detector.detector import configured_spacy_model, create_nlp_engine, load_analyzer


class ModelConfigTests(unittest.TestCase):
    def test_default_and_opt_in_model(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(configured_spacy_model(), "en_core_web_lg")
        with patch.dict(os.environ, {"PII_SPACY_MODEL": "en_core_web_sm"}):
            self.assertEqual(configured_spacy_model(), "en_core_web_sm")

    def test_invalid_model_rejected_before_loading(self):
        for value in ("", "en_core_web_md", "/tmp/model", "https://example.com/model"):
            with self.subTest(value=value), patch.dict(os.environ, {"PII_SPACY_MODEL": value}), patch("pii_detector.detector.create_nlp_engine") as create:
                with self.assertRaisesRegex(ValueError, "PII_SPACY_MODEL"):
                    load_analyzer()
                create.assert_not_called()

    def test_unused_weights_excluded_at_load_for_both_models(self):
        for model in ("en_core_web_lg", "en_core_web_sm"):
            with self.subTest(model=model), patch("spacy.load", return_value=sentinel.nlp) as load, patch("presidio_analyzer.nlp_engine.SpacyNlpEngine._enable_gpu"):
                engine = create_nlp_engine(model)
                load.assert_called_once_with(model, exclude=["parser", "senter"])
                self.assertTrue(engine.is_loaded())
                self.assertIs(engine.nlp["en"], sentinel.nlp)
                self.assertEqual(engine.models, [{"lang_code": "en", "model_name": model}])


if __name__ == "__main__":
    unittest.main()
