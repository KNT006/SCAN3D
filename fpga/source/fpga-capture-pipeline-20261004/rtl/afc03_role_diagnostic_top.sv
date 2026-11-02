`timescale 1ns/1ps
// Generated wiring + reviewed diagnostic_logic.svh. Background-only BGC1.
module afc03_role_diagnostic_top #(
 parameter REQUIRE_MARKER=0,
 parameter [3:0] ALLOWED_ROLES=4'b0001, parameter [11:0] PAGE=12'h022,
 parameter ADDR_WIDTH=28,
 parameter [ADDR_WIDTH-1:0] SLOT0_BASE=28'h0100000,SLOT1_BASE=28'h0900000,
 parameter SLOT_BYTES=8388608,PIXEL_FIFO_ADDR_BITS=8,TAP_FIFO_ADDR_BITS=8,
 parameter MOVER_TIMEOUT=1000000,FRAME_TIMEOUT=100000000,CAMERA_TIMEOUT=100000000,
 parameter HOST_WATCHDOG=125000000
)(
 output wire source_pending,output wire [31:0] source_token,
 input wire capture_allowed,
 input wire external_access,arb_grant,
 output wire arb_request,arb_idle,capture_idle,
 output wire ext_read_transport_busy,
 output wire [12:0] image_width,image_height,
 output wire [31:0] current_epoch,current_geometry,current_calibration,
 output wire [1:0] ext_active_role,
 output wire [1:0] ext_grant_role,
 output wire  ext_active_valid,
 output wire  ext_active_slot,
 output wire [127:0] ext_active_header,
 output wire [31:0] ext_active_epoch,
 output wire [31:0] ext_active_pixels,
 output wire [31:0] ext_active_bytes,
 output wire  ext_invalidate_readers,
 input wire  ext_acquire_valid,
 output wire  ext_acquire_ready,
 output wire  ext_grant_valid,
 output wire  ext_grant_slot,
 output wire [ADDR_WIDTH-1:0] ext_grant_address,
 output wire [127:0] ext_grant_header,
 output wire [31:0] ext_grant_epoch,
 output wire [31:0] ext_grant_pixels,
 output wire [31:0] ext_grant_bytes,
 input wire  ext_release_valid,
 input wire  ext_release_slot,
 input wire [127:0] ext_release_header,
 input wire [31:0] ext_release_epoch,
 output wire  ext_release_ok,
 output wire  ext_protocol_error,
 input wire  ext_read_cmd_valid,
 output wire  ext_read_cmd_ready,
 input wire [ADDR_WIDTH-1:0] ext_read_cmd_address,
 input wire [31:0] ext_read_cmd_bytes,
 input wire [31:0] ext_read_cmd_epoch,
 input wire [127:0] ext_read_cmd_header,
 output wire  ext_read_valid,
 input wire  ext_read_ready,
 output wire [127:0] ext_read_data,
 output wire [127:0] ext_read_header,
 output wire [15:0] ext_read_keep,
 output wire  ext_read_last,
 output wire [31:0] ext_read_epoch,
 output wire  ext_read_status_valid,
 input wire  ext_read_status_ready,
 output wire  ext_read_status_ok,
 output wire [7:0] ext_read_status_error,
 output wire [31:0] ext_read_status_bytes,
 output wire [31:0] ext_read_status_epoch,
 output wire [127:0] ext_read_status_header,
 output wire  ext_transport_busy,
 output wire  ext_transport_requires_reset,
 input wire hclk,hrst_n,dclk,drst_n,control_ready,ext_enabled,
 input wire [31:0] host_awaddr,host_wdata,host_araddr,
 input wire [3:0] host_wstrb,
 input wire host_awvalid,host_awready,host_wvalid,host_wready,host_arvalid,host_arready,
 output wire rd_select,output wire [31:0] rd_data,
 input wire stream_rst_n,input wire [127:0] camera_data,
 input wire camera_valid,camera_ready,camera_sof,camera_eol,
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
wire  c_arm_valid;
wire  c_arm_ready;
wire [12:0] c_cfg_width;
wire [12:0] c_cfg_height;
wire [12:0] c_cfg_x0;
wire [12:0] c_cfg_y0;
wire [12:0] c_cfg_x1;
wire [12:0] c_cfg_y1;
wire [31:0] c_cfg_token;
wire c_operator_confirmed;wire [1:0] c_cfg_role,c_active_role,c_grant_role;
wire  c_cancel;
wire  c_capture_busy;
wire  c_event_valid;
wire  c_event_ready;
wire  c_event_ok;
wire  c_event_committed;
wire [7:0] c_event_error;
wire [7:0] c_event_source_error;
wire [31:0] c_event_token;
wire [31:0] c_event_epoch;
wire [127:0] c_event_header;
wire [31:0] c_config_epoch;
wire [31:0] c_config_geometry;
wire [31:0] c_config_calibration;
wire  c_memory_invalidated;
wire  c_active_valid;
wire  c_active_slot;
wire [127:0] c_active_header;
wire [31:0] c_active_epoch;
wire [31:0] c_active_pixels;
wire [31:0] c_active_bytes;
wire  c_invalidate_readers;
wire  c_acquire_valid;
wire  c_acquire_ready;
wire  c_grant_valid;
wire  c_grant_slot;
wire [ADDR_WIDTH-1:0] c_grant_address;
wire [127:0] c_grant_header;
wire [31:0] c_grant_epoch;
wire [31:0] c_grant_pixels;
wire [31:0] c_grant_bytes;
wire  c_release_valid;
wire  c_release_slot;
wire [127:0] c_release_header;
wire [31:0] c_release_epoch;
wire  c_release_ok;
wire  c_protocol_error;
wire  c_blocked_by_readers;
wire  c_read_cmd_valid;
wire  c_read_cmd_ready;
wire [ADDR_WIDTH-1:0] c_read_cmd_address;
wire [31:0] c_read_cmd_bytes;
wire [31:0] c_read_cmd_epoch;
wire [127:0] c_read_cmd_header;
wire  c_read_valid;
wire  c_read_ready;
wire [127:0] c_read_data;
wire [127:0] c_read_header;
wire [15:0] c_read_keep;
wire  c_read_last;
wire [31:0] c_read_epoch;
wire  c_read_status_valid;
wire  c_read_status_ready;
wire  c_read_status_ok;
wire [7:0] c_read_status_error;
wire [31:0] c_read_status_bytes;
wire [31:0] c_read_status_epoch;
wire [127:0] c_read_status_header;
wire c_read_transport_busy,c_write_transport_busy;
wire  c_transport_busy;
wire  c_transport_requires_reset;
wire reset_n,dreset_n;wire [31:0] camera_epoch;
wire cmd_valid,cmd_ready;wire [351:0] cmd_data;
reg reply_valid;wire reply_ready;reg [511:0] reply_data;
afc03_laser_csr_bridge #(.HOST_WATCHDOG(HOST_WATCHDOG),.PAGE(PAGE)) bridge(
 .hclk(hclk),.hrst_n(hrst_n),.dclk(dclk),.drst_n(drst_n),
 .host_awaddr(host_awaddr),.host_wdata(host_wdata),.host_araddr(host_araddr),.host_wstrb(host_wstrb),
 .host_awvalid(host_awvalid),.host_awready(host_awready),.host_wvalid(host_wvalid),.host_wready(host_wready),
 .host_arvalid(host_arvalid),.host_arready(host_arready),.rd_select(rd_select),.rd_data(rd_data),
 .camera_epoch(camera_epoch),.reset_n(reset_n),.dreset_n(dreset_n),
 .command_valid(cmd_valid),.command_ready(cmd_ready),.command_data(cmd_data),
 .response_valid(reply_valid),.response_ready(reply_ready),.response_data(reply_data));
afc03_role_capture_cdc #(.REQUIRE_MARKER(REQUIRE_MARKER),.ALLOWED_ROLES(ALLOWED_ROLES),.ADDR_WIDTH(ADDR_WIDTH),.SLOT0_BASE(SLOT0_BASE),.SLOT1_BASE(SLOT1_BASE),
 .SLOT_BYTES(SLOT_BYTES),.PIXEL_FIFO_ADDR_BITS(PIXEL_FIFO_ADDR_BITS),.TAP_FIFO_ADDR_BITS(TAP_FIFO_ADDR_BITS),
 .MOVER_TIMEOUT(MOVER_TIMEOUT),.FRAME_TIMEOUT(FRAME_TIMEOUT),.CAMERA_TIMEOUT(CAMERA_TIMEOUT)) capture(
 .reset_n(reset_n),
 .source_pending(source_pending),.source_token(source_token),
 .camera_clk(hclk),
 .ddr_clk(dclk),
 .stream_rst_n(stream_rst_n),
 .camera_data(camera_data),
 .camera_valid(camera_valid),
 .camera_ready(camera_ready),
 .camera_sof(camera_sof),
 .camera_eol(camera_eol),
 .camera_epoch(camera_epoch),
 .arm_valid(c_arm_valid),
 .arm_ready(c_arm_ready),
 .cfg_width(c_cfg_width),
 .cfg_height(c_cfg_height),
 .cfg_x0(c_cfg_x0),
 .cfg_y0(c_cfg_y0),
 .cfg_x1(c_cfg_x1),
 .cfg_y1(c_cfg_y1),
 .cfg_token(c_cfg_token),
 .operator_confirmed(c_operator_confirmed),.cfg_role(c_cfg_role),.active_role(c_active_role),.grant_role(c_grant_role),
 .cancel(c_cancel),
 .capture_busy(c_capture_busy),
 .event_valid(c_event_valid),
 .event_ready(c_event_ready),
 .event_ok(c_event_ok),
 .event_committed(c_event_committed),
 .event_error(c_event_error),
 .event_source_error(c_event_source_error),
 .event_token(c_event_token),
 .event_epoch(c_event_epoch),
 .event_header(c_event_header),
 .config_epoch(c_config_epoch),
 .config_geometry(c_config_geometry),
 .config_calibration(c_config_calibration),
 .memory_invalidated(c_memory_invalidated),
 .active_valid(c_active_valid),
 .active_slot(c_active_slot),
 .active_header(c_active_header),
 .active_epoch(c_active_epoch),
 .active_pixels(c_active_pixels),
 .active_bytes(c_active_bytes),
 .invalidate_readers(c_invalidate_readers),
 .acquire_valid(c_acquire_valid),
 .acquire_ready(c_acquire_ready),
 .grant_valid(c_grant_valid),
 .grant_slot(c_grant_slot),
 .grant_address(c_grant_address),
 .grant_header(c_grant_header),
 .grant_epoch(c_grant_epoch),
 .grant_pixels(c_grant_pixels),
 .grant_bytes(c_grant_bytes),
 .release_valid(c_release_valid),
 .release_slot(c_release_slot),
 .release_header(c_release_header),
 .release_epoch(c_release_epoch),
 .release_ok(c_release_ok),
 .protocol_error(c_protocol_error),
 .blocked_by_readers(c_blocked_by_readers),
 .read_cmd_valid(c_read_cmd_valid),
 .read_cmd_ready(c_read_cmd_ready),
 .read_cmd_address(c_read_cmd_address),
 .read_cmd_bytes(c_read_cmd_bytes),
 .read_cmd_epoch(c_read_cmd_epoch),
 .read_cmd_header(c_read_cmd_header),
 .read_valid(c_read_valid),
 .read_ready(c_read_ready),
 .read_data(c_read_data),
 .read_header(c_read_header),
 .read_keep(c_read_keep),
 .read_last(c_read_last),
 .read_epoch(c_read_epoch),
 .read_status_valid(c_read_status_valid),
 .read_status_ready(c_read_status_ready),
 .read_status_ok(c_read_status_ok),
 .read_status_error(c_read_status_error),
 .read_status_bytes(c_read_status_bytes),
 .read_status_epoch(c_read_status_epoch),
 .read_status_header(c_read_status_header),
 .read_transport_busy(c_read_transport_busy),.write_transport_busy(c_write_transport_busy),
 .transport_busy(c_transport_busy),
 .transport_requires_reset(c_transport_requires_reset),
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
 .rready(rready)
);
wire  diag_acquire_valid;
wire  diag_release_valid;
wire  diag_release_slot;
wire [127:0] diag_release_header;
wire [31:0] diag_release_epoch;
wire  diag_read_cmd_valid;
wire [ADDR_WIDTH-1:0] diag_read_cmd_address;
wire [31:0] diag_read_cmd_bytes;
wire [31:0] diag_read_cmd_epoch;
wire [127:0] diag_read_cmd_header;
wire  diag_read_ready;
wire  diag_read_status_ready;
localparam IDLE=0,DECODE=1,ARM_FIRE=2,ARM_ACK=3,ACQUIRE=4,GRANT=5,
 READ_OFFER=6,READ_DRAIN=7,RELEASE=8,RELEASE_ACK=9,MAKE_REPLY=10,SEND_REPLY=11;
reg [3:0] state;
reg [351:0] request;
wire [7:0] opcode=request[7:0];wire [31:0] req_id=request[63:32];
wire [31:0] req_epoch=request[95:64],req_geometry=request[127:96],req_calibration=request[159:128];
wire [31:0] req_token=request[191:160],req_dims=request[223:192];
wire [31:0] req_roi0=request[255:224],req_roi1=request[287:256];
wire [31:0] req_off=request[319:288],req_offset=request[351:320];
wire [12:0] req_width=req_dims[12:0],req_height=req_dims[28:16];
wire [12:0] req_x0=req_roi0[12:0],req_y0=req_roi0[28:16],req_x1=req_roi1[12:0],req_y1=req_roi1[28:16];
wire [25:0] req_pixels=(req_x1-req_x0)*(req_y1-req_y0);
wire bad_arm_config=req_epoch==0||req_geometry==0||req_calibration==0||req_token==0||(req_off[31:3]!=0||!req_off[0]||req_off[2:1]==3||!ALLOWED_ROLES[req_off[2:1]])||
 |req_dims[31:29]|| |req_dims[15:13]|| |req_roi0[31:29]|| |req_roi0[15:13]||
 |req_roi1[31:29]|| |req_roi1[15:13]|| req_width==0||req_height==0||req_width[1:0]!=0||
 req_x0>=req_x1||req_y0>=req_y1||req_x1>req_width||req_y1>req_height||
 req_x0[1:0]!=0||req_x1[1:0]!=0||{req_pixels,2'b00}>SLOT_BYTES;
reg [1:0] cfg_role;
reg [31:0] cfg_epoch,cfg_geometry,cfg_calibration,cfg_token;
reg [12:0] cfg_width,cfg_height,cfg_x0,cfg_y0,cfg_x1,cfg_y1;
assign c_config_epoch=cfg_epoch;assign c_config_geometry=cfg_geometry;assign c_config_calibration=cfg_calibration;
assign c_cfg_token=cfg_token;assign c_cfg_width=cfg_width;assign c_cfg_height=cfg_height;
assign c_cfg_x0=cfg_x0;assign c_cfg_y0=cfg_y0;assign c_cfg_x1=cfg_x1;assign c_cfg_y1=cfg_y1;
assign c_operator_confirmed=1'b1; // Only after explicit operator confirmation validation.
assign c_cfg_role=cfg_role;
assign c_memory_invalidated=!control_ready||!ext_enabled;
assign c_cancel=state==DECODE&&opcode==3;
assign c_arm_valid=state==ARM_FIRE;
assign c_event_ready=1'b1;
assign cmd_ready=state==IDLE&&!reply_valid;
reg event_seen,last_event_ok,last_event_committed;
reg [7:0] last_event_error,last_source_error;
reg [31:0] last_event_token,last_event_epoch;
reg [7:0] result;
reg pinned,pin_slot;reg [ADDR_WIDTH-1:0] pin_address;
reg [127:0] pin_header,read_payload;reg [31:0] pin_epoch,pin_pixels,pin_bytes;
reg read_got_data,read_got_status,read_bad,release_error;
wire [32:0] read_offset_end={1'b0,req_offset}+33'd16;
wire [32:0] read_address_end={{(33-ADDR_WIDTH){1'b0}},c_grant_address}+{1'b0,req_offset}+33'd16;
wire bad_read_range=read_offset_end>{1'b0,c_grant_bytes}||read_address_end>(33'd1<<ADDR_WIDTH);
assign diag_acquire_valid=state==ACQUIRE;
assign diag_release_valid=state==RELEASE;
assign diag_release_slot=pin_slot;assign diag_release_header=pin_header;assign diag_release_epoch=pin_epoch;
assign diag_read_cmd_valid=state==READ_OFFER;
assign diag_read_cmd_address=pin_address+req_offset;
assign diag_read_cmd_bytes=32'd16;assign diag_read_cmd_epoch=pin_epoch;assign diag_read_cmd_header=pin_header;
assign diag_read_ready=state==READ_DRAIN;
assign diag_read_status_ready=state==READ_DRAIN;
wire [15:0] flags={8'd0,ext_enabled,control_ready,c_protocol_error,c_blocked_by_readers,
 c_transport_requires_reset,c_transport_busy,c_active_valid,c_capture_busy};
wire unavailable=!control_ready||!ext_enabled||c_transport_requires_reset;
wire final_read_ok=result==0&&!read_bad&&!release_error&&!unavailable&&!c_invalidate_readers&&c_active_valid;
always @(posedge dclk or negedge dreset_n)begin
 if(!dreset_n)begin
  state<=IDLE;request<=0;reply_valid<=0;reply_data<=0;result<=0;
  cfg_role<=0;cfg_epoch<=0;cfg_geometry<=0;cfg_calibration<=0;cfg_token<=0;
  cfg_width<=0;cfg_height<=0;cfg_x0<=0;cfg_y0<=0;cfg_x1<=0;cfg_y1<=0;
  event_seen<=0;last_event_ok<=0;last_event_committed<=0;last_event_error<=0;last_source_error<=0;
  last_event_token<=0;last_event_epoch<=0;
  pinned<=0;pin_slot<=0;pin_address<=0;pin_header<=0;pin_epoch<=0;pin_pixels<=0;pin_bytes<=0;
  read_payload<=0;read_got_data<=0;read_got_status<=0;read_bad<=0;release_error<=0;
 end else begin
  if(c_event_valid)begin
   event_seen<=1;last_event_ok<=c_event_ok;last_event_committed<=c_event_committed;
   last_event_error<=c_event_error;last_source_error<=c_event_source_error;
   last_event_token<=c_event_token;last_event_epoch<=c_event_epoch;
  end
  case(state)
   IDLE:if(cmd_valid&&cmd_ready)begin
    request<=cmd_data;result<=0;pinned<=0;read_payload<=0;
    read_got_data<=0;read_got_status<=0;read_bad<=0;release_error<=0;state<=DECODE;
   end
   DECODE:begin
    if(external_access&&(opcode==4||(opcode==2&&!capture_allowed)))begin result<=1;state<=MAKE_REPLY;end
    else if((opcode==2||opcode==4)&&!arb_grant)state<=DECODE;
    else case(opcode)
     1:state<=MAKE_REPLY;
     2:begin
      if(unavailable)begin result<=6;state<=MAKE_REPLY;end
      else if(c_capture_busy||c_write_transport_busy||c_event_valid||c_blocked_by_readers||!c_arm_ready)begin result<=1;state<=MAKE_REPLY;end
      else if(bad_arm_config||(external_access&&
       (req_epoch!=cfg_epoch||req_geometry!=cfg_geometry||req_calibration!=cfg_calibration||
        req_width!=cfg_width||req_height!=cfg_height||req_x0!=cfg_x0||req_y0!=cfg_y0||req_x1!=cfg_x1||req_y1!=cfg_y1)))begin result<=2;state<=MAKE_REPLY;end
      else begin
       cfg_role<=req_off[2:1];cfg_epoch<=req_epoch;cfg_geometry<=req_geometry;cfg_calibration<=req_calibration;cfg_token<=req_token;
       cfg_width<=req_width;cfg_height<=req_height;cfg_x0<=req_x0;cfg_y0<=req_y0;cfg_x1<=req_x1;cfg_y1<=req_y1;
       state<=ARM_FIRE;
      end
     end
     3:state<=ARM_ACK; // Cancellation is requested; physical drain can finish later.
     4:begin
      if(unavailable)begin result<=6;state<=MAKE_REPLY;end
      else if(c_capture_busy||c_transport_busy)begin result<=1;state<=MAKE_REPLY;end
      else if(req_offset[3:0]!=0)begin result<=2;state<=MAKE_REPLY;end
      else if(!c_active_valid)begin result<=3;state<=MAKE_REPLY;end
      else state<=ACQUIRE;
     end
     default:begin result<=2;state<=MAKE_REPLY;end
    endcase
   end
   ARM_FIRE:if(c_arm_valid&&c_arm_ready)begin
    event_seen<=0;last_event_ok<=0;last_event_committed<=0;last_event_error<=0;last_source_error<=0;
    last_event_token<=0;last_event_epoch<=0;state<=ARM_ACK;
   end
   ARM_ACK:state<=MAKE_REPLY;
   ACQUIRE:begin
    if(c_acquire_ready)state<=GRANT; // A same-edge invalidation cannot lose an already granted reference.
    else if(unavailable)begin result<=6;state<=MAKE_REPLY;end
    else if(!c_active_valid)begin result<=3;state<=MAKE_REPLY;end
   end
   GRANT:if(c_grant_valid)begin
    pinned<=1;pin_slot<=c_grant_slot;pin_address<=c_grant_address;pin_header<=c_grant_header;
    pin_epoch<=c_grant_epoch;pin_pixels<=c_grant_pixels;pin_bytes<=c_grant_bytes;
    if(unavailable)begin result<=6;state<=RELEASE;end
    else if(bad_read_range)begin result<=4;state<=RELEASE;end
    else state<=READ_OFFER;
   end
   READ_OFFER:if(c_read_cmd_valid&&c_read_cmd_ready)state<=READ_DRAIN;
   READ_DRAIN:begin
    if(c_read_valid&&c_read_ready)begin
     read_payload<=c_read_data;read_got_data<=1;
     if(read_got_data||c_read_keep!=16'hffff||!c_read_last||c_read_header!=pin_header||c_read_epoch!=pin_epoch)read_bad<=1;
    end
    if(c_read_status_valid&&c_read_status_ready)begin
     read_got_status<=1;
     if(read_got_status||!c_read_status_ok||c_read_status_error!=0||c_read_status_bytes!=16||
        c_read_status_header!=pin_header||c_read_status_epoch!=pin_epoch)read_bad<=1;
    end
    if(unavailable||c_invalidate_readers)read_bad<=1;
    // Timeout reports may precede bus drain. Never release while AXI remains outstanding.
    if(read_got_status&&!c_transport_busy&&!c_read_status_valid&&!c_read_valid)begin
     if(read_bad||!read_got_data||unavailable)result<=5;
     state<=RELEASE;
    end
   end
   RELEASE:state<=RELEASE_ACK;
   RELEASE_ACK:begin
    if(!c_release_ok)begin result<=5;release_error<=1;end
    state<=MAKE_REPLY;
   end
   MAKE_REPLY:begin
    reply_data<=0;
    reply_data[31:0]<={flags,result,opcode};reply_data[63:32]<=req_id;
    reply_data[95:64]<=pinned?pin_epoch:c_active_epoch;
    reply_data[127:96]<=pinned?pin_pixels:c_active_pixels;
    reply_data[159:128]<=pinned?pin_bytes:c_active_bytes;
    reply_data[287:160]<=pinned?pin_header:c_active_header;
    reply_data[319:288]<={13'd0,event_seen,last_event_committed,last_event_ok,last_source_error,last_event_error};
    reply_data[351:320]<=last_event_token;reply_data[383:352]<=last_event_epoch;
    if(opcode==4&&final_read_ok)reply_data[511:384]<=read_payload;
    // Invalidation during release must not turn an old pinned identity into success.
    if(opcode==4&&result==0&&!final_read_ok)reply_data[15:8]<=8'd5;
    reply_valid<=1;state<=SEND_REPLY;
   end
   SEND_REPLY:if(reply_valid&&reply_ready)begin reply_valid<=0;state<=IDLE;end
   default:state<=IDLE;
  endcase
 end
end


assign ext_active_role=c_active_role;

assign ext_grant_role=c_grant_role;

assign ext_active_valid=c_active_valid;

assign ext_active_slot=c_active_slot;

assign ext_active_header=c_active_header;

assign ext_active_epoch=c_active_epoch;

assign ext_active_pixels=c_active_pixels;

assign ext_active_bytes=c_active_bytes;

assign ext_invalidate_readers=c_invalidate_readers;

assign c_acquire_valid=external_access?ext_acquire_valid:diag_acquire_valid;

assign ext_acquire_ready=external_access&&c_acquire_ready;

assign ext_grant_valid=external_access&&c_grant_valid;

assign ext_grant_slot=c_grant_slot;

assign ext_grant_address=c_grant_address;

assign ext_grant_header=c_grant_header;

assign ext_grant_epoch=c_grant_epoch;

assign ext_grant_pixels=c_grant_pixels;

assign ext_grant_bytes=c_grant_bytes;

assign c_release_valid=external_access?ext_release_valid:diag_release_valid;

assign c_release_slot=external_access?ext_release_slot:diag_release_slot;

assign c_release_header=external_access?ext_release_header:diag_release_header;

assign c_release_epoch=external_access?ext_release_epoch:diag_release_epoch;

assign ext_release_ok=external_access&&c_release_ok;

assign ext_protocol_error=c_protocol_error;

assign c_read_cmd_valid=external_access?ext_read_cmd_valid:diag_read_cmd_valid;

assign ext_read_cmd_ready=external_access&&c_read_cmd_ready;

assign c_read_cmd_address=external_access?ext_read_cmd_address:diag_read_cmd_address;

assign c_read_cmd_bytes=external_access?ext_read_cmd_bytes:diag_read_cmd_bytes;

assign c_read_cmd_epoch=external_access?ext_read_cmd_epoch:diag_read_cmd_epoch;

assign c_read_cmd_header=external_access?ext_read_cmd_header:diag_read_cmd_header;

assign ext_read_valid=external_access&&c_read_valid;

assign c_read_ready=external_access?ext_read_ready:diag_read_ready;

assign ext_read_data=c_read_data;

assign ext_read_header=c_read_header;

assign ext_read_keep=c_read_keep;

assign ext_read_last=c_read_last;

assign ext_read_epoch=c_read_epoch;

assign ext_read_status_valid=external_access&&c_read_status_valid;

assign c_read_status_ready=external_access?ext_read_status_ready:diag_read_status_ready;

assign ext_read_status_ok=c_read_status_ok;

assign ext_read_status_error=c_read_status_error;

assign ext_read_status_bytes=c_read_status_bytes;

assign ext_read_status_epoch=c_read_status_epoch;

assign ext_read_status_header=c_read_status_header;

assign ext_transport_busy=c_transport_busy;

assign ext_transport_requires_reset=c_transport_requires_reset;

assign arb_request=state==DECODE&&((opcode==2&&(!external_access||capture_allowed))||(opcode==4&&!external_access));
assign capture_idle=state==IDLE&&!c_capture_busy&&!c_write_transport_busy;
assign ext_read_transport_busy=c_read_transport_busy;
assign arb_idle=state==IDLE&&!c_capture_busy&&!c_transport_busy&&!c_read_valid&&!c_read_status_valid;
assign image_width=cfg_width;assign image_height=cfg_height;
assign current_epoch=cfg_epoch;assign current_geometry=cfg_geometry;assign current_calibration=cfg_calibration;
endmodule
