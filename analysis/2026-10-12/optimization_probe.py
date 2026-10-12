"""Compare in-memory alternatives; never modifies the shipped implementation."""
import json
from pathlib import Path
import statistics
import sys
import time

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parents[1]))
from pii_detector import detect,load_analyzer
from presidio_analyzer.predefined_recognizers import PhoneRecognizer

cases=json.loads(OUT.joinpath('cases.json').read_text())
baseline=json.loads(OUT.joinpath('local_results.json').read_text())
a=load_analyzer();detect(a,'warm-up')
phone=next(r for r in a.registry.recognizers if isinstance(r,PhoneRecognizer))
regions=phone.supported_regions
workloads=[('user_sample',cases[0]['text']),('20k_dense',(cases[0]['text']*12)[:20000]),
           ('20k_numeric',('123456789012345678901234567890 '*700)[:20000])]
profiles=[]
for name in ['all_regions','US_IN_GB_CA','US_IN_GB_CA_without_parser']:
    phone.supported_regions=regions if name=='all_regions' else ['US','IN','GB','CA']
    if name.endswith('without_parser'):a.nlp_engine.nlp['en'].disable_pipe('parser')
    timings=[]
    for workload,text in workloads:
        runs=[]
        for _ in range(3):
            s=time.perf_counter();found=detect(a,text,collapse=True);runs.append((time.perf_counter()-s)*1000)
        timings.append(dict(name=workload,median_ms=round(statistics.median(runs),3),runs_ms=runs,count=len(found)))
        print(name,workload,timings[-1]['median_ms'],flush=True)
    differences=[]
    if name!='all_regions':
        for c,b in zip(cases,baseline['results']):
            if c['category']=='request':continue
            ds=detect(a,c['text'],threshold=float(c['query'].get('threshold',0.5)),collapse=c['query'].get('collapse')!='false')
            normalize=lambda ds:sorted((d['entity'],d['start'],d['end']) for d in ds)
            if normalize(ds)!=normalize(b['body'].get('detections',[])):
                differences.append(dict(case=c['name'],before=b['body'].get('detections'),after=ds))
    international=[]
    for text in ['Phone: +91 98765 43210','Phone: +44 20 7946 0018','Phone: +49 30 901820','Phone: +33 1 42 68 53 00','Phone: 030 901820']:
        international.append(dict(text=text,detections=detect(a,text,entities=['PHONE_NUMBER'],collapse=True)))
    profiles.append(dict(name=name,phone_regions=len(phone.supported_regions),timings=timings,output_differences=differences,international_phones=international))
OUT.joinpath('optimization_results.json').write_text(json.dumps(profiles,ensure_ascii=False,indent=2))
