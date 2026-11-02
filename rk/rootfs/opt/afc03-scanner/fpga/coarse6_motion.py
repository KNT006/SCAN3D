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
    require(type(delta) is int and delta in (53,54) and type(rate) is int and rate in (40,120),'Coarse scan only permits 53 or 54 pulses at 40 or 120 pps')
    started=clock()
    check();write(journal,dict(status='reserved_no_retry',before=before,delta=delta))
    try:
        bridge.send('PULSE_ARM '+str(before['session']))
        ack=bridge.send(f'PULSE_MOVE {delta} {rate} {before["session"]}')
        write(journal,dict(status='dispatched',before=before,delta=delta,ack=ack))
        deadline=clock()+8
        while True:
            check();sleep(.025 if rate==120 else .1)
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
                           physical_motion_verified=False,rate_pps=rate,elapsed_seconds=clock()-started));return after
    except BaseException:
        try:bridge.send('STOP')
        except Exception:pass
        raise
