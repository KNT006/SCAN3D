"""Generate an isolated COLOR-bank board top; qualified sources are never edited."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
FPGA=HERE.parents[1]
BASE=FPGA/'source/fpga-gain-handshake-20261013'

def generate():
    path=BASE/'rtl/afc03_laser_board_top.sv'
    manifest=json.loads((FPGA/'build-inputs.json').read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest[path.relative_to(FPGA/'source').as_posix()]
    s=path.read_text()
    s=s.replace('parameter MAX_HEIGHT=1080',"parameter [27:0] COLOR0=28'h2100000,COLOR1=28'h2900000,\n parameter MAX_HEIGHT=1080")
    s=s.replace('wire bg_source_pending,live_source_pending;', 'wire bg_source_pending,live_source_pending,color_source_pending;\nwire [31:0] color_source_token;')
    s=s.replace('(bg_source_pending ^ live_source_pending)', '((bg_source_pending&&!live_source_pending&&!color_source_pending)||\n (live_source_pending&&!bg_source_pending&&!color_source_pending)||\n (color_source_pending&&!bg_source_pending&&!live_source_pending))')
    s=s.replace('bg_source_pending?bg_source_token:live_source_token','color_source_pending?color_source_token:bg_source_pending?bg_source_token:live_source_token')
    decl=s[s.index('wire  bg_external_access;'):s.index('wire  live_external_access;')].replace('bg_','color_')
    s=s.replace('wire  live_external_access;',decl+'wire  live_external_access;',1)
    s=s.replace('process_rd_select||live_rd_select||bg_rd_select','color_rd_select||process_rd_select||live_rd_select||bg_rd_select')
    s=s.replace('assign rd_data=process_rd_select?', 'assign rd_data=color_rd_select?color_rd_data:process_rd_select?')
    s=s.replace('reg [1:0] axi_owner;', 'reg [2:0] axi_owner;')
    s=s.replace('wire bg_capture_idle,live_capture_idle,bg_read_busy,live_read_busy;', 'wire bg_capture_idle,live_capture_idle,bg_read_busy,live_read_busy,color_capture_idle,color_read_busy;\nassign color_arb_grant=axi_owner==4;')
    s=s.replace('process_request&&bg_arb_idle&&live_arb_idle','process_request&&bg_arb_idle&&live_arb_idle&&color_arb_idle')
    s=s.replace('else if(live_arb_request)axi_owner<=2;', 'else if(live_arb_request)axi_owner<=2;\n    else if(color_arb_request)axi_owner<=4;')
    s=s.replace('  3:if(!process_request', '  4:if(color_arb_idle)axi_owner<=0;\n  3:if(!process_request')
    s=s.replace('wire select_bg=axi_owner==1;', 'wire select_color=axi_owner==4;\nwire write_color=axi_owner==4;\nwire select_bg=axi_owner==1;')
    # COLOR owns AXI exclusively. Existing OFF/LIVE extraction overlap is unchanged.
    for signal in ['awid','awaddr','awlen','awsize','awburst','awvalid','wdata','wstrb','wlast','wvalid','bready']:
        s=s.replace('assign '+signal+'=', 'assign '+signal+'=write_color?color_'+signal+':',1)
    for signal in ['arid','araddr','arlen','arsize','arburst','arvalid','rready']:
        s=s.replace('assign '+signal+'=', 'assign '+signal+'=select_color?color_'+signal+':',1)
    ties='\n// Reserved independent COLOR read port: diagnostic READ16 until RGB consumer is added.\n'
    for signal in ['external_access','ext_acquire_valid','ext_release_valid','ext_release_slot','ext_release_header','ext_release_epoch','ext_read_cmd_valid','ext_read_cmd_address','ext_read_cmd_bytes','ext_read_cmd_epoch','ext_read_cmd_header','ext_read_ready','ext_read_status_ready']:
        ties+='assign color_'+signal+"='0;\n"
    for signal in ['awready','wready','bvalid']:ties+='assign color_'+signal+'='+signal+'&&write_color;\n'
    for signal in ['arready','rvalid']:ties+='assign color_'+signal+'='+signal+'&&select_color;\n'
    for signal in ['bid','bresp','rid','rdata','rresp','rlast']:ties+='assign color_'+signal+'='+signal+';\n'
    start=s.index('afc03_role_diagnostic_top #(');end=s.index('afc03_role_diagnostic_top #(',start+1)
    instance=s[start:end].replace('bg_','color_').replace(".PAGE(12'h022)",".PAGE(12'h025)").replace('.SLOT0_BASE(BG0),.SLOT1_BASE(BG1)', '.SLOT0_BASE(COLOR0),.SLOT1_BASE(COLOR1)').replace(')) bg(', ')) color(').replace('.capture_allowed(overlap_allowed)',".capture_allowed(1'b0)")
    s=s[:start]+ties+instance+s[start:]
    # Invalid custom layouts must not enable any DDR traffic.
    layout='''
wire color_layout_ok=(ADDR_WIDTH==28) && (SLOT_BYTES>0) && ((SLOT_BYTES%16)==0) &&
    (COLOR0[3:0]==0) && (COLOR1[3:0]==0) &&
    ({1'b0,COLOR0}+SLOT_BYTES<=29'h10000000) &&
    ({1'b0,COLOR1}+SLOT_BYTES<=29'h10000000);
'''
    ranges=['BG0','BG1','ON0','ON1','COLOR0','COLOR1']
    terms=[]
    for i,a in enumerate(ranges):
        for b in ranges[i+1:]:terms.append("(({1'b0,%s}+SLOT_BYTES<=%s)||({1'b0,%s}+SLOT_BYTES<=%s))"%(a,b,b,a))
    layout+='wire banks_disjoint='+ ' &&\n    '.join(terms)+';\n'
    s=s.replace('wire bg_source_pending,',layout+'wire bg_source_pending,',1)
    s=s.replace('.ext_enabled(ext_enabled)', '.ext_enabled(ext_enabled&&color_layout_ok&&banks_disjoint)')
    (HERE/'afc03_laser_board_top.sv').write_text(s,encoding='utf-8')
    return s

if __name__=='__main__':
    generate()
    print('Generated isolated COLOR board top (no qualified source changes)')
