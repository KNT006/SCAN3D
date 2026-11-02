"""Stationary lighting controls."""
import argparse,json,sys
sys.path.insert(0,'/opt/afc03-motor')
from rk_motor import MotorBridge
p=argparse.ArgumentParser();p.add_argument('action',choices=['status','laser','led']);p.add_argument('value',nargs='?');a=p.parse_args()
if a.action=='laser' and a.value not in ['OFF','A','B','BOTH']:p.error('laser requires OFF/A/B/BOTH')
if a.action=='led' and (a.value is None or not a.value.isdigit() or not 0<=int(a.value)<=32):p.error('led requires 0..32')
b=MotorBridge('/run/afc03-controller/control.sock')
try:
 identity=b.send('PING')
 if 'rk_control_v1' not in identity:raise RuntimeError('Unexpected control service')
 out=[identity]
 if a.action=='status':out += [b.send(c) for c in ['PULSE_STATE','ENSTATE','LEDSTATE','LASERSTATE']]
 else:out.append(b.send(('LASER ' if a.action=='laser' else 'LED ')+a.value))
 print(json.dumps(out))
finally:b.close()
