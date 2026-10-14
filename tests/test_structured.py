"""JSON boundaries, decoded values and source-offset regressions."""
import json
import unittest
from unittest.mock import patch
from pii_detector import detect, load_analyzer
from pii_detector.structured import json_scalars


class StructuredTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = load_analyzer()

    def results(self, text, **options):
        results = detect(self.analyzer, text, collapse=True, **options)
        for result in results:
            self.assertEqual(text[result['start']:result['end']], result['text'])
        return results

    def test_image_names_aliases_and_format_parity(self):
        payload = {'legal': [{'firstName': 'John', 'lastName': 'Doe', 'age': 23},
                             {'firstName': 'Mary', 'lastName': 'Smith', 'age': 32}],
                   'marketing': [{'firstName': 'Sally', 'lastName': 'Green', 'age': 27},
                                 {'firstName': 'Jim', 'lastName': 'Galley', 'age': 41}],
                   'companyName': 'True Value Corporation',
                   'passportNumber': '075977035', 'idCardNumber': '98765432',
                   'nursingLicenseNumber': 'RN-445566', 'deviceSerialNumber': 'SN48210937'}
        for indent in [None, 2]:
            results = self.results(json.dumps(payload, indent=indent))
            self.assertEqual([d['text'] for d in results if d['entity'] == 'PERSON'],
                             ['John', 'Doe', 'Mary', 'Smith', 'Sally', 'Green', 'Jim', 'Galley'])
            self.assertTrue({'ORGANIZATION', 'US_PASSPORT', 'NATIONAL_ID_NUMBER', 'PROFESSIONAL_LICENSE', 'SERIAL_NUMBER'} <= {d['entity'] for d in results})

    def test_schema_and_product_negatives(self):
        payload = {'schema': {'properties': {'password': {'type': 'string'}}, 'required': ['password', 'email'], 'fields': ['IMEI']},
                   'product': {'name': 'Desk lamp', 'currency': 'USD', 'quantity': 12}}
        for indent in [None, 2]:
            self.assertEqual(self.results(json.dumps(payload, indent=indent)), [])

    def test_unicode_punctuation_and_duplicate_offsets(self):
        value = ' ,{secret!}"\\😀'
        text = json.dumps({'people': [{'firstName': 'आरव'}, {'firstName': 'आरव'}], 'password': value})
        results = self.results(text)
        people = [d for d in results if d['entity'] == 'PERSON']
        self.assertEqual(len(people), 2)
        self.assertNotEqual(people[0]['start'], people[1]['start'])
        password = next(d for d in results if d['entity'] == 'PASSWORD')
        self.assertEqual(json.loads('"' + password['text'] + '"'), value)
        text = r'{"firstName":"\u0053arah","note":"\ud83d\ude00"}'
        self.assertEqual([(d['entity'], d['text']) for d in self.results(text)], [('PERSON', r'\u0053arah')])

    def test_no_cross_field_key_blocks_or_dates(self):
        header = '-----BEGIN RSA PRIVATE KEY-----'
        payload = {'header': header, 'note': 'unrelated business value', 'footer': '-----END RSA PRIVATE KEY-----'}
        text = json.dumps(payload)
        keys = [d for d in self.results(text) if d['entity'] == 'PRIVATE_KEY']
        self.assertEqual([d['text'] for d in keys], [header])
        results = self.results(json.dumps({'createdAt': '2026-10-12T01:10:40Z', 'duration': '45 minutes'}))
        self.assertTrue(all('duration' not in d['text'] for d in results))

    def test_lone_surrogates_and_numeric_age(self):
        for text in [r'{"x":"\ud800"}', r'{"\udfff":"hello"}', r'{"password":"\ud800secret"}']:
            self.results(text)
        results = self.results('{"age":1e2}')
        self.assertEqual([(d['entity'], d['text']) for d in results], [('AGE', '1e2')])
        for value in ['1.5', '120', '-1']:
            self.assertFalse(any(d['entity'] == 'AGE' for d in self.results('{"age":' + value + '}')))

    def test_known_fields_with_requested_or_embedded_names(self):
        for key in ['username', 'password']:
            results = self.results(json.dumps({key: 'Sarah Johnson'}), entities=['PERSON'])
            self.assertEqual([(d['entity'], d['text']) for d in results], [('PERSON', 'Sarah Johnson')])
        for key in ['passportNumber', 'idCardNumber', 'nursingLicenseNumber', 'deviceSerialNumber']:
            self.assertEqual(self.results(json.dumps({key: 'not provided'})), [])
        text = json.dumps({'phoneNumber': 'Call Sarah Johnson at +1-202-555-0123'})
        self.assertTrue(any(d['entity'] == 'PERSON' and d['text'] == 'Sarah Johnson' for d in self.results(text)))

    def test_large_json_uses_chunk_fallback(self):
        text = json.dumps({'note': 'x ' * 20 + 'jane@example.com' + ' y' * 40})
        with patch('pii_detector.detector.CHUNK_CHARS', 60):
            results = self.results(text, entities=['EMAIL_ADDRESS'])
        self.assertEqual([d['text'] for d in results], ['jane@example.com'])

    def test_options_and_fallback(self):
        text = json.dumps({'firstName': 'Sarah', 'password': 'secret!'})
        self.assertEqual([d['entity'] for d in self.results(text, entities=['PERSON'])], ['PERSON'])
        self.assertEqual(self.results(text, threshold=1, entities=['PERSON']), [])
        self.assertIsNone(json_scalars('{"password":"bad\\qvalue"}'))
        self.results('{"password":"bad\\qvalue"}')
        self.assertEqual(json_scalars('{}'), [])
        self.assertEqual(json_scalars('[]'), [])
        self.assertIsNone(json_scalars('[' * 1500 + '0' + ']' * 1500))
        no_custom = load_analyzer(custom=False)
        self.assertFalse(any(d['recognizer'] == 'StructuredFieldRecognizer' for d in detect(no_custom, text)))


if __name__ == '__main__':
    unittest.main()
