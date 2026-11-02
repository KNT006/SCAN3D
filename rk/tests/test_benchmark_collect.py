import sys,unittest,tempfile,json
from pathlib import Path
import numpy as np,cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/heterogeneous_benchmark'))
from collect import collect,spread
from row_results import Center,CandidateExtra,RowDone,ADAPTIVE_ALGORITHM
class CollectTests(unittest.TestCase):
 def test_output_boundary_and_preserve(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);jobs=root/'jobs';jobs.mkdir()
   with self.assertRaises(ValueError):collect(jobs,jobs/'new',1)
   with self.assertRaises(ValueError):collect(jobs,jobs,1)
 def test_minimal_archive_read_only(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);jobs=root/'jobs';run=jobs/'scan-test';pos=run/'position-001';a=pos/'A';off=pos/'OFF';a.mkdir(parents=True);off.mkdir()
   (run/'status.json').write_text(json.dumps({'status':'complete'}))
   im=np.zeros((1080,1920,3),np.uint8)
   cv2.imwrite(str(a/'same-frame.png'),im);cv2.imwrite(str(off/'same-frame.png'),im)
   header={'algorithm':ADAPTIVE_ALGORITHM,'complete':True,'error':0,'laser_id':'A','geometry':{'roi_xyxy':[140,1000,880,1001]}}
   (a/'hardware-frame.json').write_text(json.dumps(header))
   blob=Center(1000,0,2000,10,32800,198,202).encode()+CandidateExtra(1000,0,200,700).encode()+RowDone(1000,1).encode()
   (a/'records.bin').write_bytes(blob)
   m=collect(jobs,root/'output',32)
   self.assertEqual(len(m['samples']),1)
   data=json.loads(next((root/'output').glob('*/data.json')).read_text())
   self.assertEqual(data['steps'][0]['uv'],[[200.0,1000]])
   self.assertEqual(data['expected_records'],[[1000,2000,10,32800,198,202,200,700]])
   self.assertEqual((a/'records.bin').read_bytes(),blob)
   self.assertFalse(data['provenance']['crc_verified'])
 def test_spread_covers_once(self):
  for n in range(30):self.assertEqual(sorted(spread(list(range(n)))),list(range(n)))
if __name__=='__main__':unittest.main()
