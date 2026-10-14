"""Independent local baseline/candidate audit; preserves earlier evidence."""
import importlib.util
import json
import os
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ['PII_EAGER_INIT'] = '0'
import handler

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    label = sys.argv[1]
    old = ROOT / 'analysis/2026-10-12'
    prose = module('prose_audit', old / 'evaluate.py')
    structured = module('structured_audit', old / 'json_validation/run.py')
    handler.load()
    rows = []
    for suite, path in [('prose', old / 'cases.json'), ('json', old / 'json_validation/cases.json')]:
        for c in json.loads(path.read_text()):
            body = c['body'] if suite == 'json' else c['text']
            response = handler.handler(dict(headers={'Content-Type': c['content_type']}, body=body,
                 queryStringParameters=c.get('query', {})), None)
            decoded = json.loads(response['body'])
            row = {'suite': suite, 'case': c['name'], 'status': response['statusCode'], 'expected_status': c['status'], 'response': decoded}
            if response['statusCode'] == 200 and c['category'] != 'request':
                row['score'] = (structured if suite == 'json' else prose).score(c, decoded)
            rows.append(row)
    for c in json.loads((ROOT / 'analysis/2026-10-14/json_live_test/results.json').read_text()):
        response = handler.handler(dict(headers={'Content-Type': 'application/json'}, body=json.dumps({'text': c['text']})), None)
        rows.append({'suite': 'live_fixtures', 'case': c['case'], 'status': response['statusCode'], 'response': json.loads(response['body'])})
    benchmark = {}
    for name, payload in [('many_fields', {'people': [{'firstName':'Sarah', 'lastName':'Johnson','age':34,'email':'sarah@example.com'} for _ in range(190)]}), ('metadata', {'rows':[{'currency':'USD','quantity':12,'enabled':True} for _ in range(300)]})]:
        text = json.dumps(payload, separators=(',', ':'))
        durations = []
        for _ in range(3):
            start = time.perf_counter()
            response = handler.handler(dict(headers={'Content-Type':'application/json'}, body=json.dumps({'text':text})), None)
            durations.append(round((time.perf_counter()-start)*1000, 2))
        benchmark[name] = {'text_bytes':len(text.encode()), 'runs_ms':durations,'median_ms':statistics.median(durations),'status':response['statusCode'],'count':json.loads(response['body']).get('count')}
    out = {'label':label, 'results':rows, 'benchmarks':benchmark}
    Path(__file__).with_name(label + '.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
    for suite in ['prose','json']:
        selected = [r for r in rows if r['suite']==suite and 'score' in r]
        print(suite, sum(r['score']['exact_hits'] for r in selected), '/',sum(r['score']['expected'] for r in selected), 'invalid',sum(len(r['score']['invalid_offsets']) for r in selected),flush=True)
    print('benchmarks', benchmark, flush=True)

if __name__=='__main__':
    main()
