"""Merge valid responses, retry throttle-only gaps slowly, and probe stock batches."""
import json
import os
from pathlib import Path
import time
from evaluate import remote,score,DEFAULT_URL

OUT=Path(__file__).resolve().parent
cases=json.loads(OUT.joinpath('cases.json').read_text())
previous=[json.loads(OUT.joinpath(f).read_text()) for f in ['remote_initial_throttled.json','remote_results.json']]
rows={}
for p in previous:
    for r in p['results']:
        if r['status']!=429:rows[r['name']]=r
attempts=[]
key=os.environ['PII_API_KEY']
for c in cases+json.loads(OUT.joinpath('stock_cases.json').read_text()):
    if c['name'] in rows:continue
    for attempt in range(3):
        time.sleep(3)
        started=time.perf_counter();status,body=remote(c,DEFAULT_URL,key);ms=(time.perf_counter()-started)*1000
        attempts.append(dict(name=c['name'],status=status,ms=ms))
        row=dict(name=c['name'],category=c['category'],bytes=len(c['text'].encode()),status=status,
                 expected_status=c['status'],ms=round(ms,3),body=body)
        if status==200 and c['category']!='request':row['score']=score(c,body)
        if status!=429:break
    rows[c['name']]=row
    print(c['name'],status,round(ms,1),'ms',flush=True)
    OUT.joinpath('remote_complete.json').write_text(json.dumps(dict(results=list(rows.values()),retry_attempts=attempts,
        benchmarks=previous[-1]['benchmarks'],initial_benchmarks=previous[0]['benchmarks']),ensure_ascii=False,indent=2))
print('complete',len(rows),'responses')
