from pathlib import Path
import json,hashlib
H=Path(__file__).resolve().parent
m={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (H/'host').glob('*.py')}
assert m==json.loads((H/'host-candidate-manifest.json').read_text())
tests=['integration','core','capacity','protocol','compatibility','host-replay','runner']
for n in tests:
 d=json.loads((H/(n+'-validation.json')).read_text());assert d['passed'],n
 if isinstance(d.get('sha256'),dict):
  assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v for p,v in d['sha256'].items()),n
print('ALL_CURRENT_SOURCE_EVIDENCE_MATCHES')
