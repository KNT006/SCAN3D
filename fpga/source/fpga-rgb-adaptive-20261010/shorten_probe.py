from pathlib import Path
import shutil,json,time
H=Path('F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010');R=H/'board/fpga/imx415_pcie_4k_Runs/phy_1';A=H/'attempt-01-timing';A.mkdir(exist_ok=False)
shutil.copytree(H/'rtl',A/'rtl')
for pat in ('*-validation.json','*-qualification.json','build-*.json','eco-result.json','*.log','mapped-reset.sdc'):
 for p in H.glob(pat):shutil.copy2(p,A/p.name)
for p in R.glob('*.timing'):shutil.copy2(p,A/p.name)
for n in ('imx415_pcie_4k_pr.db','imx415_pcie_4k_eco.db'):shutil.copy2(R/n,A/n)
p=H/'rtl/afc03_rgb_roi_probe.sv';s=p.read_text();golden=s.replace('module afc03_rgb_roi_probe #','module afc03_rgb_roi_probe_golden #',1);(H/'probe-golden.sv').write_text(golden)
s=s.replace('reg [31:0] token,frame_counter,captured_frame,words_written;','reg [31:0] token,frame_counter,captured_frame;\n    // ARM validates config_words <= WORDS and increments stop at WORDS.\n    reg [ADDR_BITS:0] words_written;')
s=s.replace('reg [31:0] expected_words;','reg [ADDR_BITS:0] expected_words,expected_minus_one;')
s=s.replace("wire [31:0] count_before=starting?32'd0:words_written;","wire [ADDR_BITS:0] count_before=starting?{(ADDR_BITS+1){1'b0}}:words_written;")
s=s.replace("wire [31:0] count_after=count_before+(inside_roi?32'd1:32'd0);","wire [ADDR_BITS:0] count_after=count_before+inside_roi;\n    // Compare in parallel: no late inside_roi -> incrementer -> comparator path.\n    wire final_count_ok=inside_roi ? (expected_words!=0 && count_before==expected_minus_one) : (count_before==expected_words);")
s=s.replace('height_latched<=0;expected_words<=0;','height_latched<=0;expected_words<=0;expected_minus_one<=0;')
s=s.replace('fault==0&&count_after==expected_words','fault==0&&final_count_ok')
s=s.replace('expected_words<=config_words;','expected_words<=config_words[ADDR_BITS:0];expected_minus_one<=config_words[ADDR_BITS:0]-1\'b1;')
p.write_text(s)
B=H.parent/'fpga-capture-pipeline-20261004'
for n in ('test_atomic.py','tb_atomic.sv'):shutil.copy2(B/n,H/n)
s=(H.parent/'fpga-laser-20261001/rgb-roi/rtl/tb_rgb_roi_probe.sv').read_text()
a=s.index('afc03_rgb_roi_probe #');b=s.index('reg [129:0] queue',a);inst=s[a:b].replace('afc03_rgb_roi_probe #','afc03_rgb_roi_probe_golden #').replace(') d(',') g(')
for old,new in [('(sr)','(g_sr)'),('(md)','(g_md)'),('(mv)','(g_mv)'),('(ml)','(g_ml)'),('(mu)','(g_mu)'),('(sel)','(g_sel)'),('(rd)','(g_rd)')]:inst=inst.replace(old,new)
check='''wire g_sr,g_mv,g_ml,g_mu,g_sel;wire [127:0] g_md;wire [31:0] g_rd;
'''+inst+'''
always @(negedge clk) if(rst) begin
 if({sr,mv,ml,mu,sel,rd} !== {g_sr,g_mv,g_ml,g_mu,g_sel,g_rd})$fatal(1,"Probe interface equivalence failed");
 if(mv && md !== g_md)$fatal(1,"Probe payload equivalence failed");
 if({d.waiting,d.active,d.done,d.fault,d.rejected,d.token,d.frame_counter,d.captured_frame} !== {g.waiting,g.active,g.done,g.fault,g.rejected,g.token,g.frame_counter,g.captured_frame})$fatal(1,"Probe state equivalence failed");
 if(d.words_written !== g.words_written || d.expected_words !== g.expected_words)$fatal(1,"Probe counter equivalence failed");
end
'''
s=s[:b]+check+s[b:];(H/'tb_probe_equivalence.sv').write_text(s)
print('Archived failed attempt; optimized bounded counter and parallel final-count comparisons only')
