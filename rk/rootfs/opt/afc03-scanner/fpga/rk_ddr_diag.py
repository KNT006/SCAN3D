"""Explicit DDR-only bring-up via PCIe BAR0; status is read-only by default.

Requires the DDR candidate signature. Does not control camera/motor/lasers.
Use on RK3576 as root only after temporary candidate programming and PCIe bind.
"""
import argparse,ctypes,fcntl,json,mmap,os,sys,time
from pathlib import Path

KEYS={'hold':0x44520000,'release':0x44520001,'snapshot':0x44520002,'start':0x44520003}
MAGIC=0x44445232

class DDR:
    def __init__(self,bdf):
        if sys.byteorder!='little':raise RuntimeError('Only little-endian RK host supported')
        node=Path('/sys/bus/pci/devices')/bdf
        if (node/'vendor').read_text().strip()!='0x1edb' or (node/'device').read_text().strip()!='0xabcd':
            raise RuntimeError('Unexpected PCIe device; no writes performed')
        base,end,flags=[int(v,16) for v in (node/'resource').read_text().splitlines()[0].split()]
        if not base or end-base+1<0x2100:raise RuntimeError('BAR0 too small')
        # /dev/mem is the existing board register access path. Resolve address
        # from sysfs instead of hard-coding a physical mapping after hotplug.
        self.fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
        try:self.mem=mmap.mmap(self.fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=base+0x2000)
        except BaseException:os.close(self.fd);raise
        if self.read(0)!=MAGIC or self.read(0x18)!=0x00010000:
            self.close();raise RuntimeError('DDR candidate signature/ABI absent; no writes performed')
    def close(self):self.mem.close();os.close(self.fd)
    def read(self,offset):return ctypes.c_uint32.from_buffer(self.mem,offset).value
    def command(self,action):
        # A native aligned 32-bit MMIO store is required for WSTRB=1111;
        # byte-by-byte serialization is not a valid command transaction.
        ctypes.c_uint32.from_buffer(self.mem,8).value=KEYS[action]
        self.read(4) # posted-write readback
    def status(self):
        flags=self.read(4);init=self.read(0x10)
        return dict(flags=hex(flags),bridge_ready=bool(flags&1),pending=bool(flags&2),
                    snapshot_valid=bool(flags&4),timeout=bool(flags&8),reset_held=bool(flags&16),
                    rejected=bool(flags&32),snapshot_seq=self.read(12),
                    init_advisory=dict(pll_locked=bool(init&1),phy_reset_released=bool(init&2),
                    cal_done=bool(init&4),control_ready=bool(init&8),error=(init>>4)&255,step=(init>>12)&255),
                    region_bytes=self.read(0x14))
    def snapshot(self,start=False):
        before=self.status()
        if not before['bridge_ready'] or before['pending'] or before['timeout']:
            raise RuntimeError('Mailbox unavailable; inspect status, hold/release DDR before retrying')
        seq=before['snapshot_seq'];self.command('start' if start else 'snapshot')
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            s=self.status()
            if s['timeout'] or s['reset_held'] or not s['bridge_ready']:
                raise RuntimeError('DDR mailbox lost clock/reset or timed out; hold DDR before retrying')
            if s['snapshot_valid'] and s['snapshot_seq']!=seq:break
            time.sleep(.005)
        else:raise TimeoutError('No new DDR snapshot; no automatic retry')
        words=[self.read(0x40+i*4) for i in range(15)]
        if self.read(12)!=s['snapshot_seq']:raise RuntimeError('Concurrent diagnostic changed snapshot')
        v=words[1]
        return dict(sequence=s['snapshot_seq'],command_result=words[14],busy=bool(v&1),
                    done=bool(v&2),passed=bool(v&4),fault=(v>>3)&15,cal_error=(v>>8)&255,
                    writes=words[2],reads=words[3],first_bad_addr=hex(words[4]),
                    expected=''.join(f'{x:08x}' for x in words[5:9][::-1]),
                    observed=''.join(f'{x:08x}' for x in words[9:13][::-1]))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['status','hold','release','snapshot','test'],nargs='?',default='status')
    p.add_argument('--bdf',default='0000:21:00.0')
    a=p.parse_args();d=DDR(a.bdf)
    try:
        if a.action in ('hold','release'):
            d.command(a.action);print(json.dumps(d.status(),indent=2))
        elif a.action=='status':print(json.dumps(d.status(),indent=2))
        elif a.action=='snapshot':print(json.dumps(d.snapshot(),indent=2))
        else:
            if not d.status()['init_advisory']['control_ready']:raise RuntimeError('DDR initialization not ready')
            snap=d.snapshot(start=True)
            if snap['command_result']:raise RuntimeError('Start rejected: '+json.dumps(snap))
            deadline=time.monotonic()+10
            while not snap['done'] and time.monotonic()<deadline:
                time.sleep(.02);snap=d.snapshot()
            print(json.dumps(snap,indent=2))
            if not snap['done'] or not snap['passed'] or snap['writes']!=8192 or snap['reads']!=8192:
                raise RuntimeError('64 KiB, two-pattern BIST failed/incomplete; no retry issued')
    finally:d.close()

if __name__=='__main__':
    try:
        with open('/run/lock/afc03-ddr-diag.lock','w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            main()
    except (OSError,RuntimeError) as error:
        print(json.dumps({'ok':False,'error':str(error)}),file=sys.stderr)
        sys.exit(2)
