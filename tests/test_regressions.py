"""Exact source spans and negative controls for the audited regressions."""
import base64
import json
import unittest
from unittest.mock import patch
from pii_detector import detect, load_analyzer
from pii_detector.detector import collapse_overlaps
from tests.test_recognizers import found


class RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = load_analyzer()

    def assert_span(self, text, entity, expected):
        results = detect(self.analyzer, text, collapse=True)
        self.assertTrue(any(d['entity'] == entity and d['text'] == expected for d in results), results)
        for d in results:
            self.assertEqual(text[d['start']:d['end']], d['text'])

    def test_complete_secrets(self):
        pem = '-----BEGIN RSA PRIVATE KEY-----\n' + 'ABCD' * 100 + '\n-----END RSA PRIVATE KEY-----'
        self.assert_span(pem, 'PRIVATE_KEY', pem)
        partial = '-----BEGIN RSA PRIVATE KEY-----\nABCD1234+/==\nAAAA'
        self.assert_span(partial, 'PRIVATE_KEY', partial)
        for key, entity in [('API key', 'API_KEY'), ('session', 'SESSION_ID')]:
            value = 'ab12' * 100
            self.assert_span(f'{key}={value}', entity, value)
        for text, expected in [('password: ab{cd}ef', 'ab{cd}ef'), ('password=ab}cd', 'ab}cd'), ('password: hi', 'hi'), ('password: secret', 'secret'), ('password is alphabetic', 'alphabetic'), ('password hunter2Bravo!', 'hunter2Bravo!'), ('password is actually hunter2!', 'hunter2!'),
                               ('passphrase: "correct horse battery staple"', 'correct horse battery staple'),
                               ('Login: mbrown / P@ssw0rd2024!', 'P@ssw0rd2024!'),
                               ('{"password":"ab\\"cd\\\\ef"}', 'ab\\"cd\\\\ef')]:
            self.assert_span(text, 'PASSWORD', expected)

    def test_structured_fields_and_offsets(self):
        text = '😀 {"nested":{"customerNumber":"CUST-123","phoneNumber":"+1-808-1235678","streetName":"Arangath Cross","apartmentNumber":"5A"},"user":"jdoe"}'
        for entity, expected in [('ACCOUNT_ID', 'CUST-123'), ('PHONE_NUMBER', '+1-808-1235678'), ('ADDRESS', 'Arangath Cross'), ('ADDRESS', '5A'), ('USERNAME', 'jdoe')]:
            self.assert_span(text, entity, expected)
        self.assert_span('username: jo', 'USERNAME', 'jo')
        self.assert_span('user=jdoe sid=abcd1234', 'USERNAME', 'jdoe')
        self.assert_span('customerNumber=CUST-884213', 'ACCOUNT_ID', 'CUST-884213')
        self.assert_span('accountNumber=123456789', 'US_BANK_NUMBER', '123456789')
        self.assert_span('email=jdoe@corp.com', 'EMAIL_ADDRESS', 'jdoe@corp.com')
        self.assert_span('billing=alerts@example.com', 'EMAIL_ADDRESS', 'billing=alerts@example.com')
        # Malformed JSON-looking fragments must not crash a plain-text request.
        detect(self.analyzer, '{"user":"bad\\qvalue"}', collapse=True)

    def test_noise_and_sensitive_dates(self):
        self.assertEqual(detect(self.analyzer, 'Page 12 of 40', collapse=True), [])
        self.assertEqual(detect(self.analyzer, '2024-01-01T10:30:00', entities=['TR_LICENSE_PLATE'], collapse=True), [])
        for word in ['Tuesday', 'yesterday', '45 minutes', 'end of day']:
            self.assertEqual(detect(self.analyzer, word, entities=['DATE_TIME'], collapse=True), [])
        self.assert_span('Her birthday is March 14', 'DATE_OF_BIRTH', 'March 14')
        self.assert_span('Jean de la Cruz called me.', 'PERSON', 'Jean de la Cruz')
        self.assert_span('NASA launched a rocket.', 'ORGANIZATION', 'NASA')
        self.assert_span('IBM hired Sarah.', 'ORGANIZATION', 'IBM')
        self.assertFalse(any(d['entity'] == 'NRP' for d in detect(self.analyzer, 'Bitcoin', collapse=True)))
        for text in ['secret society', 'token bucket', 'session ended', 'Password strength matters.', 'password is compromised.', 'employee id is required', 'student number is unavailable', 'password authentication failed', 'password complexity matters', '{"password":"null"}', '{"password":"none"}', 'password reset', 'Please reset your password.', 'customerNumbering is useful']:
            self.assertFalse(any(d['entity'] in {'API_KEY', 'SESSION_ID', 'PASSWORD', 'ACCOUNT_ID', 'EMPLOYEE_ID', 'STUDENT_ID'} for d in detect(self.analyzer, text)), text)

    def test_formats_and_bounds(self):
        self.assert_span('Address: 742 evergreen terrace, springfield, il 62704', 'ADDRESS', '742 evergreen terrace, springfield, il 62704')
        self.assert_span('Address: 5A, Kadavill Court', 'ADDRESS', '5A, Kadavill Court')
        for value in ['85000', '₹12,50,000']:
            self.assert_span('Salary: ' + value, 'SALARY', value)
        self.assert_span('age: 0', 'AGE', '0')
        self.assert_span('bank account number: 1234 5678 9012', 'US_BANK_NUMBER', '1234 5678 9012')
        self.assert_span('phone: 212-555-0187 34', 'PHONE_NUMBER', '212-555-0187')
        self.assert_span('coordinates 90, -180', 'GPS_COORDINATES', '90, -180')
        for bad in ['coordinates 90.5, 180', 'coordinates 91, 181']:
            self.assertEqual(found(bad, 'GPS_COORDINATES'), [])
        self.assert_span('device 01890a5d-ac96-7a17-b1ac-2482248423de', 'UUID', '01890a5d-ac96-7a17-b1ac-2482248423de')
        self.assert_span('Call +49 30 901820', 'PHONE_NUMBER', '+49 30 901820')
        german = load_analyzer(phone_regions=['US', 'DE'])
        self.assertTrue(any(d['entity'] == 'PHONE_NUMBER' for d in detect(german, 'Call 030 901820', threshold=.4)))

    def test_containment_preserves_classification_and_coverage(self):
        def item(entity, rec, a, b):
            return dict(entity=entity, recognizer=rec, start=a, end=b, score=.9, text='x' * (b-a))
        full = item('EMAIL_ADDRESS', 'EmailRecognizer', 0, 30)
        short = item('USERNAME', 'Custom', 0, 12)
        kinds = {'Custom': 'label', 'EmailRecognizer': 'rule', 'SpacyRecognizer': 'nlp'}
        self.assertEqual(collapse_overlaps([full, short], kinds), [full])
        wide = item('PERSON', 'SpacyRecognizer', 0, 40)
        self.assertIn(short, collapse_overlaps([wide, short], kinds))

    def test_card_numbers_need_an_issuer_range_not_just_a_luhn_check(self):
        # A South African ID is 13 digits and Luhn-valid; with no issuer range it is not a card.
        self.assertFalse(any(d['entity'] == 'CREDIT_CARD' for d in detect(self.analyzer, 'id: 6601089934086', collapse=True)))
        for number in ('4111 1111 1111 1111', '4222222222222', '3782 822463 10005', '5555 5555 5555 4444'):
            with self.subTest(number=number):
                self.assert_span('card number ' + number, 'CREDIT_CARD', number)

    def test_weak_country_patterns_need_their_label(self):
        self.assert_span('plz: 98788', 'DE_PLZ', '98788')
        self.assert_span('postcode: AB10 1XG', 'UK_POSTCODE', 'AB10 1XG')
        for bare in ('98788', 'pages 98788 to 98799', 'AB10 1XG', 'DRS053415', 'CG21881CN'):
            with self.subTest(bare=bare):
                self.assertEqual([d for d in detect(self.analyzer, bare, collapse=True)
                                  if d['entity'] in {'DE_PLZ', 'UK_POSTCODE', 'ES_PASSPORT', 'IT_IDENTITY_CARD'}], [])
        # A caller asking for stricter output gets no allowance.
        self.assertEqual(detect(self.analyzer, 'plz: 98788', threshold=0.7, entities=['DE_PLZ'], collapse=True), [])

    def test_specific_types_follow_validated_rules_and_generic_types_remain_when_the_country_is_unknown(self):
        for text, entity, value in [('passport number: J36C20G26', 'DE_PASSPORT', 'J36C20G26'), ('gstin: 20KLYFB2418R4Z0', 'IN_GSTIN', '20KLYFB2418R4Z0'),
                                    ('national identity: 34588229486', 'NG_NIN', '34588229486'), ('plate number: BVR-414TM', 'NG_VEHICLE_REGISTRATION', 'BVR-414TM'),
                                    ('Thai National ID: 2406156982089', 'TH_TNIN', '2406156982089'), ('national health service: 447 618 2143', 'UK_NHS', '447 618 2143'),
                                    ('passport: R75075500', 'US_PASSPORT', 'R75075500'), ('Korean passport: R75075500', 'PASSPORT_NUMBER', 'R75075500'),
                                    ('passport: WH8163042', 'PASSPORT_NUMBER', 'WH8163042'), ('bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r', 'AUTH_TOKEN',
                                                                                              'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r')]:
            with self.subTest(text=text):
                self.assert_span(text, entity, value)
                self.assertEqual(len([d for d in detect(self.analyzer, text, collapse=True) if d['text'] == value]), 1, text)

    def test_spacy_tags_that_only_restate_a_labelled_value_are_dropped(self):
        for text in ('Her car VIN is 1HGCM82633A004352.', 'IP address: 192.168.1.1', 'employee ID EMP-016973', 'My CVV 737 is secret', 'I am 45 years old'):
            with self.subTest(text=text):
                self.assertEqual([d for d in detect(self.analyzer, text, collapse=True)
                                  if d['recognizer'] == 'SpacyRecognizer' and d['entity'] in {'ORGANIZATION', 'DATE_TIME', 'LOCATION', 'NRP'}], [])
        self.assert_span('user=Sarah Johnson', 'PERSON', 'Sarah Johnson')

    def test_a_key_named_address_is_a_postal_address_only_when_the_value_looks_like_one(self):
        wallet = '0x4e8fdb77eebc993ca7611fb27733a3b29bf5c1d2'
        found = detect(self.analyzer, json.dumps({'wallets': [{'chain': 'ethereum', 'address': wallet}]}), collapse=True)
        self.assertEqual([(d['entity'], d['text']) for d in found], [('CRYPTO', wallet)])
        self.assert_span(json.dumps({'address': '742 Evergreen Terrace, Springfield'}), 'ADDRESS', '742 Evergreen Terrace, Springfield')
        self.assert_span(json.dumps({'address': '5A, Kadavill Court'}), 'ADDRESS', '5A, Kadavill Court')

    def test_masks_and_template_variables_are_not_secrets(self):
        for text in ('{"password": "********"}', 'password: ********', 'password: [REDACTED]', 'password=${DB_PASSWORD}', '{"password": "{{ secret }}"}',
                     '{"apiKey": "<your-key-here>"}'):
            with self.subTest(text=text):
                self.assertEqual([d for d in detect(self.analyzer, text, collapse=True) if d['entity'] in {'PASSWORD', 'API_KEY'}], [])
        self.assert_span('{"password": "Tr1ck$ter#2026"}', 'PASSWORD', 'Tr1ck$ter#2026')

    def test_a_date_inside_an_identifier_is_not_a_date(self):
        for text in ('{"requestId": "REQ-2026-10-15-000481"}', 'ticket REQ-2026-10-15-000481 failed', 'file report_2024-03-01_final.csv'):
            with self.subTest(text=text):
                self.assertEqual([d for d in detect(self.analyzer, text, collapse=True) if d['entity'] == 'DATE_TIME'], [])
        for text in ('{"createdOn": "2026-10-15"}', 'created on 2026-10-15.', 'Due 2026-10-15, then', 'from 2020-01-01-2020-12-31', 'logged at 2024-03-01T10:22:31Z',
                     'due Oct-15-2026'):
            with self.subTest(text=text):
                self.assertTrue(any(d['entity'] == 'DATE_TIME' for d in detect(self.analyzer, text, collapse=True)), text)

    def test_a_domain_must_end_at_its_suffix(self):
        # Presidio's URL pattern lists top-level domains without a closing boundary, so the identifier user.signup
        # matches as "user.si" (Slovenia), payment.authorized as "payment.au", app.settings as "app.se".
        for text in ('{"event": "user.signup"}', 'event=payment.authorized', 'topic app.settings changed', 'Ask Dr.Smith', '{"type": "kyc.documents"}'):
            with self.subTest(text=text):
                self.assertEqual([d for d in detect(self.analyzer, text, collapse=True) if d['entity'] == 'URL'], [])
        for text, expected in [('visit example.com today', 'example.com'), ('see mail.contoso.co.uk/inbox?id=4', 'mail.contoso.co.uk/inbox?id=4'),
                               ('go to https://shop.example.org/cart.', 'https://shop.example.org/cart.'), ('{"site": "www.contoso.io"}', 'www.contoso.io'),
                               ('link: docs.example.com, then', 'docs.example.com')]:
            with self.subTest(text=text):
                self.assertTrue(any(d['entity'] == 'URL' and d['text'].rstrip('.,') == expected.rstrip('.,') for d in detect(self.analyzer, text, collapse=True)), text)

    def test_chunk_boundary_and_dedup(self):
        text = 'x ' * 20 + 'jane@example.com' + ' y' * 40
        with patch('pii_detector.detector.CHUNK_CHARS', 60):
            results = detect(self.analyzer, text, entities=['EMAIL_ADDRESS'], collapse=True)
        self.assertEqual([d['text'] for d in results], ['jane@example.com'])


if __name__ == '__main__':
    unittest.main()
