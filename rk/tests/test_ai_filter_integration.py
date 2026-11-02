"""Isolated API/catalog tests; mocks POSIX lock on Windows, never opens hardware."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

CODE = Path(__file__).resolve().parents[1]/'rootfs/opt/afc03-scanner/scan3d'
sys.path.insert(0, str(CODE))
if os.name == 'nt':
    sys.modules.setdefault('fcntl', types.SimpleNamespace(LOCK_EX=2, LOCK_SH=1, LOCK_NB=4, flock=lambda *args:None))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import ai_filter_tasks as tasks
import ai_filter_worker as worker
import numpy as np


class AiFilterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scan = self.root/'scan-example'
        self.scan.mkdir()
        self.patches = [patch.object(tasks, 'DATA', self.root), patch.object(tasks, 'active', lambda:None),
                        patch.object(tasks, 'job', self.job), patch.dict(os.environ, {'SCAN3D_AI_MODEL':str(self.root/'missing.rknn')})]
        for item in self.patches:item.start()
        self.app = FastAPI()
        tasks.install(self.app, threading.Lock(), lambda:False)
        self.client = TestClient(self.app)

    def job(self, name):
        if name != self.scan.name:raise ValueError('扫描不存在')
        return self.scan

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def test_missing_cloud_is_explained(self):
        value = self.client.get('/api/scan3d/runs/scan-example/ai-filter').json()
        self.assertFalse(value['available'])
        self.assertIn('合并点云', value['reason'])

    def test_missing_model_cannot_start(self):
        (self.scan/'combined.npz').write_bytes(b'source')
        response = self.client.post('/api/scan3d/runs/scan-example/ai-filter')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(list((self.root/'ai-filter-tasks').iterdir()), [])

    def test_prefer_original_archive_without_overwrite(self):
        (self.scan/'review').mkdir()
        (self.scan/'review/combined.npz').write_bytes(b'review')
        (self.scan/'combined.npz').write_bytes(b'original')
        self.assertEqual(tasks.input_cloud(self.scan), self.scan/'combined.npz')
        self.assertEqual((self.scan/'combined.npz').read_bytes(), b'original')

    def task(self, status='complete', run='scan-example'):
        folder = self.root/'ai-filter-tasks'/('a'*32)
        folder.mkdir()
        tasks.write(folder/'request.json', dict(run=run, created=1, source='combined.npz'))
        tasks.write(folder/'state.json', dict(status=status))
        (folder/'output').mkdir()
        (folder/'output/combined.npz').write_bytes(b'filtered')
        return folder

    def test_only_completed_matching_results_become_stl_sources(self):
        folder = self.task(status='failed')
        self.assertEqual(tasks.completed_sources('scan-example'), [])
        tasks.write(folder/'state.json', dict(status='complete'))
        self.assertEqual(len(tasks.completed_sources('scan-example')), 1)
        self.assertEqual(tasks.completed_sources('other-scan'), [])

    def test_incomplete_result_and_path_traversal_denied(self):
        self.task(status='running')
        self.assertEqual(self.client.get('/api/scan3d/ai-filter/'+('a'*32)+'/files/npz').status_code, 409)
        self.assertEqual(self.client.get('/api/scan3d/ai-filter/not-a-task/files/npz').status_code, 400)

    def test_download_exact_separate_output(self):
        self.task()
        response = self.client.get('/api/scan3d/ai-filter/'+('a'*32)+'/files/npz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'filtered')

    def test_worker_preserves_input_and_publishes_preview(self):
        source = self.scan/'combined.npz'
        np.savez(source, xyz=np.ones((3,3),np.float32), rgb=np.ones((3,3),np.uint8), position=np.arange(3))
        original = source.read_bytes()
        folder = self.root/'worker';folder.mkdir()
        tasks.write(folder/'request.json', dict(source_path=str(source), scan_path=str(self.scan), scripts=str(self.root), created=0, model='test'))
        def fake_script(path, run_name):
            args = sys.argv
            output = Path(args[args.index('--output')+1])
            if path.endswith('prepare_manifest.py'):
                output.write_text('{}')
            else:
                output.mkdir()
                with np.load(folder/'source.npz') as data:
                    np.savez(output/'combined.npz', **{k:data[k][:2] for k in data.files})
                tasks.write(output/'report.json', dict(output_accepted=True))
        with patch.object(worker.runpy, 'run_path', side_effect=fake_script), patch.object(sys,'argv',[]), patch.object(sys,'path',sys.path.copy()):
            worker.main(folder)
        self.assertEqual(tasks.read(folder/'state.json')['status'], 'complete')
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual((folder/'output/result-cloud-v1.bin').stat().st_size,16+2*15)
        with np.load(folder/'output/combined.npz') as data:
            np.testing.assert_array_equal(data['position'],[0,1])

    def test_worker_failure_never_publishes_success(self):
        folder = self.root/'failed-worker';folder.mkdir()
        tasks.write(folder/'request.json', dict(source_path=str(self.root/'missing.npz'),created=0))
        with self.assertRaises(FileNotFoundError):worker.main(folder)
        self.assertEqual(tasks.read(folder/'state.json')['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
