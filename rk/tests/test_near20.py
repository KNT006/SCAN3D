"""Hardware-free boundary checks for the deployed near-peak rule."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'rootfs/opt/afc03-scanner/fpga'))
from near_peak_policy import decisions
class NearPeakTest(unittest.TestCase):
 def sample(self,gap,signal,neighbors=True):
  rs=[dict(_id=0,y=10,x=100,signalmax=100,new_kept=True),dict(_id=1,y=10,x=100+gap,signalmax=signal,new_kept=True)]
  if neighbors:rs.extend(dict(_id=y+30,y=y,x=100,signalmax=100,new_kept=True) for y in range(6,15) if y!=10)
  return decisions(rs)[0]
 def test_close_weak(self):self.assertIn(1,self.sample(19.99,60))
 def test_exact_20_preserved(self):self.assertNotIn(1,self.sample(20,60))
 def test_similar_brightness_preserved(self):self.assertNotIn(1,self.sample(19.99,60.001))
 def test_unstable_anchor_preserved(self):self.assertNotIn(1,self.sample(19.99,50,False))
 def test_single_preserved(self):self.assertFalse(decisions([dict(_id=0,y=10,x=100,signalmax=100,new_kept=True)])[0])
if __name__=='__main__':unittest.main()
