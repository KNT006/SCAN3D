"""Regression cases: shade merging, tiny dark details, missing evidence, sources."""
from pathlib import Path
import sys, json, hashlib, unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from segment_colors import partition, PUBLIC, ROOT, EXPECTED

class ColorSegmentationTests(unittest.TestCase):
    def test_shading_details_and_unknown(self):
        n=41;yy,xx=np.mgrid[:n,:n]
        centers=np.c_[xx.ravel()*.3,yy.ravel()*.3,np.zeros(n*n)].astype(np.float32)
        colors=np.tile([130,140,150],(n*n,1)).astype(np.float32)
        colors[xx.ravel()>20]=[120,129,139]
        mouth=(xx.ravel()>10)&(xx.ravel()<30)&(yy.ravel()>28)
        colors[mouth]=[185,100,40]
        eye=((xx.ravel()-14)**2+(yy.ravel()-15)**2)<5
        colors[eye]=[30,30,32]
        valid=np.ones(n*n,bool);valid[yy.ravel()==0]=False
        colors[~valid]=[255,0,255] # must never influence a color prototype
        adj=np.full((n*n,3),-1,np.int32)
        for y in range(n):
            for x in range(n):
                i=y*n+x
                if x+1<n:adj[i,0]=i+1
                if y+1<n:adj[i,1]=i+n
                if x>0:adj[i,2]=i-1
        labels,_=partition(colors,valid,np.full(n*n,.09),adj,centers)
        body=int(labels[6*n+6])
        self.assertEqual(body,int(labels[6*n+32]))
        self.assertNotEqual(body,int(np.bincount(labels[mouth]).argmax()))
        self.assertNotEqual(body,int(np.bincount(labels[eye]).argmax()))
        self.assertTrue(np.all(labels[~valid]==7))
        self.assertTrue(np.all(labels[valid]<7))

    def test_asset_evidence_and_geometry(self):
        for item in json.loads((PUBLIC/'catalog.json').read_text(encoding='utf8')):
            folder=PUBLIC/item['id'];s=item['color_segmentation']
            labels=np.fromfile(folder/s['labels_file'].split('?')[0],'u1')
            old=np.fromfile(folder/'face-regions.bin','u1')
            report=json.loads((folder/'rgb-segmentation/report.json').read_text(encoding='utf8'))
            cache=np.load(ROOT/'assets'/f'{item["id"]}-measured-face-colors.npz')
            self.assertEqual(len(labels),item['faces']);self.assertEqual(len(old),item['faces'])
            evidence=cache['valid'].copy()
            if 'photo_evidence' in report['source']:
                photo=np.load(ROOT/'assets'/f'{item["id"]}-photo-evidence.npz');evidence|=photo['valid']
            self.assertTrue(np.all(labels<8));self.assertTrue(np.all(labels[~evidence]==7))
            self.assertEqual(report['source']['source_scan'],item['source_scan'])
            self.assertEqual(report['source']['source_cloud_sha256'],EXPECTED[item['id']])
            self.assertEqual(hashlib.sha256((folder/'vertices.bin').read_bytes()+(folder/'faces.bin').read_bytes()).hexdigest(),item['geometry_key'])
            self.assertEqual(len(s['regions']),8);self.assertEqual(len(s['palette']),8)
            self.assertEqual(sum(g['faces'] for g in report['regions'])+report['unknown_faces'],item['faces'])

if __name__=='__main__':unittest.main()
