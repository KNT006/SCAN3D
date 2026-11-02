`timescale 1ns/1ps
// Passive, single-outstanding AXI-Lite observer. All multi-bit CDC uses FIFOs.
module afc03_laser_csr_bridge #(parameter HOST_WATCHDOG=125000000, parameter [11:0] PAGE=12'h022, parameter MAX_OPCODE=4)(
 input wire hclk,hrst_n,dclk,drst_n,
 input wire [31:0] host_awaddr,host_wdata,host_araddr,
 input wire [3:0] host_wstrb,
 input wire host_awvalid,host_awready,host_wvalid,host_wready,host_arvalid,host_arready,
 output reg rd_select,output reg [31:0] rd_data,
 output wire [31:0] camera_epoch,
 output wire reset_n,output wire dreset_n,
 output wire command_valid,input wire command_ready,output wire [351:0] command_data,
 input wire response_valid,output wire response_ready,input wire [511:0] response_data
);
 assign reset_n=hrst_n&&drst_n;
 (* async_reg="true", max_fanout=128 *) reg [1:0] hrelease,drelease;
 always @(posedge hclk or negedge reset_n)
  if(!reset_n)hrelease<=0;else hrelease<={hrelease[0],1'b1};
 always @(posedge dclk or negedge reset_n)
  if(!reset_n)drelease<=0;else drelease<={drelease[0],1'b1};
 wire hreset_n=hrelease[1];assign dreset_n=drelease[1];
 (* async_reg="true", max_fanout=128 *) reg [1:0] bus_release;
 always @(posedge hclk or negedge hrst_n)
  if(!hrst_n)bus_release<=0;else bus_release<={bus_release[0],1'b1};
 wire bus_reset_n=bus_release[1];
 reg [31:0] config_words[0:8];reg [31:0] request_id;
 assign camera_epoch=config_words[0];
 reg aw_full,w_full;reg [31:0] saved_aw,saved_w;reg [3:0] saved_strb;
 wire ah=host_awvalid&&host_awready,wh=host_wvalid&&host_wready;
 wire pair=(aw_full||ah)&&(w_full||wh);
 wire [31:0] address=aw_full?saved_aw:host_awaddr;
 wire [31:0] data=w_full?saved_w:host_wdata;
 wire [3:0] strobes=w_full?saved_strb:host_wstrb;
 wire selected=address[19:8]==PAGE;
 reg pair_fault;
 wire pair_overflow=(aw_full&&ah&&!pair)||(w_full&&wh&&!pair);
 // DDR reset must not erase half a host write or an outstanding read mux
 // response. Support simultaneous consume-old / retain-new channel beats.
 always @(posedge hclk or negedge bus_reset_n)begin
  if(!bus_reset_n)begin aw_full<=0;w_full<=0;saved_aw<=0;saved_w<=0;saved_strb<=0;pair_fault<=0;end
  else begin
   if(pair_overflow)pair_fault<=1;
   if(ah)begin saved_aw<=host_awaddr;aw_full<=1;end
   if(wh)begin saved_w<=host_wdata;saved_strb<=host_wstrb;w_full<=1;end
   if(pair)begin aw_full<=aw_full&&ah;w_full<=w_full&&wh;end
  end
 end
 reg pending,command_busy,rejected,watchdog_fault,snapshot_valid,capture_lock;
 reg [31:0] watchdog;reg [351:0] pending_data;reg [511:0] snapshot;
 wire send_ready,send_online,receive_online,receive_valid;
 wire [511:0] receive_data;
 wire bridge_online=send_online&&receive_online;
 wire receive_ready=1'b1; // Drain stale replies even after a latched host timeout.
 afc03_frame_async_fifo #(.WIDTH(352),.ADDR_BITS(1)) commands(
  .reset_n(reset_n),.write_clk(hclk),.s_valid(pending),.s_ready(send_ready),.s_data(pending_data),
  .read_clk(dclk),.m_valid(command_valid),.m_ready(command_ready),.m_data(command_data),
  .write_online(send_online),.read_online());
 afc03_frame_async_fifo #(.WIDTH(512),.ADDR_BITS(1)) responses(
  .reset_n(reset_n),.write_clk(dclk),.s_valid(response_valid),.s_ready(response_ready),.s_data(response_data),
  .read_clk(hclk),.m_valid(receive_valid),.m_ready(receive_ready),.m_data(receive_data),
  .write_online(),.read_online(receive_online));
 integer i;
 always @(posedge hclk or negedge hreset_n)begin
  if(!hreset_n)begin
   for(i=0;i<9;i=i+1)config_words[i]<=0;
   request_id<=0;
   pending<=0;pending_data<=0;command_busy<=0;rejected<=0;watchdog_fault<=0;
   watchdog<=0;snapshot_valid<=0;snapshot<=0;capture_lock<=0;
  end else begin
   if(pending&&send_ready)pending<=0;
   if(command_busy)begin
    if(receive_valid)begin
     snapshot<=receive_data;snapshot_valid<=1;command_busy<=0;watchdog<=0;
     capture_lock<=receive_data[16]; // Coherent DDR snapshot, never a free-running CDC bus.
    end
    else if(watchdog==HOST_WATCHDOG-1)begin
     watchdog_fault<=1;command_busy<=0;snapshot_valid<=0;
     // pending/AXI request is NOT withdrawn: destination must finish/drain.
    end else watchdog<=watchdog+1'b1;
   end
   if(pair&&selected&&!pair_fault&&!pair_overflow)begin
    if(address[1:0]!=0||strobes!=4'hf)rejected<=1;
    else if(address[7:0]==8'h08)begin
     if(data[31:8]!=24'h424700||data[7:0]<1||data[7:0]>MAX_OPCODE||request_id==0||
        !bridge_online||command_busy||pending||watchdog_fault||(data[7:0]==2&&capture_lock))rejected<=1;
     else begin
      pending_data<={config_words[8],config_words[7],config_words[6],config_words[5],
       config_words[4],config_words[3],config_words[2],config_words[1],config_words[0],request_id,data};
      pending<=1;command_busy<=1;snapshot_valid<=0;watchdog<=0;rejected<=0;
      if(data[7:0]==2)capture_lock<=1;
     end
    end else if(address[7:0]==8'h0c)begin
     if(command_busy||pending)rejected<=1;else request_id<=data;
    end else if(address[7:0]>=8'h10&&address[7:0]<=8'h30)begin
     if(command_busy||pending||(capture_lock&&address[7:0]<=8'h2c))rejected<=1;
     else config_words[(address[7:0]-8'h10)>>2]<=data;
    end
   end
  end
 end
 // Parent mux retains rd_select until next accepted AR; data is coherent and
 // stable through R-channel backpressure, independent of new CSR writes.
 always @(posedge hclk or negedge bus_reset_n)begin
  if(!bus_reset_n)begin rd_select<=0;rd_data<=0;end
  else if(host_arvalid&&host_arready)begin
   rd_select<=host_araddr[19:8]==PAGE&&host_araddr[1:0]==0;
   rd_data<=0;
   case(host_araddr[7:0])
    8'h00:rd_data<=32'h42474331;
    8'h04:rd_data<={27'd0,bridge_online,watchdog_fault||pair_fault,rejected,snapshot_valid,command_busy};
    8'h08:rd_data<=(PAGE==12'h024)?32'h00060000:32'h00020000;
    8'h0c:rd_data<=request_id;
    8'h34:rd_data<=(PAGE==12'h024)?32'h9c744450:32'd0;
    8'h38:rd_data<=(PAGE==12'h024)?32'h0046000b:32'd0;
    default:begin
     if(host_araddr[7:0]>=8'h10&&host_araddr[7:0]<=8'h30&&host_araddr[1:0]==0)
      rd_data<=config_words[(host_araddr[7:0]-8'h10)>>2];
     else if(host_araddr[7:0]>=8'h80&&host_araddr[7:0]<=8'hbc&&host_araddr[1:0]==0)
      rd_data<=snapshot[((host_araddr[7:0]-8'h80)>>2)*32+:32];
    end
   endcase
  end
 end
endmodule
