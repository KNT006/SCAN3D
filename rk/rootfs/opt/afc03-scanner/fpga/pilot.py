"""Finite 0.45-degree pilot. Motion has a write-ahead journal, never auto-resumes."""
import argparse,fcntl,json,os,signal,shutil,sys,time
from pathlib import Path
from contextlib import ExitStack
import numpy as np
from stationary import acquire,motor_state,write,PORT,ROOT
from row_results import require
from rk_motor import MotorBridge

def move_once(bridge,before,delta,rate,journal,check,clock=time.monotonic,sleep=time.sleep):
    require(not journal.exists(),'Motion already journaled; never replay')
    require(type(delta) is int and delta==4 and rate==40,'Pilot only permits four pulses at 40 pps')
    check();write(journal,dict(status='reserved_no_retry',before=before,delta=delta))
    try:
        bridge.send('PULSE_ARM '+str(before['session']))
        ack=bridge.send(f'PULSE_MOVE {delta} {rate} {before["session"]}')
        write(journal,dict(status='dispatched',before=before,delta=delta,ack=ack))
        deadline=clock()+8
        while True:
            check();sleep(.1)
            fields=dict(x.split('=',1) for x in bridge.send('PULSE_STATE').split()[2:] if '=' in x)
            require(int(fields['session'])==before['session'] and int(fields['count_known'])==1,
                    'Controller reset or position unknown; never retry')
            require(fields['fault']=='none','Motor fault: '+fields['fault'])
            if int(fields['moving'])==0:break
            require(clock()<deadline,'Motion timeout; never retry')
        require(int(fields['pending'])==0 and int(fields['emitted'])==before['emitted']+delta,
                'Completed pulse count differs from target')
        bridge.send('PULSE_DISARM');after=motor_state(bridge)
        write(journal,dict(status='pulse_sequence_complete',before=before,after=after,delta=delta,
                           physical_motion_verified=False));return after
    except BaseException:
        try:bridge.send('STOP')
        except Exception:pass
        raise

def run(output,intervals):
    require(type(intervals)is int and 1<=intervals<=13,'Pilot limited to at most 5.85 degrees')
    output.mkdir(parents=True,exist_ok=False)
    state=dict(status='running',pid=os.getpid(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
               mode='pilot',points_are_static_profile=False,passed=False,lasers={},positions=[],
               motor_operations=True,commanded_step_deg=.45,planned_intervals=intervals,
               physical_motion_verified=False,absolute_accuracy_validated=False)
    write(output/'status.json',state);start=time.perf_counter()
    def check():
        require(not(output/'STOP').exists(),'Operator stop')
        require(shutil.disk_usage(output).free>1024**3,'Disk space below reserve')
    try:
        with ExitStack() as stack:
            lock=stack.enter_context(open('/run/lock/afc03-fpga-scan.lock','a'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            b=MotorBridge(PORT)
            try:initial=motor_state(b);require(b.send('PING').split()[:2]==['OK','rk_control_v1'],'Wrong controller')
            finally:b.close()
            origin=initial['emitted'];session=initial['session']
            for index in range(intervals+1):
                check()
                if index:
                    b=MotorBridge(PORT)
                    try:
                        before=motor_state(b)
                        require(before['session']==session and before['emitted']==origin+4*(index-1),'Position or session changed')
                        move_once(b,before,4,40,output/f'move-{index:03d}.json',check)
                    finally:b.close()
                    time.sleep(.6)
                folder=output/f'position-{index:03d}'
                report=acquire(folder,ROOT/'bundle',False,zero_pulses=origin,
                    expected_motor=dict(session=session,emitted=origin+4*index),
                    external_check=check,scan_lock_owned=True)
                for label in ('A','B'):
                    header=json.loads((folder/label/'frame.json').read_text())
                    require(header['angle']['emitted_after']==origin+4*index,'Capture angle differs from position')
                state['positions'].append(dict(index=index,commanded_degrees=index*.45,report=report))
                state['lasers']=report['lasers'];state['last_index']=index;write(output/'status.json',state)
                require(report['scan_ready'],'Insufficient static points at position '+str(index))
            for label in ('A','B'):
                xyz=[]
                for index in range(intervals+1):
                    with np.load(output/f'position-{index:03d}'/label/'points.npz',allow_pickle=False) as f:xyz.append(f['axis_frame_mm'])
                (output/label).mkdir();np.savez_compressed(output/label/'points.npz',axis_frame_mm=np.concatenate(xyz))
            state.update(status='complete',passed=True,scan_ready=False,
                         scan_ready_scope='Awaiting physical motion and object stability confirmation')
    except BaseException as e:
        state.update(status='failed',error=type(e).__name__+': '+str(e));raise
    finally:
        try:
            b=MotorBridge(PORT)
            try:
                b.send('STOP');b.send('LASER OFF');b.send('LED 0');state['final_motor']=motor_state(b)
            finally:b.close()
        except Exception as e:state['cleanup_error']=str(e);state.update(status='failed',passed=False)
        state['elapsed_seconds']=time.perf_counter()-start;write(output/'status.json',state)
    return state
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--intervals',type=int,default=13);a=p.parse_args()
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    print(json.dumps(run(a.output,a.intervals),indent=2))
