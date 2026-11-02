`timescale 1ns/1ps
module tb_bridge_payload_reset_equiv;
 reg hclk=0,dclk=0;
 always #4 hclk=~hclk;
 always #5 dclk=~dclk;
 reg hrst_n=0,drst_n=0;
 reg [31:0] awaddr=0,wdata=0,araddr=0;
 reg [3:0] wstrb=0;
 reg awvalid=0,wvalid=0,arvalid=0;
 reg awready=0,wready=0,arready=0;
 reg response_valid=0,command_ready=0;
 reg [511:0] response_data=0;
 wire [31:0] rd0,rd1,epoch0,epoch1;
 wire sel0,sel1,reset0,reset1,dreset0,dreset1;
 wire cmd_valid0,cmd_valid1,rsp_ready0,rsp_ready1;
 wire [351:0] cmd_data0,cmd_data1;

 afc03_laser_csr_bridge_baseline #(.HOST_WATCHDOG(31),.PAGE(12'h025)) old_bridge(
  .hclk(hclk),.hrst_n(hrst_n),.dclk(dclk),.drst_n(drst_n),
  .host_awaddr(awaddr),.host_wdata(wdata),.host_araddr(araddr),.host_wstrb(wstrb),
  .host_awvalid(awvalid),.host_awready(awready),.host_wvalid(wvalid),.host_wready(wready),
  .host_arvalid(arvalid),.host_arready(arready),.rd_select(sel0),.rd_data(rd0),
  .camera_epoch(epoch0),.reset_n(reset0),.dreset_n(dreset0),
  .command_valid(cmd_valid0),.command_ready(command_ready),.command_data(cmd_data0),
  .response_valid(response_valid),.response_ready(rsp_ready0),.response_data(response_data));
 afc03_laser_csr_bridge #(.HOST_WATCHDOG(31),.PAGE(12'h025)) new_bridge(
  .hclk(hclk),.hrst_n(hrst_n),.dclk(dclk),.drst_n(drst_n),
  .host_awaddr(awaddr),.host_wdata(wdata),.host_araddr(araddr),.host_wstrb(wstrb),
  .host_awvalid(awvalid),.host_awready(awready),.host_wvalid(wvalid),.host_wready(wready),
  .host_arvalid(arvalid),.host_arready(arready),.rd_select(sel1),.rd_data(rd1),
  .camera_epoch(epoch1),.reset_n(reset1),.dreset_n(dreset1),
  .command_valid(cmd_valid1),.command_ready(command_ready),.command_data(cmd_data1),
  .response_valid(response_valid),.response_ready(rsp_ready1),.response_data(response_data));

 integer cycle,commands_seen=0,snapshots_seen=0;
 always @(posedge dclk) if(cmd_valid0) commands_seen=commands_seen+1;
 initial begin
  for(cycle=0;cycle<2500;cycle=cycle+1)begin
   @(negedge hclk);
   if(cycle==3||cycle==700||cycle==1500)begin hrst_n=1;drst_n=1;end
   if(cycle==695||cycle==1495)begin hrst_n=0;drst_n=0;end
   awaddr={12'd0,12'h025,8'(($urandom%16)*4)};
   araddr={12'd0,12'h025,8'(($urandom%64)*4)};
   wdata=$urandom;
   if(cycle%29==0)wdata=32'h42470002;
   wstrb=(cycle%7==0)?4'hf:$urandom;
   awvalid=($urandom%3)==0;
   wvalid=($urandom%3)==0;
   arvalid=($urandom%2)==0;
   awready=($urandom%4)!=0;
   wready=($urandom%4)!=0;
   arready=($urandom%4)!=0;
   command_ready=($urandom%3)!=0;
   response_valid=($urandom%11)==0;
   response_data={$urandom,$urandom,$urandom,$urandom,$urandom,$urandom,$urandom,$urandom,
                  $urandom,$urandom,$urandom,$urandom,$urandom,$urandom,$urandom,$urandom};
   if(cycle<120)begin
    awvalid=0;wvalid=0;arvalid=0;response_valid=0;
    awready=1;wready=1;arready=1;command_ready=1;
   end
   if(cycle==40)begin
    awaddr=32'h0000250c;wdata=32'h00001234;wstrb=4'hf;
    awvalid=1;wvalid=1;awready=1;wready=1;
   end
   if(cycle==45)begin
    awaddr=32'h00002508;wdata=32'h42470002;wstrb=4'hf;
    awvalid=1;wvalid=1;awready=1;wready=1;
   end
   if(cycle==55)begin
    response_valid=1;response_data=512'h1122334455667788;
   end
   if(cycle==100||cycle==705)begin araddr=32'h00002580;arvalid=1;arready=1;end
   @(posedge hclk); #1;
   if({sel0,rd0,epoch0,reset0,dreset0,rsp_ready0} !==
      {sel1,rd1,epoch1,reset1,dreset1,rsp_ready1})
    $fatal(1,"host mismatch at cycle %0d",cycle);
   if(cmd_valid0 !== cmd_valid1 || (cmd_valid0 && cmd_data0 !== cmd_data1))
    $fatal(1,"command mismatch at cycle %0d",cycle);
   if(cycle==100 && rd1!==32'h55667788)
    $fatal(1,"reply snapshot not readable after capture");
   if(cycle==705 && rd1!==32'd0)
    $fatal(1,"reply snapshot not cleared after reset");
   if(new_bridge.snapshot_initialized)snapshots_seen=snapshots_seen+1;
  end
  if(commands_seen==0 || snapshots_seen==0) $fatal(1,"command/reply paths not exercised");
  $display("BRIDGE_PAYLOAD_RESET_EQUIV_PASS cycles=%0d commands=%0d snapshots=%0d",
   cycle,commands_seen,snapshots_seen);
  $finish;
 end
endmodule
