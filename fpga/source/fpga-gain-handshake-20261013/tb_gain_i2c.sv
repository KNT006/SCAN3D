`timescale 1ns/1ps
// Uses the production I2C master, camera ROM and reset synchronizer.
// The slave decodes SCL/SDA and ACKs bytes; it does not inspect master state.
module tb;
 reg clk=0, rst=0, pulse=0, pending=0, previous_done=1;
 reg [7:0] gain=50;
 integer camera_mode=0;
 wire scl,done,configured,error;
 tri1 sda;
 reg slave_low=0,active=0,ack_cycle=0,nack_gain=0;
 integer bit_index=0,byte_count=0,gain_count=0,completions=0;
 integer last_gain=0,acknowledged_gains=0,case_number=0;
 reg [7:0] shift=0,bytes[0:7];
 reg transaction_nacked=0;
 assign sda=slave_low?1'b0:1'bz;
 always #5 clk=~clk;
 ui_cfg_imx415 #(.CLK_DIV(239)) dut(
  .I_clk(clk),.I_rst_n(rst),.I_cam_mode(camera_mode[1:0]),.I_ae_req(pending),.I_ae_data(gain),
  .O_cam_scl(scl),.IO_cam_sda(sda),.O_cfg_done(configured),.O_ae_cfg_done(done),.O_bus_error(error));
 always @(posedge clk) begin
  if(!rst)begin pending<=0;previous_done<=1;completions<=0;end
  else begin
   previous_done<=done;
   if(pulse)pending<=1;else if(previous_done && !done)pending<=0;
   if(done && !previous_done)completions<=completions+1;
  end
 end
 always @(negedge sda) if(scl===1'b1 && !slave_low)begin
  active=1;bit_index=0;byte_count=0;ack_cycle=0;transaction_nacked=0;
 end
 always @(posedge sda) if(scl===1'b1 && active && !slave_low)begin
  if(byte_count==4 && bytes[0]==8'h34 && bytes[1]==8'h30 && bytes[2]==8'h90)begin
   gain_count=gain_count+1;last_gain=bytes[3];
   if(!transaction_nacked)acknowledged_gains=acknowledged_gains+1;
   $display("BUS_GAIN case=%0d data=%0d nack=%0d time=%0t",case_number,last_gain,transaction_nacked,$time);
  end
  active=0;
 end
 always @(posedge scl) if(active)begin
  if(bit_index<8)begin
   shift={shift[6:0],sda};bit_index=bit_index+1;
   if(bit_index==8)begin bytes[byte_count]=shift;byte_count=byte_count+1;end
  end else ack_cycle=1;
 end
 always @(negedge scl) if(active)begin
  if(ack_cycle)begin slave_low=0;ack_cycle=0;bit_index=0;end
  else if(bit_index==8)begin
   if(nack_gain && byte_count==4 && bytes[1]==8'h30 && bytes[2]==8'h90)begin
    slave_low=0;transaction_nacked=1;
   end else slave_low=1;
  end
 end
 task request;begin @(negedge clk);pulse=1;@(negedge clk);pulse=0;end endtask
 task wait_complete;begin wait(!done);wait(done);repeat(10)@(negedge clk);end endtask
 task check(input integer expected,input integer value,input integer expect_error);begin
  if(completions!=expected || gain_count!=expected || last_gain!=value || error!==expect_error[0] || pending!==0)
   $fatal(1,"case=%0d ack=%0d bus_writes=%0d value=%0d error=%0d pending=%0d",case_number,completions,gain_count,last_gain,error,pending);
  $display("PASS_I2C case=%0d completions=%0d gain_writes=%0d data=%0d error=%0d",case_number,completions,gain_count,last_gain,error);
 end endtask
 integer initial_gains;
 initial begin
  if(!$value$plusargs("MODE=%d",camera_mode))camera_mode=0;
  repeat(10)@(negedge clk);rst=1;
  wait(configured && dut.O_cfg_done_r);repeat(50)@(negedge clk);
  // Initial ROM may program a default gain. Test only subsequent host requests.
  initial_gains=gain_count;gain_count=0;acknowledged_gains=0;
  case_number=0;request();wait_complete();check(1,50,0);
  // Reproduce the original first-startup-register request collision.
  case_number=1;@(negedge clk);dut.cnt=1000000;
  wait(!dut.O_cfg_done_r);wait(dut.iic_busy && dut.reg_index==0);
  gain=0;request();wait_complete();check(2,0,0);
  case_number=2;gain=50;request();wait(!done);wait(dut.iic_busy);
  @(negedge clk);gain=73;wait(done);repeat(10)@(negedge clk);check(3,50,0);
  case_number=3;nack_gain=1;gain=42;request();wait_complete();check(4,42,1);
  // Successful unrelated startup refresh must not hide a failed gain command.
  @(negedge clk);dut.cnt=1000000;wait(!dut.O_cfg_done_r);wait(dut.O_cfg_done_r);
  repeat(50)@(negedge clk);check(4,42,1);
  case_number=4;nack_gain=0;gain=50;request();wait_complete();check(5,50,0);
  if(acknowledged_gains!=4)$fatal(1,"Unexpected ACKed gain count %0d",acknowledged_gains);
  $display("PASS_I2C_ALL cases=5 mode=%0d initial_gain_writes=%0d",camera_mode,initial_gains);$finish;
 end
 initial begin #150000000;$fatal(1,"I2C test timeout");end
endmodule
