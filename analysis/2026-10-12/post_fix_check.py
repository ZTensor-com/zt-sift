"""Compare fixes against immutable audit fixtures; no network or deployment.

This report keeps exact classification separate from character coverage. The
adversarial fixtures are not a representative estimate of production accuracy.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import statistics
import sys
import time

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parents[1]))
os.environ['PII_EAGER_INIT'] = '0'
import handler


def metrics(case, detections):
    exact = full = partial = 0
    for expected in case['expected']:
        a, b = expected['start'], expected['end']
        exact += any(d['start'] == a and d['end'] == b and d['entity'] in expected['entities'] for d in detections)
        intervals = sorted((max(a,d['start']), min(b,d['end'])) for d in detections if d['start']<b and d['end']>a)
        cursor=a
        for start,end in intervals:
            if start>cursor:break
            cursor=max(cursor,end)
        full += cursor>=b
        partial += bool(intervals) and cursor<b
    return dict(expected=len(case['expected']),exact=exact,fully_covered=full,partial_only=partial)


def main():
    fixtures=json.loads(OUT.joinpath('cases.json').read_text())
    baseline=json.loads(OUT.joinpath('local_results.json').read_text())
    before={r['name']:r for r in baseline['results']}
    started=time.perf_counter();handler.load();init_ms=(time.perf_counter()-started)*1000
    records=[]
    for c in fixtures:
        # Empty explicit filters now reject instead of silently selecting ALL.
        expected_status=400 if c['name']=='request_empty_entities' else c['status']
        event=dict(headers={'Content-Type':c['content_type']},body=c['text'],queryStringParameters=c['query'])
        with contextlib.redirect_stderr(io.StringIO()):
            started=time.perf_counter();r=handler.handler(event,None);elapsed=(time.perf_counter()-started)*1000
        body=json.loads(r['body']);detections=body.get('detections',[])
        row=dict(name=c['name'],category=c['category'],status=r['statusCode'],expected_status=expected_status,
                 ms=round(elapsed,3),body=body)
        if c['category']!='request':
            row['before']=metrics(c,before[c['name']]['body'].get('detections',[]))
            row['after']=metrics(c,detections)
            row['invalid_offsets']=[d for d in detections if not (0<=d['start']<d['end']<=len(c['text'])) or c['text'][d['start']:d['end']]!=d['text']]
        records.append(row)
    from pii_detector import detect
    sample=fixtures[0]['text']
    workloads=[('user_sample',sample),('20k_dense',(sample*12)[:20000]),('20k_numeric',('123456789012345678901234567890 '*700)[:20000])]
    bench=[]
    for name,text in workloads:
        runs=[]
        for _ in range(5):
            started=time.perf_counter();detect(handler.analyzer,text,collapse=True);runs.append((time.perf_counter()-started)*1000)
        original=next(b for b in baseline['benchmarks'] if b['name']==name)
        bench.append(dict(name=name,before_ms=original['median_ms'],after_ms=round(statistics.median(runs),3),runs_ms=runs))
    result=dict(init_ms=init_ms,records=records,benchmarks=bench,
        note='Local hardware, five calls per workload; not a deployed latency guarantee. Original audit annotations retained, including policy/out-of-scope cases.')
    OUT.joinpath('post_fix_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    for category in ['sample','canonical','stock','variant']:
        rs=[r for r in records if r['category']==category]
        print(category, 'expected',sum(r['after']['expected'] for r in rs),
              'exact',sum(r['before']['exact'] for r in rs),'->',sum(r['after']['exact'] for r in rs),
              'fully-covered',sum(r['before']['fully_covered'] for r in rs),'->',sum(r['after']['fully_covered'] for r in rs))
    print('unexpected statuses',[(r['name'],r['status']) for r in records if r['status']!=r['expected_status']])
    print('offset errors',sum(len(r.get('invalid_offsets',[])) for r in records))
    print('benchmarks',bench)


if __name__=='__main__':main()
