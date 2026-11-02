"""Execute real API route bodies with isolated archives; no hardware/services."""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid
import numpy as np

CODE = Path(__file__).resolve().parents[1] / 'rootfs/opt/afc03-scanner/scan3d'
sys.path.insert(0, str(CODE))
from common import read

class HTTPError(Exception):
    def __init__(self, status, detail=''):
        self.status_code, self.detail = status, detail
        super().__init__(detail)

def routes(environment):
    tree = ast.parse((CODE/'api.py').read_text(encoding='utf-8'))
    install = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'install')
    for node in install.body:
        if isinstance(node, ast.FunctionDef) and node.name in ('details','replay'):
            node.decorator_list = []
            exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])), str(CODE/'api.py'), 'exec'), environment)
    return environment

class HistoryAccessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.saved = self.root/'saved'
        frame = self.saved/'position-000/A'
        frame.mkdir(parents=True)
        for name in ('frame.json','hardware-frame.json','records.bin'):
            (frame/name).write_bytes(b'{}')
        (self.saved/'status.json').write_text('{"status":"complete"}')
        (frame.parent/'status.json').write_text('{"status":"complete"}')
        for role in ('OFF','A','B'):
            (frame.parent/role).mkdir(exist_ok=True)
            (frame.parent/role/'same-frame.png').write_bytes(b'image-presence-only')
        np.savez(self.saved/'combined.npz',xyz=np.array([[1,2,3],[4,6,8]]))
        store = self.root/'work'; store.mkdir()
        self.process = Mock(); self.process.poll.return_value = None
        self.env = routes(dict(Path=Path,json=json,np=np,read=read,Body=lambda *a,**kw:None,
            HTTPException=HTTPError,safejob=lambda name:self.saved,cloud_path=lambda p:p/'combined.npz',
            guard=threading.Lock(),workers={},active=lambda:self.root/'current',
            rpc=lambda d:dict(worker_running=True,last_job='current'),
            acquire_run=Mock(return_value=123),uuid=uuid,store=store,CODE=CODE,
            subprocess=Mock(),os=Mock(environ={}),))
        self.env['subprocess'].Popen.return_value=self.process
        self.request=dict(run='saved',index=0,laser='A',mode='current_scan')

    def submit(self):
        original = Path.read_text
        def text(path,*a,**kw):
            return 'MemAvailable: 1048576 kB\n' if str(path).replace('\\','/') == '/proc/meminfo' else original(path,*a,**kw)
        with patch.object(Path,'read_text',text):
            return self.env['replay'](self.request)

    def test_history_metadata_never_opens_cloud(self):
        with patch.object(np,'load',side_effect=AssertionError('cloud must not be read')):
            d=self.env['details']('saved',include_cloud=False)
        self.assertEqual(d['image_positions'],[0])
        self.assertIsNone(d['count'])
        self.assertFalse(d['model_summary_loaded'])

    def test_default_full_result_summary_unchanged(self):
        d=self.env['details']('saved')
        self.assertEqual(d['count'],2)
        self.assertEqual(d['bounds_mm'],[3,4,5])
        self.assertTrue(d['model_summary_loaded'])

    def test_other_scan_active_allows_one_readonly_replay(self):
        before={str(p):p.read_bytes() for p in self.saved.rglob('*') if p.is_file()}
        result=self.submit()
        self.assertIn(result['id'],self.env['workers'])
        args,kw=self.env['subprocess'].Popen.call_args
        self.assertEqual(args[0][:3],['/usr/bin/nice','-n','10'])
        self.assertEqual(kw['env']['OMP_NUM_THREADS'],'1')
        self.assertEqual(kw['pass_fds'],(123,))
        self.env['os'].close.assert_called_once_with(123)
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.saved.rglob('*') if p.is_file()})
        with self.assertRaises(HTTPError) as e:self.submit()
        self.assertEqual(e.exception.status_code,409)
        self.assertEqual(self.env['subprocess'].Popen.call_count,1)

    def test_active_target_and_helper_target_still_rejected(self):
        for active,helper in ((self.saved,{}),(None,dict(worker_running=True,last_job='saved'))):
            self.env.update(active=lambda:active,rpc=lambda d:helper)
            with self.assertRaises(HTTPError) as e:self.submit()
            self.assertEqual(e.exception.status_code,409)
        self.env['subprocess'].Popen.assert_not_called()

    def test_cleanup_lock_and_incomplete_archive_still_rejected(self):
        self.env['acquire_run'].side_effect=ValueError('archive locked')
        with self.assertRaises(HTTPError) as e:self.submit()
        self.assertEqual(e.exception.status_code,409)
        self.env['subprocess'].Popen.assert_not_called()
        (self.saved/'position-000/A/records.bin').unlink()
        with self.assertRaises(HTTPError) as e:self.submit()
        self.assertEqual(e.exception.status_code,409)

if __name__ == '__main__':unittest.main()
