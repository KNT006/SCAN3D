"""Production flow display must agree with the immutable scan archive."""
from pathlib import Path
import sys,unittest
import numpy as np

root=Path(__file__).resolve().parents[1]/'rootfs/opt/afc03-scanner'
sys.path[:0]=[str(root/'scan3d'),str(root/'fpga')]
from production_replay import stages_from_archive,VERSION,archive_mode


class ProductionReplayTest(unittest.TestCase):
 def setUp(self):
  self.records=[dict(_id=y,x=100.,y=y,k=100,peak32=3200,lo=98,hi=102,width=5,
   signalmax=100,threshold=40,height_mm=0.,radius_mm=5.,new_kept=True,
   final_reason='保留：固定40主支路') for y in range(9)]
  self.uv=np.array([[100.,y] for y in range(9)])
  self.report=dict(version=VERSION,candidates=9,after_ground=9,after_geometry=9,
   secondary_removed=0,near_peak_removed=0,retained_points=9,long_track_deleted=0)

 def test_version_dispatch(self):
  self.assertEqual(archive_mode({'version':VERSION},{}),'production')
  self.assertEqual(archive_mode({'version':'fpga-spatial25-rk-localrgb100-160-protected-v1'},{}),'historical')
  with self.assertRaises(ValueError):archive_mode({'version':'unknown'}, {})

 def test_final_coordinates_and_input_immutable(self):
  before=[dict(r) for r in self.records]
  stages=stages_from_archive(self.records,self.report,self.uv)
  np.testing.assert_array_equal(stages[-1]['uv'],self.uv)
  self.assertEqual(self.records,before)

 def test_ground_before_competing_candidates(self):
  self.records.append(dict(self.records[4],_id=99,x=110.,height_mm=-90.,new_kept=False,final_reason='第一步：转盘高度剔除'))
  self.report['candidates']=10
  stages=stages_from_archive(self.records,self.report,self.uv)
  self.assertEqual([s['count'] for s in stages[:3]],[10,9,9])

 def test_changed_saved_cloud_rejected(self):
  bad=self.uv.copy();bad[0,0]+=.01
  with self.assertRaises(ValueError):stages_from_archive(self.records,self.report,bad)

 def test_old_version_rejected(self):
  self.report['version']='legacy'
  with self.assertRaises(ValueError):stages_from_archive(self.records,self.report,self.uv)

 def test_inconsistent_counts_rejected(self):
  self.report['after_ground']=8
  with self.assertRaises(ValueError):stages_from_archive(self.records,self.report,self.uv)

 def test_long_track_cannot_delete(self):
  self.report['long_track_deleted']=1
  with self.assertRaises(ValueError):stages_from_archive(self.records,self.report,self.uv)

if __name__=='__main__':unittest.main()
