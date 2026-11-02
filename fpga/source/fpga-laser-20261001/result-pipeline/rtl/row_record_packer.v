`timescale 1ns/1ps
// Packs the existing row_results.py 16-byte payload records only.
// This module does NOT produce an AFR1/PCIe frame header, footer, CRC or commit.
// An external transaction controller must abort a frame on protocol_fault.
module row_record_packer(
    input wire clk,rst_n,
    input wire row_begin_valid,output wire row_begin_ready,input wire[15:0] row_id,
    input wire center_valid,output wire center_ready,
    input wire[31:0] center_num,input wire[23:0] center_den,
    input wire[15:0] center_peak32,input wire[11:0] center_lo,center_hi,
    input wire row_done,input wire[1:0] row_center_count,
    input wire row_tie_conflict,input wire[7:0] row_error,input wire[31:0] row_cycles,
    output reg[127:0] record_data,output reg record_valid,input wire record_ready,
    output wire[7:0] record_type,
    output reg row_emitted,output wire row_busy,output reg protocol_fault
);
    reg active,closing;
    reg[15:0] held_row;
    reg[1:0] observed_count;
    reg overflow;
    reg[1:0] done_count;
    reg done_tie;
    reg[7:0] done_error;
    reg[31:0] done_cycles;
    wire slot_free=!record_valid||record_ready;
    wire center_fire=center_valid&&center_ready;
    wire[2:0] observed_next={1'b0,observed_count}+(center_fire?3'd1:3'd0);
    wire center_overflow=center_fire&&observed_count>=2;
    wire done_fire=record_valid&&record_ready&&record_type==2;
    assign record_type=record_data[7:0];
    assign row_busy=active;
    assign row_begin_ready=!active&&!record_valid;
    // Contract is at most two centers. An excess center is consumed and marked
    // as a fault so a broken producer cannot deadlock waiting for ready forever.
    assign center_ready=active&&!closing&&slot_free;
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)begin
            active<=0;closing<=0;held_row<=0;observed_count<=0;overflow<=0;
            done_count<=0;done_tie<=0;done_error<=0;done_cycles<=0;
            record_data<=0;record_valid<=0;row_emitted<=0;protocol_fault<=0;
        end else begin
            row_emitted<=0;
            if(row_begin_valid&&row_begin_ready)begin
                active<=1;closing<=0;held_row<=row_id;observed_count<=0;overflow<=0;
            end
            if(record_valid&&record_ready)record_valid<=0;
            if(done_fire)begin
                active<=0;closing<=0;row_emitted<=1;
            end else if(center_fire)begin
                if(observed_count<3)observed_count<=observed_count+1;
                if(observed_count<2)begin
                    // [127:116]hi [115:104]lo [103:88]peak32 [87:64]den
                    // [63:32]num [31:16]row [15:8]index [7:0]type=1.
                    record_data<={center_hi,center_lo,center_peak32,center_den,
                                  center_num,held_row,6'b0,observed_count,8'd1};
                    record_valid<=1;
                end else begin overflow<=1;protocol_fault<=1;end
            end else if(closing&&slot_free)begin
                // Python <BBHBBHII: type,flags,row,count,error,0,cycles,0.
                record_data<={32'b0,done_cycles,16'b0,done_error,6'b0,done_count,
                              held_row,7'b0,done_tie,8'd2};
                record_valid<=1;
            end
            if(row_done)begin
                if(!active||closing)protocol_fault<=1;
                else begin
                    closing<=1;done_count<=row_center_count;done_tie<=row_tie_conflict;done_cycles<=row_cycles;
                    done_error<=row_error|
                        ((observed_next!={1'b0,row_center_count}||row_center_count>2)?8'h40:8'h00)|
                        ((overflow||center_overflow)?8'h20:8'h00);
                    if(observed_next!={1'b0,row_center_count}||row_center_count>2||overflow||center_overflow)
                        protocol_fault<=1;
                end
            end
            // Input after row_done cannot be silently accepted. A late error
            // cannot retract already transmitted records: external frame abort
            // is mandatory, even if the queued RowDone itself was already built.
            if(center_valid&&active&&closing)protocol_fault<=1;
        end
    end
endmodule
