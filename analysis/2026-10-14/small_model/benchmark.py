"""Bounded model/memory experiment; no external requests or deployment."""
import json
import os
from pathlib import Path
import resource
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ['PII_EAGER_INIT'] = '0'
import handler

def peak_mib():
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(raw / (1024**2 if sys.platform == 'darwin' else 1024), 2)

def main():
    start = time.perf_counter()
    handler.load()
    result = {'model': os.environ.get('PII_SPACY_MODEL','en_core_web_lg'),
              'init_ms':round((time.perf_counter()-start)*1000,2), 'init_peak_rss_mib':peak_mib(),
              'workloads':[]}
    sample = (ROOT / 'analysis/2026-10-12/user_sample.txt').read_text()
    workloads = [('prose_sample',sample),
        ('json_people',json.dumps({'people':[{'firstName':'Sarah','lastName':'Johnson','age':34,'email':'sarah@example.com'} for _ in range(190)]},separators=(',',':'))),
        ('20k_plain',('Call Sarah Johnson at jane@example.com. '*600)[:20000]),
        ('20k_json_note',json.dumps({'note':('Call Sarah Johnson at jane@example.com. '*600)[:19980]},separators=(',',':')))]
    for name,text in workloads:
        runs=[]
        for _ in range(int(os.environ.get('PII_BENCHMARK_RUNS', '1'))):
            start=time.perf_counter()
            response=handler.handler({'headers':{'Content-Type':'text/plain'},'body':text},None)
            runs.append(round((time.perf_counter()-start)*1000,2))
        body=json.loads(response['body'])
        row={'name':name,'text_bytes':len(text.encode()),'status':response['statusCode'],'count':body.get('count'),
             'runs_ms':runs,'median_ms':statistics.median(runs),'peak_rss_mib':peak_mib()}
        result['workloads'].append(row)
    result['final_peak_rss_mib']=peak_mib()
    for path in ['/sys/fs/cgroup/memory.peak','/sys/fs/cgroup/memory/memory.max_usage_in_bytes']:
        p=Path(path)
        if p.exists():
            result['container_peak_mib']=round(int(p.read_text())/1024**2,2)
            break
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
