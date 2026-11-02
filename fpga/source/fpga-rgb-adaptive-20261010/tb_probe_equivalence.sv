`timescale 1ns/1ps
module tb;
reg clk=0,rst=0,srst=1;always #4 clk=~clk;
reg [127:0] sd=0;reg sv=0,sl=0,su=0;wire sr;
wire [127:0] md;wire mv,ml,mu;reg mr=1;
reg [31:0] aw=0,wd=0,ar=0;reg [3:0] ws=15;reg av=0,wv=0,rv=0;
wire sel;wire [31:0] rd;
afc03_rgb_roi_probe #(.ADDR_BITS(4)) d(
 .clk(clk),.rst_n(rst),.stream_rst_n(srst),.image_width(13'd16),.image_height(13'd5),
 .s_data(sd),.s_valid(sv),.s_last(sl),.s_user(su),.s_ready(sr),
 .m_data(md),.m_valid(mv),.m_last(ml),.m_user(mu),.m_ready(mr),
 .awaddr(aw),.wdata(wd),.araddr(ar),.wstrb(ws),.awvalid(av),.awready(1'b1),
 .wvalid(wv),.wready(1'b1),.arvalid(rv),.arready(1'b1),.rd_select(sel),.rd_data(rd));
wire g_sr,g_mv,g_ml,g_mu,g_sel;wire [127:0] g_md;wire [31:0] g_rd;
afc03_rgb_roi_probe_golden #(.ADDR_BITS(4)) g(
 .clk(clk),.rst_n(rst),.stream_rst_n(srst),.image_width(13'd16),.image_height(13'd5),
 .s_data(sd),.s_valid(sv),.s_last(sl),.s_user(su),.s_ready(g_sr),
 .m_data(g_md),.m_valid(g_mv),.m_last(g_ml),.m_user(g_mu),.m_ready(mr),
 .awaddr(aw),.wdata(wd),.araddr(ar),.wstrb(ws),.awvalid(av),.awready(1'b1),
 .wvalid(wv),.wready(1'b1),.arvalid(rv),.arready(1'b1),.rd_select(g_sel),.rd_data(g_rd));

always @(negedge clk) if(rst) begin
 if({sr,mv,ml,mu,sel,rd} !== {g_sr,g_mv,g_ml,g_mu,g_sel,g_rd})$fatal(1,"Probe interface equivalence failed");
 if(mv && md !== g_md)$fatal(1,"Probe payload equivalence failed");
 if({d.waiting,d.active,d.done,d.fault,d.rejected,d.token,d.frame_counter,d.captured_frame} !== {g.waiting,g.active,g.done,g.fault,g.rejected,g.token,g.frame_counter,g.captured_frame})$fatal(1,"Probe state equivalence failed");
 if(d.words_written !== g.words_written || d.expected_words !== g.expected_words)$fatal(1,"Probe counter equivalence failed");
end
reg [129:0] queue[0:4095];integer qi=0,qo=0,tick=0;
reg [129:0] expect_word,previous;reg stalled=0;
reg [95:0] marker;integer sj,yy,xx,j;
always @(posedge clk)begin
 if(rst&&srst)begin
   if(stalled&&{md,ml,mu}!==previous)$fatal(1,"Payload changed under backpressure");
   if(sv&&sr)begin
     expect_word={sd,sl,su};
     if(d.waiting&&su)begin
       marker={d.frame_counter+32'd1,d.token,32'h31544752};
       for(sj=0;sj<4;sj=sj+1)
         expect_word[2+sj*32+:32]={8'b0,marker[sj*24+:8],marker[sj*24+8+:8],marker[sj*24+16+:8]};
     end
     queue[qi]=expect_word;qi=qi+1;
   end
   if(mv&&mr)begin
     if(qo>=qi||{md,ml,mu}!==queue[qo])$fatal(1,"Bypass/marker order mismatch at %d",qo);
     qo=qo+1;
   end
   stalled=mv&&!mr;previous={md,ml,mu};
 end else stalled=0;
end
always @(negedge clk)begin tick=tick+1;mr=(tick%5!=1&&tick%5!=2);end
function [127:0] word_at(input integer f,input integer yy,input integer xx);
 reg [127:0] z;integer p;
 begin
  z=0;
  for(p=0;p<4;p=p+1)z[32*p+:32]={8'b0,8'(f+xx+p),8'(yy+3*f),8'(xx+yy+p)};
  word_at=z;
 end
endfunction
task write_reg(input [31:0] address,input [31:0] value,input integer order);
 begin
  @(negedge clk);aw=address;wd=value;
  if(order==0)begin av=1;wv=1;@(negedge clk);av=0;wv=0;end
  else if(order==1)begin av=1;@(negedge clk);av=0;repeat(2)@(negedge clk);wv=1;@(negedge clk);wv=0;end
  else begin wv=1;@(negedge clk);wv=0;repeat(2)@(negedge clk);av=1;@(negedge clk);av=0;end
 end
endtask
reg [31:0] readback;
task read_reg(input [31:0] address);
 begin
  @(negedge clk);ar=address;rv=1;@(negedge clk);rv=0;readback=rd;
  if(!sel)$fatal(1,"ROI BAR select missing");
  repeat(3)begin @(negedge clk);if(rd!==readback)$fatal(1,"Read response not held");end
 end
endtask
task ignored_read(input [31:0] address);
 begin
  @(negedge clk);ar=address;rv=1;@(negedge clk);rv=0;
  if(sel)$fatal(1,"BAR offset alias was selected");
 end
endtask
task send_frame(input integer f,input integer bad);
 begin
  for(yy=0;yy<5;yy=yy+1)for(xx=0;xx<16;xx=xx+4)begin
    @(negedge clk);sd=word_at(f,yy,xx);sv=1;su=(yy==0&&xx==0);sl=(xx==12);
    if(bad==1&&yy==2&&xx==8)sl=1;
    do @(posedge clk);while(!sr);
    @(negedge clk);sv=0;su=0;sl=0;
  end
 end
endtask
integer idx=0;reg [127:0] expected_roi;
initial begin
 #1;rst=1;#2;rst=0;#12;rst=1;
 send_frame(1,0); // disabled: bit-for-bit original stream
 read_reg('h21202100);
 if(readback!==32'h31544752)$fatal(1,"Physical BAR-base read not decoded");
 write_reg('h2120210c,'h789abc,0);
 write_reg('h21202110,(1<<16)|4,1);write_reg('h21202114,(4<<16)|12,2);
 write_reg('h21202108,'h52470001,0);
 write_reg('h210c,'hffffffff,0); // configuration is frozen while armed
 if(d.token!=='h789abc||!d.rejected)$fatal(1,"Busy write accepted");
 send_frame(2,0);repeat(4)@(negedge clk);
 if(!d.done||d.fault||d.words_written!=6||d.captured_frame!=2)$fatal(1,"Capture geometry/status");
 write_reg('h210c,'hdeadbeef,1);
 write_reg('h2110,(2<<16)|8,2);
 if(d.token!=='h789abc||d.x0!=4||d.y0!=1||!d.done)$fatal(1,"Completed snapshot metadata changed");
 idx=0;
 for(yy=1;yy<4;yy=yy+1)for(xx=4;xx<12;xx=xx+4)begin
   write_reg('h2128,idx,idx%3);repeat(3)@(negedge clk);
   if(!d.read_valid)$fatal(1,"RAM read not completed");
   expected_roi=word_at(2,yy,xx);
   for(j=0;j<4;j=j+1)begin
     read_reg('h2140+j*4);
     if(readback!==expected_roi[j*32+:32])$fatal(1,"ROI byte/coordinate mismatch");
   end
   idx=idx+1;
 end
 @(negedge clk);srst=0;@(negedge clk);
 if(d.done||d.read_valid||d.read_pending||d.fault!=6)$fatal(1,"Completed snapshot survived reset");
 srst=1;
 // Cancel removes old validity; invalid/out-of-capacity/misaligned ROI rejected.
 write_reg('h2108,'h52470000,0);
 write_reg('h2110,0,0);write_reg('h2114,(5<<16)|16,0);write_reg('h2108,'h52470001,0);
 if(d.waiting||d.active||d.fault!=1)$fatal(1,"Invalid ROI accepted");
 write_reg('h2110,(1<<16)|4,0);write_reg('h2114,(4<<16)|12,0);
 write_reg('h2108,'h52470001,0);send_frame(3,1);
 if(d.done||d.fault!=2)$fatal(1,"Malformed frame falsely accepted");
 write_reg('h2108,'h52470000,0);write_reg('h2108,'h52470001,0);
 @(negedge clk);srst=0;@(negedge clk);
 if(d.waiting||d.active||d.done||d.fault!=6)$fatal(1,"Stream reset did not invalidate capture");
 srst=1;
 // Partial command and aliased address must never arm the module.
 ws=3;write_reg('h2108,'h52470001,0);ws=15;
 if(d.waiting)$fatal(1,"Partial write accepted");
 write_reg('h12108,'h52470001,0);
 if(d.waiting)$fatal(1,"Address alias accepted");
 write_reg('h21212108,'h52470001,0);
 if(d.waiting)$fatal(1,"Physical BAR offset alias accepted");
 write_reg('h212f210c,'hffffffff,0);
 if(d.token!=='h789abc)$fatal(1,"Aliased token write accepted");
 ignored_read('h212020fc);ignored_read('h21202200);
 ignored_read('h21212100);ignored_read('h212f2100);
 read_reg('h212021fc);if(readback!=0)$fatal(1,"Reserved in-window register value");
 repeat(8)@(negedge clk);
 if(qi!=qo)$fatal(1,"Bypass lost words");
 $display("PASS RGB bypass, stable backpressure, unique frame tag, exact ROI, split AXI-Lite, invalid frames/reset/config rejection");
 $finish;
end
initial begin #200000;$fatal(1,"Test timeout");end
endmodule


