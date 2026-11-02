`timescale 1ns/1ps
// One immutable result packet; descriptor-sized padding avoids short-read ambiguity.
// Backpressure retains every byte; no new START can overwrite the source RAM.
module afc03_result_dma # (parameter PACKET_BEATS=4096)(
 input wire dclk,hclk,reset_n,
 input wire start_valid,output wire start_ready,
 input wire [1023:0] header,input wire [31:0] records,
 output wire ram_read,output wire [10:0] ram_address,input wire [127:0] ram_data,
 output wire busy,
 output wire [127:0] m_data,output wire m_valid,input wire m_ready,output wire m_last
);
 localparam IDLE=0,HEAD=1,READ=2,WAIT_RAM=3,DATA=4,PAD=5;
 reg [2:0] state;
 reg [1023:0] saved_header;
 reg [11:0] beat;
 reg [31:0] count,index;
 wire wr_online,rd_online,ready;
 wire valid=state==HEAD||state==DATA||state==PAD;
 wire [127:0] data=state==HEAD?saved_header[127:0]:state==DATA?ram_data:128'd0;
 wire last=beat==PACKET_BEATS-1;
 wire [128:0] fifo_data;
 (* async_reg="true" *) reg [1:0] release_pipe;
 always @(posedge dclk or negedge reset_n)
  if(!reset_n)release_pipe<=0;else release_pipe<={release_pipe[0],1'b1};
 assign busy=state!=IDLE;
 assign start_ready=state==IDLE&&wr_online;
 assign ram_read=state==READ;
 assign ram_address=index[10:0];
 afc03_frame_async_fifo #(.WIDTH(129),.ADDR_BITS(4)) queue(
  .reset_n(reset_n),.write_clk(dclk),.s_valid(valid),.s_ready(ready),.s_data({last,data}),
  .read_clk(hclk),.m_valid(m_valid),.m_ready(m_ready),.m_data(fifo_data),
  .write_online(wr_online),.read_online(rd_online));
 assign {m_last,m_data}=fifo_data;
 always @(posedge dclk or negedge release_pipe[1])begin
  if(!release_pipe[1])begin state<=IDLE;saved_header<=0;beat<=0;count<=0;index<=0;end
  else case(state)
   IDLE:if(start_valid&&start_ready)begin
    saved_header<=header;count<=records;index<=0;beat<=0;state<=HEAD;
   end
   HEAD:if(valid&&ready)begin
    saved_header<=saved_header>>128;beat<=beat+1'b1;
    if(beat==7)state<=count==0?PAD:READ;
   end
   READ:state<=WAIT_RAM;
   WAIT_RAM:state<=DATA;
   DATA:if(valid&&ready)begin
    index<=index+1'b1;beat<=beat+1'b1;
    state<=index+1==count?PAD:READ;
   end
   PAD:if(valid&&ready)begin
    if(last)state<=IDLE;else beat<=beat+1'b1;
   end
   default:state<=IDLE;
  endcase
 end
endmodule
