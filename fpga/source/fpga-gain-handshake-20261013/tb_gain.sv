`timescale 1ns/1ps
// Diagnostic harness: original camera configuration FSM, deterministic I2C ACK model.
// No bitstream or production source is modified. Model checks issued register writes,
// not electrical I2C signal integrity or sensor optical behavior.
`ifndef REAL_ROM
module ui_imx415reg(input [1:0] MODE,input [7:0] REG_INDEX,output [7:0] REG_SIZE,output [23:0] REG_DATA);
 assign REG_SIZE=1; assign REG_DATA=24'h300001;
endmodule
`endif
module ui_i2c #(parameter WMEN_LEN=4,RMEN_LEN=1,CLK_DIV=239)
(input I_clk,I_rstn,input [31:0] I_wr_data,input [7:0] I_wr_cnt,I_rd_cnt,input I_iic_mode,I_iic_req,
 output O_iic_scl,inout IO_iic_sda,output [7:0] O_rd_data,output reg O_iic_busy,output O_iic_bus_error);
 assign O_iic_scl=1;assign IO_iic_sda=1'bz;assign O_rd_data=0;assign O_iic_bus_error=error_pulse;
 integer left;integer gains;reg [31:0] latched; reg inject_error=0; reg error_pulse=0; integer last_gain=0;
 always @(posedge I_clk) begin
 error_pulse<=0;
 if(O_iic_busy && left==4500 && inject_error && latched[15:8]==8'h30 && latched[23:16]==8'h90)error_pulse<=1;
  if(!I_rstn)begin O_iic_busy<=0;left<=0;gains<=0;latched<=0;end
  else if(O_iic_busy)begin
   if(left==0)begin
    O_iic_busy<=0;
    if(latched[15:8]==8'h30 && latched[23:16]==8'h90)begin
     gains<=gains+1;last_gain<=latched[31:24];$display("GAIN_WRITE data=%d at=%t",latched[31:24],$time);
    end
   end else left<=left-1;
  end else if(I_iic_req)begin O_iic_busy<=1;left<=9000;latched<=I_wr_data;end
 end
endmodule
module tb;
 reg clk=0,rst=0,pulse=0,pending=0,done_prev=1; reg [7:0] host_gain=50;
 wire done,configured,scl,sda,error;
 integer completed=0;integer base;integer kind;
 always #5 clk=~clk;
 always @(posedge clk)begin
  if(!rst)begin pending<=0;done_prev<=1;completed<=0;end
  else begin
   done_prev<=done;
   if(pulse)pending<=1;else if(!done && done_prev)pending<=0;
   if(done && !done_prev)completed<=completed+1;
  end
 end
 ui_cfg_imx415 dut(.I_clk(clk),.I_rst_n(rst),.I_cam_mode(2'd0),.I_ae_req(pending),.I_ae_data(host_gain),
 .O_cam_scl(scl),.IO_cam_sda(sda),.O_cfg_done(configured),.O_ae_cfg_done(done),.O_bus_error(error));
 task request;begin @(negedge clk);pulse=1;@(negedge clk);pulse=0;end endtask
 initial begin
  if(!$value$plusargs("CASE=%d",kind))kind=0;
  begin
   rst=0;repeat(10)@(negedge clk);rst=1;repeat(20)@(negedge clk);
   wait(configured && dut.O_cfg_done_r);repeat(50)@(negedge clk);
   $display("BOOT case=%0d idx=%0d",kind,dut.reg_index);$fflush();
   // Move the free-running periodic counter to its natural rollover state,
   // avoiding a million idle simulation cycles. All FSM/I2C transactions run normally.
   @(negedge clk);dut.cnt=1000000;
   wait(!dut.O_cfg_done_r);wait(dut.O_cfg_done_r);repeat(50)@(negedge clk);
   $display("READY case=%0d idx=%0d",kind,dut.reg_index);$fflush();
   if(kind==1 || kind==2)begin
    @(negedge clk);dut.cnt=1000000;
    wait(!dut.O_cfg_done_r);
    $display("PERIOD case=%0d idx=%0d ts=%0d",kind,dut.reg_index,dut.TS_S);$fflush();
    if(kind==1)wait(dut.iic_busy && dut.reg_index==0);
    else wait(dut.iic_busy && dut.reg_index==1);
   end
   $display("REQUEST case=%0d idx=%0d busy=%0d cfg_st_done=%0d",kind,dut.reg_index,dut.iic_busy,dut.O_cfg_done_r);$fflush();
   if(kind==6)dut.X_ui_i2c.inject_error=1;
   base=dut.X_ui_i2c.gains;request();
   if(kind>=3)begin
    wait(!done);wait(dut.iic_busy);
    if(kind==3 || kind==4)begin
     @(negedge clk);host_gain=73;
     if(kind==4)request();
    end
    if(kind==5)begin @(negedge clk);dut.cnt=1000000;end
   end
   repeat(50000)@(negedge clk);
   // Two later periodic cycles must not magically deliver a lost request.
   @(negedge clk);dut.cnt=1000000;repeat(50000)@(negedge clk);
   @(negedge clk);dut.cnt=1000000;repeat(50000)@(negedge clk);
   if(completed!=(kind==4?2:1) || dut.X_ui_i2c.gains-base!=(kind==4?2:1) || pending!==0)
    $fatal(1,"Missing or duplicate gain transaction case=%0d ack=%0d writes=%0d",kind,completed,dut.X_ui_i2c.gains-base);
   if(dut.X_ui_i2c.last_gain!=(kind==4?73:50))$fatal(1,"In-flight gain was not latched");
   if(error !== (kind==6))$fatal(1,"Error indication incorrect case=%0d error=%0d",kind,error);
   if(kind==6)begin
    dut.X_ui_i2c.inject_error=0;request();repeat(20000)@(negedge clk);
    if(error!==0 || completed!=2 || dut.X_ui_i2c.gains-base!=2)$fatal(1,"Error did not recover on explicit new request");
   end
   $display("PASS case=%0d completed_ack=%0d actual_gain_writes=%0d pending=%0d error=%0d",kind,completed,dut.X_ui_i2c.gains-base,pending,error);
  end
  $finish;
 end
 initial begin #100000000;$display("FINAL DEBUG idx=%0d size=%0d ts=%0d busy=%0d cfg=%0d st=%0d ae=%0d cnt=%0d",dut.reg_index,dut.REG_SIZE,dut.TS_S,dut.iic_busy,configured,dut.O_cfg_done_r,done,dut.cnt);$fatal(1,"timeout");end
endmodule
