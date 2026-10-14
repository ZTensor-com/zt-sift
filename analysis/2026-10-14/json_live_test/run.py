"""Live JSON tests. Credentials come from PII_API_KEY and are not saved."""
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

OUT = Path(__file__).resolve().parent
URL = 'https://<api-id>.execute-api.<region>.amazonaws.com/dev/detect'
IMAGE = {
    'legal': [
        {'firstName': 'John', 'lastName': 'Doe', 'age': 23},
        {'firstName': 'Mary', 'lastName': 'Smith', 'age': 32},
    ],
    'marketing': [
        {'firstName': 'Sally', 'lastName': 'Green', 'age': 27},
        {'firstName': 'Jim', 'lastName': 'Galley', 'age': 41},
    ],
    'companyName': 'True Value Corporation',
    'address': '123 First Street, Newyork, NY, USA',
    'contactNumber': '202-787-2098',
}
OWN = {
    'person': {'firstName': 'Sarah', 'lastName': 'Johnson', 'age': 34,
               'email': 'sarah.johnson@example.com', 'phoneNumber': '+1-202-555-0123'},
    'documents': {'passportNumber': '075977035', 'idCardNumber': '98765432'},
    'work': {'nursingLicenseNumber': 'RN-445566'},
    'device': {'deviceSerialNumber': 'SN48210937'},
    'credentials': {'username': 'sarah_j89', 'password': ',{Sup3rSecret!}',
                    'sessionId': '3f2a9c1e7b4d8a6f0c2e5b1d9a7f4c3e'},
}
NEGATIVE = {
    'schema': {'type': 'object', 'properties': {'password': {'type': 'string'},
                                              'email': {'type': 'string'}},
               'required': ['password', 'email']},
    'product': {'name': 'Desk lamp', 'currency': 'USD', 'quantity': 12,
                'enabled': True, 'note': 'No customer records are included.'},
}

def main():
    results = []
    for name, payload in [('image', IMAGE), ('own_positive', OWN), ('own_negative', NEGATIVE)]:
        for formatted in [False, True]:
            text = json.dumps(payload, indent=2, ensure_ascii=False) if formatted else json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
            case = name + ('_formatted' if formatted else '_minified')
            OUT.joinpath(case + '.json').write_text(text + '\n')
            request = urllib.request.Request(URL, json.dumps({'text': text}).encode(),
                {'Content-Type': 'application/json', 'x-api-key': os.environ['PII_API_KEY']}, method='POST')
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    status = response.status
                    body = json.loads(response.read())
            except urllib.error.HTTPError as error:
                status = error.code
                body = json.loads(error.read())
            row = {'case': case, 'status': status, 'elapsed_ms': round((time.perf_counter()-started)*1000, 2),
                   'text': text, 'response': body}
            results.append(row)
            OUT.joinpath('results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False))
            print(case, status, row['elapsed_ms'], flush=True)
            for detection in body.get('detections', []):
                print(' ', detection, flush=True)
    print('Saved', OUT / 'results.json')

if __name__ == '__main__':
    main()
