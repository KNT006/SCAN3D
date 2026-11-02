"""No hardware calls: validate non-replay and position guards using a fake controller."""
import tempfile,unittest,json
from pathlib import Path
from pilot import move_once

class Bridge:
    def __init__(self,mode='ok'):self.commands=[];self.mode=mode;self.stopped=False
    def send(self,command):
        self.commands.append(command)
        if command.startswith('PULSE_MOVE') and self.mode=='lost_ack':raise TimeoutError('lost ack')
        if command=='PULSE_DISARM':self.stopped=True
        if command=='PULSE_STATE':
            return 'OK PULSE_STATE session={} emitted={} moving=0 pending=0 count_known=1 armed={} fault={}'.format(
                8 if self.mode=='reset' else 7,103 if self.mode=='short' else 104,
                0 if self.stopped else 1,'stopped' if self.stopped else 'none')
        return 'OK'

class MotionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.journal=Path(self.tmp.name)/'move.json';self.before=dict(session=7,emitted=100)
    def move(self,b,check=lambda:None):
        return move_once(b,self.before,4,40,self.journal,check,sleep=lambda _:None)
    def test_success_and_no_replay(self):
        b=Bridge();self.assertEqual(self.move(b)['emitted'],104)
        self.assertEqual(json.loads(self.journal.read_text())['status'],'pulse_sequence_complete')
        with self.assertRaises(Exception):self.move(b)
        self.assertEqual(sum(c.startswith('PULSE_MOVE') for c in b.commands),1)
    def test_lost_ack_is_never_retried(self):
        b=Bridge('lost_ack')
        with self.assertRaises(TimeoutError):self.move(b)
        self.assertEqual(b.commands[-1],'STOP')
        with self.assertRaises(Exception):self.move(b)
        self.assertEqual(sum(c.startswith('PULSE_MOVE') for c in b.commands),1)
    def test_wrong_completed_count_rejected(self):
        b=Bridge('short')
        with self.assertRaises(Exception):self.move(b)
        self.assertEqual(b.commands[-1],'STOP')
    def test_controller_reset_rejected(self):
        b=Bridge('reset')
        with self.assertRaises(Exception):self.move(b)
        self.assertEqual(b.commands[-1],'STOP')
    def test_cancel_before_dispatch(self):
        b=Bridge()
        def stop():raise RuntimeError('operator stop')
        with self.assertRaises(RuntimeError):self.move(b,stop)
        self.assertFalse(self.journal.exists());self.assertEqual(b.commands,[])

if __name__=='__main__':unittest.main()
