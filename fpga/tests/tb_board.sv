`timescale 1ns/1ps
module tb;
localparam ADDR_WIDTH=28;
reg  hclk=0;
reg  hrst_n=0;
reg  dclk=0;
reg  drst_n=0;
reg  control_ready=0;
reg  ext_enabled=0;
reg [31:0] host_awaddr=0;
reg [31:0] host_wdata=0;
reg [31:0] host_araddr=0;
reg [3:0] host_wstrb=0;
reg  host_awvalid=0;
reg  host_awready=0;
reg  host_wvalid=0;
reg  host_wready=0;
reg  host_arvalid=0;
reg  host_arready=0;
wire  rd_select;
wire [31:0] rd_data;
reg  stream_rst_n=0;
reg [127:0] camera_data=0;
reg  camera_valid=0;
reg  camera_ready=0;
reg  camera_sof=0;
reg  camera_eol=0;
wire [3:0] awid;
wire [ADDR_WIDTH-1:0] awaddr;
wire [7:0] awlen;
wire [2:0] awsize;
wire [1:0] awburst;
wire  awvalid;
reg  awready=0;
wire [127:0] wdata;
wire [15:0] wstrb;
wire  wlast;
wire  wvalid;
reg  wready=0;
reg [3:0] bid=0;
reg [1:0] bresp=0;
reg  bvalid=0;
wire  bready;
wire [3:0] arid;
wire [ADDR_WIDTH-1:0] araddr;
wire [7:0] arlen;
wire [2:0] arsize;
wire [1:0] arburst;
wire  arvalid;
reg  arready=0;
reg [3:0] rid=0;
reg [127:0] rdata=0;
reg [1:0] rresp=0;
reg  rlast=0;
reg  rvalid=0;
wire rready;
wire capture_pending;wire [31:0] capture_token;
wire [127:0] result_dma_data;
wire result_dma_valid,result_dma_last;
reg result_dma_ready=0;
integer dma_fd,dma_beats=0,dma_packets=0;
reg [127:0] previous_dma;reg previous_stall=0;
always @(negedge hclk)begin result_dma_ready=hrst_n&&rng[7]&&rng[8];end
always @(posedge hclk)if(hrst_n)begin
 if(previous_stall && (!result_dma_valid || result_dma_data!==previous_dma))$fatal(1,"DMA backpressure changed payload");
 previous_stall<=result_dma_valid&&!result_dma_ready;previous_dma<=result_dma_data;
 if(result_dma_valid&&result_dma_ready)begin
  $fdisplay(dma_fd,"%032h",result_dma_data);
  if(result_dma_last!=(dma_beats==4095))$fatal(1,"DMA TLAST length");
  if(result_dma_last)begin dma_beats<=0;dma_packets<=dma_packets+1;end else dma_beats<=dma_beats+1;
 end
end

always #4 hclk=~hclk;always #5 dclk=~dclk;
afc03_laser_board_top #(.BG0(28'h1000),.BG1(28'h2000),.ON0(28'h3000),.ON1(28'h4000),.SLOT_BYTES(4096),.MAX_HEIGHT(16),.RESULT_DEPTH(64)) dut(.*);
reg [7:0] mem[0:65535];reg [127:0] wb[0:15];reg [15:0] ws[0:15];
integer wa=0,wn=0,wc=0,ra=0,rn=0,ri=0,i,j,ticks=0,writes=0,reads=0;
reg awseen=0,wdone=0,rpending=0;reg [31:0] rng=32'h278901fa;
reg inject_error=0;
always @(negedge dclk)begin
 ticks=ticks+1;if(ticks>500000)$fatal(1,"timeout owner %0d proc%0d pipe%0d",dut.axi_owner,dut.owner.state,dut.pipeline.sequencer.state);
 rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
 awready=drst_n&&!awseen&&!bvalid&&rng[0];wready=drst_n&&!wdone&&!bvalid&&rng[1];
 arready=drst_n&&!rpending&&!rvalid&&rng[2];
end
always @(posedge dclk)begin
 if(!drst_n)begin awseen<=0;wdone<=0;wc<=0;bvalid<=0;rvalid<=0;rpending<=0;end
 else begin
  if(awvalid&&awready)begin
   if(awlen>=16||awsize!=4||awid!=0||awaddr+16*(awlen+1)>65536)$fatal(1,"bad AW");
   awseen<=1;wa<=awaddr;wn<=awlen+1;
  end
  if(wvalid&&wready)begin wb[wc]<=wdata;ws[wc]<=wstrb;wc<=wc+1;if(wlast)wdone<=1;end
  if(awseen&&wdone&&!bvalid&&rng[3])begin
   if(wc!=wn)$fatal(1,"write count");
   for(i=0;i<wn;i=i+1)for(j=0;j<16;j=j+1)if(ws[i][j])mem[wa+i*16+j]<=wb[i][j*8+:8];
   bvalid<=1;bid<=0;bresp<=0;
  end
  if(bvalid&&bready)begin bvalid<=0;awseen<=0;wdone<=0;wc<=0;writes=writes+1;end
  if(arvalid&&arready)begin
   if(arid||arsize!=4||arburst!=1||araddr[3:0]||araddr+16*(arlen+1)>65536)$fatal(1,"bad AR");
   ra<=araddr;rn<=arlen+1;ri<=0;rpending<=1;reads=reads+1;
  end
  if(rpending&&!rvalid&&rng[4])begin
   for(i=0;i<16;i=i+1)rdata[i*8+:8]<=mem[ra+ri*16+i];
   rlast<=ri+1==rn;rvalid<=1;rid<=0;rresp<=inject_error?2:0;
  end
  if(rvalid&&rready)begin rvalid<=0;if(ri+1==rn)rpending<=0;else ri<=ri+1;end
 end
end
task wr;input [31:0] a,v;begin
 @(negedge hclk);host_awaddr=a;host_awvalid=1;
 @(negedge hclk);host_awvalid=0;host_wdata=v;host_wstrb=15;host_wvalid=1;
 @(negedge hclk);host_wvalid=0;
end endtask
task rd;input [31:0] a;output [31:0] v;begin
 @(negedge hclk);host_araddr=a;host_arvalid=1;
 @(negedge hclk);host_arvalid=0;v=rd_data;if(!rd_select)$fatal(1,"read mux");
end endtask
integer seq=0,n,waits;reg [511:0] response;reg [31:0] word;
task cmd;input [31:0] page;input integer op,expected;begin
 seq=seq+1;wr(page+'h0c,seq);wr(page+'h08,32'h42470000+op);
 waits=0;word=1;
 while((word[0]||!word[1])&&waits<20000)begin rd(page+4,word);waits=waits+1;if(word[3:2])$fatal(1,"host fault %h page%h",word,page);end
 if(waits==20000)$fatal(1,"cmd timeout page%h op%0d bg%0d live%0d",page,op,dut.bg.state,dut.live.state);
 for(n=0;n<16;n=n+1)begin rd(page+'h80+n*4,word);response[n*32+:32]=word;end
 if(response[15:8]!=expected||response[7:0]!=op||response[63:32]!=seq)$fatal(1,"reply mismatch page%h op%0d exp%0d got%h",page,op,expected,response[63:0]);
end endtask
task setup;input [31:0] page;input integer role,token;begin
 wr(page+'h10,7);wr(page+'h14,31);wr(page+'h18,11);wr(page+'h1c,token);
 wr(page+'h20,{16'd16,16'd16});wr(page+'h24,0);wr(page+'h28,{16'd16,16'd16});wr(page+'h2c,1+role*2);
end endtask
integer x,y,lane,salt=20;reg [127:0] pixels;
task frame;input integer on;begin
 for(y=0;y<16;y=y+1)for(x=0;x<16;x=x+4)begin
  pixels=0;for(lane=0;lane<4;lane=lane+1)begin
   salt=(on&&y>=5&&y<=9)?180:20;pixels[lane*32+:32]={8'd0,8'(salt),8'(salt),8'(salt)};
  end
  @(negedge hclk);camera_valid=1;camera_data=pixels;camera_sof=x==0&&y==0;camera_eol=x==12;
  @(negedge hclk);camera_valid=0;camera_sof=0;camera_eol=0;
 end
 repeat(8)@(negedge hclk);
end endtask
task capture;input [31:0] page;input integer on;begin
 cmd(page,2,0);repeat(50)@(negedge hclk);frame(on);frame(on);
 cmd(page,1,0);
 while(response[16])cmd(page,1,0);
 if(!response[17]||!response[305]||!response[306])$fatal(1,"capture not committed page%h flags%h event%h errbg%h live%h",page,response[31:0],response[319:288],dut.bg.last_event_error,dut.live.last_event_error);
end endtask
task readback;input [31:0] page;begin
 wr(page+'h30,16);cmd(page,4,0);
 if(response[511:384]!==128'h00141414001414140014141400141414)$fatal(1,"READ16 data mismatch %h",response[511:384]);
 if(dut.o_recovery_required)$fatal(1,"diagnostic read poisoned pair owner");
end endtask
integer f,idx,count;reg [31:0] crc;
task process;input integer role,expected_ok;begin
 setup('h2400,role,100+role);wr('h2424,{16'd0,16'd4});wr('h2428,{16'd16,16'd12});wr('h2430,{16'd14,16'd1});
 cmd('h2400,5,0);cmd('h2400,1,0);
 while(response[16])cmd('h2400,1,0);
 if(response[17]!=expected_ok)$fatal(1,"process result flags%h err%h owner%0d",response[31:0],response[351:320],dut.owner.state);
 if(expected_ok)begin
  count=response[127:96];crc=response[223:192];
  if(response[159:128]!=8||response[191:160]!=8||count!=16)$fatal(1,"algorithm counts rows%0d centers%0d records%0d",response[159:128],response[191:160],count);
  cmd('h2400,7,0);
  cmd('h2400,5,1); // Cannot overwrite a DMA-owned result RAM.
  while(dut.dma_busy)@(negedge hclk);
  while(dma_packets<role)@(negedge hclk);
  $fdisplay(f,"FRAME %0d %0d %08h",role,count,crc);
  for(idx=0;idx<count;idx=idx+1)begin
   wr('h2430,idx*16);cmd('h2400,6,0);$fdisplay(f,"RECORD %032h",response[511:384]);
  end
 end else begin cmd('h2400,7,4);wr('h2430,0);cmd('h2400,6,4);if(response[511:384]!=0)$fatal(1,"failed payload leaked");end
end endtask
initial begin
 dma_fd=$fopen("dma-packets.txt","w");
 f=$fopen("board-records.txt","w");host_awready=1;host_wready=1;host_arready=1;camera_ready=1;stream_rst_n=1;
 repeat(12)@(negedge hclk);hrst_n=1;drst_n=1;control_ready=1;ext_enabled=1;repeat(30)@(negedge hclk);
 rd('h2408,word);if(word!=32'h00050000)$fatal(1,"new job ABI");
 rd('h2208,word);if(word!=32'h00020000)$fatal(1,"unchanged capture ABI");
 setup('h2200,0,10);capture('h2200,0);readback('h2200);
 setup('h2300,1,11);capture('h2300,1);readback('h2300);process(1,1);readback('h2200);
 setup('h2300,2,12);capture('h2300,1);readback('h2300);process(2,1);readback('h2300);
 inject_error=1;process(2,0);
 if(dma_packets!=2)$fatal(1,"unexpected DMA packet count");$fclose(dma_fd);$fclose(f);$display("BOARD_INTEGRATION_PASS writes=%0d reads=%0d",writes,reads);$finish;
end
endmodule
