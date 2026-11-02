"""BGC1 diagnostic client. No device is opened and no operation runs on import.

The caller supplies aligned BAR-relative read32/write32 functions. This is not
the production scanner API or FPGA result DMA. A firmware identity check is
mandatory before the first write, so this client cannot drive the current RGB
probe-only bitstream by accident.
"""
from dataclasses import dataclass
import struct,time

BASE=0x2200
MAGIC=0x42474331
ABI=0x00020000
COMMANDS={'SNAP':1,'ARM':2,'CANCEL':3,'READ16':4}

class DiagnosticError(RuntimeError):pass

class CommandRejected(DiagnosticError):
    """A matched, complete reply explicitly says no command was accepted."""
    def __init__(self,result):
        self.result=result
        super().__init__('Hardware diagnostic result '+str(result))

@dataclass(frozen=True)
class BackgroundIdentity:
    epoch:int
    pixels:int
    byte_count:int
    calibration:int
    geometry:int
    generation:int
    source_frame:int

@dataclass(frozen=True)
class Reply:
    opcode:int
    request_id:int
    result:int
    flags:int
    background:BackgroundIdentity
    event_error:int
    event_source_error:int
    event_ok:bool
    event_committed:bool
    event_seen:bool
    event_token:int
    event_epoch:int
    data:bytes

    @classmethod
    def decode(cls,words):
        if len(words)!=16 or any(type(w)!=int or not 0<=w<2**32 for w in words):
            raise DiagnosticError('Malformed response words')
        flags=words[0]>>16
        if flags&~0xff or words[9]&~0x7ffff:
            raise DiagnosticError('Reserved response bits are nonzero')
        return cls(words[0]&255,words[1],(words[0]>>8)&255,flags,
            BackgroundIdentity(words[2],words[3],words[4],*words[5:9]),
            words[9]&255,(words[9]>>8)&255,bool(words[9]&(1<<16)),
            bool(words[9]&(1<<17)),bool(words[9]&(1<<18)),words[10],words[11],
            struct.pack('<4I',*words[12:16]))

    @property
    def active(self):return bool(self.flags&2)

    @property
    def busy(self):return bool(self.flags&1)

def uint(value,bits,label):
    if type(value)!=int or not 0<=value<1<<bits:
        raise ValueError(label+' is outside its unsigned range')
    return value

class RoleClient:
    def __init__(self,read32,write32,*,role,timeout=2.0,poll_seconds=.001,first_request_id=1,color_bank=False):
        assert role in (0,1,2)
        if color_bank and role!=0:raise ValueError('COLOR bank requires lasers OFF')
        self.role=role;self.base=0x2200 if role==0 else 0x2300
        if color_bank:self.base=0x2500
        self.read32=read32;self.write32=write32
        self.timeout=timeout;self.poll_seconds=poll_seconds
        self.next_id=uint(first_request_id,32,'request id')
        if self.next_id==0:raise ValueError('request id must be nonzero')
        self.verify()
        # A fresh Python process must not mistake the previous process's
        # reply for its own while a posted command write is still pending.
        if self.read32(self.base+4)&2:
            self.next_id=max(self.next_id,self.read32(self.base+0x84)+1)

    def verify(self):
        if self.read32(self.base)!=MAGIC or self.read32(self.base+8)!=ABI:
            raise DiagnosticError('BGC1 firmware/ABI not present; no writes performed')

    def command(self,name,registers=None):
        opcode=COMMANDS[name]
        self.verify()
        before=self.read32(self.base+4)
        if not before&16 or before&9:
            raise DiagnosticError('Mailbox offline, busy or watchdog fault; no command retry')
        if self.next_id==0 or self.next_id>=0xffffffff:
            raise DiagnosticError('Request counter exhausted; establish a new reset epoch')
        request=self.next_id;self.next_id+=1
        for offset,value in (registers or {}).items():
            if offset not in range(0x10,0x34,4):raise ValueError('Not a config register')
            self.write32(self.base+offset,uint(value,32,'register value'))
        self.write32(self.base+0x0c,request)
        self.write32(self.base+8,0x42470000|opcode)
        deadline=time.monotonic()+self.timeout
        while time.monotonic()<deadline:
            state=self.read32(self.base+4)
            if state&12:raise DiagnosticError('Command rejected or timed out in hardware')
            if not state&16:raise DiagnosticError('Mailbox reset during command')
            if state&2 and not state&1:
                words=[self.read32(self.base+0x80+4*i) for i in range(16)]
                # The snapshot is atomically published by the FPGA, but these
                # sixteen MMIO reads are not an atomic transaction. A DDR reset
                # can clear its payload after we read the old successful header.
                # Recheck both publication identity and mailbox validity after
                # the payload; never turn such a torn snapshot into valid data.
                final_header=self.read32(self.base+0x80)
                final_request=self.read32(self.base+0x84)
                final_state=self.read32(self.base+4)
                if (final_state&0x1f)!=0x12:
                    raise DiagnosticError('Mailbox response invalidated during read; command was not reissued')
                if (final_header,final_request)!=(words[0],words[1]):
                    raise DiagnosticError('Mailbox response changed during read; command was not reissued')
                reply=Reply.decode(words)
                if reply.request_id!=request or reply.opcode!=opcode:
                    # The passive AXI monitor can take a few cycles to process
                    # the command write. A previous response is never accepted.
                    time.sleep(self.poll_seconds);continue
                if reply.result:
                    raise CommandRejected(reply.result)
                return reply
            time.sleep(self.poll_seconds)
        raise DiagnosticError('No matching reply before timeout; command was not reissued')

    def snapshot(self):return self.command('SNAP')

    def arm(self,*,epoch,geometry,calibration,token,width,height,roi,operator_confirmed):
        if operator_confirmed is not True:
            raise ValueError('Role capture needs explicit operator confirmation')
        for label,value in [('epoch',epoch),('geometry',geometry),('calibration',calibration),('token',token)]:
            if not uint(value,32,label):raise ValueError(label+' must be nonzero')
        uint(width,13,'width');uint(height,13,'height')
        x0,y0,x1,y1=roi
        for value in roi:uint(value,13,'ROI coordinate')
        if not(0<=x0<x1<=width and 0<=y0<y1<=height) or width%4 or x0%4 or x1%4:
            raise ValueError('Invalid four-pixel-aligned native ROI')
        if (x1-x0)*(y1-y0)*4>8388608:raise ValueError('ROI exceeds background slot')
        return self.command('ARM',{0x10:epoch,0x14:geometry,0x18:calibration,0x1c:token,
            0x20:(height<<16)|width,0x24:(y0<<16)|x0,0x28:(y1<<16)|x1,0x2c:1+2*self.role})

    def wait_capture(self,token,epoch,*,timeout=3.0):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            reply=self.snapshot()
            if reply.event_seen and reply.event_token==token and reply.event_epoch==epoch:
                if reply.busy:raise DiagnosticError('Completion event conflicts with capture_busy')
                if not(reply.event_ok and reply.event_committed and reply.active) or reply.event_error or reply.event_source_error:
                    raise DiagnosticError('Capture unusable: committed='+str(reply.event_committed)+
                                          ', error='+hex(reply.event_error)+', source='+hex(reply.event_source_error))
                if reply.background.epoch!=epoch:raise DiagnosticError('Capture epoch mismatch')
                return reply.background
            time.sleep(self.poll_seconds)
        raise DiagnosticError('Capture completion not observed; it was not rearmed')

    def read_word(self,offset,identity):
        uint(offset,32,'offset')
        if offset%16 or offset+16>identity.byte_count:raise ValueError('Read outside pinned background')
        reply=self.command('READ16',{0x30:offset})
        if reply.background!=identity or not reply.active:
            raise DiagnosticError('Background changed or was invalidated during read')
        if reply.flags&0x2d:raise DiagnosticError('Capture/transport/protocol fault in read reply')
        return reply.data

    def read_span(self,offset,byte_count,identity):
        uint(byte_count,32,'byte count')
        if offset%16 or byte_count%16 or offset+byte_count>identity.byte_count:
            raise ValueError('Span must contain complete 128-bit words within one background')
        return b''.join(self.read_word(at,identity) for at in range(offset,offset+byte_count,16))

    def cancel(self):return self.command('CANCEL')
