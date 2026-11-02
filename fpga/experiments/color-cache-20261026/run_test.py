"""Compile/run isolated COLOR cache board test with the qualified dependency list."""
from pathlib import Path
import argparse,json,subprocess,struct,zlib
from generate import generate,FPGA,BASE,HERE

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--iverilog',default='iverilog');ap.add_argument('--vvp',default='vvp');a=ap.parse_args()
    generate();out=FPGA/'test-output/color-cache';out.mkdir(parents=True,exist_ok=True)
    core=(BASE/'rtl/laser_full_row_core.v').read_text()
    rom=BASE/'rtl/spatial_mask.hex'
    assert rom.is_file()
    core=core.replace('F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010/rtl/spatial_mask.hex',rom.resolve().as_posix())
    (out/'laser_full_row_core.v').write_text(core)
    inputs=json.loads((FPGA/'build-inputs.json').read_text())
    dirs=list(dict.fromkeys([str(out.resolve()),str(BASE/'rtl')]+[str((FPGA/'source'/n).parent) for n in inputs if n.endswith(('.sv','.v'))]))
    cmd=[a.iverilog,'-g2012','-s','tb','-o',str(out/'test.vvp'),'-Y','.sv','-Y','.v']
    for d in dirs:cmd+=['-y',d]
    cmd += [str(HERE/'afc03_laser_board_top.sv'),str(HERE/'tb_color_cache.sv')]
    for name,command in [('compile',cmd),('simulation',[a.vvp,str(out/'test.vvp')])]:
        r=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=180)
        log=r.stdout+r.stderr;(out/(name+'.log')).write_text(log)
        print(log)
        if r.returncode or any(x in log for x in ('ERROR:','FATAL:','Unable to open','Unknown module')):raise SystemExit(name+' failed')
        if name=='simulation' and 'COLOR_CACHE_PASS' not in log:raise SystemExit('Missing pass marker')
    data=b''.join(int(x,16).to_bytes(16,'little') for x in (out/'dma-packets.txt').read_text().splitlines())
    assert len(data)==2*65536
    records=[]
    for line in (out/'board-records.txt').read_text().splitlines():
        parts=line.split()
        if parts[0]=='FRAME':records.append(bytearray())
        else:records[-1].extend(int(parts[1],16).to_bytes(16,'little'))
    assert len(records)==2
    for i in range(2):
        packet=data[i*65536:(i+1)*65536];header=struct.unpack('<32I',packet[:128])
        payload=packet[128:128+16*header[12]]
        assert header[:4]==(0x51444d41,0x10000,65536,128)
        assert header[5:10]==(7,101+i,1+i,31,11)
        assert header[12:15]==(24,8,8) and header[15]==zlib.crc32(payload)
        assert header[17:20]==(0,0x60000,0)
        assert payload==records[i] and not any(packet[128+len(payload):])
    (out/'result.json').write_text(json.dumps(dict(passed=True,scope='RTL simulation only; no synthesis or hardware deployment',color_survives_off_a_b=True,color_ping_pong=True,reset_invalidates=True,csr_dma_payload_exact=True),indent=2))
if __name__=='__main__':main()
