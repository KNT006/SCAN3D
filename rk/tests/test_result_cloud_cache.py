"""Full result cache revalidation must preserve every coordinate and color."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'rootfs/opt/afc03-scanner/scan3d'))
from cloud_binary import build_cloud,cloud_response

class CloudCacheTest(unittest.TestCase):
    def test_full_bytes_reuse_and_source_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);source=folder/'combined.npz'
            xyz=np.array([[1.5,2,3],[4,5,6]],dtype='<f4')
            rgb=np.array([[1,2,3],[255,0,128]],dtype=np.uint8)
            np.savez_compressed(source,xyz=xyz,rgb=rgb)
            original=source.read_bytes()
            target,meta=build_cloud(folder,source)
            data=target.read_bytes()
            np.testing.assert_array_equal(np.frombuffer(data,dtype='<f4',count=6,offset=16).reshape(-1,3),xyz)
            np.testing.assert_array_equal(np.frombuffer(data,dtype='u1',offset=40).reshape(-1,3),rgb)
            self.assertEqual(source.read_bytes(),original)
            response=cloud_response(target,meta)
            tag=response.headers['etag']
            with patch.object(np,'load',side_effect=AssertionError('cache must avoid decompression')):
                again,info=build_cloud(folder,source)
                self.assertEqual(cloud_response(again,info,tag).status_code,304)
                self.assertEqual(cloud_response(again,info,'W/'+tag).status_code,304)
            xyz[0,0]=10
            np.savez_compressed(source,xyz=xyz,rgb=rgb)
            target,meta=build_cloud(folder,source)
            updated=cloud_response(target,meta,tag)
            self.assertEqual(updated.status_code,200)
            self.assertNotEqual(updated.headers['etag'],tag)
            self.assertNotEqual(target.read_bytes(),data)

    def test_corrupt_binary_is_rebuilt(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);source=folder/'combined.npz'
            np.savez(source,xyz=np.zeros((1,3)),rgb=np.ones((1,3),dtype=np.uint8))
            target,meta=build_cloud(folder,source)
            target.write_bytes(b'bad')
            target,meta=build_cloud(folder,source)
            self.assertEqual(target.stat().st_size,31)
            self.assertEqual(cloud_response(target,meta,'"stale"').status_code,200)

if __name__=='__main__':unittest.main()
