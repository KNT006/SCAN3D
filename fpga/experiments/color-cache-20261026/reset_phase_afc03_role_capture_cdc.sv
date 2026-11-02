`timescale 1ns/1ps
// Background-only two-domain capture owner. DDR and camera share reset assert.
// Original preview is observed, never backpressured. No hardware laser control.
module afc03_role_capture_cdc #(
 parameter REQUIRE_MARKER=0, parameter RESET_STAGES=2,
 parameter [3:0] ALLOWED_ROLES=4'b0001,
 parameter ADDR_WIDTH=28,
 parameter [ADDR_WIDTH-1:0] SLOT0_BASE=28'h0100000,
 parameter [ADDR_WIDTH-1:0] SLOT1_BASE=28'h0900000,
 parameter SLOT_BYTES=8388608,
 parameter PIXEL_FIFO_ADDR_BITS=8,TAP_FIFO_ADDR_BITS=8,
 parameter MOVER_TIMEOUT=1000000,FRAME_TIMEOUT=100000000,
 parameter CAMERA_TIMEOUT=100000000
)(
 input wire reset_n, camera_clk, ddr_clk,
 output wire source_pending,output wire [31:0] source_token,
 input wire stream_rst_n,
 input wire [127:0] camera_data,
 input wire camera_valid,camera_ready,camera_sof,camera_eol,
 input wire [31:0] camera_epoch,
 input wire arm_valid,output wire arm_ready,
 input wire [12:0] cfg_width,cfg_height,cfg_x0,cfg_y0,cfg_x1,cfg_y1,
 input wire [31:0] cfg_token,
 input wire operator_confirmed,cancel,
 input wire [1:0] cfg_role,
 output wire [1:0] active_role,grant_role,
 output reg capture_busy,
 output reg event_valid,input wire event_ready,
 output reg event_ok,event_committed,output reg [7:0] event_error,event_source_error,
 output reg [31:0] event_token,event_epoch,
 output reg [127:0] event_header,
input wire [31:0] config_epoch,
input wire [31:0] config_geometry,
input wire [31:0] config_calibration,
input wire  memory_invalidated,
output wire  active_valid,
output wire  active_slot,
output wire [127:0] active_header,
output wire [31:0] active_epoch,
output wire [31:0] active_pixels,
output wire [31:0] active_bytes,
output wire  invalidate_readers,
input wire  acquire_valid,
output wire  acquire_ready,
output wire  grant_valid,
output wire  grant_slot,
output wire [ADDR_WIDTH-1:0] grant_address,
output wire [127:0] grant_header,
output wire [31:0] grant_epoch,
output wire [31:0] grant_pixels,
output wire [31:0] grant_bytes,
input wire  release_valid,
input wire  release_slot,
input wire [127:0] release_header,
input wire [31:0] release_epoch,
output wire  release_ok,
output wire  protocol_error,
output wire  blocked_by_readers,
input wire  read_cmd_valid,
output wire  read_cmd_ready,
input wire [ADDR_WIDTH-1:0] read_cmd_address,
input wire [31:0] read_cmd_bytes,
input wire [31:0] read_cmd_epoch,
input wire [127:0] read_cmd_header,
output wire  read_valid,
input wire  read_ready,
output wire [127:0] read_data,
output wire [127:0] read_header,
output wire [15:0] read_keep,
output wire  read_last,
output wire [31:0] read_epoch,
output wire  read_status_valid,
input wire  read_status_ready,
output wire  read_status_ok,
output wire [7:0] read_status_error,
output wire [31:0] read_status_bytes,
output wire [31:0] read_status_epoch,
output wire [127:0] read_status_header,
output wire read_transport_busy,write_transport_busy,
output wire  transport_busy,
output wire  transport_requires_reset,
output wire [3:0] awid,
output wire [ADDR_WIDTH-1:0] awaddr,
output wire [7:0] awlen,
output wire [2:0] awsize,
output wire [1:0] awburst,
output wire  awvalid,
input wire  awready,
output wire [127:0] wdata,
output wire [15:0] wstrb,
output wire  wlast,
output wire  wvalid,
input wire  wready,
input wire [3:0] bid,
input wire [1:0] bresp,
input wire  bvalid,
output wire  bready,
output wire [3:0] arid,
output wire [ADDR_WIDTH-1:0] araddr,
output wire [7:0] arlen,
output wire [2:0] arsize,
output wire [1:0] arburst,
output wire  arvalid,
input wire  arready,
input wire [3:0] rid,
input wire [127:0] rdata,
input wire [1:0] rresp,
input wire  rlast,
input wire  rvalid,
output wire  rready
);
wire  c_begin_valid;
wire  c_begin_ready;
wire [31:0] c_begin_frame_id;
wire [12:0] c_begin_roi_width;
wire [12:0] c_begin_roi_height;
wire [31:0] c_begin_expected_pixels;
wire [31:0] c_begin_expected_bytes;
wire [1:0] c_begin_role;
wire  c_cancel_update;
wire  c_source_frame_status_valid;
wire  c_source_frame_status_ready;
wire  c_source_frame_status_complete;
wire  c_source_frame_status_ok;
wire [7:0] c_source_frame_status_error;
wire [31:0] c_source_frame_status_frame_id;
wire [31:0] c_source_frame_status_epoch;
wire [127:0] c_source_frame_status_header;
wire [127:0] c_pending_write_header;
wire [31:0] c_pending_write_epoch;
wire  c_sample_valid;
wire  c_sample_ready;
wire [127:0] c_sample_data;
wire [15:0] c_sample_keep;
wire [2:0] c_sample_pixels;
wire [4:0] c_sample_bytes;
wire  c_sample_sof;
wire  c_sample_eof;
wire [31:0] c_sample_frame_id;
wire [1:0] c_sample_lasers;
wire [7:0] c_sample_error;
wire  c_writer_abort;
wire  c_writer_quiescent;
wire  c_update_busy;
wire  c_update_event_valid;
wire  c_update_event_ready;
wire  c_update_event_ok;
wire [7:0] c_update_event_error;
wire [127:0] c_update_event_header;
wire [31:0] c_update_event_epoch;
wire cache_read_cmd_ready;

// Both local functional resets assert asynchronously and release locally.
(* async_reg="true" *) reg [RESET_STAGES-1:0] camera_release,ddr_release;
always @(posedge camera_clk or negedge reset_n)
 if(!reset_n)camera_release<=0;else camera_release<={camera_release[RESET_STAGES-2:0],1'b1};
always @(posedge ddr_clk or negedge reset_n)
 if(!reset_n)ddr_release<=0;else ddr_release<={ddr_release[RESET_STAGES-2:0],1'b1};
wire camera_reset_n=camera_release[RESET_STAGES-1],ddr_reset_n=ddr_release[RESET_STAGES-1];
reg cancel_latched;
(* async_reg="true" *) reg [1:0] cancel_camera_sync;
always @(posedge camera_clk or negedge camera_reset_n)
 if(!camera_reset_n)cancel_camera_sync<=0;
 else cancel_camera_sync<={cancel_camera_sync[0],cancel_latched};

// command={epoch,token,geometry,calibration,width,height,x0,y0,x1,y1}.
wire [207:0] command_in={cfg_role,config_epoch,cfg_token,config_geometry,config_calibration,
 cfg_width,cfg_height,cfg_x0,cfg_y0,cfg_x1,cfg_y1};
wire [207:0] command_out;
wire command_s_ready,command_valid,command_ready;
wire [1:0] cmd_role,armed_role;
wire [31:0] cmd_epoch,cmd_token,cmd_geometry,cmd_calibration;
wire [12:0] cmd_width,cmd_height,cmd_x0,cmd_y0,cmd_x1,cmd_y1;
assign {cmd_role,cmd_epoch,cmd_token,cmd_geometry,cmd_calibration,cmd_width,cmd_height,
 cmd_x0,cmd_y0,cmd_x1,cmd_y1}=command_out;
wire [25:0] request_pixels=(cfg_x1-cfg_x0)*(cfg_y1-cfg_y0);
wire [27:0] request_bytes={request_pixels,2'b00};
reg known_geometry;
reg [31:0] last_geometry;
reg [77:0] last_rectangle;
wire rectangle_reuse=known_geometry&&config_geometry==last_geometry&&
 {cfg_width,cfg_height,cfg_x0,cfg_y0,cfg_x1,cfg_y1}!=last_rectangle;
wire bad_arm=!operator_confirmed||cfg_role==3||!ALLOWED_ROLES[cfg_role]||cancel||config_epoch==0||cfg_token==0||
 cfg_width==0||cfg_height==0||cfg_width[1:0]!=0||cfg_x0[1:0]!=0||cfg_x1[1:0]!=0||
 cfg_x0>=cfg_x1||cfg_y0>=cfg_y1||cfg_x1>cfg_width||cfg_y1>cfg_height||
 request_bytes>SLOT_BYTES||rectangle_reuse;
assign arm_ready=ddr_reset_n&&!capture_busy&&!event_valid&&
 (bad_arm||(command_s_ready&&c_begin_ready&&!write_transport_busy&&!transport_requires_reset));
wire arm_take=arm_valid&&arm_ready;
afc03_frame_async_fifo #(.WIDTH(208),.ADDR_BITS(1)) commands(
 .reset_n(reset_n),.write_clk(ddr_clk),.s_valid(arm_take&&!bad_arm),
 .s_ready(command_s_ready),.s_data(command_in),.read_clk(camera_clk),
 .m_valid(command_valid),.m_ready(command_ready),.m_data(command_out),
 .write_online(),.read_online());

wire tap_arm_ready,tap_busy,tap_fault;
wire [7:0] tap_fault_code;
reg [31:0] camera_geometry,camera_calibration;reg [1:0] camera_role;
always @(posedge camera_clk or negedge camera_reset_n)
 if(!camera_reset_n)begin camera_geometry<=0;camera_calibration<=0;camera_role<=0;end
 else if(command_valid&&command_ready)begin
  camera_role<=cmd_role;camera_geometry<=cmd_geometry;camera_calibration<=cmd_calibration;
 end
assign command_ready=tap_arm_ready;
wire td_valid,td_ready,tv,tr,ts_valid,ts_ready,ts_ok;
wire [7:0] ts_error;
wire [31:0] td_frame,td_epoch,td_token,td_geometry,td_calibration,td_pixels,td_bytes;
wire [12:0] td_width,td_height,td_x0,td_y0,td_x1,td_y1;
wire [127:0] tp_data;wire [15:0] tp_keep;
wire tp_sof,tp_eol,tp_eof;wire [12:0] tp_x,tp_y;
wire [31:0] tp_frame,tp_epoch,tp_token,ts_frame,ts_epoch,ts_token,ts_source,ts_stored,ts_output;
afc03_camera_roi_tap #(.REQUIRE_MARKER(REQUIRE_MARKER),.FIFO_ADDR_BITS(TAP_FIFO_ADDR_BITS),.TIMEOUT_CYCLES(CAMERA_TIMEOUT)) tap(
 .source_pending(source_pending),.source_token(source_token),
 .clk(camera_clk),.rst_n(camera_reset_n),.stream_rst_n(stream_rst_n),
 .s_data(camera_data),.s_valid(camera_valid),.source_ready(camera_ready),
 .s_user(camera_sof),.s_last(camera_eol),.source_epoch(camera_epoch),
 .arm_valid(command_valid),.arm_ready(tap_arm_ready),
 .cfg_width(cmd_width),.cfg_height(cmd_height),.cfg_x0(cmd_x0),.cfg_y0(cmd_y0),
 .cfg_x1(cmd_x1),.cfg_y1(cmd_y1),
 .cfg_token(cmd_epoch==camera_epoch?cmd_token:32'd0),
 .cfg_geometry(cmd_geometry),.cfg_calibration(cmd_calibration),.cancel(cancel_camera_sync[1]),
 .busy(tap_busy),.fault_pending(tap_fault),.fault_code(tap_fault_code),
 .desc_valid(td_valid),.desc_ready(td_ready),.desc_frame_id(td_frame),.desc_epoch(td_epoch),
 .desc_token(td_token),.desc_geometry(td_geometry),.desc_calibration(td_calibration),
 .desc_image_width(td_width),.desc_image_height(td_height),.desc_x0(td_x0),.desc_y0(td_y0),
 .desc_x1(td_x1),.desc_y1(td_y1),.desc_pixels(td_pixels),.desc_bytes(td_bytes),
 .m_valid(tv),.m_ready(tr),.m_data(tp_data),.m_keep(tp_keep),.m_sof(tp_sof),.m_eol(tp_eol),.m_eof(tp_eof),
 .m_x(tp_x),.m_y(tp_y),.m_frame_id(tp_frame),.m_epoch(tp_epoch),.m_token(tp_token),
 .frame_status_valid(ts_valid),.frame_status_ready(ts_ready),.frame_status_ok(ts_ok),.frame_status_error(ts_error),
 .frame_status_frame_id(ts_frame),.frame_status_epoch(ts_epoch),.frame_status_token(ts_token),
 .frame_status_source_pixels(ts_source),.frame_status_stored_pixels(ts_stored),.frame_status_output_pixels(ts_output));

wire [303:0] desc_out;
wire desc_valid,desc_ready;
afc03_frame_async_fifo #(.WIDTH(304),.ADDR_BITS(1)) descriptors(
 .reset_n(reset_n),.write_clk(camera_clk),.s_valid(td_valid),.s_ready(td_ready),
 .s_data({camera_role,td_frame,td_epoch,td_token,td_geometry,td_calibration,td_width,td_height,
 td_x0,td_y0,td_x1,td_y1,td_pixels,td_bytes}),.read_clk(ddr_clk),
 .m_valid(desc_valid),.m_ready(desc_ready),.m_data(desc_out),.write_online(),.read_online());
wire [334:0] pixel_out;
wire pixel_valid,pixel_ready;
afc03_frame_async_fifo #(.WIDTH(335),.ADDR_BITS(PIXEL_FIFO_ADDR_BITS)) pixels(
 .reset_n(reset_n),.write_clk(camera_clk),.s_valid(tv),.s_ready(tr),
 .s_data({camera_role,camera_geometry,camera_calibration,tp_token,tp_epoch,tp_frame,tp_x,tp_y,
 tp_sof,tp_eol,tp_eof,tp_keep,tp_data}),.read_clk(ddr_clk),.m_valid(pixel_valid),
 .m_ready(pixel_ready),.m_data(pixel_out),.write_online(),.read_online());
wire [266:0] status_out;
wire final_valid,final_ready;
afc03_frame_async_fifo #(.WIDTH(267),.ADDR_BITS(1)) final_status(
 .reset_n(reset_n),.write_clk(camera_clk),.s_valid(ts_valid),.s_ready(ts_ready),
 .s_data({camera_role,camera_geometry,camera_calibration,ts_ok,ts_error,ts_frame,ts_epoch,ts_token,
 ts_source,ts_stored,ts_output}),.read_clk(ddr_clk),.m_valid(final_valid),
 .m_ready(final_ready),.m_data(status_out),.write_online(),.read_online());

reg [207:0] armed_command;
wire [31:0] armed_epoch,armed_token,armed_geometry,armed_calibration;
wire [12:0] armed_width,armed_height,armed_x0,armed_y0,armed_x1,armed_y1;
assign {armed_role,armed_epoch,armed_token,armed_geometry,armed_calibration,armed_width,armed_height,
 armed_x0,armed_y0,armed_x1,armed_y1}=armed_command;
reg desc_seen,started,final_seen,source_sent,result_seen,local_bad,offered_pixel;
reg [303:0] description;
wire [31:0] df,de,dt,dg,dc,dp,db;
wire [12:0] dw,dh,dx0,dy0,dx1,dy1;
wire [1:0] descriptor_role,source_role,pixel_role;
assign {descriptor_role,df,de,dt,dg,dc,dw,dh,dx0,dy0,dx1,dy1,dp,db}=description;
reg [266:0] source_result;
wire [31:0] sg,sc,sf,se,st,sp,ss,so;
wire sok;wire [7:0] serr;
assign {source_role,sg,sc,sok,serr,sf,se,st,sp,ss,so}=source_result;
wire [31:0] pg,pc,pt,pe,pf;
wire [12:0] px,py;wire psof,peol,peof;
wire [15:0] pkeep;wire [127:0] pdata;
assign {pixel_role,pg,pc,pt,pe,pf,px,py,psof,peol,peof,pkeep,pdata}=pixel_out;
reg [31:0] drained_pixels;
reg [12:0] expected_x,expected_y;
reg [127:0] joined_header;
reg [31:0] joined_epoch;
reg result_ok;reg [7:0] result_error;
reg [127:0] result_header;
wire config_changed=config_epoch!=armed_epoch||config_geometry!=armed_geometry||config_calibration!=armed_calibration;
wire descriptor_bad=descriptor_role!=armed_role||de!=armed_epoch||dt!=armed_token||dg!=armed_geometry||dc!=armed_calibration||
 {dw,dh,dx0,dy0,dx1,dy1}!=armed_command[77:0]||df==0||dp==0||db!=dp*4;
wire source_bad=source_role!=armed_role||!sok||serr!=0||se!=armed_epoch||st!=armed_token||sg!=armed_geometry||sc!=armed_calibration||
 (desc_seen&&(sf!=df||sp!=dp||ss!=dp||so!=dp));
wire pixel_bad=pixel_role!=armed_role||pg!=armed_geometry||pc!=armed_calibration||pt!=armed_token||pe!=armed_epoch||pf!=df||
 pkeep!=16'hffff||px!=expected_x||py!=expected_y||
 psof!=(drained_pixels==0)||peol!=(px+14'd4=={1'b0,armed_x1})||
 peof!=((px+14'd4=={1'b0,armed_x1})&&(py+14'd1=={1'b0,armed_y1}));
wire discard=local_bad||cancel_latched||c_writer_abort||transport_requires_reset||
 (result_seen&&!result_ok)||(final_seen&&source_bad);
assign desc_ready=capture_busy&&!desc_seen;
assign final_ready=capture_busy&&!final_seen;
// A SOF descriptor can precede bottom-of-image ROI by almost one full frame.
// Do not start the mover's inactivity timer until an actual pixel is queued.
assign c_begin_valid=capture_busy&&desc_seen&&!started&&pixel_valid&&!discard&&!descriptor_bad;
assign c_begin_frame_id=df;assign c_begin_roi_width=dx1-dx0;assign c_begin_roi_height=dy1-dy0;
assign c_begin_expected_pixels=dp;assign c_begin_expected_bytes=db;assign c_begin_role=armed_role;
// Same-cycle abort reaches slots before its atomic commit edge; waiting for
// cancel_latched here would incorrectly allow a last-cycle cancellation.
assign c_cancel_update=capture_busy&&(cancel_latched||local_bad||cancel||config_changed||memory_invalidated);
// Once offered, a pixel remains VALID/stable through a cancellation until the
// mover accepts it, or a failed mover is explicitly quiescent. Pending bytes
// that have not yet been offered can be discarded immediately after failure.
wire abandon_offered=discard&&c_writer_quiescent;
assign c_sample_valid=capture_busy&&started&&pixel_valid&&
 (!discard||(offered_pixel&&!abandon_offered));
assign pixel_ready=capture_busy&&((discard&&(!offered_pixel||abandon_offered))||
 (started&&c_sample_ready));
assign c_sample_data=pdata;assign c_sample_keep=pkeep;assign c_sample_pixels=3'd4;assign c_sample_bytes=5'd16;
assign c_sample_sof=psof;assign c_sample_eof=peof;assign c_sample_frame_id=pf;
assign c_sample_lasers=pixel_role;assign c_sample_error=pixel_bad?8'h81:8'd0;
assign c_source_frame_status_valid=capture_busy&&started&&final_seen&&!source_sent&&c_update_busy&&
 joined_header[127:96]==df&&joined_epoch==de;
assign c_source_frame_status_complete=1'b1;assign c_source_frame_status_ok=!source_bad&&!local_bad&&!cancel_latched;
assign c_source_frame_status_error=source_bad?(serr!=0?serr:8'h82):local_bad?8'h83:cancel_latched?8'h84:0;
assign c_source_frame_status_frame_id=sf;assign c_source_frame_status_epoch=se;
assign c_source_frame_status_header=joined_header;
assign c_update_event_ready=1'b1;
assign read_cmd_ready=cache_read_cmd_ready;

always @(posedge ddr_clk or negedge ddr_reset_n)begin
 if(!ddr_reset_n)begin
  capture_busy<=0;event_valid<=0;event_ok<=0;event_committed<=0;event_error<=0;event_source_error<=0;
  event_token<=0;event_epoch<=0;event_header<=0;cancel_latched<=0;armed_command<=0;
  desc_seen<=0;started<=0;final_seen<=0;source_sent<=0;result_seen<=0;local_bad<=0;offered_pixel<=0;
  description<=0;source_result<=0;drained_pixels<=0;expected_x<=0;expected_y<=0;
  joined_header<=0;joined_epoch<=0;result_ok<=0;result_error<=0;result_header<=0;
  known_geometry<=0;last_geometry<=0;last_rectangle<=0;
 end else begin
  if(event_valid&&event_ready)event_valid<=0;
  if(arm_take)begin
   event_token<=cfg_token;event_epoch<=config_epoch;event_header<=0;event_source_error<=0;event_committed<=0;
   if(bad_arm)begin event_valid<=1;event_ok<=0;event_error<=!operator_confirmed?8'h80:rectangle_reuse?8'h82:8'h81;end
   else begin
    capture_busy<=1;cancel_latched<=0;armed_command<=command_in;
    known_geometry<=1;last_geometry<=config_geometry;
    last_rectangle<={cfg_width,cfg_height,cfg_x0,cfg_y0,cfg_x1,cfg_y1};
    desc_seen<=0;started<=0;final_seen<=0;source_sent<=0;result_seen<=0;local_bad<=0;offered_pixel<=0;
    drained_pixels<=0;expected_x<=cfg_x0;expected_y<=cfg_y0;result_header<=0;
   end
  end
  if(capture_busy)begin
   if(c_sample_valid&&!c_sample_ready)offered_pixel<=1;
   if((c_sample_valid&&c_sample_ready)||abandon_offered)offered_pixel<=0;
   if(cancel||config_changed||memory_invalidated)begin cancel_latched<=1;local_bad<=1;end
   if(desc_valid&&desc_ready)begin description<=desc_out;desc_seen<=1;end
   if(desc_seen&&descriptor_bad)local_bad<=1;
   if(final_valid&&final_ready)begin source_result<=status_out;final_seen<=1;end
   if(c_begin_valid&&c_begin_ready)started<=1;
   // The slots' new header is registered one cycle after begin acceptance.
   if(started&&!source_sent)begin joined_header<=c_pending_write_header;joined_epoch<=c_pending_write_epoch;end
   if(pixel_valid&&pixel_ready)begin
    drained_pixels<=drained_pixels+4;
    if(!discard&&pixel_bad)local_bad<=1;
    if(expected_x+14'd4=={1'b0,armed_x1})begin expected_x<=armed_x0;expected_y<=expected_y+1'b1;end
    else expected_x<=expected_x+13'd4;
   end
   if(c_source_frame_status_valid&&c_source_frame_status_ready)source_sent<=1;
   if(c_update_event_valid)begin
    result_seen<=1;result_ok<=c_update_event_ok;result_error<=c_update_event_error;result_header<=c_update_event_header;
   end
   // A final camera status is emitted only after every tap word entered the
   // pixel FIFO. Its output count is a cross-queue drain barrier, not an empty
   // flag sampled too early. Failure without any descriptor/pixels also ends.
   if(final_seen&&((sf==0&&serr!=11)||desc_seen)&&drained_pixels==so&&!c_update_busy&&c_writer_quiescent&&
      (!started||result_seen))begin
    capture_busy<=0;cancel_latched<=0;event_valid<=1;event_token<=armed_token;event_epoch<=armed_epoch;
    event_header<=started?result_header:128'd0;event_source_error<=serr;
    event_committed<=started&&result_seen&&result_ok;
    event_ok<=started&&result_ok&&!source_bad&&!local_bad&&!cancel_latched&&!cancel&&!config_changed&&!memory_invalidated;
    event_error<=started&&result_ok&&(config_changed||memory_invalidated)?8'h87:
      started&&result_ok&&cancel?8'h86:started&&!result_ok?result_error:source_bad?8'h83:
      (local_bad||cancel_latched)?8'h84:!started?8'h85:8'd0;
   end
  end
 end
end

afc03_role_cache_adapter #(.ALLOWED_ROLES(ALLOWED_ROLES),.ADDR_WIDTH(ADDR_WIDTH),.SLOT0_BASE(SLOT0_BASE),
 .SLOT1_BASE(SLOT1_BASE),.SLOT_BYTES(SLOT_BYTES),.MOVER_TIMEOUT(MOVER_TIMEOUT),
 .FRAME_TIMEOUT(FRAME_TIMEOUT)) cache(
.clk(ddr_clk),
.rst_n(ddr_reset_n),
.transport_rst_n(ddr_reset_n),
.config_epoch(config_epoch),
.config_geometry(config_geometry),
.config_calibration(config_calibration),
.memory_invalidated(memory_invalidated),
.begin_valid(c_begin_valid),
.begin_ready(c_begin_ready),
.begin_frame_id(c_begin_frame_id),
.begin_roi_width(c_begin_roi_width),
.begin_roi_height(c_begin_roi_height),
.begin_expected_pixels(c_begin_expected_pixels),
.begin_expected_bytes(c_begin_expected_bytes),
.begin_role(c_begin_role),
.cancel_update(c_cancel_update),
.source_frame_status_valid(c_source_frame_status_valid),
.source_frame_status_ready(c_source_frame_status_ready),
.source_frame_status_complete(c_source_frame_status_complete),
.source_frame_status_ok(c_source_frame_status_ok),
.source_frame_status_error(c_source_frame_status_error),
.source_frame_status_frame_id(c_source_frame_status_frame_id),
.source_frame_status_epoch(c_source_frame_status_epoch),
.source_frame_status_header(c_source_frame_status_header),
.pending_write_header(c_pending_write_header),
.pending_write_epoch(c_pending_write_epoch),
.sample_valid(c_sample_valid),
.sample_ready(c_sample_ready),
.sample_data(c_sample_data),
.sample_keep(c_sample_keep),
.sample_pixels(c_sample_pixels),
.sample_bytes(c_sample_bytes),
.sample_sof(c_sample_sof),
.sample_eof(c_sample_eof),
.sample_frame_id(c_sample_frame_id),
.sample_lasers(c_sample_lasers),
.sample_error(c_sample_error),
.writer_abort(c_writer_abort),
.writer_quiescent(c_writer_quiescent),
.update_busy(c_update_busy),
.update_event_valid(c_update_event_valid),
.update_event_ready(c_update_event_ready),
.update_event_ok(c_update_event_ok),
.update_event_error(c_update_event_error),
.update_event_header(c_update_event_header),
.update_event_epoch(c_update_event_epoch),
.active_role(active_role),.grant_role(grant_role),.active_valid(active_valid),
.active_slot(active_slot),
.active_header(active_header),
.active_epoch(active_epoch),
.active_pixels(active_pixels),
.active_bytes(active_bytes),
.invalidate_readers(invalidate_readers),
.acquire_valid(acquire_valid),
.acquire_ready(acquire_ready),
.grant_valid(grant_valid),
.grant_slot(grant_slot),
.grant_address(grant_address),
.grant_header(grant_header),
.grant_epoch(grant_epoch),
.grant_pixels(grant_pixels),
.grant_bytes(grant_bytes),
.release_valid(release_valid),
.release_slot(release_slot),
.release_header(release_header),
.release_epoch(release_epoch),
.release_ok(release_ok),
.protocol_error(protocol_error),
.blocked_by_readers(blocked_by_readers),
.read_cmd_valid(read_cmd_valid),
.read_cmd_ready(cache_read_cmd_ready),
.read_cmd_address(read_cmd_address),
.read_cmd_bytes(read_cmd_bytes),
.read_cmd_epoch(read_cmd_epoch),
.read_cmd_header(read_cmd_header),
.read_valid(read_valid),
.read_ready(read_ready),
.read_data(read_data),
.read_header(read_header),
.read_keep(read_keep),
.read_last(read_last),
.read_epoch(read_epoch),
.read_status_valid(read_status_valid),
.read_status_ready(read_status_ready),
.read_status_ok(read_status_ok),
.read_status_error(read_status_error),
.read_status_bytes(read_status_bytes),
.read_status_epoch(read_status_epoch),
.read_status_header(read_status_header),
.read_transport_busy(read_transport_busy),.write_transport_busy(write_transport_busy),
.transport_busy(transport_busy),
.transport_requires_reset(transport_requires_reset),
.awid(awid),
.awaddr(awaddr),
.awlen(awlen),
.awsize(awsize),
.awburst(awburst),
.awvalid(awvalid),
.awready(awready),
.wdata(wdata),
.wstrb(wstrb),
.wlast(wlast),
.wvalid(wvalid),
.wready(wready),
.bid(bid),
.bresp(bresp),
.bvalid(bvalid),
.bready(bready),
.arid(arid),
.araddr(araddr),
.arlen(arlen),
.arsize(arsize),
.arburst(arburst),
.arvalid(arvalid),
.arready(arready),
.rid(rid),
.rdata(rdata),
.rresp(rresp),
.rlast(rlast),
.rvalid(rvalid),
.rready(rready));
endmodule
