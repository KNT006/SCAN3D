`timescale 1ns/1ps
module tb;
reg clk=0;always #5 clk=~clk;
reg rst_n=0,laser_b=0,sample_we=0,start=0,center_ready=0;
reg[12:0] row_id=0;reg[11:0] sample_addr=0,width=0,roi_left=0,roi_right=0;
reg[7:0] signal_value=0,rawmax_value=0;
wire busy,done,error,center_valid,tie_conflict;wire[31:0] center_num,center_extra;wire[23:0] center_den;wire[15:0] center_peak32;wire[11:0] center_lo,center_hi;wire[4:0] center_count;
wire[31:0] cycles_gaussian,cycles_find,cycles_evaluate,cycles_select,cycles_total;
laser_full_row_core dut(.*);
integer f,ret,total,c,i,w,y,b,l,r,n,e,got,ticks;reg[15:0] pixel;
reg[31:0] en[0:15],ed[0:15],ep[0:15],el[0:15],eh[0:15],ee[0:15];reg[127:0] prev;reg stall=0;
always @(posedge clk)if(rst_n)begin
 if(stall && (!center_valid || {center_extra,center_num,center_den,center_peak32,center_lo,center_hi}!==prev))$fatal(1,"Stalled output changed");
 stall<=center_valid&&!center_ready;prev<={center_extra,center_num,center_den,center_peak32,center_lo,center_hi};
 if(center_valid&&center_ready)begin
  if(got>=n || center_num!==en[got] || center_den!==ed[got][23:0] || center_peak32!==ep[got][15:0] || center_lo!==el[got][11:0] || center_hi!==eh[got][11:0] || center_extra!==ee[got])$fatal(1,"Case %0d candidate %0d got %0d/%0d tag%0d [%0d,%0d] extra%0d expected %0d/%0d tag%0d [%0d,%0d] extra%0d",c,got,center_num,center_den,center_peak32,center_lo,center_hi,center_extra,en[got],ed[got],ep[got],el[got],eh[got],ee[got]);
  got=got+1;
 end
end
initial begin
 f=$fopen("capacity-vectors.txt","r");ret=$fscanf(f,"%d\n",total);repeat(4)@(negedge clk);rst_n=1;
 for(c=0;c<total;c=c+1)begin
  ret=$fscanf(f,"%d %d %d %d %d %d %d\n",w,y,b,l,r,n,e);width=w;row_id=y;laser_b=b;roi_left=l;roi_right=r;got=0;center_ready=0;
  for(i=0;i<w;i=i+1)begin ret=$fscanf(f,"%h\n",pixel);sample_we=1;sample_addr=i;signal_value=pixel[7:0];rawmax_value=pixel[15:8];@(negedge clk);end
  sample_we=0;for(i=0;i<n;i=i+1)ret=$fscanf(f,"%d %d %d %d %d %d\n",en[i],ed[i],ep[i],el[i],eh[i],ee[i]);
  start=1;@(negedge clk);start=0;ticks=0;
  while(!done && ticks<2000000)begin center_ready=(ticks%5==0);@(negedge clk);ticks=ticks+1;end
  if(!done||error!==e[0]||got!=n||(!e&&center_count!=n))$fatal(1,"Case %0d done%0d error%0d count%0d expected%0d",c,done,error,got,n);
  @(negedge clk);
 end
 $display("CORE_PASS rows=%0d",total);$finish;
end
endmodule
