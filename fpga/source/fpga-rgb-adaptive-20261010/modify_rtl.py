from pathlib import Path
H=Path(__file__).resolve().parent;R=H/'rtl'
def edit(name,fn):
 p=R/name;s=p.read_text();p.write_text(fn(s))
def core(s):
 s=s.replace('input wire clk,rst_n,','input wire clk,rst_n,\n    input wire laser_b,input wire [12:0] row_id,\n    output reg [31:0] center_extra,')
 s=s.replace('output reg [1:0] center_count','output reg [4:0] center_count')
 marker='    reg [7:0] signal_mem'
 rom=f'''    (* ram_style="bram" *) reg [47:0] spatial_rom[0:4095];
    reg [47:0] spatial_ranges;
    initial $readmemh("{(R/'spatial_mask.hex').as_posix()}",spatial_rom);
    always @(posedge clk)spatial_ranges<=spatial_rom[{{laser_b,row_id[10:0]}}];
'''
 s=s.replace(marker,rom+marker)
 s=s.replace('.start(front_start),','.spatial_ranges(spatial_ranges),.spatial_enable(row_width==1080 && row_id<1920),\n        .start(front_start),')
 s=s.replace('center_num<=r[31:0];','center_extra<={4\'d0,r[107:96],r[71:56]};\n            center_num<=r[31:0];')
 s=s.replace('center_num<=0;','center_extra<=0;center_num<=0;')
 start=s.index('            EVAL_WAIT:if(eval_done)begin')
 end=s.index('            default:begin',start)
 s=s[:start]+'''            EVAL_WAIT:if(eval_done)begin
                t_eval<=ticks;cycles_evaluate<=ticks-t_find;
                if(eval_error || accepted_count>16)begin error<=1;finish;end
                else begin scan<=0;center_count<=accepted_count[4:0];state<=READ_RECORD;end
            end
            READ_RECORD:begin
                if(scan==accepted_count)begin cycles_select<=ticks-t_eval;finish;end
                else state<=WAIT_RECORD;
            end
            WAIT_RECORD:begin load_output(record_q);state<=SEND_FIRST;end
            SEND_FIRST:if(center_ready)begin center_valid<=0;scan<=scan+1;state<=READ_RECORD;end
'''+s[end:]
 return s
edit('laser_full_row_core.v',core)
edit('laser_row_evaluator_precomputed.v',lambda s:s.replace('signal_next<40','signal_next<25'))
def front(s):
 s=s.replace('input wire clk, rst_n,','input wire clk, rst_n,\n    input wire [47:0] spatial_ranges,input wire spatial_enable,')
 s=s.replace('    reg [11:0] output_index', '''    wire spatial_reject=spatial_enable &&
        ((midpoint>=spatial_ranges[11:0] && midpoint<=spatial_ranges[23:12]) ||
         (midpoint>=spatial_ranges[35:24] && midpoint<=spatial_ranges[47:36]));
    reg [11:0] output_index''')
 s=s.replace('sample_q<previous && rising && local_count<MAX_LOCAL','sample_q<previous && rising && !spatial_reject && local_count<MAX_LOCAL')
 s=s.replace('if(rising)begin','if(rising && !spatial_reject)begin')
 s=s.replace('sample_q<previous && rising && local_count==MAX_LOCAL','sample_q<previous && rising && !spatial_reject && local_count==MAX_LOCAL')
 return s
edit('laser_peak_frontend.v',front)
def stream(s):
 s=s.replace('input wire clk,rst_n,abort,','input wire clk,rst_n,abort,\n    input wire cfg_laser_b,output wire [31:0] center_extra,')
 s=s.replace('[1:0] row_center_count','[4:0] row_center_count').replace('[1:0] sent_centers','[4:0] sent_centers').replace('[1:0] core_count','[4:0] core_count')
 s=s.replace('    reg core_release;','    reg core_release,laser_b;')
 s=s.replace('.clk(clk),.rst_n(core_reset_n),','.laser_b(laser_b),.row_id(row_id),.center_extra(center_extra),\n        .clk(clk),.rst_n(core_reset_n),')
 s=s.replace('state<=IDLE;core_release<=0;width<=0;','state<=IDLE;laser_b<=0;core_release<=0;width<=0;')
 s=s.replace('frame_id<=cfg_frame_id;','laser_b<=cfg_laser_b;frame_id<=cfg_frame_id;')
 return s
edit('laser_full_row_stream.v',stream)
def tile(s):
 s=s.replace(' input wire clk,rst_n,cancel,',' input wire clk,rst_n,cancel,input wire cfg_laser_b,')
 s=s.replace(' wire [1:0] r_count;',' wire [4:0] r_count;wire [31:0] r_extra;')
 s=s.replace('.cfg_row(expected_row),','.cfg_laser_b(cfg_laser_b),.cfg_row(expected_row),')
 s=s.replace('.center_num(r_num),','.center_extra(r_extra),.center_num(r_num),')
 return s
edit('afc03_tile_laser_pipeline.sv',tile)
def pinned(s):
 s=s.replace(' input wire cfg_valid,',' input wire cfg_laser_b,\n input wire cfg_valid,')
 s=s.replace('.cfg_valid(tile_cfg_valid),','.cfg_laser_b(cfg_laser_b),.cfg_valid(tile_cfg_valid),')
 return s
edit('afc03_pinned_frame_pipeline.sv',pinned)
def board(s):
 s=s.replace('.cfg_valid(o_session_valid),','.cfg_laser_b(job_role[1]),.cfg_valid(o_session_valid),')
 s=s.replace("32'h00050000","32'h00060000")
 # 16 candidates, each two 128-bit beats, plus one row completion.
 s=s.replace('({', '({')
 s=s.replace('column_span*3','column_span*33').replace('cols_span*3','cols_span*33')
 return s
edit('afc03_laser_board_top.sv',board)
edit('afc03_laser_csr_bridge.sv',lambda s:s.replace("32'h00050000","32'h00060000"))
print('Modified candidate RTL; packer/sequencer pending')
