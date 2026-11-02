from pathlib import Path
import subprocess,concurrent.futures,json,hashlib,time
H=Path(__file__).parent;BIN=H.parent/'capture-repair-20260928/tools/bin'
RTL=H/'sources/fpga-capture-pipeline-20261004/board/fpga/uisrc/03_ip/ui_imx415_cfg'
src=Path('F:/AAA_FPGA/analysis/black-cloud-audit-20261013/gain_handshake_tb.sv').read_text()
src=src.replace('integer left;integer gains;reg [31:0] latched;', 'integer left;integer gains;reg [31:0] latched; reg inject_error=0; reg error_pulse=0; integer last_gain=0;')
src=src.replace('assign O_iic_bus_error=0;', 'assign O_iic_bus_error=error_pulse;')
src=src.replace('always @(posedge I_clk) begin', 'always @(posedge I_clk) begin\n error_pulse<=0;\n if(O_iic_busy && left==4500 && inject_error && latched[15:8]==8\'h30 && latched[23:16]==8\'h90)error_pulse<=1;')
src=src.replace('gains<=gains+1;', 'gains<=gains+1;last_gain<=latched[31:24];')
src=src.replace('reg clk=0,rst=0,pulse=0,pending=0,done_prev=1;', 'reg clk=0,rst=0,pulse=0,pending=0,done_prev=1; reg [7:0] host_gain=50;')
src=src.replace(".I_ae_data(8'd50)",'.I_ae_data(host_gain)')
src=src.replace('if(kind>0)begin','if(kind==1 || kind==2)begin')
src=src.replace('base=dut.X_ui_i2c.gains;request();', '''if(kind==6)dut.X_ui_i2c.inject_error=1;
   base=dut.X_ui_i2c.gains;request();
   if(kind>=3)begin
    wait(!done);wait(dut.iic_busy);
    if(kind==3 || kind==4)begin
     @(negedge clk);host_gain=73;
     if(kind==4)request();
    end
    if(kind==5)begin @(negedge clk);dut.cnt=1000000;end
   end''')
src=src.replace('$display("CASE=%0d completed_ack=%0d actual_gain_writes=%0d pending=%0d",kind,completed,dut.X_ui_i2c.gains-base,pending);', '''if(completed!=(kind==4?2:1) || dut.X_ui_i2c.gains-base!=(kind==4?2:1) || pending!==0)
    $fatal(1,"Missing or duplicate gain transaction case=%0d ack=%0d writes=%0d",kind,completed,dut.X_ui_i2c.gains-base);
   if(dut.X_ui_i2c.last_gain!=(kind==4?73:50))$fatal(1,"In-flight gain was not latched");
   if(error !== (kind==6))$fatal(1,"Error indication incorrect case=%0d error=%0d",kind,error);
   if(kind==6)begin
    dut.X_ui_i2c.inject_error=0;request();repeat(20000)@(negedge clk);
    if(error!==0 || completed!=2 || dut.X_ui_i2c.gains-base!=2)$fatal(1,"Error did not recover on explicit new request");
   end
   $display("PASS case=%0d completed_ack=%0d actual_gain_writes=%0d pending=%0d error=%0d",kind,completed,dut.X_ui_i2c.gains-base,pending,error);''')
tb=H/'tb_gain.sv';tb.write_text(src)
cmd=[str(BIN/'iverilog.exe'),'-g2012','-DREAL_ROM','-s','tb','-o',str(H/'gain.vvp'),str(RTL/'ui_cfg_imx415.v'),str(RTL/'ui_imx415_reg.v'),str(tb)]
r=subprocess.run(cmd,capture_output=True,text=True);(H/'gain-compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
def run(k):
 start=time.time();r=subprocess.run([str(BIN/'vvp.exe'),str(H/'gain.vvp'),f'+CASE={k}'],capture_output=True,text=True,timeout=160)
 (H/f'gain-case-{k}.log').write_text(r.stdout+r.stderr)
 result=dict(case=k,passed=r.returncode==0 and f'PASS case={k}' in r.stdout,seconds=time.time()-start)
 print(json.dumps(result),flush=True);return result
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,range(7)))
report=dict(passed=all(x['passed'] for x in results),cases=results,sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [RTL/'ui_cfg_imx415.v',RTL/'ui_imx415_reg.v',tb]})
(H/'gain-validation.json').write_text(json.dumps(report,indent=2));assert report['passed']
