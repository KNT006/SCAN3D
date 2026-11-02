from pathlib import Path
H=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010/host')
p=H/'row_results.py';s=p.read_text().replace('from dataclasses import dataclass','from dataclasses import dataclass,replace').replace('MAX_PAYLOAD=MAX_ROWS*3*16','MAX_PAYLOAD=MAX_ROWS*33*16\nADAPTIVE_ALGORITHM="fpga-spatial-candidates25-rgb100-160-v1"')
s=s.replace('    hi:int\n','    hi:int\n    peak_x:int=None\n    strength:int=None\n',1)
pos=s.index('@dataclass(frozen=True)\nclass RowDone:')
s=s[:pos]+'''@dataclass(frozen=True)
class CandidateExtra:
    row:int
    index:int
    peak_x:int
    strength:int
    def encode(self):
        uint(self.row,16,'row');uint(self.index,8,'candidate index')
        uint(self.peak_x,12,'peak x');uint(self.strength,16,'peak strength')
        return struct.pack('<BBHIQ',3,self.index,self.row,(self.peak_x<<16)|self.strength,0)


'''+s[pos:]
s=s.replace("    require(kind==2,'Unknown record type')", "    if kind==3:\n        value,reserved=struct.unpack_from('<IQ',raw,4)\n        require(reserved==0 and value>>28==0,'Nonzero candidate reserved bits')\n        return CandidateExtra(row,index,value>>16,value&65535)\n    require(kind==2,'Unknown record type')")
s=s.replace("s=self.staged;g=self.context['geometry'];x0,y0,x1,y1=g['roi_xyxy']", "s=self.staged;g=self.context['geometry'];x0,y0,x1,y1=g['roi_xyxy']\n            adaptive=self.context['algorithm']==ADAPTIVE_ALGORITHM\n            limit=16 if adaptive else 2\n            waiting=adaptive and bool(s['current']) and s['current'][-1].peak_x is None")
s=s.replace("record.index==len(s['current']) and record.index<2", "not waiting and record.index==len(s['current']) and record.index<limit")
s=s.replace("if self.context.get('algorithm')=='fpga-brightcore-width100-signal40-v1':", "if adaptive or self.context.get('algorithm')=='fpga-brightcore-width100-signal40-v1':")
s=s.replace('(record.peak32 & 255)>=40','(record.peak32 & 255)>=(25 if adaptive else 40)').replace("if s['current']:\n                    prev=", "if s['current'] and not adaptive:\n                    prev=")
s=s.replace('            elif isinstance(record,RowDone):', '''            elif isinstance(record,CandidateExtra):
                require(adaptive and waiting and record.index==len(s['current'])-1,'Orphan/duplicate candidate metadata')
                c=s['current'][-1]
                require(c.lo<=record.peak_x<=c.hi and 18*32<=record.strength<=8160,'Invalid candidate peak position/strength')
                if len(s['current'])>1:require(record.peak_x>s['current'][-2].peak_x,'Candidate peaks not ordered')
                s['current'][-1]=replace(c,peak_x=record.peak_x,strength=record.strength)
            elif isinstance(record,RowDone):
                require(not waiting,'Candidate metadata missing before row completion')''')
s=s.replace("record.count<=2,'Row completion", "record.count<=limit,'Row completion")
p.write_text(s)
p=H/'job_client.py';s=p.read_text().replace('(ABI,0x00030000,DMA_ABI,0x00050000)','(ABI,0x00030000,DMA_ABI,0x00050000,0x00060000)').replace('self.capture_overlap=version==0x00050000','self.spatial_candidates=version==0x00060000\n  self.capture_overlap=version in (0x00050000,0x00060000)\n  if self.spatial_candidates and (self.read(self.base+0x34),self.read(self.base+0x38))!=(0x9c744450,0x0046000b):raise DiagnosticError("Spatial ROM profile mismatch; no writes performed")')
s=s.replace('if 3*(x1-x0)>2048', 'if (33 if self.spatial_candidates else 3)*(x1-x0)>2048')
s=s.replace("if w[4]!=x1-x0 or w[3]!=w[4]+w[5] or not w[4]<=w[3]<=3*w[4]", "if w[4]!=x1-x0 or w[3]!=w[4]+(2 if self.spatial_candidates else 1)*w[5] or not w[4]<=w[3]<=(33 if self.spatial_candidates else 3)*w[4]")
s=s.replace('(DMA_ABI,0x00050000)', '(DMA_ABI,0x00050000,0x00060000)');p.write_text(s)
p=H/'result_dma.py';s=p.read_text().replace('(ABI,0x00050000)', '(ABI,0x00050000,0x00060000)').replace('    if not (0<rows<=2048//3 and rows<=n<=3*rows and n==rows+centers and n<=2048)', '    factor=33 if abi==0x00060000 else 3\n    if not (0<rows<=2048//factor and rows<=n<=factor*rows and n==rows+(2 if abi==0x00060000 else 1)*centers and n<=2048)');p.write_text(s)
p=H/'full_roi.py';s=p.read_text().replace('PROTOCOL, RowDone,','PROTOCOL, RowDone, Center,').replace("    role = {'A':1,'B':2}[context['laser_id']]", "    if getattr(job,'spatial_candidates',False):\n        from rgb_adaptive_strategy import validate_profile\n        validate_profile(context)\n        maximum_rows=min(maximum_rows,60)\n    role = {'A':1,'B':2}[context['laser_id']]").replace('if not isinstance(record,RowDone):count+=1','if isinstance(record,Center):count+=1');p.write_text(s)
