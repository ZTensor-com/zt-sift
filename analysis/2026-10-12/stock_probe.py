"""Independent seeded stock fixtures, without selecting on detector output.

These reuse the project's format generators, so are coverage probes rather than
an independently certified ground truth benchmark. Generated IDs are synthetic.
"""
import json
from pathlib import Path
import random
import sys
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parents[1]))
from pii_detector import load_analyzer,detect
from tools.world_pii import ENTITY_GENERATORS

a=load_analyzer();rng=random.Random(20261012);records=[]
for entity,generator in ENTITY_GENERATORS().items():
    if generator is None: continue
    rec=next((r for r in a.registry.recognizers if entity in r.supported_entities and r.context),None)
    native=rec.context[0] if rec else 'identifier'
    for i in range(2):
        value=generator(rng);lead=entity.lower().replace('_',' ') if i==0 else native
        text=f'{lead}: {value}'
        found=detect(a,text,threshold=0.0,collapse=False)
        at=text.index(value);end=at+len(value)
        candidates=[d for d in found if d['entity']==entity and d['start']==at and d['end']==end]
        records.append(dict(entity=entity,text=text,value=value,start=at,end=end,
            exact_score=max((d['score'] for d in candidates),default=0),
            collapsed=detect(a,text,collapse=True),raw=found))
covered={r['entity'] for r in records}
all_entities=set(a.get_supported_entities(language='en'))
OUT.joinpath('stock_results.json').write_text(json.dumps(dict(records=records,
    registry_entities=sorted(all_entities),generator_entities=sorted(covered),
    note='Not externally validated; formats from project generators; no filtering based on detection score.'),ensure_ascii=False,indent=2))
fixtures=[]
for i in range(0,len(records),35):
    batch=records[i:i+35];text='';expected=[]
    for r in batch:
        offset=len(text);text+=r['text']+';\n'
        expected.append(dict(text=r['value'],entities=[r['entity']],start=offset+r['start'],end=offset+r['end']))
    fixtures.append(dict(name=f'stock_catalog_batch_{i//35+1}',text=text,expected=expected,
        category='stock_catalog',query={},status=200,content_type='text/plain'))
OUT.joinpath('stock_cases.json').write_text(json.dumps(fixtures,ensure_ascii=False,indent=2))
print(len(all_entities),'registry entities;',len(covered),'stock generator types;',len(records),'isolated probes')
for entity in sorted(covered):
    scores=[r['exact_score'] for r in records if r['entity']==entity]
    if max(scores)<0.5: print(entity,scores)
