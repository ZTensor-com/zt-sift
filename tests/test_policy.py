"""Ranking, acceptance and noise rules, tested on synthetic candidates (no model loaded)."""
import itertools
import random
import unittest

from pii_detector import policy
from pii_detector.detector import collapse_overlaps, drop_nlp_noise

KINDS = {
    "SpacyRecognizer": "nlp",
    "LabeledPassportNumberRecognizer": "label", "LabeledNationalIdNumberRecognizer": "label", "LabeledTaxIdNumberRecognizer": "label",
    "LabeledUsPassportRecognizer": "label", "LabeledDateOfBirthRecognizer": "label", "LabeledUsernameRecognizer": "label",
    "LabeledPhoneNumberRecognizer": "label",
    "DePassportRecognizer": "rule", "DeIdCardRecognizer": "rule", "NgNinRecognizer": "rule", "DeTaxIdRecognizer": "rule",
    "ThTninRecognizer": "rule", "InPassportRecognizer": "rule", "UkPassportRecognizer": "rule", "KrPassportRecognizer": "rule",
    "NhsRecognizer": "rule", "UsPhoneFormatRecognizer": "rule", "DateRecognizer": "rule", "EmailRecognizer": "rule",
}


def item(entity, recognizer, start=0, end=10, score=0.85, context=False, label_start=None):
    out = {"text": "x" * (end - start), "entity": entity, "start": start, "end": end, "score": score,
           "recognizer": recognizer, "context": context}
    if label_start is not None:
        out["label_start"] = label_start
    return out


def entities(found):
    return sorted(d["entity"] for d in found)


class AcceptanceTests(unittest.TestCase):
    def test_a_score_at_or_above_the_threshold_is_accepted(self):
        self.assertTrue(policy.accepts("US_SSN", 0.5, False, 0.5))
        self.assertFalse(policy.accepts("US_SSN", 0.49, False, 0.5))

    def test_weak_country_pattern_is_accepted_only_with_a_context_word(self):
        self.assertTrue(policy.accepts("DE_PLZ", 0.40, True, 0.5))
        self.assertTrue(policy.accepts("UK_POSTCODE", 0.45, True, 0.5))
        self.assertFalse(policy.accepts("DE_PLZ", 0.40, False, 0.5))
        self.assertFalse(policy.accepts("DE_PLZ", 0.05, False, 0.5))

    def test_context_does_not_rescue_a_score_below_the_floor_or_an_unlisted_entity(self):
        self.assertFalse(policy.accepts("DE_PLZ", 0.39, True, 0.5))
        self.assertFalse(policy.accepts("IN_VOTER", 0.45, True, 0.5))
        # A shape that cannot tell the issuing country apart is not given the allowance.
        for entity in ("IN_PASSPORT", "UK_PASSPORT", "KR_PASSPORT"):
            self.assertFalse(policy.accepts(entity, 0.45, True, 0.5), entity)

    def test_a_caller_who_raises_the_threshold_gets_no_exception_for_weak_patterns(self):
        self.assertFalse(policy.accepts("DE_PLZ", 0.40, True, 0.7))

    def test_candidate_floor_never_exceeds_the_threshold(self):
        self.assertEqual(policy.candidate_floor(0.5), policy.WEAK_FLOOR)
        self.assertEqual(policy.candidate_floor(0.0), 0.0)
        self.assertEqual(policy.candidate_floor(0.8), policy.WEAK_FLOOR)


class AliasTests(unittest.TestCase):
    def test_registered_names_no_english_model_emits_resolve_to_real_entities(self):
        self.assertEqual(policy.resolve_entities(["EMAIL", "US_SSN", "ID"]), ["EMAIL_ADDRESS", "US_SSN", "NATIONAL_ID_NUMBER"])
        self.assertIsNone(policy.resolve_entities(None))

    def test_duplicates_after_resolution_are_removed_in_order(self):
        self.assertEqual(policy.resolve_entities(["EMAIL", "EMAIL_ADDRESS"]), ["EMAIL_ADDRESS"])


class RankingTests(unittest.TestCase):
    def test_a_validated_rule_beats_a_weaker_rule_on_the_same_span(self):
        found = [item("PHONE_NUMBER", "UsPhoneFormatRecognizer", score=0.6), item("UK_NHS", "NhsRecognizer", score=1.0)]
        for order in itertools.permutations(found):
            self.assertEqual(entities(collapse_overlaps(list(order), KINDS)), ["UK_NHS"])

    def test_label_evidence_beats_a_higher_scoring_rule(self):
        found = [item("DATE_TIME", "DateRecognizer", score=0.95), item("DATE_OF_BIRTH", "LabeledDateOfBirthRecognizer", score=0.9)]
        for order in itertools.permutations(found):
            self.assertEqual(entities(collapse_overlaps(list(order), KINDS)), ["DATE_OF_BIRTH"])

    def test_a_specific_validated_rule_replaces_the_generic_label_result(self):
        found = [item("PASSPORT_NUMBER", "LabeledPassportNumberRecognizer", score=0.85),
                 item("DE_PASSPORT", "DePassportRecognizer", score=1.0), item("DE_ID_CARD", "DeIdCardRecognizer", score=1.0)]
        for order in itertools.permutations(found):
            self.assertEqual(entities(collapse_overlaps(list(order), KINDS)), ["DE_PASSPORT"])

    def test_the_specific_entity_must_belong_to_the_label_family(self):
        found = [item("NATIONAL_ID_NUMBER", "LabeledNationalIdNumberRecognizer", score=0.8),
                 item("NG_NIN", "NgNinRecognizer", score=1.0), item("DE_TAX_ID", "DeTaxIdRecognizer", score=1.0)]
        for order in itertools.permutations(found):
            self.assertEqual(entities(collapse_overlaps(list(order), KINDS)), ["NG_NIN"])

    def test_the_best_member_of_the_family_wins(self):
        found = [item("NATIONAL_ID_NUMBER", "LabeledNationalIdNumberRecognizer", score=0.8),
                 item("TH_TNIN", "ThTninRecognizer", score=1.0), item("KR_FRN", "ThTninRecognizer", score=0.5)]
        self.assertEqual(entities(collapse_overlaps(found, KINDS)), ["TH_TNIN"])

    def test_a_weak_specific_guess_does_not_replace_the_generic_result(self):
        # IN_PASSPORT at 0.45 is a shape guess: the generic type is the honest answer.
        found = [item("PASSPORT_NUMBER", "LabeledPassportNumberRecognizer", score=0.85),
                 item("IN_PASSPORT", "InPassportRecognizer", score=0.45, context=True)]
        for order in itertools.permutations(found):
            self.assertEqual(entities(collapse_overlaps(list(order), KINDS)), ["PASSPORT_NUMBER"])

    def test_the_label_settles_the_family_so_a_stronger_rival_from_another_family_goes(self):
        # "passport number: US4515396": a 1.0 medical-licence rule matches the same characters but the label says passport.
        found = [item("PASSPORT_NUMBER", "LabeledPassportNumberRecognizer", score=0.85),
                 item("DE_PASSPORT", "DePassportRecognizer", score=0.9), item("MEDICAL_LICENSE", "DeIdCardRecognizer", score=1.0)]
        self.assertEqual(entities(collapse_overlaps(found, KINDS)), ["DE_PASSPORT"])

    def test_a_validated_jwt_replaces_the_generic_api_key_label_result(self):
        found = [item("API_KEY", "LabeledPassportNumberRecognizer", score=0.8), item("AUTH_TOKEN", "InPassportRecognizer", score=1.0)]
        self.assertEqual(entities(collapse_overlaps(found, KINDS)), ["AUTH_TOKEN"])

    def test_a_specific_on_a_different_span_does_not_replace_the_generic_result(self):
        # Refinement needs the identical value; a partly overlapping span is an extension, so both are reported.
        found = [item("PASSPORT_NUMBER", "LabeledPassportNumberRecognizer", start=0, end=10),
                 item("DE_PASSPORT", "DePassportRecognizer", start=5, end=15, score=1.0)]
        self.assertEqual(entities(collapse_overlaps(found, KINDS)), ["DE_PASSPORT", "PASSPORT_NUMBER"])

    def test_a_specific_that_contains_the_generic_span_subsumes_it(self):
        found = [item("PASSPORT_NUMBER", "LabeledPassportNumberRecognizer", start=0, end=10),
                 item("DE_PASSPORT", "DePassportRecognizer", start=0, end=12, score=1.0)]
        self.assertEqual(entities(collapse_overlaps(found, KINDS)), ["DE_PASSPORT"])

    def test_output_does_not_depend_on_input_order(self):
        found = [item("PASSPORT_NUMBER", "LabeledPassportNumberRecognizer"), item("DE_PASSPORT", "DePassportRecognizer", score=1.0),
                 item("PHONE_NUMBER", "UsPhoneFormatRecognizer", start=20, end=30, score=0.6), item("UK_NHS", "NhsRecognizer", start=20, end=30, score=1.0),
                 item("PERSON", "SpacyRecognizer", start=40, end=50)]
        expected = collapse_overlaps(found, KINDS)
        rng = random.Random(7)
        for _ in range(20):
            shuffled = found[:]
            rng.shuffle(shuffled)
            self.assertEqual(collapse_overlaps(shuffled, KINDS), expected)

    def test_a_full_validated_span_still_replaces_a_shorter_label_result(self):
        full = item("EMAIL_ADDRESS", "EmailRecognizer", 0, 30, score=1.0)
        short = item("USERNAME", "LabeledUsernameRecognizer", 0, 12)
        self.assertEqual(collapse_overlaps([full, short], KINDS), [full])


class PlaceholderTests(unittest.TestCase):
    def test_masks_and_template_variables_are_placeholders(self):
        for value in ("********", "••••••••", "xxxxxxxx", "####", "[REDACTED]", "redacted", "<password>", "${DB_PASSWORD}", "{{ secret }}", "%DB_PASS%"):
            with self.subTest(value=value):
                self.assertTrue(policy.is_placeholder(value))

    def test_real_values_are_not_placeholders(self):
        for value in ("Tr1ck$ter#2026", "hunter2", "changeme", "xX_gamer_Xx", "a*b*c*d", "***secret***", "x", "REQ-2026", "password"):
            with self.subTest(value=value):
                self.assertFalse(policy.is_placeholder(value))


class ContextEvidenceTests(unittest.TestCase):
    """A recognizer whose own label word sits beside the value outranks one that matched by chance."""

    def test_a_context_supported_accepted_rule_beats_a_lucky_checksum_collision(self):
        # "bsnr: 337700093": 9 digits that also happen to satisfy the LANR checksum (1.0, no label word).
        found = [item("DE_LANR", "NhsRecognizer", score=1.0), item("DE_BSNR", "NgNinRecognizer", score=0.55, context=True)]
        for order in itertools.permutations(found):
            self.assertEqual(entities(collapse_overlaps(list(order), KINDS)), ["DE_BSNR"])

    def test_context_does_not_help_a_result_that_is_not_accepted_on_its_own(self):
        found = [item("DE_LANR", "NhsRecognizer", score=1.0), item("DE_BSNR", "NgNinRecognizer", score=0.4, context=True)]
        self.assertEqual(entities(collapse_overlaps(found, KINDS)), ["DE_LANR"])

    def test_without_any_context_the_higher_score_still_wins(self):
        found = [item("DE_LANR", "NhsRecognizer", score=1.0), item("DE_BSNR", "NgNinRecognizer", score=0.55)]
        self.assertEqual(entities(collapse_overlaps(found, KINDS)), ["DE_LANR"])


class AgreementTests(unittest.TestCase):
    """Two recognizers naming the same entity on the same value is corroboration, never a reason to lower the score."""

    def test_the_agreeing_results_collapse_to_one_carrying_the_highest_score(self):
        label = item("VIN", "LabeledUsernameRecognizer", score=0.85)
        rule = item("VIN", "DeIdCardRecognizer", score=1.0, context=True)
        for order in itertools.permutations([label, rule]):
            kept = collapse_overlaps(list(order), KINDS)
            self.assertEqual([(d["entity"], d["score"]) for d in kept], [("VIN", 1.0)])
            self.assertTrue(kept[0]["context"])

    def test_the_evidence_winner_decides_the_recognizer_but_not_the_score(self):
        label = item("PHONE_NUMBER", "LabeledPhoneNumberRecognizer", score=0.8)
        rule = item("PHONE_NUMBER", "UsPhoneFormatRecognizer", score=0.95)
        kept = collapse_overlaps([rule, label], KINDS)
        self.assertEqual((kept[0]["recognizer"], kept[0]["score"]), ("LabeledPhoneNumberRecognizer", 0.95))

    def test_different_entities_on_one_value_never_share_a_score(self):
        label = item("DATE_OF_BIRTH", "LabeledDateOfBirthRecognizer", score=0.9)
        rule = item("DATE_TIME", "DateRecognizer", score=0.95)
        kept = collapse_overlaps([label, rule], KINDS)
        self.assertEqual([(d["entity"], d["score"]) for d in kept], [("DATE_OF_BIRTH", 0.9)])

    def test_collapse_does_not_modify_the_results_it_is_given(self):
        label = item("VIN", "LabeledUsernameRecognizer", score=0.85)
        rule = item("VIN", "DeIdCardRecognizer", score=1.0)
        collapse_overlaps([label, rule], KINDS)
        self.assertEqual((label["score"], rule["score"]), (0.85, 1.0))


class NlpNoiseTests(unittest.TestCase):
    def test_a_spacy_span_that_contains_a_typed_result_is_dropped(self):
        age = item("AGE", "YearsOldRecognizer", 0, 2)
        for entity in ("DATE_TIME", "ORGANIZATION", "LOCATION", "NRP"):
            spacy = item(entity, "SpacyRecognizer", 0, 13)
            self.assertEqual(drop_nlp_noise([spacy, age], KINDS), [age], entity)

    def test_a_person_span_may_extend_a_typed_result(self):
        username = item("USERNAME", "LabeledUsernameRecognizer", 5, 10)
        person = item("PERSON", "SpacyRecognizer", 5, 18)
        self.assertEqual(drop_nlp_noise([person, username], KINDS), [person, username])

    def test_a_spacy_span_inside_a_labelled_phrase_is_dropped(self):
        value = item("US_BANK_NUMBER", "LabeledUsBankNumberRecognizer", 23, 33, label_start=0)
        label_words = item("ORGANIZATION", "SpacyRecognizer", 0, 4)
        elsewhere = item("ORGANIZATION", "SpacyRecognizer", 40, 50)
        self.assertEqual(drop_nlp_noise([label_words, value, elsewhere], {**KINDS, "LabeledUsBankNumberRecognizer": "label"}), [value, elsewhere])

    def test_a_spacy_tag_that_is_the_context_word_beside_its_value_is_dropped(self):
        # "VIN: 1HGCM...": the VIN rule was boosted by the word "vin", and spaCy tags that same word as an organization.
        value = item("VIN", "DePassportRecognizer", 5, 22, score=1.0, context=True)
        value["context_word"] = "vin"
        label = item("ORGANIZATION", "SpacyRecognizer", 0, 3)
        label["text"] = "VIN"
        self.assertEqual(drop_nlp_noise([label, value], KINDS), [value])
        # case does not matter
        value["context_word"] = "VIN"
        self.assertEqual(drop_nlp_noise([label, value], KINDS), [value])

    def test_the_context_word_rule_needs_the_tag_to_equal_the_word_and_stay_near_the_value(self):
        value = item("VIN", "DePassportRecognizer", 200, 217, score=1.0, context=True)
        value["context_word"] = "vin"
        other_word = item("ORGANIZATION", "SpacyRecognizer", 195, 198)           # next to the value, but not the context word
        other_word["text"] = "ACM"
        too_far = item("ORGANIZATION", "SpacyRecognizer", 0, 3)                  # equals the word, 197 characters away
        too_far["text"] = "VIN"
        label_near = item("ORGANIZATION", "SpacyRecognizer", 195, 198)
        label_near["text"] = "VIN"
        self.assertEqual(drop_nlp_noise([label_near, value], KINDS), [value])
        self.assertEqual(drop_nlp_noise([other_word, too_far, value], KINDS), [other_word, too_far, value])
        # PERSON is never treated as label noise
        person = item("PERSON", "SpacyRecognizer", 195, 198)
        self.assertIn(person, drop_nlp_noise([person, {**value, "context_word": "vin"}], KINDS))

    def test_an_unrelated_spacy_span_is_kept(self):
        self.assertEqual(len(drop_nlp_noise([item("ORGANIZATION", "SpacyRecognizer", 0, 9)], KINDS)), 1)


if __name__ == "__main__":
    unittest.main()
