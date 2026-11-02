`timescale 1ns/1ps
// Passive observer: source_ready is INPUT, never driven by this module.
// Original pixels are 4 x {8'b0,R,G,B}, before rgb24 pack4 / diagnostic marker.
// ROI output is speculative until successful frame_status, not just m_eof.
// s_last is EOL, NOT EOF. Next SOF verifies the previous physical frame ended
// at the configured height; an extra line or missing next SOF fails the frame.
module afc03_camera_roi_tap #(
 parameter REQUIRE_MARKER=0,
 parameter FIFO_ADDR_BITS=8,
 parameter TIMEOUT_CYCLES=100000000
)(
 input wire clk,rst_n,stream_rst_n,
 input wire [127:0] s_data,
 input wire s_valid,source_ready,s_user,s_last,
 input wire [31:0] source_epoch,
 input wire arm_valid,output wire arm_ready,
 input wire [12:0] cfg_width,cfg_height,cfg_x0,cfg_y0,cfg_x1,cfg_y1,
 input wire [31:0] cfg_token,cfg_geometry,cfg_calibration,
 input wire cancel,
 output wire source_pending,output wire [31:0] source_token,
 output reg busy,output wire fault_pending,output reg [7:0] fault_code,
 output reg desc_valid,input wire desc_ready,
 output reg [31:0] desc_frame_id,desc_epoch,desc_token,desc_geometry,desc_calibration,
 output reg [12:0] desc_image_width,desc_image_height,desc_x0,desc_y0,desc_x1,desc_y1,
 output reg [31:0] desc_pixels,desc_bytes,
 output reg m_valid,input wire m_ready,output wire [127:0] m_data,
 output wire [15:0] m_keep,output wire m_sof,m_eol,m_eof,
 output wire [12:0] m_x,m_y,output wire [31:0] m_frame_id,m_epoch,m_token,
 output reg frame_status_valid,input wire frame_status_ready,
 output reg frame_status_ok,output reg [7:0] frame_status_error,
 output reg [31:0] frame_status_frame_id,frame_status_epoch,frame_status_token,
 output reg [31:0] frame_status_source_pixels,frame_status_stored_pixels,frame_status_output_pixels
);
 localparam DEPTH=1<<FIFO_ADDR_BITS;
 localparam BAD_CONFIG=1,CANCELLED=2,STREAM_RESET=3,EPOCH_CHANGED=4,
  OVERFLOW=5,BAD_LINE=6,UNEXPECTED_SOF=7,BAD_FRAME_END=8,TIMEOUT=9,
  BAD_COUNT=10,FRAME_ID_WRAP=11;
 reg waiting,active,await_boundary,finished,desc_accepted;
 reg [31:0] frame_counter,watchdog,roi_seen,roi_stored,roi_output;
 reg [12:0] x,y;
 reg [FIFO_ADDR_BITS-1:0] wr_ptr,rd_ptr;
 reg [FIFO_ADDR_BITS:0] fill;
 // Synchronous one-write/one-read RAM; valid bits/counters reset, RAM does not.
 reg [156:0] memory[0:DEPTH-1];
 reg [156:0] output_word;
 wire accept=s_valid&&source_ready&&stream_rst_n;
 // Unpack exactly the same four native RGB pixels seen by the RK marker reader.
 wire [95:0] marker_bytes;
 genvar lane;
 generate for(lane=0;lane<4;lane=lane+1)begin: marker_unpack
  assign marker_bytes[lane*24+:24]={s_data[lane*32+:8],s_data[lane*32+8+:8],s_data[lane*32+16+:8]};
 end endgenerate
 wire marker_match=marker_bytes[31:0]==32'h31544752 && marker_bytes[63:32]==desc_token;
 assign source_pending=waiting&&!cancel&&stream_rst_n&&!fault_pending;
 assign source_token=desc_token;
 wire start=waiting&&accept&&s_user&&(!REQUIRE_MARKER||marker_match);
 wire capturing=active||start;
 wire [12:0] px=start?13'd0:x,py=start?13'd0:y;
 wire inside_roi=px>=desc_x0&&px<desc_x1&&py>=desc_y0&&py<desc_y1;
 wire bad_line=(s_last!=({1'b0,px}+14'd4=={1'b0,desc_image_width}))||
  px>=desc_image_width||py>=desc_image_height;
 wire unexpected_sof=active&&s_user;
 wire final_line=s_last&&py+14'd1=={1'b0,desc_image_height};
 wire fifo_full=fill==DEPTH;
 wire roi_attempt=accept&&capturing&&inside_roi;
 wire timeout_now=busy&&!finished&&watchdog>=TIMEOUT_CYCLES-1;
 wire abort_now=cancel||!stream_rst_n||source_epoch!=desc_epoch||timeout_now;
 // Conservative full handling deliberately avoids same-address BRAM R/W
 // collision when full: even a simultaneous pop cannot hide an overflow.
 wire push=roi_attempt&&!fault_pending&&!abort_now&&!bad_line&&!unexpected_sof&&!fifo_full;
 wire pop=desc_accepted&&fill!=0&&(!m_valid||m_ready);
 wire roi_first=px==desc_x0&&py==desc_y0;
 wire roi_eol=px+14'd4=={1'b0,desc_x1};
 wire roi_final=roi_eol&&py+14'd1=={1'b0,desc_y1};
 wire [25:0] cfg_pixels=(cfg_x1-cfg_x0)*(cfg_y1-cfg_y0);
 wire bad_config=FIFO_ADDR_BITS<1||TIMEOUT_CYCLES<2||!stream_rst_n||source_epoch==0||
  cfg_token==0||cfg_width==0||cfg_height==0||cfg_width[1:0]!=0||
  cfg_x0[1:0]!=0||cfg_x1[1:0]!=0||cfg_x0>=cfg_x1||cfg_y0>=cfg_y1||
  cfg_x1>cfg_width||cfg_y1>cfg_height;
 assign arm_ready=rst_n&&!busy&&!frame_status_valid;
 assign fault_pending=busy&&fault_code!=0;
 assign m_data=output_word[127:0];
 assign m_x=output_word[140:128];assign m_y=output_word[153:141];
 assign m_sof=output_word[154];assign m_eol=output_word[155];assign m_eof=output_word[156];
 assign m_keep=16'hffff;assign m_frame_id=desc_frame_id;
 assign m_epoch=desc_epoch;assign m_token=desc_token;
 always @(posedge clk)begin
  if(push)memory[wr_ptr]<={roi_final,roi_eol,roi_first,py,px,s_data};
  if(pop)output_word<=memory[rd_ptr];
 end
 task fail_frame;
  input [7:0] code;
  begin
   if(fault_code==0)fault_code<=code;
   waiting<=0;active<=0;await_boundary<=0;finished<=1;
  end
 endtask
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   busy<=0;fault_code<=0;waiting<=0;active<=0;await_boundary<=0;finished<=0;desc_accepted<=0;
   frame_counter<=0;watchdog<=0;roi_seen<=0;roi_stored<=0;roi_output<=0;x<=0;y<=0;
   wr_ptr<=0;rd_ptr<=0;fill<=0;m_valid<=0;desc_valid<=0;
   desc_frame_id<=0;desc_epoch<=0;desc_token<=0;desc_geometry<=0;desc_calibration<=0;
   desc_image_width<=0;desc_image_height<=0;desc_x0<=0;desc_y0<=0;desc_x1<=0;desc_y1<=0;
   desc_pixels<=0;desc_bytes<=0;
   frame_status_valid<=0;frame_status_ok<=0;frame_status_error<=0;
   frame_status_frame_id<=0;frame_status_epoch<=0;frame_status_token<=0;
   frame_status_source_pixels<=0;frame_status_stored_pixels<=0;frame_status_output_pixels<=0;
  end else begin
   if(accept&&s_user)frame_counter<=frame_counter+1'b1;
   if(desc_valid&&desc_ready)begin desc_valid<=0;desc_accepted<=1;end
   if(m_valid&&m_ready)begin m_valid<=0;roi_output<=roi_output+4;end
   if(pop)begin m_valid<=1;rd_ptr<=rd_ptr+1'b1;end
   if(push)begin wr_ptr<=wr_ptr+1'b1;roi_stored<=roi_stored+4;end
   case({push,pop})
    2'b10:fill<=fill+1'b1;
    2'b01:fill<=fill-1'b1;
    default:begin end
   endcase
   if(frame_status_valid&&frame_status_ready)begin frame_status_valid<=0;busy<=0;end
   if(arm_valid&&arm_ready)begin
    busy<=1;fault_code<=bad_config?BAD_CONFIG:0;waiting<=!bad_config;
    active<=0;await_boundary<=0;finished<=bad_config;desc_accepted<=0;desc_valid<=0;
    desc_frame_id<=0;desc_epoch<=source_epoch;desc_token<=cfg_token;
    desc_geometry<=cfg_geometry;desc_calibration<=cfg_calibration;
    desc_image_width<=cfg_width;desc_image_height<=cfg_height;
    desc_x0<=cfg_x0;desc_y0<=cfg_y0;desc_x1<=cfg_x1;desc_y1<=cfg_y1;
    desc_pixels<={6'b0,cfg_pixels};desc_bytes<={4'b0,cfg_pixels,2'b00};
    roi_seen<=0;roi_stored<=0;roi_output<=0;watchdog<=0;
    wr_ptr<=0;rd_ptr<=0;fill<=0;m_valid<=0;x<=0;y<=0;
   end else if(busy&&!frame_status_valid)begin
    // Waiting for SOF has an absolute timeout, even if unframed data flows.
    if(waiting||(active||await_boundary)&&!accept)watchdog<=watchdog+1'b1;
    else watchdog<=0;
    if(fault_code==0)begin
     if(cancel)fail_frame(CANCELLED);
     else if(!stream_rst_n)fail_frame(STREAM_RESET);
     else if(source_epoch!=desc_epoch)fail_frame(EPOCH_CHANGED);
     else if(timeout_now)fail_frame(TIMEOUT);
     else if(await_boundary&&accept)begin
      if(!s_user)fail_frame(BAD_FRAME_END);
      else begin
       await_boundary<=0;finished<=1;
       if(roi_seen!=desc_pixels||roi_stored!=desc_pixels)fail_frame(BAD_COUNT);
      end
     end else if(accept&&capturing)begin
      if(start)begin
       waiting<=0;active<=1;desc_frame_id<=REQUIRE_MARKER?marker_bytes[95:64]:frame_counter+1'b1;desc_valid<=1;watchdog<=0;
      end
      if(inside_roi)roi_seen<=roi_seen+4;
      if(start&&frame_counter==32'hffffffff)fail_frame(FRAME_ID_WRAP);
      else if(unexpected_sof)fail_frame(UNEXPECTED_SOF);
      else if(bad_line)fail_frame(BAD_LINE);
      else if(roi_attempt&&fifo_full)fail_frame(OVERFLOW);
      else if(final_line)begin active<=0;await_boundary<=1;end
      else if(s_last)begin x<=0;y<=py+1'b1;end
      else begin x<=px+13'd4;y<=py;end
     end
    end
    // Publication waits for descriptor acceptance, FIFO and output drain.
    // A source fault never withdraws a previously offered output/descriptor.
    if(finished&&!desc_valid&&fill==0&&!m_valid&&(fault_code!=0||!abort_now))begin
     frame_status_valid<=1;
     frame_status_ok<=fault_code==0&&roi_seen==desc_pixels&&roi_stored==desc_pixels&&roi_output==desc_pixels;
     frame_status_error<=fault_code!=0?fault_code:
      (roi_seen!=desc_pixels||roi_stored!=desc_pixels||roi_output!=desc_pixels)?BAD_COUNT:0;
     frame_status_frame_id<=desc_frame_id;frame_status_epoch<=desc_epoch;frame_status_token<=desc_token;
     frame_status_source_pixels<=roi_seen;frame_status_stored_pixels<=roi_stored;frame_status_output_pixels<=roi_output;
    end
   end
  end
 end
endmodule
