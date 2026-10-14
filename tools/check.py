#!/usr/bin/env python3
"""Check only this immutable calculus consumer kit and its selected scenarios."""
from pathlib import Path
import argparse,json,hashlib,subprocess,concurrent.futures
ROOT=Path(__file__).resolve().parents[1]
def read(rel):return json.loads((ROOT/rel).read_text())
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--law',default='law');ap.add_argument('--packages',action='store_true');ap.add_argument('--all-questions',action='store_true');a=ap.parse_args()
 for rel in ['source-pin.json','CANON-MANIFEST.json']:
  for row in read(rel)['files']:
   raw=(ROOT/row['path']).read_bytes();assert len(raw)==row['size'] and 'sha256:'+hashlib.sha256(raw).hexdigest()==row['sha256'],row['path']
 for m in read('source-pin.json')['models']:
  for flavor,h in m['hashes'].items():
   raw=(ROOT/f"registry/{flavor}/{m['name']}.lawir.json").read_bytes();assert 'sha256:'+hashlib.sha256(raw).hexdigest()==h;ir=json.loads(raw);assert ir['package']['name']==m['name'] and ir['package']['version']==(m.get('originalVersion',m['version']) if flavor=='original' else m['version']);assert ir['semanticVersion']=='0.2.11'
  own=read(f"registry/package/{m['name']}.lawir.json");assert all(n['package']==m['namespace'] for n in own['nodes']);pubs={n['id']:n for n in own['nodes'] if n['kind']=='publication'}
  for pubid,p in own.get('metadata',{}).get('localSources',{}).items():assert 'sha256:'+hashlib.sha256((ROOT/m['path']/p).read_bytes()).hexdigest()==pubs[pubid]['documentHash']
 rows=read('examples/index.json');assert len({x['name'].casefold() for x in rows})==len(rows)
 def replay(row):
  folder=ROOT/row['path'];expected=json.loads((folder/'result.json').read_text());assert expected['resultHash']==row['resultHash'] and not expected.get('issues');req=json.loads((folder/'request.json').read_text());assert req['ir']==read('registry/world/'+row['spec'].split('@')[0]+'.lawir.json')
  for _ in range(2):assert json.loads(subprocess.check_output([a.law,'eval',str(folder)],text=True))==expected,row['name']
  print('REPLAY PASS',row['name'],flush=True)
 selected=rows if a.all_questions else [row for row in rows if row['primary'] or (row['case'] in ['differentiate-constant','differentiate-zero'] and row['question']=='zero') or (row['case']=='ambiguous-integral-bounds' and row['question']=='integral')]
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(replay,selected))
 tree=json.loads(subprocess.check_output([a.law,'engine','unfold',str(ROOT/'registry/world/openstax.calculus_integrals.lawir.json'),'computed_integral','--clir',str(ROOT/'registry/package'),'--depth','2','--lang','en','--json'],text=True));assert tree==read('reports/unfold-integral.json');assert tree['producers'][0]['anchors']
 for name,predicate in [('openstax.calculus_limits','automatic_limit_result'),('openstax.calculus_derivatives','computed_coefficient'),('openstax.calculus_integrals','computed_integral')]:assert json.loads(subprocess.check_output([a.law,'engine','unfold',str(ROOT/'registry/world'/f'{name}.lawir.json'),predicate,'--clir',str(ROOT/'registry/package'),'--depth','1','--json'],text=True))['name']==predicate
 sample=ROOT/'examples/integrate-polynomial/integral/result.json';assert json.loads(subprocess.check_output([a.law,'inspect',str(sample),'summary'],text=True))['ok']
 if a.packages:
  def suite(row):
   name=row['spec'].split('@')[0];doc=json.loads(subprocess.check_output([a.law,'test',str(ROOT/'packages'/name),'--file',row['suite'],'--json'],text=True));assert doc['failed']==0 and doc['total']==row['total'],(row,doc);print('SUITE PASS',name,row['suite'],doc['total'],flush=True)
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(suite,read('reports/targeted-package-checks.json')['packages']))
 print('PASS: seven exact models; primary task questions and critical zero/ambiguity questions replayed twice; three reader worlds; native unfold and inspect; full corpus not_checked')
if __name__=='__main__':main()
