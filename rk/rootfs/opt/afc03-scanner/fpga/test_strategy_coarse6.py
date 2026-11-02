import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import strategy_coarse6 as scan

class OrchestrationTests(unittest.TestCase):
    def scenario(self,fail_at=None):
        tmp=tempfile.TemporaryDirectory(dir='/dev/shm');self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        (root/'new-strategy-bundle').mkdir();(root/'new-strategy-bundle/config.json').write_text('{}')
        emitted=10;moves=[];shots=[];commands=[]
        class Bridge:
            def __init__(self,*_):pass
            def send(self,c):commands.append(c);return 'OK'
            def close(self):pass
        def motor(_):return dict(session=7,emitted=emitted)
        def move(b,before,delta,rate,journal,check):
            nonlocal emitted
            self.assertEqual(before['emitted'],emitted);self.assertIn(delta,(53,54));self.assertEqual(rate,40)
            self.assertFalse(journal.exists());journal.write_text('reserved')
            moves.append(delta);emitted+=delta
        def acquire(folder,*a,**kw):
            i=len(shots);shots.append(i);self.assertEqual(kw['expected_motor'],dict(session=7,emitted=10+round(i*3200/60)))
            if i==fail_at:raise RuntimeError('injected capture failure')
            folder.mkdir()
            for label in ('A','B'):
                (folder/label).mkdir();(folder/label/'frame.json').write_text(json.dumps({'angle':{'emitted_after':emitted}}))
            return dict(scan_ready=True,lasers={k:{'retained_points':30} for k in ('A','B')},color={'median_max':100,'saturated_fraction':0})
        with patch.multiple(scan,ROOT=root,MotorBridge=Bridge,motor_state=motor,move_once=move,acquire=acquire,
                compress_position=lambda _:1000,closure=lambda _:{'passed':True}),patch.object(scan.time,'sleep'),patch.object(scan.shutil,'disk_usage',return_value=SimpleNamespace(free=100*1024**3)),patch('builtins.print'),patch.object(scan,'merge',return_value={'A':1,'B':1}) as merge:
            output=root/'run'
            if fail_at is None:
                result=scan.run(output,data_root=root);self.assertTrue(result['passed'])
                self.assertEqual(list(merge.call_args.args[1]),list(range(60)))
            else:
                with self.assertRaises(RuntimeError):scan.run(output,data_root=root)
                self.assertFalse(merge.called)
                self.assertEqual(json.loads((output/'status.json').read_text())['status'],'paused')
        self.assertEqual(commands[-3:],['STOP','LASER OFF','LED 0'])
        return moves,shots
    def test_full_round_and_no_duplicate_endpoint(self):
        moves,shots=self.scenario();self.assertEqual(len(moves),60);self.assertEqual(sum(moves),3200);self.assertEqual(len(shots),61)
    def test_capture_failure_stops_without_extra_move(self):
        moves,shots=self.scenario(fail_at=3);self.assertEqual(len(moves),3);self.assertEqual(len(shots),4)

if __name__=='__main__':unittest.main()
