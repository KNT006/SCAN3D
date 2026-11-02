from pathlib import Path
import sys,json,unittest
import numpy as np
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from image_colors import rigid,raster,weighted_quantile,ROOT
from segment_colors import partition

class PhotoTests(unittest.TestCase):
 def test_rigid_and_occlusion(self):
  x=np.random.default_rng(2).normal(size=(30,3));r=cv2.Rodrigues(np.array([.3,-.8,.1]))[0];t=np.array([4,5,220])
  rr,tt=rigid(x[:15],(x@r+t)[:15]);np.testing.assert_allclose(x[15:]@rr+tt,(x@r+t)[15:],atol=1e-10)
  uv=np.array([[0.,0.],[9.,0.],[0.,9.]]*2);z=np.array([3.,3.,3.,6.,6.,6.]);f=np.array([[3,4,5],[0,1,2]])
  d=raster(uv,z,f,10,10);self.assertAlmostEqual(d[2,2],3);self.assertGreater(d[9,9],1e8)
  np.testing.assert_array_equal(d,raster(uv,z,f[::-1].copy(),10,10))

 def test_fusion_rejects_oblique_outlier(self):
  c=np.array([[30.,50.],[32.,51.],[250.,200.]]);w=np.array([[1.,1.],[1.,1.],[.01,.01]])
  np.testing.assert_array_equal(weighted_quantile(c,w,.5),[32.,51.])

 def test_photos_and_labels(self):
  catalog=json.loads((ROOT/'public/museum/catalog.json').read_text(encoding='utf8'))
  for a in catalog:
   r=json.loads((ROOT/'public/museum'/a['id']/'rgb-segmentation/report.json').read_text(encoding='utf8'))
   p=r['source']['photo_evidence'];self.assertGreaterEqual(len(p['views']),40)
   self.assertLess(p['held_out_projection_max_p95_px'],.25)
   z=np.load(ROOT/'assets'/f'{a["id"]}-photo-evidence.npz')
   self.assertTrue(np.isfinite(z['colors']).all());self.assertTrue(np.all(z['observations'][z['valid']]>=3))
   self.assertNotEqual(a['color_segmentation']['version'],a['previous_color_segmentation']['version'])
   # No inferred flat base becomes a measured color region.
   folder=ROOT/'public/museum'/a['id'];v=np.fromfile(folder/'vertices.bin','<f4').reshape(-1,3);f=np.fromfile(folder/'faces.bin','<u4').reshape(-1,3)
   c=v[f].mean(1);normal=np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]])
   cap=(c[:,1]<.04)&(np.abs(normal[:,1])/np.maximum(np.linalg.norm(normal,axis=1),1e-8)>.97)
   labels=np.fromfile(folder/'rgb-segmentation/face-regions.bin',np.uint8);self.assertTrue(np.all(labels[cap]==7))

if __name__=='__main__':unittest.main()
