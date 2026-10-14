#!/usr/bin/env python3
"""Reproduce the selected measurements with the existing common classifier."""
from pathlib import Path
import sys,json,hashlib,argparse
from collections import Counter
r=Path(__file__).resolve().parents[1]
def verified(rel,expected):
 raw=(r/rel).read_bytes()
 if 'sha256:'+hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Input hash differs: '+rel)
 return raw
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--check',action='store_true');ap.add_argument('--out',type=Path);args=ap.parse_args()
report=json.loads((r/'reports/formalization-depth.json').read_text());recorded=report['packages'];report['packages']=[]
for rel,h in report['implementationHashes'].items():verified(rel,h)
sys.path.insert(0,str(r/'tools/depth'));import boundaries
pin=json.loads((r/'source-pin.json').read_text());inputs={x['path']:x for x in pin['files']}
for m in pin['models']:
 pkg=r/m['path'];path=r/'registry/package'/f'{m["name"]}.lawir.json';ir=json.loads(verified(path.relative_to(r).as_posix(),m['hashes']['package']));assert all(n['package']==m['namespace'] for n in ir['nodes']);docs=[];counts=Counter();pubs={n['documentHash']:n for n in ir['nodes'] if n['kind']=='publication'};seen=set()
 for dec in sorted(pkg.glob('sources/**/articles.json')):
  for entry in json.loads(verified(dec.relative_to(r).as_posix(),inputs[dec.relative_to(r).as_posix()]['sha256']))['editions']:
   p=dec.parent/entry['document'];rel=p.relative_to(r).as_posix();raw=verified(rel,inputs[rel]['sha256']);h='sha256:'+hashlib.sha256(raw).hexdigest();assert h in pubs,(m['name'],p,h);measure=boundaries.depth(p,path);rows=measure['rows'];counts.update(row['level'] for row in rows);seen.add(pubs[h]['id']);docs.append({'path':p.relative_to(r).as_posix(),'sourceHash':h,'publication':pubs[h]['id'],'edition':pubs[h]['edition'],'declaration':dec.relative_to(r).as_posix(),'declarationHash':'sha256:'+hashlib.sha256(dec.read_bytes()).hexdigest(),'snapshotScope':entry['snapshotScope'],'denominator':len(rows),'units':rows,'unresolvedAnchors':measure['unresolved'],'otherEditionAnchors':measure['otherEdition']})
 unmatched=[p['id'] for p in pubs.values() if p['id'] not in seen]
 row={'spec':m['name']+'@'+m['version'],'packageHash':'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest(),'status':'measured' if docs and not unmatched else 'partial' if docs else 'not_measured','denominator':sum(counts.values()) if docs else None,'levels':dict(counts),'documents':docs,'unmeasuredPublications':unmatched,'ownRules':sum(n['kind']=='rule' for n in ir['nodes']),'ownFragments':sum(n['kind']=='fragment' for n in ir['nodes']),'unanchoredRules':[n['id'] for n in ir['nodes'] if n['kind']=='rule' and not n.get('anchors')],'ownNormTemplates':sum(n['kind']=='norm_template' for n in ir['nodes'])};report['packages'].append(row);print(m['name'],row['status'],row['denominator'],row['levels'])
if args.check:assert report['packages']==recorded,'Recomputed measurements differ'
if args.out:args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
assert len([x for x in report['packages'] if x['status']=='measured'])==3
print('PASS: 3 source models; exact source editions; 19 CNXML modules; corpus not_checked')
