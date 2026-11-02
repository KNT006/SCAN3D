from pathlib import Path
import json,zipfile,struct,hashlib,shutil,argparse
import numpy as np
H=Path(__file__).parent;E=H/'museum-deliverables';E.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--duck');parser.add_argument('--doll');args=parser.parse_args()
catalog=json.loads((H/'public/museum/catalog.json').read_text(encoding='utf8'));result=[]
for a in catalog:
 p=Path(getattr(args,a['id']) or str(Path('D:/Downloads')/(a['id']+'-scan3d-exhibit.zip')))
 if not p.exists():continue
 with zipfile.ZipFile(p) as z:
  assert z.testzip() is None
  record=json.loads(z.read('exhibit.json'));assert record['asset']['geometry_key']==a['geometry_key']
  assert hashlib.sha256(z.read('vertices.bin')+z.read('faces.bin')).hexdigest()==a['geometry_key']
  assert len(z.read('face-regions.bin'))==a['faces']
  glb=z.read('model.glb');magic,ver,total=struct.unpack_from('<III',glb,0);assert magic==0x46546c67 and ver==2 and total==len(glb)
  length,typ=struct.unpack_from('<II',glb,12);g=json.loads(glb[20:20+length]);binstart=20+length+8;binary=glb[binstart:]
  prim=g['meshes'][0]['primitives'][0];assert 'COLOR_0' in prim['attributes']
  def accessor(i):
   ac=g['accessors'][i];bv=g['bufferViews'][ac['bufferView']];n={'VEC3':3,'VEC4':4,'SCALAR':1}[ac['type']]
   dtype={5126:'<f4',5121:'u1',5123:'<u2',5125:'<u4'}[ac['componentType']]
   return np.frombuffer(binary,dtype,count=ac['count']*n,offset=bv.get('byteOffset',0)+ac.get('byteOffset',0)).reshape(-1,n)
  xyz=accessor(prim['attributes']['POSITION']);colors=accessor(prim['attributes']['COLOR_0']);bounds=np.ptp(xyz,axis=0)*1000
  error=float(np.max(np.abs(bounds-a['bounds_mm'])));assert error<.001
  assert len(xyz)==a['faces']*3;assert np.isfinite(colors).all()
  (E/(a['id']+'-museum.glb')).write_bytes(glb);shutil.copy2(p,E/(a['id']+'-scan3d-exhibit.zip'))
  result.append(dict(id=a['id'],triangles=len(xyz)//3,glb_bytes=len(glb),zip_bytes=p.stat().st_size,bounds_mm=bounds.tolist(),max_bounds_error_mm=error,unique_colors=len(np.unique(colors,axis=0)),story_empty=not record['record']['story']))
(E/'export-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,indent=2))
