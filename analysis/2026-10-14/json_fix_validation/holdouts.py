"""Independent Unicode, value-boundary and query-option checks."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pii_detector import detect, load_analyzer

def main():
    analyzer = load_analyzer()
    cases = [
        ('unicode_names', {'firstName':'आरव', 'lastName':'शर्मा'}, [('PERSON','आरव'),('PERSON','शर्मा')]),
        ('escaped_letters', {'firstName':'Sarah','lastName':'Johnson'}, [('PERSON','Sarah'),('PERSON','Johnson')]),
        ('punctuation_secrets', {'password':' ,{secret!}"\\ 😀','email':'jane@example.com'}, [('PASSWORD',' ,{secret!}"\\ 😀'),('EMAIL_ADDRESS','jane@example.com')]),
        ('duplicate_values', [{'firstName':'John'},{'firstName':'John'}], [('PERSON','John'),('PERSON','John')]),
        ('embedded_prose', {'note':'Call Sarah Johnson at jane@example.com.'}, [('PERSON','Sarah Johnson'),('EMAIL_ADDRESS','jane@example.com')]),
        ('contextual_prose', {'note':'Call (201) 555-0123. Ship to 12 Main Street'}, [('PHONE_NUMBER','(201) 555-0123'),('ADDRESS','12 Main Street')]),
        ('nested_note', {'note':'{"password":"secret123!"}'}, [('PASSWORD','secret123!')]),
    ]
    rows=[]
    for name, payload, expected in cases:
        for ensure_ascii in [False, True]:
            text=json.dumps(payload, ensure_ascii=ensure_ascii, separators=(',',':'))
            if name=='escaped_letters':
                text=text.replace('Sarah',r'\u0053arah')
            ds=detect(analyzer,text,collapse=True)
            values=[(d['entity'],json.loads('"'+d['text']+'"')) for d in ds]
            missing=[]
            remaining=values.copy()
            for pair in expected:
                if pair in remaining:remaining.remove(pair)
                else:missing.append(pair)
            assert not missing, (name,text,ds,missing)
            assert all(text[d['start']:d['end']]==d['text'] for d in ds), (name,ds)
            rows.append({'name':name,'ensure_ascii':ensure_ascii,'text':text,'detections':ds,'additional':remaining})
    text=json.dumps({'firstName':'Sarah','password':'secret!','age':34})
    assert all(d['entity']=='PERSON' for d in detect(analyzer,text,entities=['PERSON'],collapse=True))
    assert not detect(analyzer,text,threshold=1,entities=['PERSON'],collapse=True)
    negative=json.dumps({'firstName':None,'lastName':False,'age':True,'password':{},'currency':'USD','quantity':23})
    assert not detect(analyzer,negative,collapse=True), detect(analyzer,negative,collapse=True)
    Path(__file__).with_name('holdout_results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    print('Passed',len(rows),'holdout variants plus entity/threshold and negative controls')

if __name__=='__main__':main()
