`timescale 1ns/1ps
// Bring-up BIST, not a throughput benchmark. AXI4, one outstanding full beat.
// Writes entire region then reads it, with address-derived data and complement.
// start must be a pulse. No automatic writes after reset. Dedicated DDR region.
// A fault latches until reset: resetting this master also requires resetting or
// draining the downstream controller, because a timed-out AXI request may exist.
module ddr_axi_bist #(
    parameter integer DATA_WIDTH=128,
    parameter integer ADDR_WIDTH=32,
    parameter integer WORDS=4096,
    parameter [ADDR_WIDTH-1:0] BASE_ADDR=0,
    parameter integer TIMEOUT_CYCLES=1000000
)(
    input wire clk, rst_n, start, init_done,
    input wire [7:0] init_error,
    output reg busy, done, passed,
    output reg [3:0] fault,
    output reg [31:0] writes, reads,
    output reg [ADDR_WIDTH-1:0] first_bad_addr,
    output reg [DATA_WIDTH-1:0] expected_data, observed_data,
    output wire [ADDR_WIDTH-1:0] awaddr,
    output wire [7:0] awlen,
    output wire [2:0] awsize,
    output wire [1:0] awburst,
    output wire awvalid, input wire awready,
    output wire [DATA_WIDTH-1:0] wdata,
    output wire [DATA_WIDTH/8-1:0] wstrb,
    output wire wlast, wvalid, input wire wready,
    input wire [1:0] bresp, input wire bvalid, output wire bready,
    output wire [ADDR_WIDTH-1:0] araddr,
    output wire [7:0] arlen,
    output wire [2:0] arsize,
    output wire [1:0] arburst,
    output wire arvalid, input wire arready,
    input wire [DATA_WIDTH-1:0] rdata,
    input wire [1:0] rresp, input wire rlast, rvalid,
    output wire rready
);
    localparam IDLE=0, INIT=1, WRITE=2, BRESP=3, READ_ADDR=4,
               READ_DATA=5, COMPLETE=6, FAILED=7;
    localparam integer BYTES=DATA_WIDTH/8;
    reg [2:0] state;
    reg [31:0] word_index, watchdog;
    reg phase, addr_sent, data_sent;
    wire [ADDR_WIDTH-1:0] address=BASE_ADDR+word_index*BYTES;
    wire active=(state>=WRITE && state<=READ_DATA);
    wire usable=init_done && init_error==0;
    wire progress=(awvalid&&awready)||(wvalid&&wready)||
                  (bvalid&&bready)||(arvalid&&arready)||(rvalid&&rready);
    function [DATA_WIDTH-1:0] pattern;
        input [31:0] index;
        input invert;
        integer lane;
        reg [31:0] v;
        begin
            for(lane=0;lane<DATA_WIDTH/32;lane=lane+1) begin
                v=index ^ (32'h9e3779b9*(lane+1));
                pattern[lane*32+:32]=invert ? ~v : v;
            end
        end
    endfunction
    assign awaddr=address;
    assign awlen=0;
    assign awsize=$clog2(BYTES);
    assign awburst=2'b01;
    assign awvalid=state==WRITE && !addr_sent && usable;
    assign wdata=pattern(word_index,phase);
    assign wstrb={BYTES{1'b1}};
    assign wlast=1;
    assign wvalid=state==WRITE && !data_sent && usable;
    assign bready=state==BRESP && usable;
    assign araddr=address;
    assign arlen=0;
    assign arsize=$clog2(BYTES);
    assign arburst=2'b01;
    assign arvalid=state==READ_ADDR && usable;
    assign rready=state==READ_DATA && usable;
    task fail;
        input [3:0] code;
        begin
            fault<=code; busy<=0; done<=1; passed<=0; state<=FAILED;
            first_bad_addr<=address;
            expected_data<=pattern(word_index,phase); observed_data<=rdata;
        end
    endtask
    always @(posedge clk) begin
        if(!rst_n) begin
            state<=IDLE;busy<=0;done<=0;passed<=0;fault<=0;
            writes<=0;reads<=0;word_index<=0;watchdog<=0;phase<=0;
            addr_sent<=0;data_sent<=0;first_bad_addr<=0;
            expected_data<=0;observed_data<=0;
        end else begin
            if(busy) begin
                if(progress) watchdog<=0;
                else watchdog<=watchdog+1;
            end
            if(busy && init_error!=0) fail(1);
            else if(active && !init_done) fail(2);
            else if(busy && !progress && watchdog>=TIMEOUT_CYCLES-1) fail(3);
            else case(state)
                IDLE,COMPLETE: if(start) begin
                    busy<=1;done<=0;passed<=0;fault<=0;
                    writes<=0;reads<=0;word_index<=0;phase<=0;watchdog<=0;
                    addr_sent<=0;data_sent<=0;state<=INIT;
                end
                INIT: if(usable) begin state<=WRITE;watchdog<=0;end
                WRITE: begin
                    if(awvalid&&awready) addr_sent<=1;
                    if(wvalid&&wready) data_sent<=1;
                    if((addr_sent||(awvalid&&awready)) &&
                       (data_sent||(wvalid&&wready))) state<=BRESP;
                end
                BRESP: if(bvalid&&bready) begin
                    if(bresp!=0) fail(4);
                    else begin
                        writes<=writes+1;addr_sent<=0;data_sent<=0;
                        if(word_index==WORDS-1) begin word_index<=0;state<=READ_ADDR;end
                        else begin word_index<=word_index+1;state<=WRITE;end
                    end
                end
                READ_ADDR: if(arvalid&&arready) state<=READ_DATA;
                READ_DATA: if(rvalid&&rready) begin
                    if(rresp!=0 || !rlast) fail(5);
                    else if(rdata!=pattern(word_index,phase)) fail(6);
                    else begin
                        reads<=reads+1;
                        if(word_index==WORDS-1) begin
                            word_index<=0;
                            if(!phase) begin phase<=1;state<=WRITE;end
                            else begin state<=COMPLETE;busy<=0;done<=1;passed<=1;end
                        end else begin word_index<=word_index+1;state<=READ_ADDR;end
                    end
                end
                FAILED: begin end
                default: begin end
            endcase
        end
    end
endmodule
