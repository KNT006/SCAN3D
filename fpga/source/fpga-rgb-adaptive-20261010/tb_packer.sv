`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;reg rst_n=0;
reg row_begin_valid=0,center_valid=0,row_done=0,row_tie_conflict=0,record_ready=0;
wire row_begin_ready,center_ready,record_valid,row_emitted,row_busy,protocol_fault;wire[127:0] record_data;wire[7:0] record_type;
reg[15:0] row_id=100,center_peak32=32793;reg[31:0] center_num=0,center_extra=0,row_cycles=7;
reg[23:0] center_den=10;reg[11:0] center_lo=0,center_hi=0;reg[4:0] row_center_count=0;reg[7:0] row_error=0;
row_record_packer dut(.*);
integer tick=0,idx=0,received=0,n=0,caseid=0;reg[127:0] prev;reg stalled=0;
always @(negedge clk)begin tick=tick+1;record_ready=(tick%7<2);end
always @(posedge clk)if(rst_n)begin
 if(stalled&&(!record_valid||prev!==record_data))$fatal(1,"stalled record changed");
 stalled<=record_valid&&!record_ready;prev<=record_data;
 if(record_valid&&record_ready)begin
  if(received<2*n)begin
   if(record_data[31:16]!==row_id||record_data[15:8]!==received/2||record_type!==(received%2==0?8'd1:8'd3))$fatal(1,"record order");
   if(received%2==1 && record_data[63:32]!==32'h10000000+received/2)$fatal(1,"extra mismatch");
  end else if(record_type!=2||record_data[39:32]!==n)$fatal(1,"rowdone mismatch");
  received=received+1;
 end
end
initial begin
 repeat(4)@(negedge clk);rst_n=1;
 for(caseid=0;caseid<2;caseid=caseid+1)begin
  n=caseid*16;received=0;row_id=100+caseid;row_begin_valid=1;@(negedge clk);while(!row_busy)@(negedge clk);row_begin_valid=0;
  for(idx=0;idx<n;idx=idx+1)begin
   center_num=(150+idx*10)*10;center_extra=32'h10000000+idx;center_lo=149+idx*10;center_hi=151+idx*10;center_valid=1;
   @(posedge clk);while(!center_ready)@(posedge clk);
   @(negedge clk);center_valid=0;
  end
  row_done=1;row_center_count=n;@(negedge clk);row_done=0;
  while(!row_emitted)@(negedge clk);
  if(protocol_fault||received!=2*n+1)$fatal(1,"packer completion");
  @(negedge clk);
 end
 $display("PACKER_PASS zero and sixteen candidates under backpressure");$finish;
end
initial begin #1000000;$fatal(1,"timeout");end
endmodule
