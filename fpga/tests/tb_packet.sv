`timescale 1ns/1ps
module tb;
 reg dclk=0,hclk=0,reset_n=0,start_valid=0,ready=0;
 always #5 dclk=~dclk;always #4 hclk=~hclk;
 reg [31:0] records=0;
 reg [1023:0] header=0;
 wire start_ready,ram_read,busy,valid,last;wire [10:0] address;wire[127:0] data;
 reg [127:0] ram_data;
 always @(posedge dclk)if(ram_read)ram_data<={96'hbadc0ffee1234567890,21'd0,address};
 afc03_result_dma dut(dclk,hclk,reset_n,start_valid,start_ready,header,records,ram_read,address,ram_data,busy,data,valid,ready,last);
 reg [31:0] rng=32'hdeface;
 always @(negedge hclk)begin rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};ready=reset_n&&rng[5];end
 integer beat=0,packets=0,expected_count=0,i;reg checking=1;
 reg stalled=0;reg [128:0] held;
 always @(posedge hclk)begin
  if(!reset_n)begin stalled<=0;beat<=0;end
  else begin
   if(stalled&&(!valid||{last,data}!==held))$fatal(1,"unstable stalled beat");
   stalled<=valid&&!ready;held<={last,data};
   if(valid&&ready)begin
    if(checking)begin
     if(last!==(beat==4095))$fatal(1,"wrong last");
     if(beat<8)begin if(data!==128'h1234)$fatal(1,"header");end
     else if(beat<8+expected_count)begin if(data!=={96'hbadc0ffee1234567890,32'(beat-8)})$fatal(1,"record %d",beat);end
     else if(data!==0)$fatal(1,"padding");
    end
    if(last)begin beat<=0;packets<=packets+1;end else beat<=beat+1;
   end
  end
 end
 task start(input integer n);
 begin
  @(negedge dclk);while(!start_ready)@(negedge dclk);
  records=n;expected_count=n;header={8{128'h1234}};start_valid=1;
  @(negedge dclk);start_valid=0;
 end endtask
 initial begin
  #40;reset_n=1;
  start(0);wait(packets==1);start(2048);wait(packets==2);
  // Abort a partially consumed packet; synchronized restart cannot leak old data.
  checking=0;start(2048);wait(beat>30);@(negedge dclk);reset_n=0;
  #48;reset_n=1;checking=1;start(3);wait(packets==3);
  #80;if(valid||busy)$fatal(1,"not drained");
  $display("PACKET_MAX_ZERO_RESET_PASS");$finish;
 end
 initial begin #3000000;$fatal(1,"timeout");end
endmodule
