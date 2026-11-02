`timescale 1ns/1ps
// Exactly one owner may be selected per COMMON DDR reset. Completion, timeout,
// deasserted VALID or !busy never authorizes changing an already selected owner.
module afc03_axi_owner_lock #(parameter ADDR_WIDTH=28)(
 input wire clk,reset_n,control_ready,
 input wire select_valid,output wire select_ready,input wire [1:0] select_owner,
 output reg select_result_valid,input wire select_result_ready,
 output reg select_result_ok,output reg [3:0] select_result_error,
 output reg [1:0] owner,
 output wire external_enabled,bist_enabled,
 output reg [4:0] response_faults,
 output reg [3:0] last_bid,last_rid,
 output reg [1:0] last_bresp,last_rresp,
input wire [4-1:0] b_awid,
input wire [ADDR_WIDTH-1:0] b_awaddr,
input wire [8-1:0] b_awlen,
input wire [3-1:0] b_awsize,
input wire [2-1:0] b_awburst,
input wire  b_awvalid,
input wire [128-1:0] b_wdata,
input wire [16-1:0] b_wstrb,
input wire  b_wlast,
input wire  b_wvalid,
input wire  b_bready,
input wire [4-1:0] b_arid,
input wire [ADDR_WIDTH-1:0] b_araddr,
input wire [8-1:0] b_arlen,
input wire [3-1:0] b_arsize,
input wire [2-1:0] b_arburst,
input wire  b_arvalid,
input wire  b_rready,
output wire  b_awready,
output wire  b_wready,
output wire [4-1:0] b_bid,
output wire [2-1:0] b_bresp,
output wire  b_bvalid,
output wire  b_arready,
output wire [4-1:0] b_rid,
output wire [128-1:0] b_rdata,
output wire [2-1:0] b_rresp,
output wire  b_rlast,
output wire  b_rvalid,
input wire [4-1:0] e_awid,
input wire [ADDR_WIDTH-1:0] e_awaddr,
input wire [8-1:0] e_awlen,
input wire [3-1:0] e_awsize,
input wire [2-1:0] e_awburst,
input wire  e_awvalid,
input wire [128-1:0] e_wdata,
input wire [16-1:0] e_wstrb,
input wire  e_wlast,
input wire  e_wvalid,
input wire  e_bready,
input wire [4-1:0] e_arid,
input wire [ADDR_WIDTH-1:0] e_araddr,
input wire [8-1:0] e_arlen,
input wire [3-1:0] e_arsize,
input wire [2-1:0] e_arburst,
input wire  e_arvalid,
input wire  e_rready,
output wire  e_awready,
output wire  e_wready,
output wire [4-1:0] e_bid,
output wire [2-1:0] e_bresp,
output wire  e_bvalid,
output wire  e_arready,
output wire [4-1:0] e_rid,
output wire [128-1:0] e_rdata,
output wire [2-1:0] e_rresp,
output wire  e_rlast,
output wire  e_rvalid,
output wire [4-1:0] m_awid,
output wire [ADDR_WIDTH-1:0] m_awaddr,
output wire [8-1:0] m_awlen,
output wire [3-1:0] m_awsize,
output wire [2-1:0] m_awburst,
output wire  m_awvalid,
output wire [128-1:0] m_wdata,
output wire [16-1:0] m_wstrb,
output wire  m_wlast,
output wire  m_wvalid,
output wire  m_bready,
output wire [4-1:0] m_arid,
output wire [ADDR_WIDTH-1:0] m_araddr,
output wire [8-1:0] m_arlen,
output wire [3-1:0] m_arsize,
output wire [2-1:0] m_arburst,
output wire  m_arvalid,
output wire  m_rready,
input wire  m_awready,
input wire  m_wready,
input wire [4-1:0] m_bid,
input wire [2-1:0] m_bresp,
input wire  m_bvalid,
input wire  m_arready,
input wire [4-1:0] m_rid,
input wire [128-1:0] m_rdata,
input wire [2-1:0] m_rresp,
input wire  m_rlast,
input wire  m_rvalid
);
localparam NONE=0,BIST=1,EXTERNAL=2;
assign select_ready=reset_n&&!select_result_valid;
assign external_enabled=reset_n&&owner==EXTERNAL;
assign bist_enabled=reset_n&&owner==BIST;
wire offered_request=b_awvalid||b_wvalid||b_arvalid||e_awvalid||e_wvalid||e_arvalid;
wire orphan_response=owner==NONE&&(m_bvalid||m_rvalid);
always @(posedge clk or negedge reset_n)begin
 if(!reset_n)begin
  owner<=NONE;select_result_valid<=0;select_result_ok<=0;select_result_error<=0;
  response_faults<=0;last_bid<=0;last_rid<=0;last_bresp<=0;last_rresp<=0;
 end else begin
  if(select_result_valid&&select_result_ready)select_result_valid<=0;
  if(orphan_response)response_faults[0]<=1;
  if(m_bvalid)begin
   last_bid<=m_bid;last_bresp<=m_bresp;
   if(m_bresp!=0)response_faults[1]<=1;
   if(owner==BIST&&m_bid!=0)response_faults[3]<=1;
  end
  if(m_rvalid)begin
   last_rid<=m_rid;last_rresp<=m_rresp;
   if(m_rresp!=0)response_faults[2]<=1;
   if(owner==BIST&&m_rid!=0)response_faults[4]<=1;
  end
  if(select_valid&&select_ready)begin
   select_result_valid<=1;select_result_ok<=0;
   if(owner!=NONE)select_result_error<=4'd1; // locked until common reset
   else if(!control_ready)select_result_error<=4'd2;
   else if(select_owner!=BIST&&select_owner!=EXTERNAL)select_result_error<=4'd3;
   else if(offered_request||orphan_response||response_faults[0])select_result_error<=4'd4;
   else begin owner<=select_owner;select_result_ok<=1;select_result_error<=0;end
  end
 end
end
assign m_awid=bist_enabled?b_awid:external_enabled?e_awid:4'd0;
assign m_awaddr=bist_enabled?b_awaddr:external_enabled?e_awaddr:{ADDR_WIDTH{1'b0}};
assign m_awlen=bist_enabled?b_awlen:external_enabled?e_awlen:8'd0;
assign m_awsize=bist_enabled?b_awsize:external_enabled?e_awsize:3'd0;
assign m_awburst=bist_enabled?b_awburst:external_enabled?e_awburst:2'd0;
assign m_awvalid=bist_enabled?b_awvalid:external_enabled?e_awvalid:1'd0;
assign m_wdata=bist_enabled?b_wdata:external_enabled?e_wdata:128'd0;
assign m_wstrb=bist_enabled?b_wstrb:external_enabled?e_wstrb:16'd0;
assign m_wlast=bist_enabled?b_wlast:external_enabled?e_wlast:1'd0;
assign m_wvalid=bist_enabled?b_wvalid:external_enabled?e_wvalid:1'd0;
assign m_bready=bist_enabled?b_bready:external_enabled?e_bready:1'd0;
assign m_arid=bist_enabled?b_arid:external_enabled?e_arid:4'd0;
assign m_araddr=bist_enabled?b_araddr:external_enabled?e_araddr:{ADDR_WIDTH{1'b0}};
assign m_arlen=bist_enabled?b_arlen:external_enabled?e_arlen:8'd0;
assign m_arsize=bist_enabled?b_arsize:external_enabled?e_arsize:3'd0;
assign m_arburst=bist_enabled?b_arburst:external_enabled?e_arburst:2'd0;
assign m_arvalid=bist_enabled?b_arvalid:external_enabled?e_arvalid:1'd0;
assign m_rready=bist_enabled?b_rready:external_enabled?e_rready:1'd0;
assign b_awready=bist_enabled?m_awready:1'd0;
assign b_wready=bist_enabled?m_wready:1'd0;
assign b_bid=bist_enabled?m_bid:4'd0;
assign b_bresp=bist_enabled?m_bresp:2'd0;
assign b_bvalid=bist_enabled?m_bvalid:1'd0;
assign b_arready=bist_enabled?m_arready:1'd0;
assign b_rid=bist_enabled?m_rid:4'd0;
assign b_rdata=bist_enabled?m_rdata:128'd0;
assign b_rresp=bist_enabled?m_rresp:2'd0;
assign b_rlast=bist_enabled?m_rlast:1'd0;
assign b_rvalid=bist_enabled?m_rvalid:1'd0;
assign e_awready=external_enabled?m_awready:1'd0;
assign e_wready=external_enabled?m_wready:1'd0;
assign e_bid=external_enabled?m_bid:4'd0;
assign e_bresp=external_enabled?m_bresp:2'd0;
assign e_bvalid=external_enabled?m_bvalid:1'd0;
assign e_arready=external_enabled?m_arready:1'd0;
assign e_rid=external_enabled?m_rid:4'd0;
assign e_rdata=external_enabled?m_rdata:128'd0;
assign e_rresp=external_enabled?m_rresp:2'd0;
assign e_rlast=external_enabled?m_rlast:1'd0;
assign e_rvalid=external_enabled?m_rvalid:1'd0;
endmodule
