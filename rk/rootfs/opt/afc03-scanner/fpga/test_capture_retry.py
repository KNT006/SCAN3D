import copy,tempfile,unittest
from pathlib import Path
from capture_retry import retryable,capture_with_retry

def dropped():
    return dict(passed=False,stage='wait_raw_marker',token=10,cleanup_errors=[],
        cleanup_background={'quiescent':True},cleanup_probe_idle=True,cleanup_camera_released=True,
        camera_arm=dict(token=10,generation=1,stream_id='s'),
        camera_observed=dict(token=10,generation=1,stream_id='s',state='expired',error='capture_timeout'),
        fpga_capture=dict(token=10,done=True,fault=0,fault_present=False,rejected=False,waiting=False,active=False))

class RetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'A';self.calls=0
    def acquire(self,reports):
        def shot(path):
            path.mkdir();(path/'audit').write_text(str(self.calls));self.calls+=1
            return copy.deepcopy(reports[self.calls-1])
        return shot
    def test_lost_frame_new_token(self):
        result=capture_with_retry(self.path,self.acquire([dropped(),dict(passed=True,token=11,camera_arm={'stream_id':'s'})]),lambda:None)
        self.assertTrue(result['passed']);self.assertEqual(self.calls,2)
        self.assertEqual((self.path.with_name('A-rejected-01')/'audit').read_text(),'0')
    def test_second_failure_never_repeats(self):
        second=dropped();second['token']=11
        result=capture_with_retry(self.path,self.acquire([dropped(),second]),lambda:None)
        self.assertFalse(result['passed']);self.assertEqual(self.calls,2)
    def test_unsafe_failures_rejected(self):
        for key,value in [('cleanup_errors',['drain failed']),('requires_ddr_recovery',True),('stage','arm_background')]:
            r=dropped();r[key]=value;self.assertFalse(retryable(r))
        for key,value in [('done',False),('fault',1),('rejected',True),('active',True),('token',99)]:
            r=dropped();r['fpga_capture'][key]=value;self.assertFalse(retryable(r))
    def test_restarted_stream_rejected(self):
        with self.assertRaises(Exception):capture_with_retry(self.path,self.acquire([dropped(),dict(passed=True,token=11,camera_arm={'stream_id':'new'})]),lambda:None)
    def test_same_token_rejected(self):
        with self.assertRaises(Exception):capture_with_retry(self.path,self.acquire([dropped(),dict(passed=True,token=10,camera_arm={'stream_id':'s'})]),lambda:None)
    def test_changed_position_prevents_retry(self):
        checks=0
        def check():
            nonlocal checks
            checks+=1
            if checks==2:raise RuntimeError('position changed')
        with self.assertRaises(RuntimeError):capture_with_retry(self.path,self.acquire([dropped()]),check)
        self.assertEqual(self.calls,1)

if __name__=='__main__':unittest.main()
