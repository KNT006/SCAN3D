`timescale 1ns/1ps
// Functional full-row composition, in rotated-row coordinates.
// RGB positive-difference max and raw-on max are provided as two uint8 streams.
// Computes Gaussian, median, all peaks, all rejection gates, and up to 2 centers.
// Center is an exact (numerator,denominator) pair; no RK peak selection required.
// Functional prototype: no synthesis/board speed claim. One Gaussian computation
// feeds both the peak detector and a clearly derived precomputed evaluator.
module laser_full_row_core #(
    parameter MAX_WIDTH=2048, parameter MAX_PEAKS=256
)(
    input wire clk,rst_n,
    input wire sample_we,input wire [11:0] sample_addr,
    input wire [7:0] signal_value,rawmax_value,
    input wire start,input wire [11:0] width,roi_left,roi_right,
    output reg busy,done,error,
    output reg center_valid,input wire center_ready,
    output reg [31:0] center_num,output reg [23:0] center_den,
    output reg [15:0] center_peak32,
    output reg [11:0] center_lo,center_hi,
    output reg [1:0] center_count,
    output wire tie_conflict,
    output reg [31:0] cycles_gaussian,cycles_find,cycles_evaluate,cycles_select,cycles_total
);
    reg [7:0] signal_mem[0:MAX_WIDTH-1];
    reg [11:0] raw_addr;reg [7:0] raw_q;
    wire input_accept=sample_we&&!busy&&sample_addr<MAX_WIDTH;
    reg input_invalid;
    always @(posedge clk)begin
        if(input_accept)signal_mem[sample_addr]<=signal_value;
        raw_q<=signal_mem[raw_addr];
    end
    reg [11:0] row_width,left,right,gx;
    reg [2:0] tap;reg[12:0] sum;
    wire[12:0] term=(tap==2)?{5'b0,raw_q}*6:
                               ((tap==1||tap==3)?{5'b0,raw_q}*4:{5'b0,raw_q});
    reg smooth_we,front_start,eval_start;
    reg[11:0] smooth_addr,smooth_value;
    wire front_busy,front_done,front_error,front_fallback,front_valid;
    wire[13:0] base32;wire[11:0] front_x,front_count;
    laser_peak_frontend #(.MAX_WIDTH(MAX_WIDTH),.TIE_POLICY(1)) front(
        .clk(clk),.rst_n(rst_n),.sample_we(smooth_we),.sample_addr(smooth_addr),.sample16(smooth_value),
        .start(front_start),.width(row_width),.roi_left(left),.roi_right(right),
        .busy(front_busy),.done(front_done),.error(front_error),.fallback(front_fallback),
        .tie_conflict(tie_conflict),.base32(base32),.peak_valid(front_valid),.peak_x(front_x),
        .peak_ready(1'b1),.peak_count(front_count));
    reg [8:0] peak_write_index;
    wire eval_busy,eval_done,eval_error,eval_valid;wire[127:0] eval_record;
    // Synthetic one-channel on/off encodes exactly the existing evaluator's
    // dmax=signal and omax=rawmax, without altering its tested implementation.
    wire[7:0] encoded_off=rawmax_value-signal_value;
    laser_row_evaluator_precomputed #(.MAX_WIDTH(MAX_WIDTH),.MAX_PEAKS(MAX_PEAKS),.PRECOMPUTED(1)) evaluator(
        .clk(clk),.rst_n(rst_n),.pixel_we(input_accept),.pixel_addr(sample_addr),
        .pixel_on({16'b0,rawmax_value}),.pixel_off({16'b0,encoded_off}),
        .precomputed_we(smooth_we),.precomputed_addr(smooth_addr),.precomputed_smooth(smooth_value),
        .peak_we(front_valid),.peak_addr(peak_write_index[7:0]),.peak_value(front_x),
        .start(eval_start),.width(row_width),.roi_left(left),.roi_right(right),
        .base32(base32),.peak_count(front_count[8:0]),.busy(eval_busy),.done(eval_done),
        .error(eval_error),.result_data(eval_record),.result_valid(eval_valid),.result_ready(1'b1));
    reg [127:0] accepted[0:MAX_PEAKS-1];
    reg[127:0] record_q,best_record,second_record,send_second;
    reg [8:0] accepted_count,scan;
    reg have_best,have_second;
    reg[55:0] product_a,product_b;reg[50:0] separation_limit;
    reg disjoint;
    wire[55:0] product_difference=(product_a>=product_b)?product_a-product_b:product_b-product_a;
    wire[15:0] record_score=record_q[71:56];
    always @(posedge clk)record_q<=accepted[scan];
    localparam IDLE=0,WAIT_RAW=1,GAUSS=2,FRONT_START=3,FRONT_WAIT=4,
       EVAL_WAIT=5,READ_RECORD=6,WAIT_RECORD=7,MULTIPLY=8,COMPARE=9,
       NEXT_RECORD=10,SORT_MULTIPLY=11,SORT_OUTPUT=12,SEND_FIRST=13,SEND_SECOND=14;
    reg[3:0] state;
    reg[31:0] ticks,t_gauss,t_find,t_eval;
    function [11:0] reflect101;
        input integer x;input [11:0] w;
        begin
            if(x<0)reflect101=-x;
            else if(x>=w)reflect101=2*w-2-x;
            else reflect101=x;
        end
    endfunction
    task read_raw;
        input[11:0] address;
        begin raw_addr<=address;state<=WAIT_RAW;end
    endtask
    task load_output;
        input[127:0] r;
        begin
            center_num<=r[31:0];center_den<=r[55:32];center_peak32<={1'b1,6'd0,r[120:112]};
            center_lo<=r[83:72];center_hi<=r[95:84];center_valid<=1;
        end
    endtask
    task finish;
        begin busy<=0;done<=1;cycles_total<=ticks+1;state<=IDLE;end
    endtask
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)begin
            state<=IDLE;busy<=0;done<=0;error<=0;center_valid<=0;center_count<=0;
            center_num<=0;center_den<=0;center_peak32<=0;center_lo<=0;center_hi<=0;
            cycles_gaussian<=0;cycles_find<=0;cycles_evaluate<=0;cycles_select<=0;cycles_total<=0;
            ticks<=0;t_gauss<=0;t_find<=0;t_eval<=0;row_width<=0;left<=0;right<=0;
            gx<=0;tap<=0;sum<=0;raw_addr<=0;smooth_we<=0;smooth_addr<=0;smooth_value<=0;
            front_start<=0;eval_start<=0;peak_write_index<=0;accepted_count<=0;scan<=0;
            best_record<=0;second_record<=0;send_second<=0;have_best<=0;have_second<=0;
            product_a<=0;product_b<=0;separation_limit<=0;disjoint<=0;input_invalid<=0;
        end else begin
            done<=0;smooth_we<=0;front_start<=0;eval_start<=0;
            if(input_accept && signal_value>rawmax_value)input_invalid<=1;
            if(busy)ticks<=ticks+1;
            if(front_valid)peak_write_index<=peak_write_index+1;
            if(state==EVAL_WAIT && eval_valid && eval_record[111:108]==0)begin
                accepted[accepted_count]<=eval_record;accepted_count<=accepted_count+1;
                if(!have_best || eval_record[71:56]>best_record[71:56])begin
                    have_best<=1;best_record<=eval_record;
                end
            end
            case(state)
            IDLE:if(start)begin
                error<=0;center_count<=0;center_valid<=0;peak_write_index<=0;
                accepted_count<=0;have_best<=0;have_second<=0;best_record<=0;second_record<=0;scan<=0;
                ticks<=0;t_gauss<=0;t_find<=0;t_eval<=0;cycles_gaussian<=0;cycles_find<=0;
                cycles_evaluate<=0;cycles_select<=0;cycles_total<=0;
                if(width<3||width>MAX_WIDTH||roi_left>=roi_right||roi_right>=width||input_invalid)begin
                    error<=1;done<=1;input_invalid<=0;
                end else begin
                    busy<=1;row_width<=width;left<=roi_left;right<=roi_right;
                    gx<=0;tap<=0;sum<=0;read_raw(12'd2);
                end
            end
            WAIT_RAW:state<=GAUSS;
            GAUSS:begin
                if(tap==4)begin
                    smooth_we<=1;smooth_addr<=gx;smooth_value<=sum+term;
                    if(gx==row_width-1)state<=FRONT_START;
                    else begin
                        gx<=gx+1;tap<=0;sum<=0;
                        read_raw(reflect101($signed({1'b0,gx})-1,row_width));
                    end
                end else begin
                    sum<=sum+term;tap<=tap+1;
                    read_raw(reflect101($signed({1'b0,gx})+$signed({1'b0,tap})-1,row_width));
                end
            end
            FRONT_START:begin
                front_start<=1;t_gauss<=ticks;cycles_gaussian<=ticks;
                state<=FRONT_WAIT;
            end
            FRONT_WAIT:if(front_done)begin
                t_find<=ticks;cycles_find<=ticks-t_gauss;
                if(front_error||front_fallback||front_count>MAX_PEAKS)begin error<=1;finish;end
                else begin eval_start<=1;state<=EVAL_WAIT;end
            end
            EVAL_WAIT:if(eval_done)begin
                t_eval<=ticks;cycles_evaluate<=ticks-t_find;
                if(eval_error)begin error<=1;finish;end
                else if(!have_best)begin cycles_select<=0;finish;end
                else begin scan<=0;state<=READ_RECORD;end
            end
            READ_RECORD:begin
                if(scan==accepted_count)state<=SORT_MULTIPLY;
                else state<=WAIT_RECORD;
            end
            WAIT_RECORD:state<=MULTIPLY;
            MULTIPLY:begin
                product_a<=record_q[31:0]*best_record[55:32];
                product_b<=best_record[31:0]*record_q[55:32];
                separation_limit<=({3'b0,best_record[55:32]}*{3'b0,record_q[55:32]})<<3;
                disjoint<=(record_q[95:84]<best_record[83:72] || record_q[83:72]>best_record[95:84]);
                state<=COMPARE;
            end
            COMPARE:begin
                if(disjoint && product_difference>=separation_limit &&
                   (!have_second || record_score>second_record[71:56]))begin
                    have_second<=1;second_record<=record_q;
                end
                state<=NEXT_RECORD;
            end
            NEXT_RECORD:begin scan<=scan+1;state<=READ_RECORD;end
            SORT_MULTIPLY:begin
                product_a<=best_record[31:0]*second_record[55:32];
                product_b<=second_record[31:0]*best_record[55:32];state<=SORT_OUTPUT;
            end
            SORT_OUTPUT:begin
                cycles_select<=ticks-t_eval;center_count<=have_second?2:1;
                if(!have_second || product_a<=product_b)begin load_output(best_record);send_second<=second_record;end
                else begin load_output(second_record);send_second<=best_record;end
                state<=SEND_FIRST;
            end
            SEND_FIRST:if(center_ready)begin
                if(have_second)begin load_output(send_second);state<=SEND_SECOND;end
                else begin center_valid<=0;finish;end
            end
            SEND_SECOND:if(center_ready)begin center_valid<=0;finish;end
            default:begin center_valid<=0;error<=1;finish;end
            endcase
        end
    end
endmodule
