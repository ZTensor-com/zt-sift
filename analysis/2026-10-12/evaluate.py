"""Audit only: python evaluate.py --mode local|remote.

Remote runs need PII_API_KEY in the environment. Sequential, bounded requests;
no credentials are persisted. Exact typed spans and overlapping coverage differ.
"""
import argparse
import cProfile
import json
import os
from pathlib import Path
import pstats
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent
DEFAULT_URL = "https://<api-id>.execute-api.<region>.amazonaws.com/dev/detect"

def score(case, body):
    detections = body.get('detections', [])
    expected = case['expected']
    exact = lambda e,d: e['start']==d['start'] and e['end']==d['end'] and d['entity'] in e['entities']
    overlap = lambda e,d: e['start']<d['end'] and d['start']<e['end']
    return dict(expected=len(expected), exact_hits=sum(any(exact(e,d) for d in detections) for e in expected),
        typed_overlap_hits=sum(any(overlap(e,d) and d['entity'] in e['entities'] for d in detections) for e in expected),
        any_overlap_hits=sum(any(overlap(e,d) for d in detections) for e in expected),
        unmatched=[d for d in detections if not any(exact(e,d) for e in expected)],
        misses=[dict(e,overlapping=[d for d in detections if overlap(e,d)]) for e in expected if not any(exact(e,d) for d in detections)],
        invalid_offsets=[d for d in detections if not (0<=d['start']<d['end']<=len(case['text'])) or case['text'][d['start']:d['end']]!=d['text']])

def remote(case, url, key):
    url = url + ('?' + urllib.parse.urlencode(case['query']) if case['query'] else '')
    req = urllib.request.Request(url,case['text'].encode(),{'Content-Type':case['content_type'],'x-api-key':key},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=60) as res:
            return res.status,json.loads(res.read())
    except urllib.error.HTTPError as e:
        raw=e.read()
        try: body=json.loads(raw)
        except ValueError: body={'error':'non-JSON HTTP error response'}
        return e.code,body

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['local','remote'],default='local');p.add_argument('--url',default=DEFAULT_URL)
    p.add_argument('--limit',type=int);p.add_argument('--benchmark-only',action='store_true');args=p.parse_args()
    cases=json.loads(OUT.joinpath('cases.json').read_text())
    init=None
    if args.mode=='local':
        os.environ['PII_EAGER_INIT']='0'
        import handler
        s=time.perf_counter();handler.load();init=(time.perf_counter()-s)*1000
        def call(c):
            r=handler.handler(dict(headers={'Content-Type':c['content_type']},body=c['text'],queryStringParameters=c['query']),None)
            return r['statusCode'],json.loads(r['body'])
    else:
        key=os.environ['PII_API_KEY']
        call=lambda c:remote(c,args.url,key)
    rows=[]
    if not args.benchmark_only:
        for i,c in enumerate(cases[:args.limit]):
            s=time.perf_counter(); status,body=call(c);ms=(time.perf_counter()-s)*1000
            row=dict(name=c['name'],category=c['category'],bytes=len(c['text'].encode()),status=status,
                     expected_status=c['status'],ms=round(ms,3),body=body)
            if c['category']!='request' and status==200: row['score']=score(c,body)
            rows.append(row)
            if (i+1)%20==0 or c['name']=='user_sample': print(f'{args.mode} {i+1}/{len(cases)} {c["name"]}: {status}, {ms:.1f} ms',flush=True)
            if args.mode=='remote': time.sleep(0.65)
    benchmarks=[]
    if not args.limit:
        sample=cases[0]['text']
        workloads=[('short','Email jane@example.com',{}),('user_sample',sample,{}),
            ('20k_benign',('This is a regular product update with no private content. '*400)[:20000],{}),
            ('20k_dense',(sample*12)[:20000],{}),
            ('20k_numeric',('123456789012345678901234567890 '*700)[:20000],{}),
            ('email_only',sample,{'entities':'EMAIL_ADDRESS'}),
            ('no_collapse',sample,{'collapse':'false'})]
        for name,text,query in workloads:
            runs=[];count=None;statuses=[]
            for _ in range(5):
                c=dict(text=text,query=query,content_type='text/plain');s=time.perf_counter();status,body=call(c)
                runs.append((time.perf_counter()-s)*1000);statuses.append(status);count=body.get('count')
                if args.mode=='remote': time.sleep(0.65)
            b=dict(name=name,bytes=len(text.encode()),runs_ms=[round(x,3) for x in runs],median_ms=round(statistics.median(runs),3),
                   max_ms=round(max(runs),3),statuses=statuses,count=count)
            benchmarks.append(b);print('benchmark',name,b['median_ms'],'ms',statuses,flush=True)
    result=dict(mode=args.mode,init_ms=init,results=rows,benchmarks=benchmarks,
                note='Five sequential timings per workload; not a load test or controlled cold-start measurement.')
    OUT.joinpath(args.mode+'_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    if args.mode=='local' and not args.limit:
        from pii_detector import detect
        profiler=cProfile.Profile();profiler.runcall(detect,handler.analyzer,cases[0]['text'],collapse=True)
        with OUT.joinpath('profile.txt').open('w') as f:pstats.Stats(profiler,stream=f).sort_stats('cumulative').print_stats(35)
    return 0

if __name__=='__main__':raise SystemExit(main())
