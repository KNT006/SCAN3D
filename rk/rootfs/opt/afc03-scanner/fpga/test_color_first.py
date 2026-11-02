"""Acquisition orchestration with fake hardware; never opens a real device."""
import io
import json
import sys
import tempfile
import threading
import types
import unittest
import numpy as np
from pathlib import Path
from unittest.mock import patch

if sys.platform == 'win32':
    sys.modules.setdefault('fcntl', types.SimpleNamespace(flock=lambda *a: None, LOCK_EX=1, LOCK_NB=2))
import stationary_strategy as scan


class ColorFirstTests(unittest.TestCase):
    def scenario(self, overlap=True, color=True, fail=None, color_cache=False):
        events=[];shots=[];state=dict(gain=20,laser='OFF',led=0)
        cpu_started=threading.Event();b_started=threading.Event()
        original_read=Path.read_text
        def read(path,*a,**kw):
            if str(path).replace('\\','/').endswith('/proc/sys/kernel/random/boot_id'):return 'test-boot'
            if path.name=='name':return 'milianke'
            return original_read(path,*a,**kw)
        class Bridge:
            def __init__(self,*a):pass
            def send(self,command):
                events.append(command)
                if command=='PING':return 'OK rk_control_v1 test'
                if command=='PULSE_STATE':return 'OK STATE session=1 emitted=0 moving=0 pending=0 count_known=1 armed=0 fault=none'
                if command=='LASERSTATE':return 'A=%d B=%d'%(state['laser']=='A',state['laser']=='B')
                if command.startswith('LASER '):state['laser']=command.split()[1]
                if command.startswith('LED '):state['led']=int(command.split()[1])
                return 'OK'
            def close(self):pass
        def set_gain(args,**kw):
            state['gain']=int(args[-1].split('=')[-1]);events.append('gain:'+str(state['gain']))
        def gain(*a,**kw):
            if fail=='gain' and 'COLOR' in shots and state['gain']==20:return 'gain: 50'
            return 'gain: '+str(state['gain'])
        def capture(probe,client,api,target,*args,**kwargs):
            label=target.name;shots.append(label);events.append('shot:'+label);target.mkdir()
            self.assertEqual(client.color_bank,color_cache and label=='COLOR')
            self.assertEqual(state['gain'],50 if label=='COLOR' else 20)
            self.assertEqual(state['led'],8 if label=='COLOR' else 0)
            self.assertEqual(state['laser'],label if label in ('A','B') else 'OFF')
            if fail==label:raise RuntimeError('injected '+label)
            return dict(passed=True,camera_arm={'stream_id':'other' if fail=='stream' and label=='OFF' else 's'},
                        background=dict(generation=len(shots),source_frame=len(shots)))
        def receive(job,snap,context,angle,bg,on,*args,**kwargs):
            label=context['laser_id'];events.append('extract:'+label)
            self.assertEqual(bg.generation,2 if color else 1) # OFF, never COLOR
            self.assertEqual(context['background_generation'],bg.generation)
            if label=='B' and color:
                self.assertTrue(cpu_started.wait(3),'A CPU work was not started before B extraction')
                b_started.set()
            callback=kwargs['during_last']
            self.assertEqual(callback is not None,overlap and label=='A')
            if callback:callback()
            return types.SimpleNamespace(header={'algorithm':'adaptive','laser_id':label}),{}
        rgb=object()
        def client(*a,**kw):
            return types.SimpleNamespace(color_bank=kw.get('color_bank',False),snapshot=lambda:types.SimpleNamespace(
                active=True,background=types.SimpleNamespace(generation=99 if fail=='cache' else 1,source_frame=1)))
        def load(folder):events.append('decode:COLOR');return rgb
        def process(frame,adapter,folder,image):
            self.assertIs(image,rgb);cpu_started.set()
            if not b_started.wait(3):raise RuntimeError('B extraction did not overlap A CPU work')
            if fail=='cpu':raise RuntimeError('injected cpu')
            return ('arrays','report','header',.01)
        def finish(*args,**kwargs):
            report=args[2]
            self.assertEqual(bool(kwargs['prepared']),color)
            self.assertIs(kwargs['rgb'],rgb if color else None)
            report['passed']=True
            return report
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);bundle=root/'bundle';bundle.mkdir()
            (bundle/'config.json').write_text(json.dumps(dict(scan_roi=[0,0,1080,1920],gain_geometry=20,pulses_per_revolution=3200)))
            output=root/'angle'
            motor=types.SimpleNamespace(MotorBridge=Bridge)
            job=types.SimpleNamespace(spatial_candidates=color,new_stripes=True,capture_overlap=overlap,close=lambda:None,transport='test')
            with patch.dict(sys.modules,{'rk_motor':motor}),patch.object(Path,'read_text',read),\
                 patch.object(Path,'glob',return_value=[Path('/sys/class/video4linux/video0/name')]),\
                 patch.object(scan,'open',side_effect=lambda *a,**k:io.StringIO(),create=True),\
                 patch.object(scan.fcntl,'flock'),patch.object(scan.time,'sleep',side_effect=lambda t:events.append('wait:'+str(t))),\
                 patch.object(scan.subprocess,'run',set_gain),patch.object(scan.subprocess,'check_output',gain),\
                 patch.multiple(scan,scanner_idle=lambda *a:None,PointCloudAdapter=lambda *a:types.SimpleNamespace(hashes={}),
                    Probe=lambda:types.SimpleNamespace(close=lambda:None),BackgroundMMIO=lambda *a:types.SimpleNamespace(read=None,write=None),
                    CameraAPI=lambda:types.SimpleNamespace(request=lambda *a:{'stream_id':'s'}),JobClient=lambda *a:job,
                    RoleClient=client,BackgroundIdentity=lambda **kw:types.SimpleNamespace(**kw),
                    capture=capture,receive_full_roi=receive,load_color=load,process_rgb_frame=process,finish_position=finish):
                if fail:
                    with self.assertRaises(Exception):scan.acquire(output,bundle,color_led=8 if color else None,scan_lock_owned=True,timing_profile='qualified',color_cache=color_cache)
                    self.assertEqual(json.loads((output/'status.json').read_text())['status'],'failed')
                else:
                    result=scan.acquire(output,bundle,color_led=8 if color else None,scan_lock_owned=True,timing_profile='qualified',color_cache=color_cache)
                    self.assertTrue(result['passed'])
                    self.assertEqual(result['color_cache']['independent'],color_cache)
                    if color_cache:self.assertTrue(result['color_cache']['verified_after_lasers'])
                    self.assertEqual(result['capture_order'],['COLOR','OFF','A','B'] if color else ['OFF','A','B'])
        self.assertEqual(state['laser'],'OFF');self.assertEqual(state['led'],0)
        if fail in ('COLOR','gain'):self.assertNotIn('OFF',shots)
        if fail=='stream':self.assertNotIn('A',shots)
        if not fail:
            self.assertEqual(shots,['COLOR','OFF','A','B'] if color else ['OFF','A','B'])
            if color:
                start=events.index('shot:COLOR');end=events.index('shot:OFF')
                self.assertLess(events.index('LED 0',start),end)
                self.assertLess(events.index('gain:20',start),end)
                self.assertLess(events.index('wait:0.25',start),end)

    def test_overlap_and_background_identity(self):self.scenario()
    def test_without_fpga_overlap(self):self.scenario(overlap=False)
    def test_legacy_without_color(self):self.scenario(color=False)
    def test_color_failure_cleanup(self):self.scenario(fail='COLOR')
    def test_gain_mismatch_prevents_off(self):self.scenario(fail='gain')
    def test_stream_change_prevents_lasers(self):self.scenario(fail='stream')
    def test_worker_error_propagates(self):self.scenario(fail='cpu')
    def test_independent_bank_routing(self):self.scenario(color_cache=True)
    def test_overwritten_color_rejected(self):self.scenario(color_cache=True,fail='cache')

    def test_color_bank_requires_supported_firmware(self):
        from role_client import RoleClient,DiagnosticError,MAGIC,ABI
        writes=[];registers={0x2500:MAGIC,0x2508:ABI}
        client=RoleClient(lambda a:registers.get(a,0),lambda *a:writes.append(a),role=0,color_bank=True)
        self.assertEqual(client.base,0x2500)
        with self.assertRaises(DiagnosticError):RoleClient(lambda a:0,lambda *a:writes.append(a),role=0,color_bank=True)
        with self.assertRaises(ValueError):RoleClient(lambda a:0,lambda *a:writes.append(a),role=1,color_bank=True)
        self.assertEqual(writes,[])

    def test_prepared_a_matches_serial_finish(self):
        """Cached A must be consumed once; all point fields and RGB stay identical."""
        from row_results import ADAPTIVE_ALGORITHM
        import rgb_adaptive_strategy
        rgb=np.full((1920,1080,3),100,dtype=np.uint8)
        arrays={'uv':np.array([[10.,20.]]),'axis_frame_mm':np.array([[1.,2.,3.]])}
        strategy={'turntable_filter':{},'test':'unchanged'}
        header={'algorithm':ADAPTIVE_ALGORITHM}
        frame=types.SimpleNamespace(header=header,payload=b'records',rows=[])
        captured=[(label,frame,{},.1,.2) for label in ('A','B')]
        reports=[];points=[]
        with tempfile.TemporaryDirectory() as temp:
            profile=dict(version=1,led=8,gain=50,
                         matrix_rgb=[[1,0,0,0],[0,1,0,0],[0,0,1,0]])
            (Path(temp)/'color_profile.json').write_text(json.dumps(profile))
            for cached in (False,True):
                folder=Path(temp)/str(cached)
                for label in ('A','B'):(folder/label).mkdir(parents=True)
                report={'lasers':{}}
                with patch.object(rgb_adaptive_strategy,'process_frame',return_value=(arrays,strategy,header)) as process,\
                     patch.object(scan,'load_color',side_effect=AssertionError('COLOR decoded again')):
                    scan.finish_position(folder,Path(temp),report,captured,True,False,
                        {'background':{'source_frame':7}},.3,8,'s',scan.time.perf_counter(),
                        adapter=object(),rgb=rgb,prepared={'A':(arrays,strategy,header,.01)} if cached else None)
                    self.assertEqual(process.call_count,1 if cached else 2)
                reports.append(report)
                points.append({label:dict(np.load(folder/label/'points.npz')) for label in ('A','B')})
        self.assertEqual(reports[0]['color'],reports[1]['color'])
        for label in ('A','B'):
            self.assertEqual(reports[0]['lasers'][label]['strategy'],reports[1]['lasers'][label]['strategy'])
            for field in points[0][label]:np.testing.assert_array_equal(points[0][label][field],points[1][label][field])


if __name__=='__main__':unittest.main()
