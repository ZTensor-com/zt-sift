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
        self.assertEqual(collapse_overlaps([full, short], {'Custom'}), [full])
        wide = item('PERSON', 'SpacyRecognizer', 0, 40)
        self.assertIn(short, collapse_overlaps([wide, short], {'Custom'}))

    def test_chunk_boundary_and_dedup(self):
        text = 'x ' * 20 + 'jane@example.com' + ' y' * 40
        with patch('pii_detector.detector.CHUNK_CHARS', 60):
            results = detect(self.analyzer, text, entities=['EMAIL_ADDRESS'], collapse=True)
        self.assertEqual([d['text'] for d in results], ['jane@example.com'])


if __name__ == '__main__':
    unittest.main()
