`timescale 1ns/1ps
module tb;
reg clk=0;always #4 clk=~clk;
reg reset_n=0,stream_reset=0,sink_ready=1;
reg [127:0] s_data=0;reg s_valid=0,s_sof=0,s_eol=0;wire s_ready;
wire [127:0] a_data,p_data;wire a_valid,a_sof,a_eol,a_ready,p_valid,p_sof,p_eol;
reg p_ready=1;wire [31:0] pass_count,drop_count;
afc03_capture_admission gate(.clk(clk),.reset_n(stream_reset),.frame_sink_ready(sink_ready),
 .s_data(s_data),.s_valid(s_valid),.s_sof(s_sof),.s_eol(s_eol),.s_ready(s_ready),
 .m_data(a_data),.m_valid(a_valid),.m_sof(a_sof),.m_eol(a_eol),.m_ready(a_ready),
 .pass_count(pass_count),.drop_count(drop_count));
reg [31:0] addr=0,data=0;reg wr=0;wire pending;wire [31:0] pending_token;
afc03_rgb_roi_probe #(.WAIT_DDR(1),.ADDR_BITS(6)) probe(
 .clk(clk),.rst_n(reset_n),.stream_rst_n(stream_reset),.capture_pending(pending),.capture_token(pending_token),
 .image_width(13'd16),.image_height(13'd16),.s_data(a_data),.s_valid(a_valid),.s_last(a_eol),.s_user(a_sof),.s_ready(a_ready),
 .m_data(p_data),.m_valid(p_valid),.m_last(p_eol),.m_user(p_sof),.m_ready(p_ready),
 .awaddr(addr),.wdata(data),.araddr(32'd0),.wstrb(4'hf),.awvalid(wr),.awready(1'b1),
 .wvalid(wr),.wready(1'b1),.arvalid(1'b0),.arready(1'b1),.rd_select(),.rd_data());
reg arm=0,cancel=0;reg [31:0] token=11;
wire arm_ready,busy,desc_valid,m_valid,fs_valid,fs_ok;
wire [127:0] m_data;wire [31:0] frame_id,desc_token;wire [7:0] fault;
afc03_camera_roi_tap #(.REQUIRE_MARKER(1),.FIFO_ADDR_BITS(6),.TIMEOUT_CYCLES(100000)) tap(
 .clk(clk),.rst_n(reset_n),.stream_rst_n(stream_reset),.s_data(p_data),.s_valid(p_valid),.source_ready(p_ready),.s_user(p_sof),.s_last(p_eol),
 .source_epoch(32'd1),.arm_valid(arm),.arm_ready(arm_ready),.cfg_width(13'd16),.cfg_height(13'd16),
 .cfg_x0(13'd0),.cfg_y0(13'd0),.cfg_x1(13'd16),.cfg_y1(13'd16),.cfg_token(token),.cfg_geometry(32'd1),.cfg_calibration(32'd1),
 .cancel(cancel),.source_pending(pending),.source_token(pending_token),.busy(busy),.fault_pending(),.fault_code(fault),
 .desc_valid(desc_valid),.desc_ready(1'b1),.desc_frame_id(frame_id),.desc_token(desc_token),
 .m_valid(m_valid),.m_ready(1'b1),.m_data(m_data),.frame_status_valid(fs_valid),.frame_status_ready(1'b1),.frame_status_ok(fs_ok));
integer video_frames=0,marked_frames=0,stored=0,seen_status=0,expected_count=0;
reg [127:0] expected[0:63];reg saving=0;reg stalled=0;reg [129:0] last_payload;
always @(posedge clk)if(reset_n)begin
 if(stalled&&(!p_valid||{p_sof,p_eol,p_data}!==last_payload))$fatal(1,"elastic payload changed");
 stalled<=p_valid&&!p_ready;last_payload<={p_sof,p_eol,p_data};
 if(p_valid&&p_ready)begin
  if(p_sof)begin
   video_frames=video_frames+1;
   saving=probe.captured_frame==probe.frame_counter&&probe.active;
   if(saving)begin marked_frames=marked_frames+1;expected_count=0;end
  end
  if(saving&&expected_count<64)begin expected[expected_count]=p_data;expected_count=expected_count+1;end
 end
 if(m_valid)begin
  if(stored>=expected_count||m_data!==expected[stored])$fatal(1,"DDR/video pixel mismatch word%0d",stored);
  stored=stored+1;
 end
 if(fs_valid)begin
  if(!fs_ok||fault||stored!=64||frame_id!=probe.captured_frame||desc_token!=11)$fatal(1,"capture identity/count failure");
  seen_status=seen_status+1;
 end
end
task mmio;input [7:0] off;input [31:0] value;begin
 @(negedge clk);addr='h2100+off;data=value;wr=1;@(negedge clk);wr=0;
end endtask
integer x,y,n;
task frame;input integer change_ready;begin
 for(y=0;y<16;y=y+1)for(x=0;x<16;x=x+4)begin
  @(negedge clk);s_valid=1;s_sof=x==0&&y==0;s_eol=x==12;
  s_data={32'(y*16+x+3),32'(y*16+x+2),32'(y*16+x+1),32'(y*16+x)};
  while(!s_ready)@(negedge clk);
  @(negedge clk);s_valid=0;s_sof=0;s_eol=0;
  if(change_ready&&y==3)sink_ready=0;
  if(x==4)begin p_ready=0;repeat(3)@(negedge clk);p_ready=1;end
 end
 repeat(12)@(negedge clk);
end endtask
initial begin
 repeat(4)@(negedge clk);reset_n=1;stream_reset=1;
 mmio('h0c,11);mmio('h10,4);mmio('h14,{16'd16,16'd12});mmio('h08,'h52470001);
 frame(0);if(!probe.waiting||marked_frames)$fatal(1,"marker consumed before DDR ready");
 @(negedge clk);arm=1;@(negedge clk);arm=0;
 sink_ready=0;frame(0);
 if(!pending||!probe.waiting||drop_count!=1||marked_frames)$fatal(1,"rejected frame consumed token");
 sink_ready=1;frame(1);
 if(marked_frames!=1||stored!=64||pending)$fatal(1,"admitted frame not captured once");
 // A rejected following frame cannot produce a spurious successful completion.
 frame(0);if(seen_status)$fatal(1,"false source boundary");
 sink_ready=1;frame(0);
 if(seen_status!=1||!probe.done||probe.fault||pass_count!=3||drop_count!=2)$fatal(1,"final handshake/count failure");
 mmio('h08,'h52470000);mmio('h0c,99);mmio('h08,'h52470001);
 // A source reset removes a pending request rather than reusing a stale token.
 @(negedge clk);stream_reset=0;repeat(3)@(negedge clk);stream_reset=1;
 frame(0);if(probe.waiting||marked_frames!=1)$fatal(1,"stale marker after reset");
 $display("ATOMIC_PASS: reject retains token; DDR/video exact64; midframe readiness/backpressure; reset");$finish;
end
initial begin #10000000;$fatal(1,"test watchdog");end
endmodule
