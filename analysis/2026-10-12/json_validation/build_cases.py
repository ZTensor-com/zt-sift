"""Synthetic JSON source-offset fixtures; no service credentials or production edits.

Offsets index Python Unicode characters in the serialized detection text, not the
outer API wrapper. Escaped values retain their literal JSON source representation.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
CASES = []


def source_intervals(text):
    """Walk valid JSON without losing source locations or duplicate values."""
    keys, values = [], []
    decoder = json.JSONDecoder()

    def skip(i):
        while i < len(text) and text[i].isspace():
            i += 1
        return i

    def walk(i, path):
        i = skip(i)
        if text[i] == '{':
            i = skip(i + 1)
            while text[i] != '}':
                key, end = decoder.raw_decode(text, i)
                child = path + [key]
                keys.append(dict(path=child, start=i + 1, end=end - 1, text=text[i+1:end-1]))
                i = skip(end)
                assert text[i] == ':'
                i = skip(walk(i + 1, child))
                if text[i] == ',':
                    i = skip(i + 1)
                else:
                    break
            return i + 1
        if text[i] == '[':
            i, count = skip(i + 1), 0
            while text[i] != ']':
                i = skip(walk(i, path + [count]))
                count += 1
                if text[i] == ',':
                    i = skip(i + 1)
                else:
                    break
            return i + 1
        value, end = decoder.raw_decode(text, i)
        start, stop = (i + 1, end - 1) if isinstance(value, str) else (i, end)
        values.append(dict(path=path, start=start, end=stop, text=text[start:stop], value=value))
        return end

    assert skip(walk(0, [])) == len(text)
    return keys, values


def add_pair(name, obj, gold=None, category='positive', exhaustive=True, note='', ascii=False):
    gold = gold or {}
    for pretty in (False, True):
        text = json.dumps(obj, ensure_ascii=ascii, indent=2 if pretty else None,
                          separators=None if pretty else (',', ':'))
        keys, values = source_intervals(text)
        expected = []
        for interval in values:
            entities = gold.get(tuple(interval['path']))
            if entities:
                expected.append({k: interval[k] for k in ('path', 'start', 'end', 'text')} |
                                {'entities': entities.split('|')})
        # Alternate valid API transport between variants to test both forms.
        ct = 'application/json' if pretty else 'text/plain'
        CASES.append(dict(name=name + ('_pretty' if pretty else '_minified'),
                          text=text, serialized_text=text, expected=expected,
                          category=category, exhaustive_gold=exhaustive, note=note,
                          content_type=ct, requestbody=json.dumps({'text': text}) if pretty else text,
                          status=200, query={}, key_intervals=keys, value_intervals=values))


profile = json.loads((ROOT / 'samples/us_custom_all.json').read_text())
old = json.loads((ROOT / 'analysis/2026-10-12/cases.json').read_text())
lookup = {e['text']: '|'.join(e['entities']) for e in old[0]['expected']}
gold = {}
for group, fields in profile.items():
    for field, value in fields.items():
        source = str(value)
        if field == 'date_of_birth':
            entity = 'DATE_OF_BIRTH'
        elif field == 'mailing':
            entity = 'ADDRESS'
        else:
            entity = lookup[source]
        gold[(group, field)] = entity
add_pair('full_profile', profile, gold,
         note='Equivalent to samples/us_custom_all.json. Full leaf values are gold; geographic subspans can be reviewed as legitimate secondary classifications.')


def camel(key):
    words = key.split('_')
    return words[0] + ''.join(w.title() for w in words[1:])

camel_profile = {camel(group): {camel(k): v for k, v in fields.items()} for group, fields in profile.items()}
add_pair('camel_profile', camel_profile, {(camel(g), camel(k)): v for (g, k), v in gold.items()})
reversed_profile = {g: dict(reversed(list(v.items()))) for g, v in reversed(list(profile.items()))}
add_pair('reordered_profile', reversed_profile, gold)

add_pair('duplicate_arrays', {'contacts': [{'email': 'jane@example.com'}, {'email': 'jane@example.com'}],
                             'username': 'jane@example.com'},
         {('contacts', 0, 'email'): 'EMAIL_ADDRESS', ('contacts', 1, 'email'): 'EMAIL_ADDRESS',
          ('username',): 'EMAIL_ADDRESS|USERNAME'}, note='Same source value at three separate positions; username overlap must retain whole email coverage.')
add_pair('unicode_escaped_secrets', {'note': '😀 café', 'email': 'jane@example.com',
                                   'password': 'pass"word\\123!'},
         {('email',): 'EMAIL_ADDRESS', ('password',): 'PASSWORD'}, ascii=True,
         note='Gold offsets and lengths include literal surrogate and quote/backslash escapes, not decoded values.')
add_pair('pem_escaped_newlines', {'privateKey': '-----BEGIN PRIVATE KEY-----\nQUJDREVGRw==\n-----END PRIVATE KEY-----'},
         {('privateKey',): 'PRIVATE_KEY'}, note='Synthetic nonfunctional PEM; full encoded JSON value must be covered.')
add_pair('pem_cross_field_fragments', {'templateHeader': '-----BEGIN PRIVATE KEY-----',
                                     'description': 'test fixture template only',
                                     'templateFooter': '-----END PRIVATE KEY-----'},
         {('templateHeader',): 'PRIVATE_KEY'},
         note='Header alone may be detected, but a key block must not bridge unrelated JSON keys and values. Synthetic template fragments are not an actual secret block.')
add_pair('organizations', {'employer': 'NASA', 'partners': ['IBM', '3M', 'BBC', 'AMD']},
         {('employer',): 'ORGANIZATION', **{('partners', i): 'ORGANIZATION' for i in range(4)}},
         note='Valid organizations, not false positives merely because they are short acronyms.')

add_pair('metadata_negative', {'app': 'dashboard', 'version': '2.4.1', 'retryCount': 3,
                              'durationMs': 45000, 'page': 12, 'totalPages': 40,
                              'enabled': True, 'status': 'ready'}, category='negative')
add_pair('product_negative', {'product': 'ceramic mug', 'price': 19.99, 'rating': 4.5,
                             'stock': 742, 'quantity': 34, 'currency': 'USD'}, category='negative')
add_pair('labels_negative', {'description': 'password reset required', 'help': 'enter your email address',
                            'fields': ['EIN', 'CVV', 'IMEI', 'password', 'username'],
                            'validation': 'phone number required'}, category='negative',
         note='Bare field labels are not organizations or disclosed credential values.')
add_pair('suffix_negative', {'customerNumbering': 'sequential', 'tokenCount': 1024,
                            'sessionTimeout': 3600, 'passwordPolicy': 'strong',
                            'accountNumbering': 'automatic'}, category='negative')
add_pair('schema_negative', {'properties': {'password': {'type': 'string'},
                                           'email': {'type': 'string'},
                                           'customerId': {'description': 'generated identifier'}},
                            'required': ['password', 'email'], 'additionalProperties': False},
         category='negative', note='Schema describes fields and contains no credential or identifier instance.')
add_pair('math_numbers_policy', {'matrix': [[40.71278, -74.00594], [12.345, 67.890]],
                                'counts': [123456789, 1234567890]}, category='policy', exhaustive=False,
         note='Declared mathematical data, but numeric signatures may be indistinguishable from coordinates or IDs without schema context.')
add_pair('timestamps_policy', {'createdAt': '2026-10-12T01:10:40Z', 'duration': '45 minutes',
                              'deadline': 'Tuesday'}, category='policy', exhaustive=False,
         note='Generic DATE_TIME policy is undecided. License plates, names, and cross-key spans are still suspicious.')
add_pair('placeholders_policy', {'password': None, 'apiKey': 'none', 'token': 'unavailable',
                                'sid': '0', 'secret': 'changeme'}, category='policy', exhaustive=False,
         note='Null/none/unavailable are absent-value markers; changeme can be a real weak secret and is not an indisputable false positive.')

for name, body, status in [('raw_domain_json_contract', {'email': 'jane@example.com'}, 400),
                         ('wrapper_json_contract', {'text': '{"email":"jane@example.com"}'}, 200)]:
    text = body.get('text', '')
    keys, values = source_intervals(text) if text else ([], [])
    expected = [dict(start=v['start'], end=v['end'], text=v['text'], entities=['EMAIL_ADDRESS'], path=v['path'])
                for v in values]
    CASES.append(dict(name=name, text=text, serialized_text=text,
                      requestbody=json.dumps(body), content_type='application/json', status=status,
                      query={}, category='contract', expected=expected, exhaustive_gold=status == 200,
                      key_intervals=keys, value_intervals=values,
                      note='API accepts a JSON envelope with a text field, not arbitrary raw domain JSON.'))

# Hold the analyzed text constant while changing only the valid transport.
# This separates JSON formatting effects from Content-Type/envelope handling.
for original_name, content_type in [('full_profile_minified', 'application/json'),
                                    ('full_profile_pretty', 'text/plain')]:
    original = next(c for c in CASES if c['name'] == original_name)
    CASES.append({**original, 'name': original_name + '_transport_control',
                  'category': 'transport', 'content_type': content_type,
                  'requestbody': json.dumps({'text': original['text']}) if content_type == 'application/json' else original['text'],
                  'note': 'Same analyzed JSON text as the named profile case; only valid HTTP transport differs.'})

for case in CASES:
    case['body'] = case['requestbody']
    case['group'] = case['category']
    case['format'] = ('pretty' if '_pretty' in case['name'] else 'minified')
    case['key_spans'] = [{**i, 'key': i['text']} for i in case['key_intervals']]
    case['value_spans'] = case['value_intervals']
    for e in case['expected']:
        assert case['text'][e['start']:e['end']] == e['text']
(OUT / 'cases.json').write_text(json.dumps(CASES, indent=2, ensure_ascii=False) + '\n')
print(f'Wrote {len(CASES)} cases; {sum(len(c["expected"]) for c in CASES)} annotated source spans.')
