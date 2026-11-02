`timescale 1ns/1ps
// Data and all pixel identity/geometry metadata travel in ONE opaque word.
// reset_n must assert for BOTH domains together. A reset discards all queued
// words; the owner must invalidate the frame/background and change its epoch.
// Physical integration MUST constrain Gray-pointer flight to < the faster
// source/destination period and keep the two synchronizer stages adjacent.
module afc03_frame_async_fifo #(
    parameter WIDTH=288,
    parameter ADDR_BITS=8
)(
    input wire reset_n,
    input wire write_clk,
    input wire s_valid,
    output wire s_ready,
    input wire [WIDTH-1:0] s_data,
    input wire read_clk,
    output reg m_valid,
    input wire m_ready,
    output reg [WIDTH-1:0] m_data,
    output wire write_online,
    output wire read_online
);
    localparam DEPTH=1<<ADDR_BITS;
    // Shallow, wide mailboxes otherwise consume one whole ERAM per 36 bits.
    // Keep their exact storage/read timing, while leaving ERAM for deep buffers.
    // Values are the vendor APM_MEMORY ram_style spellings (auto / dram).
    localparam MEMORY_STYLE=(ADDR_BITS<=4)?"dram":"auto";
    (* ram_style=MEMORY_STYLE *) reg [WIDTH-1:0] memory[0:DEPTH-1];
    (* async_reg="true" *) reg [1:0] write_release,read_release;
    (* async_reg="true" *) reg [1:0] reader_up_sync,writer_up_sync;
    (* async_reg="true" *) reg [ADDR_BITS:0] read_gray_meta,read_gray_sync;
    (* async_reg="true" *) reg [ADDR_BITS:0] write_gray_meta,write_gray_sync;
    // Only these two release chains see the external asynchronous reset.
    // All functional state releases reset synchronously in its own domain,
    // including when the other clock was stopped during reset assertion.
    wire write_reset_n=write_release[1];
    wire read_reset_n=read_release[1];
    reg [ADDR_BITS:0] write_binary,write_gray,read_binary,read_gray;
    reg full;
    wire push=s_valid&&s_ready;
    wire empty=(read_gray==write_gray_sync);
    wire prefetch=read_online&&!empty&&(!m_valid||m_ready);
    wire [ADDR_BITS:0] next_write_binary=write_binary+push;
    wire [ADDR_BITS:0] next_write_gray=(next_write_binary>>1)^next_write_binary;
    wire [ADDR_BITS:0] next_read_binary=read_binary+1'b1;
    wire [ADDR_BITS:0] next_read_gray=(next_read_binary>>1)^next_read_binary;
    wire [ADDR_BITS:0] full_target=read_gray_sync ^ ((1<<ADDR_BITS)|(1<<(ADDR_BITS-1)));
    assign write_online=write_release[1]&&reader_up_sync[1];
    assign read_online=read_release[1]&&writer_up_sync[1];
    assign s_ready=write_online&&!full;

    // True dual-port, synchronous read, no RAM initialization/reset loop.
    always @(posedge write_clk) if(push)memory[write_binary[ADDR_BITS-1:0]]<=s_data;
    always @(posedge read_clk) if(prefetch)m_data<=memory[read_binary[ADDR_BITS-1:0]];

    always @(posedge write_clk or negedge reset_n) begin
        if(!reset_n)write_release<=0;
        else write_release<={write_release[0],1'b1};
    end
    always @(posedge read_clk or negedge reset_n) begin
        if(!reset_n)read_release<=0;
        else read_release<={read_release[0],1'b1};
    end
    always @(posedge write_clk or negedge write_reset_n) begin
        if(!write_reset_n)begin
            reader_up_sync<=0;read_gray_meta<=0;read_gray_sync<=0;
            write_binary<=0;write_gray<=0;full<=0;
        end else begin
            reader_up_sync<={reader_up_sync[0],read_release[1]};
            read_gray_meta<=read_gray;read_gray_sync<=read_gray_meta;
            if(write_online)begin
                write_binary<=next_write_binary;write_gray<=next_write_gray;
                full<=next_write_gray==full_target;
            end
        end
    end
    always @(posedge read_clk or negedge read_reset_n) begin
        if(!read_reset_n)begin
            writer_up_sync<=0;write_gray_meta<=0;write_gray_sync<=0;
            read_binary<=0;read_gray<=0;m_valid<=0;
        end else begin
            writer_up_sync<={writer_up_sync[0],write_release[1]};
            write_gray_meta<=write_gray;write_gray_sync<=write_gray_meta;
            if(prefetch)begin
                read_binary<=next_read_binary;read_gray<=next_read_gray;m_valid<=1;
            end else if(m_valid&&m_ready) m_valid<=0;
        end
    end
`ifndef SYNTHESIS
    initial begin
        if(ADDR_BITS<1||WIDTH<1)begin $display("invalid FIFO parameters");$finish;end
    end
`endif
endmodule
