`timescale 1ns/1ps
module tb;
 reg clk=0,reset_n=0;always #4 clk=~clk;
 reg [129:0] wd=0;reg we=0,mr=0;wire full,empty,ready,mv;
 wire [129:0] fd,md;
 sync_fifo_130 #(.ADDR_WIDTH(4)) fifo(clk,reset_n,wd,we,full,fd,ready&&!empty,empty);
 afc03_stream_register stage(clk,reset_n,fd,!empty,ready,md,mv,mr);
 reg [129:0] expected[0:50000],previous;
 integer head=0,tail=0,total=0,phase,i,run=0,longest=0,full_hits=0;
 reg held=0;reg [31:0] rng=32'h6abc0783;
 always @(posedge clk)begin
  if(!reset_n)begin head=0;tail=0;held=0;run=0;end
  else begin
   if(held&&(!mv||md!==previous))$fatal(1,"payload/sidebands changed while stalled");
   if(we&&!full)begin expected[tail]=wd;tail=tail+1;end
   if(full)full_hits=full_hits+1;
   if(mv&&mr)begin
    if(head>=tail||md!==expected[head])$fatal(1,"FIFO/stage loss, duplicate, or metadata mismatch");
    head=head+1;total=total+1;run=run+1;if(run>longest)longest=run;
   end else run=0;
   held=mv&&!mr;previous=md;
  end
 end
 initial begin
  #1;reset_n=1;#1;reset_n=0;
  for(phase=0;phase<4;phase=phase+1)begin
   @(negedge clk);reset_n=0;we=0;mr=0;
   repeat(3)@(negedge clk);reset_n=1;
   for(i=0;i<10000;i=i+1)begin
    @(negedge clk);
    rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
    wd={1'(i%64==0),1'(i%16==15),32'(phase),32'(i),rng,~rng};
    we=(i<7000)?1:rng[0];
    mr=(i<128)?0:(i<7000)?1:(rng[2]&&rng[3]);
   end
   if(phase%2==0)begin
    @(negedge clk);we=0;mr=1;
    repeat(32)@(negedge clk);
    if(head!=tail||mv||!empty)$fatal(1,"drain did not retire all words");
   end
   // Other phases reset a nonempty, backpressured queue; old payload must flush.
   else begin @(negedge clk);mr=0;we=1;repeat(24)@(negedge clk);end
  end
  if(total<20000||longest<1000||full_hits==0)$fatal(1,"coverage insufficient");
  $display("PASS video stage: %0d exact beats; longest continuous %0d; full %0d; reset flush",total,longest,full_hits);
  $finish;
 end
 initial begin #1000000;$fatal(1,"timeout");end
endmodule
