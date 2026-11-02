"""Transport-independent strict receiver prototype; no PCIe/device access.

The binary records follow laser_full_row_core outputs exactly. Headers bind
hardware ids to the RK request context; they do not claim FPGA measured angle.
Only a validated complete frame is returned to point-cloud consumers.
"""
from dataclasses import dataclass,replace
import json
import math
import re
import struct
import time
import zlib

PROTOCOL='afc03.rows.v1'
PREAMBLE=struct.Struct('<4sIII')
MAX_ROWS=4096
MAX_PAYLOAD=MAX_ROWS*33*16
ADAPTIVE_ALGORITHM="fpga-spatial-candidates25-rgb100-160-v1"


class ProtocolError(ValueError): pass


def require(test,message):
    if not test:raise ProtocolError(message)


def uint(value,bits,name):
    require(type(value) is int and 0<=value<(1<<bits),'Invalid '+name)
    return value


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def clone(value):return json.loads(canonical(value))


@dataclass(frozen=True)
class Center:
    row:int
    index:int
    num:int
    den:int
    peak32:int
    lo:int
    hi:int
    peak_x:int=None
    strength:int=None

    def encode(self):
        uint(self.row,16,'row');uint(self.index,8,'center index')
        uint(self.num,32,'numerator');uint(self.den,24,'denominator')
        uint(self.peak32,16,'peak32');uint(self.lo,12,'lo');uint(self.hi,12,'hi')
        return (struct.pack('<BBHI',1,self.index,self.row,self.num)+
                self.den.to_bytes(3,'little')+struct.pack('<H',self.peak32)+
                (self.lo|(self.hi<<12)).to_bytes(3,'little'))


@dataclass(frozen=True)
class CandidateExtra:
    row:int
    index:int
    peak_x:int
    strength:int
    def encode(self):
        uint(self.row,16,'row');uint(self.index,8,'candidate index')
        uint(self.peak_x,12,'peak x');uint(self.strength,16,'peak strength')
        return struct.pack('<BBHIQ',3,self.index,self.row,(self.peak_x<<16)|self.strength,0)


@dataclass(frozen=True)
class RowDone:
    row:int
    count:int
    tie_conflict:bool=False
    error:int=0
    cycles:int=0

    def encode(self):
        uint(self.row,16,'row');uint(self.count,8,'count')
        uint(self.error,8,'row error');uint(self.cycles,32,'cycles')
        require(type(self.tie_conflict) is bool,'Invalid tie flag')
        return struct.pack('<BBHBBHII',2,int(self.tie_conflict),self.row,
                           self.count,self.error,0,self.cycles,0)


def decode_record(raw):
    require(type(raw) is bytes and len(raw)==16,'Record must be exactly 16 bytes')
    kind,index,row=struct.unpack_from('<BBH',raw)
    if kind==1:
        limits=int.from_bytes(raw[13:16],'little')
        return Center(row,index,struct.unpack_from('<I',raw,4)[0],
                      int.from_bytes(raw[8:11],'little'),struct.unpack_from('<H',raw,11)[0],
                      limits&0xfff,limits>>12)
    if kind==3:
        value,reserved=struct.unpack_from('<IQ',raw,4)
        require(reserved==0 and value>>28==0,'Nonzero candidate reserved bits')
        return CandidateExtra(row,index,value>>16,value&65535)
    require(kind==2,'Unknown record type')
    _,flags,row,count,error,reserved,cycles,reserved2=struct.unpack('<BBHBBHII',raw)
    require(flags<2 and reserved==reserved2==0,'Nonzero reserved row bits')
    return RowDone(row,count,bool(flags),error,cycles)


def validate_geometry(g):
    require(set(g)=={'raw_size_wh','rotation_cw','processing_size_wh','roi_xyxy',
                     'global_x_origin','row_input_width'},'Unknown/missing geometry fields')
    w,h=g['raw_size_wh'];pw,ph=g['processing_size_wh'];rotation=g['rotation_cw']
    require(all(type(v)is int and 0<v<=4096 for v in (w,h,pw,ph)),'Invalid image size')
    require(type(rotation)is int and rotation in (0,90,180,270),'Unsupported image rotation')
    require([pw,ph]==([h,w] if rotation in (90,270) else [w,h]),'Rotated geometry mismatch')
    x0,y0,x1,y1=g['roi_xyxy'];origin=g['global_x_origin'];width=g['row_input_width']
    require(all(type(v)is int for v in (x0,y0,x1,y1,origin,width)),'Noninteger ROI geometry')
    require(0<=x0<x1<=pw and 0<=y0<y1<=ph and y1-y0<=MAX_ROWS,'ROI outside processing frame')
    require(0<=origin<=x0 and 1<=width<=2048 and x1<=origin+width<=pw,'Invalid row origin/width')


def validate_context(context):
    require(set(context)=={'stream_epoch','background_generation','geometry','laser_id',
                           'laser_control','calibration','algorithm'},'Unknown/missing context fields')
    require(isinstance(context['stream_epoch'],str) and bool(context['stream_epoch']),'Missing stream epoch')
    require(uint(context['background_generation'],32,'background generation')>0,'Background is not loaded')
    validate_geometry(context['geometry'])
    require(context['laser_id'] in ('A','B','UNASSIGNED'),'Invalid laser identity')
    require(context['laser_control'] in ('manual_single_laser','electrical_single_laser','unassigned'),
            'Invalid laser control provenance')
    require((context['laser_id']=='UNASSIGNED')==(context['laser_control']=='unassigned'),
            'Laser label conflicts with provenance')
    calibration=context['calibration']
    require(set(calibration)=={'version','camera_sha256','planes_sha256','axis_sha256'},'Invalid calibration binding')
    require(isinstance(calibration['version'],str) and bool(calibration['version']),'Missing calibration version')
    for key in ('camera_sha256','planes_sha256','axis_sha256'):
        require(isinstance(calibration[key],str) and re.fullmatch('[0-9a-f]{64}',calibration[key]) is not None,
                'Invalid calibration hash: '+key)
    require(isinstance(context['algorithm'],str) and bool(context['algorithm']),'Missing algorithm version')


def angle_degrees(angle):
    require(isinstance(angle,dict),'Angle provenance must be an object')
    require(angle.get('moving_before') is False and angle.get('moving_after') is False,'Motion during capture')
    if angle.get('source')=='commanded_pulses_no_encoder':
        keys={'source','moving_before','moving_after','emitted_before','emitted_after',
              'zero_pulses','pulses_per_revolution','command_complete'}
        require(set(angle)==keys and angle['command_complete'] is True,'Incomplete pulse command evidence')
        before,after,zero,ppr=[angle[k] for k in ('emitted_before','emitted_after','zero_pulses','pulses_per_revolution')]
        require(all(type(v)is int for v in (before,after,zero,ppr)) and ppr>0 and before==after,
                'Unstable/invalid emitted pulse position')
        degrees=(after-zero)*360.0/ppr
        require(math.isfinite(degrees),'Nonfinite commanded angle')
        return degrees
    if angle.get('source')=='encoder_observed':
        keys={'source','moving_before','moving_after','before_deg','after_deg','zero_deg','max_stationary_error_deg'}
        require(set(angle)==keys,'Incomplete encoder evidence')
        before,after,zero,tolerance=[angle[k] for k in ('before_deg','after_deg','zero_deg','max_stationary_error_deg')]
        require(all(type(v) in (int,float) and math.isfinite(v) for v in (before,after,zero,tolerance)),
                'Nonfinite encoder angle')
        require(0<=tolerance<=1 and abs(after-before)<=tolerance,'Encoder position changed during capture')
        return (before+after)/2-zero
    raise ProtocolError('Unknown angle source')


@dataclass(frozen=True)
class CommittedFrame:
    header_json:str
    centers:tuple
    rows:tuple
    payload:bytes
    payload_crc32:int

    @property
    def header(self):return json.loads(self.header_json)

    def processing_uv(self):
        origin=self.header['geometry']['global_x_origin']
        return [(origin+c.num/c.den,float(c.row)) for c in self.centers]


class FrameReceiver:
    """Single-consumer receiver with a bounded staging frame. No partial output."""
    def __init__(self,context,timeout_s=5.0,clock=time.monotonic):
        require(0<timeout_s<=60,'Invalid receive timeout')
        self.clock,self.timeout_s=clock,timeout_s
        self.context=None;self.pending=None;self.staged=None
        self.last_request=self.last_source=-1
        self.accepted=self.rejected=self.expired=0
        self.activate(context)

    def activate(self,context):
        validate_context(context)
        different_epoch=self.context is None or context['stream_epoch']!=self.context['stream_epoch']
        self.context=clone(context);self.pending=self.staged=None
        if different_epoch:self.last_request=self.last_source=-1

    def _fail(self,message):
        self.rejected+=1;self.pending=self.staged=None
        raise ProtocolError(message)

    def expire(self):
        if self.pending is not None and self.clock()>=self.pending['deadline']:
            self.expired+=1;self._fail('Incomplete result frame expired')

    def register(self,request_id,angle,expected_source_frame_id=None):
        self.expire()
        uint(request_id,32,'request id');angle_degrees(angle)
        require(request_id>self.last_request,'Duplicate/out-of-order request id')
        require(self.pending is None,'A request is already pending')
        if expected_source_frame_id is not None:uint(expected_source_frame_id,32,'expected source frame id')
        self.last_request=request_id
        self.pending=dict(request_id=request_id,angle=clone(angle),expected_source=expected_source_frame_id,
                          deadline=self.clock()+self.timeout_s)

    def begin(self,header):
        self.expire()
        try:
            require(self.pending is not None and self.staged is None,'No unique pending frame request')
            expected=dict(self.context,protocol=PROTOCOL,request_id=self.pending['request_id'],
                          angle=self.pending['angle'],complete=False,error=0)
            require(set(header)==set(expected)|{'source_frame_id'},'Unknown/missing frame header fields')
            require(canonical({k:header[k] for k in expected})==canonical(expected),'Result context/request mismatch')
            frame_id=uint(header['source_frame_id'],32,'source frame id')
            require(frame_id>self.last_source,'Duplicate/out-of-order source frame id')
            if self.pending['expected_source'] is not None:
                require(frame_id==self.pending['expected_source'],'Unexpected source frame id')
            self.last_source=frame_id
            self.staged=dict(header=clone(header),centers=[],rows=[],payload=bytearray(),
                             next_row=self.context['geometry']['roi_xyxy'][1],current=[])
        except (ProtocolError,TypeError,KeyError,ValueError) as exc:self._fail(str(exc))

    def push(self,record):
        self.expire()
        try:
            require(self.staged is not None,'No frame in progress')
            if isinstance(record,bytes):raw=record;record=decode_record(raw)
            else:raw=record.encode();decode_record(raw)
            s=self.staged;g=self.context['geometry'];x0,y0,x1,y1=g['roi_xyxy']
            adaptive=self.context['algorithm']==ADAPTIVE_ALGORITHM
            limit=16 if adaptive else 2
            waiting=adaptive and bool(s['current']) and s['current'][-1].peak_x is None
            require(s['next_row']<y1 and record.row==s['next_row'],'Missing/duplicate/out-of-order row')
            if isinstance(record,Center):
                require(not waiting and record.index==len(s['current']) and record.index<limit,'Duplicate/out-of-order center')
                require(record.den>0 and x0-g['global_x_origin']<=record.lo<=record.hi<x1-g['global_x_origin'],
                        'Invalid center denominator/window')
                if adaptive or self.context.get('algorithm')=='fpga-brightcore-width100-signal40-v1':
                    require(record.peak32 & 0xfe00 == 0x8000 and (record.peak32 & 255)>=(25 if adaptive else 40),
                            'Invalid brightcore candidate metadata')
                    require(2<=record.hi-record.lo+1<=100,'Invalid brightcore window width')
                else:
                    require(576<=record.peak32<=8160,'Center peak outside the old core range')
                require(record.lo*record.den<=record.num<=record.hi*record.den,'Center outside its window')
                if s['current'] and not adaptive:
                    prev=s['current'][-1]
                    require(prev.num*record.den<=record.num*prev.den,'Centers not sorted by rational coordinate')
                s['current'].append(record)
            elif isinstance(record,CandidateExtra):
                require(adaptive and waiting and record.index==len(s['current'])-1,'Orphan/duplicate candidate metadata')
                c=s['current'][-1]
                require(c.lo<=record.peak_x<=c.hi and 18*32<=record.strength<=8160,'Invalid candidate peak position/strength')
                if len(s['current'])>1:require(record.peak_x>s['current'][-2].peak_x,'Candidate peaks not ordered')
                s['current'][-1]=replace(c,peak_x=record.peak_x,strength=record.strength)
            elif isinstance(record,RowDone):
                require(not waiting,'Candidate metadata missing before row completion')
                require(record.error==0,'Row core reported error')
                require(record.count==len(s['current']) and record.count<=limit,'Row completion count mismatch')
                s['centers'].extend(s['current']);s['current']=[];s['rows'].append(record);s['next_row']+=1
            else:raise ProtocolError('Unknown result record')
            s['payload'].extend(raw)
            require(len(s['payload'])<=MAX_PAYLOAD,'Result frame exceeds bounded staging capacity')
        except (ProtocolError,TypeError,ValueError,AttributeError) as exc:self._fail(str(exc))

    def finish(self,footer):
        self.expire()
        try:
            require(self.staged is not None,'No frame in progress')
            s=self.staged;h=s['header'];g=self.context['geometry']
            expected=dict(stream_epoch=h['stream_epoch'],request_id=h['request_id'],source_frame_id=h['source_frame_id'],
                          complete=True,error=0,row_count=g['roi_xyxy'][3]-g['roi_xyxy'][1],
                          center_count=len(s['centers']),record_count=len(s['payload'])//16,
                          payload_crc32=zlib.crc32(s['payload']))
            require(canonical(footer)==canonical(expected),'Incomplete/faulted/count/CRC/footer identity mismatch')
            require(s['next_row']==g['roi_xyxy'][3] and not s['current'],'Not all rows completed')
            committed_header=dict(h,complete=True,error=0)
            result=CommittedFrame(canonical(committed_header),tuple(s['centers']),tuple(s['rows']),
                                  bytes(s['payload']),expected['payload_crc32'])
            self.pending=self.staged=None;self.accepted+=1
            return result
        except (ProtocolError,TypeError,ValueError) as exc:self._fail(str(exc))


def encode_packet(header,records,footer):
    """Offline transport fixture format, not a claim of implemented PCIe ABI."""
    h=canonical(header).encode();f=canonical(footer).encode()
    payload=b''.join(r if isinstance(r,bytes) else r.encode() for r in records)
    require(len(h)<=65536 and len(f)<=4096 and len(payload)<=MAX_PAYLOAD,'Packet too large')
    return PREAMBLE.pack(b'AFR1',len(h),len(payload),len(f))+h+payload+f


def receive_packet(receiver,packet):
    try:
        require(type(packet)is bytes and len(packet)>=PREAMBLE.size,'Truncated/nonbinary packet preamble')
        magic,hn,pn,fn=PREAMBLE.unpack_from(packet)
        require(magic==b'AFR1' and hn<=65536 and fn<=4096 and pn<=MAX_PAYLOAD and pn%16==0,'Invalid packet bounds')
        require(len(packet)==PREAMBLE.size+hn+pn+fn,'Truncated/extra packet bytes')
        at=PREAMBLE.size
        header=json.loads(packet[at:at+hn]);at+=hn
        receiver.begin(header)
        for offset in range(at,at+pn,16):receiver.push(packet[offset:offset+16])
        return receiver.finish(json.loads(packet[at+pn:]))
    except (ProtocolError,ValueError,TypeError,KeyError,struct.error) as exc:
        if receiver.pending is not None or receiver.staged is not None:receiver._fail('Packet rejected: '+str(exc))
        raise ProtocolError(str(exc)) from exc
