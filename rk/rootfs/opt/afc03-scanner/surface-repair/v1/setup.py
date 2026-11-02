import pathlib,json,hashlib,zipfile
r=pathlib.Path('/opt/afc03-scanner/surface-repair/v1')
for p,h in json.loads((r/'manifest.json').read_text()).items():assert hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()==h,p
for p in (r/'wheels').glob('*.whl'):
 with zipfile.ZipFile(p) as z:
  assert all(not n.startswith('/') and '..' not in pathlib.PurePosixPath(n).parts for n in z.namelist())
  z.extractall(r/'vendor')
print('all uploaded hashes verified; isolated dependencies extracted')
