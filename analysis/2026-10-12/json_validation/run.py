"""Bounded JSON audit; no production edits or deployment.

python run.py --mode local|remote
Remote credentials are read from PII_API_KEY and never persisted.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parents[2]))
URL = 'https://<api-id>.execute-api.<region>.amazonaws.com/dev/detect'


def overlap(a, b):
    return a['start'] < b['end'] and b['start'] < a['end']


def exact(e, d):
    return e['start'] == d['start'] and e['end'] == d['end'] and d['entity'] in e['entities']


def score(c, body):
    detections = body.get('detections', [])
    expected = c['expected']
    misses = [e for e in expected if not any(exact(e, d) for d in detections)]
    covered = 0
    for e in expected:
        cursor = e['start']
        for a, b in sorted((max(e['start'], d['start']), min(e['end'], d['end']))
                           for d in detections if overlap(e, d)):
            if a > cursor:
                break
            cursor = max(cursor, b)
        covered += cursor >= e['end']
    key_hits = [dict(detection=d, keys=[k for k in c['key_spans'] if overlap(k,d)])
                for d in detections if any(overlap(k,d) for k in c['key_spans'])]
    cross_fields = []
    outside_values = []
    for d in detections:
        values = [v for v in c['value_spans'] if overlap(v,d)]
        if len(values) > 1:
            cross_fields.append(dict(detection=d, paths=[v['path'] for v in values]))
        if not any(v['start'] <= d['start'] and d['end'] <= v['end'] for v in values):
            outside_values.append(d)
    return dict(expected=len(expected), exact_hits=len(expected)-len(misses), fully_covered=covered,
                detections=len(detections), misses=misses,
                unmatched=[d for d in detections if not any(exact(e,d) for e in expected)],
                orphan_detections=[d for d in detections if not any(overlap(e,d) for e in expected)],
                key_hits=key_hits, cross_fields=cross_fields, outside_value_spans=outside_values,
                invalid_offsets=[d for d in detections if not (0<=d['start']<d['end']<=len(c['text']))
                                 or c['text'][d['start']:d['end']]!=d['text']])


def remote(c, key):
    url = URL + ('?' + urllib.parse.urlencode(c.get('query',{})) if c.get('query') else '')
    req = urllib.request.Request(url, c['body'].encode(),
                                 {'Content-Type':c['content_type'], 'x-api-key':key}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        raw=error.read()
        try: body=json.loads(raw)
        except ValueError: body={'error':'Non-JSON HTTP error response'}
        return error.code, body


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['local','remote'], default='local')
    parser.add_argument('--resume', action='store_true', help='Continue the same fixture set after checkpointed requests')
    args=parser.parse_args()
    cases=json.loads(OUT.joinpath('cases.json').read_text())
    if args.mode=='local':
        os.environ['PII_EAGER_INIT']='0'
        import handler
        handler.load()
        def call(c):
            r=handler.handler(dict(headers={'Content-Type':c['content_type']},body=c['body'],
                                   queryStringParameters=c.get('query',{})),None)
            return r['statusCode'],json.loads(r['body'])
    else:
        key=os.environ['PII_API_KEY']
        call=lambda c:remote(c,key)
    result_path=OUT.joinpath(args.mode+'_results.json')
    rows=json.loads(result_path.read_text())['results'] if args.resume and result_path.exists() else []
    completed={r['name'] for r in rows}
    for i,c in enumerate(cases):
        if c['name'] in completed:
            continue
        attempts=[]
        for attempt in range(3):
            started=time.perf_counter();status,body=call(c);ms=(time.perf_counter()-started)*1000
            attempts.append(dict(status=status,ms=round(ms,3)))
            if status!=429: break
            if attempt<2: time.sleep(3)
        row=dict(name=c['name'],category=c['category'],format=c['format'],bytes=len(c['body'].encode()),
                 content_type=c['content_type'],status=status,expected_status=c['status'],
                 ms=round(ms,3),attempts=attempts,body=body,exhaustive_gold=c['exhaustive_gold'])
        if status==200: row['score']=score(c,body)
        rows.append(row)
        OUT.joinpath(args.mode+'_results.json').write_text(json.dumps(dict(mode=args.mode,results=rows,
                notes=['Exact typing and complete coverage are distinct. Unmatched overlaps may be legitimate secondary classifications.',
                       'Policy cases are excluded from indisputable false-positive counts. Delays/retries are recorded separately.']),
                ensure_ascii=False,indent=2))
        if i==0 or (i+1)%8==0 or i+1==len(cases):
            s=row.get('score',{});print(args.mode,f'{i+1}/{len(cases)}',c['name'],status,
                f"exact {s.get('exact_hits',0)}/{s.get('expected',0)}",f"keys {len(s.get('key_hits',[]))}",flush=True)
        if args.mode=='remote':time.sleep(1.25)
    return 0


if __name__=='__main__':raise SystemExit(main())
