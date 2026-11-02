"""Explicit, recorded timing profiles. Optical extraction thresholds are unchanged."""
import json
from pathlib import Path
CONFIG=Path(__file__).with_name('scan-performance.json')
PROFILES={
 'qualified':dict(background_wait=.25,laser_wait=.25,color_wait=.4,motor_settle=.6,rate_pps=40),
 'fast':dict(background_wait=.05,laser_wait=.05,color_wait=.1,motor_settle=.15,rate_pps=120),
}
def settings(name=None):
 if name is None:name=json.loads(CONFIG.read_text())['active'] if CONFIG.exists() else 'qualified'
 if name not in PROFILES:raise ValueError('Unknown scan timing profile')
 return dict(PROFILES[name],name=name)

def full_pixel_check(profile,index,last):
 return profile['name']=='qualified' or index in (0,last)
