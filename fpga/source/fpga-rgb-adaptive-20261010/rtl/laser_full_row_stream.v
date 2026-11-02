`timescale 1ns/1ps
// Checked row adapter for afc03_diff_tile_transpose's CW90 pixel stream.
// Caller cfg is the expected transaction, not metadata guessed from pixels.
// Complete source-frame commit must already have been checked upstream.
// Each accepted row writes exactly width samples in order before start.
module laser_full_row_stream #(
    parameter MAX_WIDTH=2048, parameter MAX_PEAKS=256,
    parameter INPUT_TIMEOUT=1000000, parameter CORE_TIMEOUT=10000000
)(
    input wire clk,rst_n,abort,
    input wire cfg_laser_b,output wire [31:0] center_extra,
    input wire cfg_valid,output wire cfg_ready,
    input wire[11:0] cfg_width,cfg_roi_left,cfg_roi_right,
    input wire[12:0] cfg_row,cfg_global_x_origin,
    input wire[31:0] cfg_frame_id,cfg_background_generation,cfg_geometry,cfg_request_id,
    input wire s_valid,output wire s_ready,
    input wire[7:0] s_signal,s_rawmax,
    input wire[11:0] s_local_x,s_width,
    input wire[12:0] s_row,s_global_x_origin,
    input wire s_sof,s_eol,
    input wire[31:0] s_frame_id,s_background_generation,s_geometry,s_request_id,
    output wire center_valid,input wire center_ready,
    output wire[31:0] center_num,output wire[23:0] center_den,
    output wire[15:0] center_peak32,output wire[11:0] center_lo,center_hi,
    output wire row_done_valid,input wire row_done_ready,
    output reg[4:0] row_center_count,output reg row_tie_conflict,
    output reg[15:0] row_error,
    output wire[7:0] row_record_error,
    output reg[12:0] row_id,global_x_origin,
    output reg[31:0] frame_id,background_generation,geometry,request_id,
    output reg[31:0] row_cycles,
    output wire busy
);
    localparam IDLE=0,ARM=1,FILL=2,GAP=3,START=4,RUN=5,COMPLETE=6;
    localparam[15:0] E_CONFIG=16'h0001,E_COORD=16'h0002,E_ID=16'h0004,
        E_MARKER=16'h0008,E_VALUE=16'h0010,E_INPUT_TIMEOUT=16'h0020,
        E_CORE=16'h0040,E_CORE_TIMEOUT=16'h0080,E_ABORT=16'h0100;
    reg[2:0] state;
    reg[11:0] width,left,right,next_x;
    reg core_release,laser_b;
    reg[31:0] idle_cycles,run_cycles;
    reg[4:0] sent_centers;
    wire cfg_bad=cfg_width<3||cfg_width>MAX_WIDTH||
        cfg_roi_left>=cfg_roi_right||cfg_roi_right>=cfg_width||
        cfg_background_generation==0;
    reg[15:0] beat_error;
    always @* begin
        beat_error=0;
        if(s_local_x!=next_x||s_width!=width||s_row!=row_id||s_global_x_origin!=global_x_origin)
            beat_error=beat_error|E_COORD;
        if(s_frame_id!=frame_id||s_background_generation!=background_generation||
           s_geometry!=geometry||s_request_id!=request_id)beat_error=beat_error|E_ID;
        if(s_sof!=(next_x==0)||s_eol!=(next_x==width-1'b1))beat_error=beat_error|E_MARKER;
        if(s_signal>s_rawmax)beat_error=beat_error|E_VALUE;
    end
    assign cfg_ready=rst_n&&!abort&&state==IDLE;
    assign s_ready=rst_n&&!abort&&state==FILL;
    assign busy=state!=IDLE;
    assign row_done_valid=rst_n&&state==COMPLETE;
    // Existing RowDone has only an 8-bit error field. Never truncate a nonzero
    // high-bit reason (e.g. abort) to success. Full diagnostic stays row_error.
    assign row_record_error=row_error[7:0]|{7'b0,(|row_error[15:8])};
    wire pixel_fire=s_valid&&s_ready;
    wire core_sample_we=pixel_fire&&beat_error==0;
    wire core_start=rst_n&&!abort&&state==START;
    wire core_reset_n=rst_n&&core_release;
    wire core_busy,core_done,core_error,core_valid,core_tie;
    wire[4:0] core_count;
    wire[31:0] core_cycles;
    assign center_valid=rst_n&&!abort&&state==RUN&&core_valid;
    laser_full_row_core #(.MAX_WIDTH(MAX_WIDTH),.MAX_PEAKS(MAX_PEAKS)) core(
        .laser_b(laser_b),.row_id(row_id),.center_extra(center_extra),
        .clk(clk),.rst_n(core_reset_n),.sample_we(core_sample_we),.sample_addr(s_local_x),
        .signal_value(s_signal),.rawmax_value(s_rawmax),.start(core_start),
        .width(width),.roi_left(left),.roi_right(right),.busy(core_busy),.done(core_done),.error(core_error),
        .center_valid(core_valid),.center_ready(center_ready&&state==RUN&&!abort),
        .center_num(center_num),.center_den(center_den),.center_peak32(center_peak32),
        .center_lo(center_lo),.center_hi(center_hi),.center_count(core_count),.tie_conflict(core_tie),
        .cycles_gaussian(),.cycles_find(),.cycles_evaluate(),.cycles_select(),.cycles_total(core_cycles));
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)begin
            state<=IDLE;laser_b<=0;core_release<=0;width<=0;left<=0;right<=0;next_x<=0;
            idle_cycles<=0;run_cycles<=0;sent_centers<=0;
            row_center_count<=0;row_tie_conflict<=0;row_error<=0;row_cycles<=0;
            row_id<=0;global_x_origin<=0;frame_id<=0;background_generation<=0;geometry<=0;request_id<=0;
        end else begin
            if(abort&&state!=IDLE&&state!=COMPLETE)begin
                core_release<=0;row_error<=E_ABORT;row_center_count<=sent_centers;
                row_cycles<=run_cycles;state<=COMPLETE;
            end else case(state)
                IDLE:if(cfg_valid&&cfg_ready)begin
                    width<=cfg_width;left<=cfg_roi_left;right<=cfg_roi_right;next_x<=0;
                    row_id<=cfg_row;global_x_origin<=cfg_global_x_origin;
                    laser_b<=cfg_laser_b;frame_id<=cfg_frame_id;background_generation<=cfg_background_generation;
                    geometry<=cfg_geometry;request_id<=cfg_request_id;
                    row_error<=0;row_cycles<=0;row_center_count<=0;row_tie_conflict<=0;
                    idle_cycles<=0;run_cycles<=0;sent_centers<=0;core_release<=0;
                    if(cfg_bad)begin row_error<=E_CONFIG;state<=COMPLETE;end
                    else state<=ARM;
                end
                ARM:begin core_release<=1;state<=FILL;end
                FILL:begin
                    if(pixel_fire)begin
                        idle_cycles<=0;
                        if(beat_error!=0)begin row_error<=beat_error;core_release<=0;state<=COMPLETE;end
                        else if(next_x==width-1'b1)state<=GAP;
                        else next_x<=next_x+1'b1;
                    end else if(idle_cycles>=INPUT_TIMEOUT-1)begin
                        row_error<=E_INPUT_TIMEOUT;core_release<=0;state<=COMPLETE;
                    end else idle_cycles<=idle_cycles+1'b1;
                end
                // Last sample was written entering GAP. No sample write and
                // no start here; core sees start at the following START edge.
                GAP:state<=START;
                START:begin state<=RUN;run_cycles<=0;end
                RUN:begin
                    run_cycles<=run_cycles+1'b1;
                    if(center_valid&&center_ready)sent_centers<=sent_centers+1'b1;
                    if(core_done)begin
                        row_error<=core_error?E_CORE:16'h0;row_cycles<=core_cycles;
                        row_center_count<=core_count;row_tie_conflict<=core_tie;state<=COMPLETE;
                    end else if(run_cycles>=CORE_TIMEOUT-1)begin
                        row_error<=E_CORE_TIMEOUT;row_cycles<=run_cycles;
                        row_center_count<=sent_centers+((center_valid&&center_ready)?2'd1:2'd0);
                        core_release<=0;state<=COMPLETE;
                    end
                end
                COMPLETE:if(row_done_valid&&row_done_ready)begin state<=IDLE;core_release<=0;end
                default:begin state<=IDLE;core_release<=0;end
            endcase
        end
    end
endmodule
