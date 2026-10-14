#!/usr/bin/env python3
"""Serialize a new calculus problem; every mathematical answer comes from law."""
from pathlib import Path
import argparse,json,subprocess,tempfile,hashlib
from input_syntax import source_case,ParseError
ROOT=Path(__file__).resolve().parents[1]
TASK={'kind':'entity_ref','id':'urn:example:calculus:task'}
def verified(rel):
 raw=(ROOT/rel).read_bytes();manifest=ROOT/'CANON-MANIFEST.json'
 if manifest.exists():
  row=next(x for x in json.loads(manifest.read_text())['files'] if x['path']==rel)
  if len(raw)!=row['size'] or 'sha256:'+hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Pinned asset mismatch: '+rel)
 return raw

def collect(predicate,fields,qid):
 vars=[{'kind':'var','var':'v'+str(i)} for i in range(len(fields))]
 comp={'kind':'comprehension','distinct':True,'variable':{'id':'v0'},'element':vars[0] if len(fields)==1 else {'kind':'record','fields':{name:v for name,v in zip(fields,vars)}},'generator':{'kind':'status','status':'established','formula':{'kind':'literal','polarity':'positive','predicate':predicate,'args':[TASK,*vars]}}}
 if len(fields)>1:comp['binders']=[{'id':'v'+str(i)} for i in range(1,len(fields))]
 return {'kind':'collect','queryId':qid,'comprehension':comp}
def truth(predicate,qid):return {'kind':'truth','queryId':qid,'literal':{'kind':'literal','polarity':'positive','predicate':predicate,'args':[TASK]}}
def queries(pkg,operation):
 ns='urn:openstax:clir:'+pkg.removeprefix('openstax.').replace('_','-')+'#'
 if operation=='limit':return {'result':collect(ns+'automatic_limit_result',['outcome','kind','value'],'urn:query:calculus:limit')}
 qs={'coefficients':collect(ns+'computed_coefficient',['exponent','coefficient'],'urn:query:calculus:coefficients'),'solved':truth(ns+'polynomial_solved','urn:query:calculus:solved'),'zero':truth(ns+'computed_zero_polynomial','urn:query:calculus:zero'),'problems':collect(ns+'polynomial_problem',['reason'],'urn:query:calculus:problems')}
 if operation=='integrate':qs['integral']=collect(ns+'computed_integral',['value'],'urn:query:calculus:integral')
 return qs

def evaluate(source,pkg,operation,law='law',out=None):
 world=json.loads(verified('registry/world/'+pkg+'.lawir.json'));verified('registry/interfaces/case-input.json')
 with tempfile.TemporaryDirectory(prefix='arxo-calculus-') as tmp:
  folder=Path(tmp);casefile=folder/'input.lawcase';casefile.write_text(source)
  lower=[law,'engine','lower-ask',str(casefile),'--case','Problem','--program',str(ROOT/'registry/world'/ (pkg+'.lawir.json')),'--imports',str(ROOT/'registry/interfaces/case-input.json'),'--evaluate','evaluate truth('+pkg+'::'+('automatic_limit_task' if operation=='limit' else 'polynomial_solved')+'(entity_ref("urn:example:calculus:task")));','--query-id','urn:query:calculus:input']
  parsed=json.loads(subprocess.check_output(lower,text=True));case=parsed['case'];results={}
  for name,query in queries(pkg,operation).items():
   req={'ir':world,'case':case,'query':query,'schemaVersion':'law.core.evaluation-request/0.2','semanticVersion':world['semanticVersion']};(folder/'request.json').write_text(json.dumps(req,ensure_ascii=False,indent=2)+'\n');raw=subprocess.check_output([law,'eval',str(folder)],text=True);doc=json.loads(raw)
   if doc.get('issues'):raise RuntimeError(json.dumps(doc['issues'],ensure_ascii=False))
   results[name]=doc
   if out is not None:
    target=Path(out)/name;target.mkdir(parents=True,exist_ok=False);target.joinpath('input.lawcase').write_text(source);target.joinpath('request.json').write_bytes((folder/'request.json').read_bytes());target.joinpath('result.json').write_text(raw)
 return results

def plain(value):
 if isinstance(value,list):return [plain(x) for x in value]
 if isinstance(value,dict):
  if value.get('kind')=='value':return value['value']
  if value.get('kind')=='record':return {k:plain(v) for k,v in value['fields'].items()}
 return value

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('operation',choices=['limit','differentiate','antidifferentiate','integrate']);ap.add_argument('expression');ap.add_argument('--variable',default='x');ap.add_argument('--point',default='0');ap.add_argument('--approach',choices=['at','plus_inf','minus_inf'],default='at');ap.add_argument('--side',choices=['both','left','right'],default='both');ap.add_argument('--constant');ap.add_argument('--lower');ap.add_argument('--upper');ap.add_argument('--cap',type=int,default=64);ap.add_argument('--law',default='law');ap.add_argument('--out',type=Path);ap.add_argument('--json',action='store_true');a=ap.parse_args()
 if a.operation=='antidifferentiate' and a.constant is None:ap.error('--constant is required; use 0 for the explicitly chosen zero-constant primitive')
 if a.operation=='integrate' and (a.lower is None or a.upper is None):ap.error('--lower and --upper are required')
 try:source,pkg=source_case(a.operation,a.expression,variable=a.variable,point=a.point,approach=a.approach,side=a.side,constant=a.constant if a.constant is not None else '0',bounds=(a.lower,a.upper) if a.operation=='integrate' else None,cap=a.cap)
 except (ParseError,ValueError,ZeroDivisionError) as e:ap.error(str(e))
 docs=evaluate(source,pkg,a.operation,a.law,a.out)
 if a.json:print(json.dumps(docs,ensure_ascii=False,indent=2))
 else:
  print(json.dumps({k:plain(d['results'][0].get('value',d['results'][0].get('truthStatus'))) for k,d in docs.items()},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
