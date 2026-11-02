`timescale 1ns/1ps
module afc03_laser_board_top #(
 parameter REQUIRE_MARKER=0,
 parameter ADDR_WIDTH=28,SLOT_BYTES=8388608,
 parameter [27:0] BG0=28'h0100000,BG1=28'h0900000,ON0=28'h1100000,ON1=28'h1900000,
 parameter MAX_HEIGHT=1080,RESULT_DEPTH=2048
)(
output wire capture_pending,output wire [31:0] capture_token,
input wire  hclk,
input wire  hrst_n,
input wire  dclk,
input wire  drst_n,
input wire  control_ready,
input wire  ext_enabled,
input wire [31:0] host_awaddr,
input wire [31:0] host_wdata,
input wire [31:0] host_araddr,
input wire [3:0] host_wstrb,
input wire  host_awvalid,
input wire  host_awready,
input wire  host_wvalid,
input wire  host_wready,
input wire  host_arvalid,
input wire  host_arready,
output wire  rd_select,
output wire [31:0] rd_data,
input wire  stream_rst_n,
input wire [127:0] camera_data,
input wire  camera_valid,
input wire  camera_ready,
input wire  camera_sof,
input wire  camera_eol,
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
output wire [127:0] result_dma_data,
output wire result_dma_valid,result_dma_last,
input wire result_dma_ready,
output wire  rready
);
wire bg_source_pending,live_source_pending;
wire [31:0] bg_source_token,live_source_token;
// The write arbiter permits only one capture request to be in flight.
assign capture_pending=(bg_source_pending ^ live_source_pending);
assign capture_token=bg_source_pending?bg_source_token:live_source_token;
wire  bg_external_access;
wire  bg_arb_grant;
wire  bg_arb_request;
wire  bg_arb_idle;
wire [12:0] bg_image_width;
wire [12:0] bg_image_height;
wire [31:0] bg_current_epoch;
wire [31:0] bg_current_geometry;
wire [31:0] bg_current_calibration;
wire [1:0] bg_ext_active_role;
wire [1:0] bg_ext_grant_role;
wire  bg_ext_active_valid;
wire  bg_ext_active_slot;
wire [127:0] bg_ext_active_header;
wire [31:0] bg_ext_active_epoch;
wire [31:0] bg_ext_active_pixels;
wire [31:0] bg_ext_active_bytes;
wire  bg_ext_invalidate_readers;
wire  bg_ext_acquire_valid;
wire  bg_ext_acquire_ready;
wire  bg_ext_grant_valid;
wire  bg_ext_grant_slot;
wire [ADDR_WIDTH-1:0] bg_ext_grant_address;
wire [127:0] bg_ext_grant_header;
wire [31:0] bg_ext_grant_epoch;
wire [31:0] bg_ext_grant_pixels;
wire [31:0] bg_ext_grant_bytes;
wire  bg_ext_release_valid;
wire  bg_ext_release_slot;
wire [127:0] bg_ext_release_header;
wire [31:0] bg_ext_release_epoch;
wire  bg_ext_release_ok;
wire  bg_ext_protocol_error;
wire  bg_ext_read_cmd_valid;
wire  bg_ext_read_cmd_ready;
wire [ADDR_WIDTH-1:0] bg_ext_read_cmd_address;
wire [31:0] bg_ext_read_cmd_bytes;
wire [31:0] bg_ext_read_cmd_epoch;
wire [127:0] bg_ext_read_cmd_header;
wire  bg_ext_read_valid;
wire  bg_ext_read_ready;
wire [127:0] bg_ext_read_data;
wire [127:0] bg_ext_read_header;
wire [15:0] bg_ext_read_keep;
wire  bg_ext_read_last;
wire [31:0] bg_ext_read_epoch;
wire  bg_ext_read_status_valid;
wire  bg_ext_read_status_ready;
wire  bg_ext_read_status_ok;
wire [7:0] bg_ext_read_status_error;
wire [31:0] bg_ext_read_status_bytes;
wire [31:0] bg_ext_read_status_epoch;
wire [127:0] bg_ext_read_status_header;
wire  bg_ext_transport_busy;
wire  bg_ext_transport_requires_reset;
wire  bg_rd_select;
wire [31:0] bg_rd_data;
wire [3:0] bg_awid;
wire [ADDR_WIDTH-1:0] bg_awaddr;
wire [7:0] bg_awlen;
wire [2:0] bg_awsize;
wire [1:0] bg_awburst;
wire  bg_awvalid;
wire  bg_awready;
wire [127:0] bg_wdata;
wire [15:0] bg_wstrb;
wire  bg_wlast;
wire  bg_wvalid;
wire  bg_wready;
wire [3:0] bg_bid;
wire [1:0] bg_bresp;
wire  bg_bvalid;
wire  bg_bready;
wire [3:0] bg_arid;
wire [ADDR_WIDTH-1:0] bg_araddr;
wire [7:0] bg_arlen;
wire [2:0] bg_arsize;
wire [1:0] bg_arburst;
wire  bg_arvalid;
wire  bg_arready;
wire [3:0] bg_rid;
wire [127:0] bg_rdata;
wire [1:0] bg_rresp;
wire  bg_rlast;
wire  bg_rvalid;
wire  bg_rready;
wire  live_external_access;
wire  live_arb_grant;
wire  live_arb_request;
wire  live_arb_idle;
wire [12:0] live_image_width;
wire [12:0] live_image_height;
wire [31:0] live_current_epoch;
wire [31:0] live_current_geometry;
wire [31:0] live_current_calibration;
wire [1:0] live_ext_active_role;
wire [1:0] live_ext_grant_role;
wire  live_ext_active_valid;
wire  live_ext_active_slot;
wire [127:0] live_ext_active_header;
wire [31:0] live_ext_active_epoch;
wire [31:0] live_ext_active_pixels;
wire [31:0] live_ext_active_bytes;
wire  live_ext_invalidate_readers;
wire  live_ext_acquire_valid;
wire  live_ext_acquire_ready;
wire  live_ext_grant_valid;
wire  live_ext_grant_slot;
wire [ADDR_WIDTH-1:0] live_ext_grant_address;
wire [127:0] live_ext_grant_header;
wire [31:0] live_ext_grant_epoch;
wire [31:0] live_ext_grant_pixels;
wire [31:0] live_ext_grant_bytes;
wire  live_ext_release_valid;
wire  live_ext_release_slot;
wire [127:0] live_ext_release_header;
wire [31:0] live_ext_release_epoch;
wire  live_ext_release_ok;
wire  live_ext_protocol_error;
wire  live_ext_read_cmd_valid;
wire  live_ext_read_cmd_ready;
wire [ADDR_WIDTH-1:0] live_ext_read_cmd_address;
wire [31:0] live_ext_read_cmd_bytes;
wire [31:0] live_ext_read_cmd_epoch;
wire [127:0] live_ext_read_cmd_header;
wire  live_ext_read_valid;
wire  live_ext_read_ready;
wire [127:0] live_ext_read_data;
wire [127:0] live_ext_read_header;
wire [15:0] live_ext_read_keep;
wire  live_ext_read_last;
wire [31:0] live_ext_read_epoch;
wire  live_ext_read_status_valid;
wire  live_ext_read_status_ready;
wire  live_ext_read_status_ok;
wire [7:0] live_ext_read_status_error;
wire [31:0] live_ext_read_status_bytes;
wire [31:0] live_ext_read_status_epoch;
wire [127:0] live_ext_read_status_header;
wire  live_ext_transport_busy;
wire  live_ext_transport_requires_reset;
wire  live_rd_select;
wire [31:0] live_rd_data;
wire [3:0] live_awid;
wire [ADDR_WIDTH-1:0] live_awaddr;
wire [7:0] live_awlen;
wire [2:0] live_awsize;
wire [1:0] live_awburst;
wire  live_awvalid;
wire  live_awready;
wire [127:0] live_wdata;
wire [15:0] live_wstrb;
wire  live_wlast;
wire  live_wvalid;
wire  live_wready;
wire [3:0] live_bid;
wire [1:0] live_bresp;
wire  live_bvalid;
wire  live_bready;
wire [3:0] live_arid;
wire [ADDR_WIDTH-1:0] live_araddr;
wire [7:0] live_arlen;
wire [2:0] live_arsize;
wire [1:0] live_arburst;
wire  live_arvalid;
wire  live_arready;
wire [3:0] live_rid;
wire [127:0] live_rdata;
wire [1:0] live_rresp;
wire  live_rlast;
wire  live_rvalid;
wire  live_rready;
wire reset_n,dreset_n;wire [31:0] unused_epoch;
wire command_valid,command_ready,response_ready;
wire [351:0] command_data;reg response_valid;reg [511:0] response_data;
wire process_rd_select;wire [31:0] process_rd_data;
afc03_laser_csr_bridge #(.PAGE(12'h024),.MAX_OPCODE(7),.HOST_WATCHDOG(625000000)) bridge(
 .hclk(hclk),.hrst_n(hrst_n),.dclk(dclk),.drst_n(drst_n),
 .host_awaddr(host_awaddr),.host_wdata(host_wdata),.host_araddr(host_araddr),.host_wstrb(host_wstrb),
 .host_awvalid(host_awvalid),.host_awready(host_awready),.host_wvalid(host_wvalid),.host_wready(host_wready),
 .host_arvalid(host_arvalid),.host_arready(host_arready),.rd_select(process_rd_select),.rd_data(process_rd_data),
 .camera_epoch(unused_epoch),.reset_n(reset_n),.dreset_n(dreset_n),
 .command_valid(command_valid),.command_ready(command_ready),.command_data(command_data),
 .response_valid(response_valid),.response_ready(response_ready),.response_data(response_data));
assign rd_select=process_rd_select||live_rd_select||bg_rd_select;
assign rd_data=process_rd_select?process_rd_data:live_rd_select?live_rd_data:bg_rd_data;
reg [1:0] axi_owner;
reg [1:0] parallel_writer;
wire bg_capture_idle,live_capture_idle,bg_read_busy,live_read_busy;
wire overlap_allowed=(o_bg_pinned&&o_on_pinned&&!o_recovery_required)||!process_request;
// Only write ownership is shared with extraction. AR/R remains pinned to LIVE.
always @(posedge dclk or negedge dreset_n)begin
 if(!dreset_n)parallel_writer<=0;
 else if(axi_owner!=3)parallel_writer<=0;
 else case(parallel_writer)
  0:if(overlap_allowed&&bg_arb_request)parallel_writer<=1;
    else if(overlap_allowed&&live_arb_request)parallel_writer<=2;
  1:if(bg_capture_idle)parallel_writer<=0;
  2:if(live_capture_idle)parallel_writer<=0;
 endcase
end
wire process_request,process_drained;
assign bg_arb_grant=axi_owner==1||(axi_owner==3&&parallel_writer==1);
assign live_arb_grant=axi_owner==2||(axi_owner==3&&parallel_writer==2);
wire process_grant=axi_owner==3;
// Physical AXI ownership is held for the WHOLE capture/diagnostic/frame job.
// No transaction may migrate between movers, including timeout draining.
always @(posedge dclk or negedge dreset_n)begin
 if(!dreset_n)axi_owner<=0;
 else case(axi_owner)
  0:if(process_request&&bg_arb_idle&&live_arb_idle)axi_owner<=3;
    else if(bg_arb_request)axi_owner<=1;
    else if(live_arb_request)axi_owner<=2;
  1:if(bg_arb_idle)axi_owner<=0;
  2:if(live_arb_idle)axi_owner<=0;
  3:if(!process_request&&process_drained&&parallel_writer==0&&bg_arb_idle&&live_arb_idle)axi_owner<=0;
 endcase
end
wire select_bg=axi_owner==1;
wire select_live=axi_owner==2||axi_owner==3;
wire write_bg=axi_owner==1||(axi_owner==3&&parallel_writer==1);
wire write_live=axi_owner==2||(axi_owner==3&&parallel_writer==2);
assign awid=write_bg?bg_awid:write_live?live_awid:0;
assign awaddr=write_bg?bg_awaddr:write_live?live_awaddr:0;
assign awlen=write_bg?bg_awlen:write_live?live_awlen:0;
assign awsize=write_bg?bg_awsize:write_live?live_awsize:0;
assign awburst=write_bg?bg_awburst:write_live?live_awburst:0;
assign awvalid=write_bg?bg_awvalid:write_live?live_awvalid:0;
assign bg_awready=awready&&write_bg;
assign live_awready=awready&&write_live;
assign wdata=write_bg?bg_wdata:write_live?live_wdata:0;
assign wstrb=write_bg?bg_wstrb:write_live?live_wstrb:0;
assign wlast=write_bg?bg_wlast:write_live?live_wlast:0;
assign wvalid=write_bg?bg_wvalid:write_live?live_wvalid:0;
assign bg_wready=wready&&write_bg;
assign live_wready=wready&&write_live;
assign bg_bid=bid;
assign live_bid=bid;
assign bg_bresp=bresp;
assign live_bresp=bresp;
assign bg_bvalid=bvalid&&write_bg;
assign live_bvalid=bvalid&&write_live;
assign bready=write_bg?bg_bready:write_live?live_bready:0;
assign arid=select_bg?bg_arid:select_live?live_arid:0;
assign araddr=select_bg?bg_araddr:select_live?live_araddr:0;
assign arlen=select_bg?bg_arlen:select_live?live_arlen:0;
assign arsize=select_bg?bg_arsize:select_live?live_arsize:0;
assign arburst=select_bg?bg_arburst:select_live?live_arburst:0;
assign arvalid=select_bg?bg_arvalid:select_live?live_arvalid:0;
assign bg_arready=arready&&select_bg;
assign live_arready=arready&&select_live;
assign bg_rid=rid;
assign live_rid=rid;
assign bg_rdata=rdata;
assign live_rdata=rdata;
assign bg_rresp=rresp;
assign live_rresp=rresp;
assign bg_rlast=rlast;
assign live_rlast=rlast;
assign bg_rvalid=rvalid&&select_bg;
assign live_rvalid=rvalid&&select_live;
assign rready=select_bg?bg_rready:select_live?live_rready:0;
afc03_role_diagnostic_top #(.REQUIRE_MARKER(REQUIRE_MARKER),.PAGE(12'h022),.ALLOWED_ROLES(4'b0001),.SLOT0_BASE(BG0),.SLOT1_BASE(BG1),.SLOT_BYTES(SLOT_BYTES)) bg(
 .source_pending(bg_source_pending),.source_token(bg_source_token),
 .capture_allowed(overlap_allowed),.capture_idle(bg_capture_idle),.ext_read_transport_busy(bg_read_busy),
 .external_access(bg_external_access),
 .arb_grant(bg_arb_grant),
 .arb_request(bg_arb_request),
 .arb_idle(bg_arb_idle),
 .image_width(bg_image_width),
 .image_height(bg_image_height),
 .current_epoch(bg_current_epoch),
 .current_geometry(bg_current_geometry),
 .current_calibration(bg_current_calibration),
 .ext_active_role(bg_ext_active_role),
 .ext_grant_role(bg_ext_grant_role),
 .ext_active_valid(bg_ext_active_valid),
 .ext_active_slot(bg_ext_active_slot),
 .ext_active_header(bg_ext_active_header),
 .ext_active_epoch(bg_ext_active_epoch),
 .ext_active_pixels(bg_ext_active_pixels),
 .ext_active_bytes(bg_ext_active_bytes),
 .ext_invalidate_readers(bg_ext_invalidate_readers),
 .ext_acquire_valid(bg_ext_acquire_valid),
 .ext_acquire_ready(bg_ext_acquire_ready),
 .ext_grant_valid(bg_ext_grant_valid),
 .ext_grant_slot(bg_ext_grant_slot),
 .ext_grant_address(bg_ext_grant_address),
 .ext_grant_header(bg_ext_grant_header),
 .ext_grant_epoch(bg_ext_grant_epoch),
 .ext_grant_pixels(bg_ext_grant_pixels),
 .ext_grant_bytes(bg_ext_grant_bytes),
 .ext_release_valid(bg_ext_release_valid),
 .ext_release_slot(bg_ext_release_slot),
 .ext_release_header(bg_ext_release_header),
 .ext_release_epoch(bg_ext_release_epoch),
 .ext_release_ok(bg_ext_release_ok),
 .ext_protocol_error(bg_ext_protocol_error),
 .ext_read_cmd_valid(bg_ext_read_cmd_valid),
 .ext_read_cmd_ready(bg_ext_read_cmd_ready),
 .ext_read_cmd_address(bg_ext_read_cmd_address),
 .ext_read_cmd_bytes(bg_ext_read_cmd_bytes),
 .ext_read_cmd_epoch(bg_ext_read_cmd_epoch),
 .ext_read_cmd_header(bg_ext_read_cmd_header),
 .ext_read_valid(bg_ext_read_valid),
 .ext_read_ready(bg_ext_read_ready),
 .ext_read_data(bg_ext_read_data),
 .ext_read_header(bg_ext_read_header),
 .ext_read_keep(bg_ext_read_keep),
 .ext_read_last(bg_ext_read_last),
 .ext_read_epoch(bg_ext_read_epoch),
 .ext_read_status_valid(bg_ext_read_status_valid),
 .ext_read_status_ready(bg_ext_read_status_ready),
 .ext_read_status_ok(bg_ext_read_status_ok),
 .ext_read_status_error(bg_ext_read_status_error),
 .ext_read_status_bytes(bg_ext_read_status_bytes),
 .ext_read_status_epoch(bg_ext_read_status_epoch),
 .ext_read_status_header(bg_ext_read_status_header),
 .ext_transport_busy(bg_ext_transport_busy),
 .ext_transport_requires_reset(bg_ext_transport_requires_reset),
 .hclk(hclk),
 .hrst_n(hrst_n),
 .dclk(dclk),
 .drst_n(drst_n),
 .control_ready(control_ready),
 .ext_enabled(ext_enabled),
 .host_awaddr(host_awaddr),
 .host_wdata(host_wdata),
 .host_araddr(host_araddr),
 .host_wstrb(host_wstrb),
 .host_awvalid(host_awvalid),
 .host_awready(host_awready),
 .host_wvalid(host_wvalid),
 .host_wready(host_wready),
 .host_arvalid(host_arvalid),
 .host_arready(host_arready),
 .rd_select(bg_rd_select),
 .rd_data(bg_rd_data),
 .stream_rst_n(stream_rst_n),
 .camera_data(camera_data),
 .camera_valid(camera_valid),
 .camera_ready(camera_ready),
 .camera_sof(camera_sof),
 .camera_eol(camera_eol),
 .awid(bg_awid),
 .awaddr(bg_awaddr),
 .awlen(bg_awlen),
 .awsize(bg_awsize),
 .awburst(bg_awburst),
 .awvalid(bg_awvalid),
 .awready(bg_awready),
 .wdata(bg_wdata),
 .wstrb(bg_wstrb),
 .wlast(bg_wlast),
 .wvalid(bg_wvalid),
 .wready(bg_wready),
 .bid(bg_bid),
 .bresp(bg_bresp),
 .bvalid(bg_bvalid),
 .bready(bg_bready),
 .arid(bg_arid),
 .araddr(bg_araddr),
 .arlen(bg_arlen),
 .arsize(bg_arsize),
 .arburst(bg_arburst),
 .arvalid(bg_arvalid),
 .arready(bg_arready),
 .rid(bg_rid),
 .rdata(bg_rdata),
 .rresp(bg_rresp),
 .rlast(bg_rlast),
 .rvalid(bg_rvalid),
 .rready(bg_rready)
);
afc03_role_diagnostic_top #(.REQUIRE_MARKER(REQUIRE_MARKER),.PAGE(12'h023),.ALLOWED_ROLES(4'b0110),.SLOT0_BASE(ON0),.SLOT1_BASE(ON1),.SLOT_BYTES(SLOT_BYTES)) live(
 .source_pending(live_source_pending),.source_token(live_source_token),
 .capture_allowed(overlap_allowed),.capture_idle(live_capture_idle),.ext_read_transport_busy(live_read_busy),
 .external_access(live_external_access),
 .arb_grant(live_arb_grant),
 .arb_request(live_arb_request),
 .arb_idle(live_arb_idle),
 .image_width(live_image_width),
 .image_height(live_image_height),
 .current_epoch(live_current_epoch),
 .current_geometry(live_current_geometry),
 .current_calibration(live_current_calibration),
 .ext_active_role(live_ext_active_role),
 .ext_grant_role(live_ext_grant_role),
 .ext_active_valid(live_ext_active_valid),
 .ext_active_slot(live_ext_active_slot),
 .ext_active_header(live_ext_active_header),
 .ext_active_epoch(live_ext_active_epoch),
 .ext_active_pixels(live_ext_active_pixels),
 .ext_active_bytes(live_ext_active_bytes),
 .ext_invalidate_readers(live_ext_invalidate_readers),
 .ext_acquire_valid(live_ext_acquire_valid),
 .ext_acquire_ready(live_ext_acquire_ready),
 .ext_grant_valid(live_ext_grant_valid),
 .ext_grant_slot(live_ext_grant_slot),
 .ext_grant_address(live_ext_grant_address),
 .ext_grant_header(live_ext_grant_header),
 .ext_grant_epoch(live_ext_grant_epoch),
 .ext_grant_pixels(live_ext_grant_pixels),
 .ext_grant_bytes(live_ext_grant_bytes),
 .ext_release_valid(live_ext_release_valid),
 .ext_release_slot(live_ext_release_slot),
 .ext_release_header(live_ext_release_header),
 .ext_release_epoch(live_ext_release_epoch),
 .ext_release_ok(live_ext_release_ok),
 .ext_protocol_error(live_ext_protocol_error),
 .ext_read_cmd_valid(live_ext_read_cmd_valid),
 .ext_read_cmd_ready(live_ext_read_cmd_ready),
 .ext_read_cmd_address(live_ext_read_cmd_address),
 .ext_read_cmd_bytes(live_ext_read_cmd_bytes),
 .ext_read_cmd_epoch(live_ext_read_cmd_epoch),
 .ext_read_cmd_header(live_ext_read_cmd_header),
 .ext_read_valid(live_ext_read_valid),
 .ext_read_ready(live_ext_read_ready),
 .ext_read_data(live_ext_read_data),
 .ext_read_header(live_ext_read_header),
 .ext_read_keep(live_ext_read_keep),
 .ext_read_last(live_ext_read_last),
 .ext_read_epoch(live_ext_read_epoch),
 .ext_read_status_valid(live_ext_read_status_valid),
 .ext_read_status_ready(live_ext_read_status_ready),
 .ext_read_status_ok(live_ext_read_status_ok),
 .ext_read_status_error(live_ext_read_status_error),
 .ext_read_status_bytes(live_ext_read_status_bytes),
 .ext_read_status_epoch(live_ext_read_status_epoch),
 .ext_read_status_header(live_ext_read_status_header),
 .ext_transport_busy(live_ext_transport_busy),
 .ext_transport_requires_reset(live_ext_transport_requires_reset),
 .hclk(hclk),
 .hrst_n(hrst_n),
 .dclk(dclk),
 .drst_n(drst_n),
 .control_ready(control_ready),
 .ext_enabled(ext_enabled),
 .host_awaddr(host_awaddr),
 .host_wdata(host_wdata),
 .host_araddr(host_araddr),
 .host_wstrb(host_wstrb),
 .host_awvalid(host_awvalid),
 .host_awready(host_awready),
 .host_wvalid(host_wvalid),
 .host_wready(host_wready),
 .host_arvalid(host_arvalid),
 .host_arready(host_arready),
 .rd_select(live_rd_select),
 .rd_data(live_rd_data),
 .stream_rst_n(stream_rst_n),
 .camera_data(camera_data),
 .camera_valid(camera_valid),
 .camera_ready(camera_ready),
 .camera_sof(camera_sof),
 .camera_eol(camera_eol),
 .awid(live_awid),
 .awaddr(live_awaddr),
 .awlen(live_awlen),
 .awsize(live_awsize),
 .awburst(live_awburst),
 .awvalid(live_awvalid),
 .awready(live_awready),
 .wdata(live_wdata),
 .wstrb(live_wstrb),
 .wlast(live_wlast),
 .wvalid(live_wvalid),
 .wready(live_wready),
 .bid(live_bid),
 .bresp(live_bresp),
 .bvalid(live_bvalid),
 .bready(live_bready),
 .arid(live_arid),
 .araddr(live_araddr),
 .arlen(live_arlen),
 .arsize(live_arsize),
 .arburst(live_arburst),
 .arvalid(live_arvalid),
 .arready(live_arready),
 .rid(live_rid),
 .rdata(live_rdata),
 .rresp(live_rresp),
 .rlast(live_rlast),
 .rvalid(live_rvalid),
 .rready(live_rready)
);
wire  o_request_valid;
wire  o_request_ready;
wire [127:0] o_request_bg_header;
wire [127:0] o_request_on_header;
wire [31:0] o_request_epoch;
wire [31:0] o_request_token;
wire [31:0] o_request_geometry;
wire [31:0] o_request_calibration;
wire [1:0] o_request_role;
wire [12:0] o_request_image_width;
wire [12:0] o_request_image_height;
wire [31:0] o_request_stride;
wire [31:0] o_current_epoch;
wire [31:0] o_current_geometry;
wire [31:0] o_current_calibration;
wire  o_cancel;
wire  o_memory_invalidated;
wire  o_transport_requires_reset;
wire  o_busy;
wire  o_fault_pending;
wire  o_recovery_required;
wire [7:0] o_error_code;
wire [15:0] o_pipeline_error;
wire  o_bg_pinned;
wire  o_on_pinned;
wire  o_bg_acquire_valid;
wire  o_bg_acquire_ready;
wire  o_bg_grant_valid;
wire  o_bg_grant_slot;
wire  o_bg_grant_committed;
wire [1:0] o_bg_grant_role;
wire [ADDR_WIDTH-1:0] o_bg_grant_address;
wire [127:0] o_bg_grant_header;
wire [31:0] o_bg_grant_epoch;
wire [31:0] o_bg_grant_pixels;
wire [31:0] o_bg_grant_bytes;
wire  o_on_acquire_valid;
wire  o_on_acquire_ready;
wire  o_on_grant_valid;
wire  o_on_grant_slot;
wire  o_on_grant_committed;
wire [1:0] o_on_grant_role;
wire [ADDR_WIDTH-1:0] o_on_grant_address;
wire [127:0] o_on_grant_header;
wire [31:0] o_on_grant_epoch;
wire [31:0] o_on_grant_pixels;
wire [31:0] o_on_grant_bytes;
wire  o_bg_protocol_error;
wire  o_on_protocol_error;
wire  o_bg_release_valid;
wire  o_bg_release_ready;
wire  o_bg_release_slot;
wire [127:0] o_bg_release_header;
wire [31:0] o_bg_release_epoch;
wire  o_bg_ack_valid;
wire  o_bg_ack_ok;
wire  o_bg_ack_slot;
wire [127:0] o_bg_ack_header;
wire [31:0] o_bg_ack_epoch;
wire  o_on_release_valid;
wire  o_on_release_ready;
wire  o_on_release_slot;
wire [127:0] o_on_release_header;
wire [31:0] o_on_release_epoch;
wire  o_on_ack_valid;
wire  o_on_ack_ok;
wire  o_on_ack_slot;
wire [127:0] o_on_ack_header;
wire [31:0] o_on_ack_epoch;
wire  o_read_claim_valid;
wire  o_read_claim_ready;
wire  o_read_release_valid;
wire  o_read_release_ready;
wire [31:0] o_read_owner_token;
wire  o_read_exclusive;
wire  o_read_port_drained;
wire  o_downstream_drained;
wire  o_session_valid;
wire  o_session_ready;
wire  o_session_cancel;
wire [ADDR_WIDTH-1:0] o_session_bg_base;
wire [ADDR_WIDTH-1:0] o_session_on_base;
wire [31:0] o_session_bg_bytes;
wire [31:0] o_session_on_bytes;
wire [127:0] o_session_bg_header;
wire [127:0] o_session_on_header;
wire [31:0] o_session_epoch;
wire [31:0] o_session_token;
wire [31:0] o_session_geometry;
wire [31:0] o_session_calibration;
wire [1:0] o_session_role;
wire [12:0] o_session_image_width;
wire [12:0] o_session_image_height;
wire [31:0] o_session_stride;
wire  o_session_progress;
wire  o_session_done_valid;
wire  o_session_done_ready;
wire  o_session_done_ok;
wire [15:0] o_session_done_error;
wire [127:0] o_session_done_bg_header;
wire [127:0] o_session_done_on_header;
wire [31:0] o_session_done_epoch;
wire [31:0] o_session_done_token;
wire  o_event_valid;
wire  o_event_ready;
wire  o_event_ok;
wire [7:0] o_event_error;
wire [15:0] o_event_pipeline_error;
wire [31:0] o_event_epoch;
wire [31:0] o_event_token;
afc03_frame_pair_owner owner(
 .clk(dclk),
 .rst_n(dreset_n),
 .request_valid(o_request_valid),
 .request_ready(o_request_ready),
 .request_bg_header(o_request_bg_header),
 .request_on_header(o_request_on_header),
 .request_epoch(o_request_epoch),
 .request_token(o_request_token),
 .request_geometry(o_request_geometry),
 .request_calibration(o_request_calibration),
 .request_role(o_request_role),
 .request_image_width(o_request_image_width),
 .request_image_height(o_request_image_height),
 .request_stride(o_request_stride),
 .current_epoch(o_current_epoch),
 .current_geometry(o_current_geometry),
 .current_calibration(o_current_calibration),
 .cancel(o_cancel),
 .memory_invalidated(o_memory_invalidated),
 .transport_requires_reset(o_transport_requires_reset),
 .busy(o_busy),
 .fault_pending(o_fault_pending),
 .recovery_required(o_recovery_required),
 .error_code(o_error_code),
 .pipeline_error(o_pipeline_error),
 .bg_pinned(o_bg_pinned),
 .on_pinned(o_on_pinned),
 .bg_acquire_valid(o_bg_acquire_valid),
 .bg_acquire_ready(o_bg_acquire_ready),
 .bg_grant_valid(o_bg_grant_valid),
 .bg_grant_slot(o_bg_grant_slot),
 .bg_grant_committed(o_bg_grant_committed),
 .bg_grant_role(o_bg_grant_role),
 .bg_grant_address(o_bg_grant_address),
 .bg_grant_header(o_bg_grant_header),
 .bg_grant_epoch(o_bg_grant_epoch),
 .bg_grant_pixels(o_bg_grant_pixels),
 .bg_grant_bytes(o_bg_grant_bytes),
 .on_acquire_valid(o_on_acquire_valid),
 .on_acquire_ready(o_on_acquire_ready),
 .on_grant_valid(o_on_grant_valid),
 .on_grant_slot(o_on_grant_slot),
 .on_grant_committed(o_on_grant_committed),
 .on_grant_role(o_on_grant_role),
 .on_grant_address(o_on_grant_address),
 .on_grant_header(o_on_grant_header),
 .on_grant_epoch(o_on_grant_epoch),
 .on_grant_pixels(o_on_grant_pixels),
 .on_grant_bytes(o_on_grant_bytes),
 .bg_protocol_error(o_bg_protocol_error),
 .on_protocol_error(o_on_protocol_error),
 .bg_release_valid(o_bg_release_valid),
 .bg_release_ready(o_bg_release_ready),
 .bg_release_slot(o_bg_release_slot),
 .bg_release_header(o_bg_release_header),
 .bg_release_epoch(o_bg_release_epoch),
 .bg_ack_valid(o_bg_ack_valid),
 .bg_ack_ok(o_bg_ack_ok),
 .bg_ack_slot(o_bg_ack_slot),
 .bg_ack_header(o_bg_ack_header),
 .bg_ack_epoch(o_bg_ack_epoch),
 .on_release_valid(o_on_release_valid),
 .on_release_ready(o_on_release_ready),
 .on_release_slot(o_on_release_slot),
 .on_release_header(o_on_release_header),
 .on_release_epoch(o_on_release_epoch),
 .on_ack_valid(o_on_ack_valid),
 .on_ack_ok(o_on_ack_ok),
 .on_ack_slot(o_on_ack_slot),
 .on_ack_header(o_on_ack_header),
 .on_ack_epoch(o_on_ack_epoch),
 .read_claim_valid(o_read_claim_valid),
 .read_claim_ready(o_read_claim_ready),
 .read_release_valid(o_read_release_valid),
 .read_release_ready(o_read_release_ready),
 .read_owner_token(o_read_owner_token),
 .read_exclusive(o_read_exclusive),
 .read_port_drained(o_read_port_drained),
 .downstream_drained(o_downstream_drained),
 .session_valid(o_session_valid),
 .session_ready(o_session_ready),
 .session_cancel(o_session_cancel),
 .session_bg_base(o_session_bg_base),
 .session_on_base(o_session_on_base),
 .session_bg_bytes(o_session_bg_bytes),
 .session_on_bytes(o_session_on_bytes),
 .session_bg_header(o_session_bg_header),
 .session_on_header(o_session_on_header),
 .session_epoch(o_session_epoch),
 .session_token(o_session_token),
 .session_geometry(o_session_geometry),
 .session_calibration(o_session_calibration),
 .session_role(o_session_role),
 .session_image_width(o_session_image_width),
 .session_image_height(o_session_image_height),
 .session_stride(o_session_stride),
 .session_progress(o_session_progress),
 .session_done_valid(o_session_done_valid),
 .session_done_ready(o_session_done_ready),
 .session_done_ok(o_session_done_ok),
 .session_done_error(o_session_done_error),
 .session_done_bg_header(o_session_done_bg_header),
 .session_done_on_header(o_session_done_on_header),
 .session_done_epoch(o_session_done_epoch),
 .session_done_token(o_session_done_token),
 .event_valid(o_event_valid),
 .event_ready(o_event_ready),
 .event_ok(o_event_ok),
 .event_error(o_event_error),
 .event_pipeline_error(o_event_pipeline_error),
 .event_epoch(o_event_epoch),
 .event_token(o_event_token)
);
assign bg_ext_acquire_valid=o_bg_acquire_valid;
assign o_bg_acquire_ready=bg_ext_acquire_ready;
assign o_bg_grant_valid=bg_ext_grant_valid;
assign o_bg_grant_slot=bg_ext_grant_slot;
assign o_bg_grant_role=bg_ext_grant_role;
assign o_bg_grant_address=bg_ext_grant_address;
assign o_bg_grant_header=bg_ext_grant_header;
assign o_bg_grant_epoch=bg_ext_grant_epoch;
assign o_bg_grant_pixels=bg_ext_grant_pixels;
assign o_bg_grant_bytes=bg_ext_grant_bytes;
assign o_bg_protocol_error=bg_ext_protocol_error||bg_release_fault;
assign o_bg_grant_committed=bg_ext_grant_valid;
wire bg_release_fault;
afc03_slot_release_bridge bg_release(
 .clk(dclk),
 .rst_n(dreset_n),
 .release_valid(o_bg_release_valid),
 .release_ready(o_bg_release_ready),
 .release_slot(o_bg_release_slot),
 .release_header(o_bg_release_header),
 .release_epoch(o_bg_release_epoch),
 .slots_release_valid(bg_ext_release_valid),
 .slots_release_slot(bg_ext_release_slot),
 .slots_release_header(bg_ext_release_header),
 .slots_release_epoch(bg_ext_release_epoch),
 .slots_release_ok(bg_ext_release_ok),
 .slots_protocol_error(bg_ext_protocol_error),
 .ack_valid(o_bg_ack_valid),
 .ack_ok(o_bg_ack_ok),
 .ack_slot(o_bg_ack_slot),
 .ack_header(o_bg_ack_header),
 .ack_epoch(o_bg_ack_epoch),
 .recovery_required(bg_release_fault)
);
assign live_ext_acquire_valid=o_on_acquire_valid;
assign o_on_acquire_ready=live_ext_acquire_ready;
assign o_on_grant_valid=live_ext_grant_valid;
assign o_on_grant_slot=live_ext_grant_slot;
assign o_on_grant_role=live_ext_grant_role;
assign o_on_grant_address=live_ext_grant_address;
assign o_on_grant_header=live_ext_grant_header;
assign o_on_grant_epoch=live_ext_grant_epoch;
assign o_on_grant_pixels=live_ext_grant_pixels;
assign o_on_grant_bytes=live_ext_grant_bytes;
assign o_on_protocol_error=live_ext_protocol_error||on_release_fault;
assign o_on_grant_committed=live_ext_grant_valid;
wire on_release_fault;
afc03_slot_release_bridge on_release(
 .clk(dclk),
 .rst_n(dreset_n),
 .release_valid(o_on_release_valid),
 .release_ready(o_on_release_ready),
 .release_slot(o_on_release_slot),
 .release_header(o_on_release_header),
 .release_epoch(o_on_release_epoch),
 .slots_release_valid(live_ext_release_valid),
 .slots_release_slot(live_ext_release_slot),
 .slots_release_header(live_ext_release_header),
 .slots_release_epoch(live_ext_release_epoch),
 .slots_release_ok(live_ext_release_ok),
 .slots_protocol_error(live_ext_protocol_error),
 .ack_valid(o_on_ack_valid),
 .ack_ok(o_on_ack_ok),
 .ack_slot(o_on_ack_slot),
 .ack_header(o_on_ack_header),
 .ack_epoch(o_on_ack_epoch),
 .recovery_required(on_release_fault)
);
reg queued,job_cancel,result_valid,result_failed,overflow;
reg [127:0] job_bg_header,job_on_header;
reg [31:0] job_epoch,job_token,job_geometry,job_calibration;
reg [1:0] job_role;
reg [12:0] job_width,job_height,job_x0,job_x1,job_y0;
reg [11:0] job_rows,job_left,job_right;
reg [31:0] result_count,result_rows,result_centers,result_crc,result_error,cycles;
reg [127:0] records[0:RESULT_DEPTH-1];
wire pipeline_done,pipeline_done_ready,pipeline_ok,pipeline_busy,pipeline_drained,pipeline_progress;
wire [15:0] pipeline_error;
wire [31:0] pipeline_rows,pipeline_records,pipeline_centers,pipeline_crc;
wire [127:0] pipeline_on_header,pipeline_bg_header;
wire [31:0] pipeline_epoch,pipeline_token,pipeline_geometry,pipeline_calibration;
wire record_valid;wire [127:0] record_data;wire [7:0] record_type;
wire record_ready=o_busy;
assign process_request=queued||o_busy||o_recovery_required;
assign bg_external_access=process_request||axi_owner==3;assign live_external_access=process_request||axi_owner==3;
assign process_drained=!live_read_busy&&!live_ext_read_valid&&!live_ext_read_status_valid&&pipeline_drained;
assign o_request_valid=queued&&process_grant;
assign o_request_bg_header=job_bg_header;assign o_request_on_header=job_on_header;
assign o_request_epoch=job_epoch;assign o_request_token=job_token;
assign o_request_geometry=job_geometry;assign o_request_calibration=job_calibration;assign o_request_role=job_role;
assign o_request_image_width=job_width;assign o_request_image_height=job_height;assign o_request_stride={19'd0,job_width}<<2;
assign o_current_epoch=bg_current_epoch;assign o_current_geometry=bg_current_geometry;assign o_current_calibration=bg_current_calibration;
assign o_cancel=job_cancel||overflow;
assign o_memory_invalidated=!control_ready||!ext_enabled||bg_ext_invalidate_readers||live_ext_invalidate_readers||
 live_current_epoch!=job_epoch||live_current_geometry!=job_geometry||live_current_calibration!=job_calibration;
assign o_transport_requires_reset=bg_ext_transport_requires_reset||live_ext_transport_requires_reset;
assign o_read_claim_ready=process_grant&&!live_read_busy&&!live_ext_read_valid&&!live_ext_read_status_valid;
assign o_read_release_ready=process_drained;
assign o_read_port_drained=process_drained;
assign o_downstream_drained=pipeline_drained;
assign o_session_done_valid=pipeline_done;assign pipeline_done_ready=o_session_done_ready;
assign o_session_done_ok=pipeline_ok&&!overflow;assign o_session_done_error=pipeline_error|(overflow?16'h8000:16'd0);
assign o_session_done_bg_header=pipeline_bg_header;assign o_session_done_on_header=pipeline_on_header;
assign o_session_done_epoch=pipeline_epoch;assign o_session_done_token=pipeline_token;
assign o_session_progress=pipeline_progress;assign o_event_ready=1'b1;
assign bg_ext_read_cmd_valid=0;assign bg_ext_read_cmd_address=0;assign bg_ext_read_cmd_bytes=0;
assign bg_ext_read_cmd_epoch=0;assign bg_ext_read_cmd_header=0;assign bg_ext_read_ready=0;assign bg_ext_read_status_ready=0;
afc03_pinned_frame_pipeline #(.ADDR_WIDTH(ADDR_WIDTH),.MAX_HEIGHT(MAX_HEIGHT)) pipeline(
 .clk(dclk),.rst_n(dreset_n),.cancel(o_session_cancel),.memory_invalidated(o_memory_invalidated),
 .ownership_valid(o_bg_pinned&&o_on_pinned&&!o_recovery_required),.read_exclusive(o_read_exclusive),
 .cfg_laser_b(job_role[1]),.cfg_valid(o_session_valid),.cfg_ready(o_session_ready),
 .cfg_on_base(o_session_on_base),.cfg_bg_base(o_session_bg_base),
 .cfg_on_region_bytes(o_session_on_bytes),.cfg_bg_region_bytes(o_session_bg_bytes),
 .cfg_on_stride(o_session_stride),.cfg_bg_stride(o_session_stride),
 .cfg_width(o_session_image_width),.cfg_height(o_session_image_height),
 .cfg_x0(job_x0),.cfg_x1(job_x1),.cfg_y0(job_y0),.cfg_rows(job_rows),.cfg_roi_left(job_left),.cfg_roi_right(job_right),
 .cfg_on_header(o_session_on_header),.cfg_bg_header(o_session_bg_header),
 .cfg_epoch(o_session_epoch),.cfg_token(o_session_token),.cfg_geometry(o_session_geometry),.cfg_calibration(o_session_calibration),
 .transport_busy(live_read_busy),.transport_requires_reset(live_ext_transport_requires_reset),
 .read_cmd_valid(live_ext_read_cmd_valid),
 .read_cmd_ready(live_ext_read_cmd_ready),
 .read_cmd_address(live_ext_read_cmd_address),
 .read_cmd_bytes(live_ext_read_cmd_bytes),
 .read_cmd_epoch(live_ext_read_cmd_epoch),
 .read_cmd_header(live_ext_read_cmd_header),
 .read_valid(live_ext_read_valid),
 .read_ready(live_ext_read_ready),
 .read_data(live_ext_read_data),
 .read_header(live_ext_read_header),
 .read_keep(live_ext_read_keep),
 .read_last(live_ext_read_last),
 .read_epoch(live_ext_read_epoch),
 .read_status_valid(live_ext_read_status_valid),
 .read_status_ready(live_ext_read_status_ready),
 .read_status_ok(live_ext_read_status_ok),
 .read_status_error(live_ext_read_status_error),
 .read_status_bytes(live_ext_read_status_bytes),
 .read_status_epoch(live_ext_read_status_epoch),
 .read_status_header(live_ext_read_status_header),
 .record_valid(record_valid),.record_ready(record_ready),.record_data(record_data),.record_type(record_type),
 .done_valid(pipeline_done),.done_ready(pipeline_done_ready),.done_ok(pipeline_ok),.done_error(pipeline_error),
 .done_rows(pipeline_rows),.done_records(pipeline_records),.done_centers(pipeline_centers),.done_crc32(pipeline_crc),
 .on_header(pipeline_on_header),.bg_header(pipeline_bg_header),.epoch(pipeline_epoch),.token(pipeline_token),
 .geometry(pipeline_geometry),.calibration(pipeline_calibration),
 .busy(pipeline_busy),.downstream_drained(pipeline_drained),.progress(pipeline_progress));
localparam J_IDLE=0,J_DECODE=1,J_RAM_WAIT=2,J_REPLY=3,J_SEND=4;
reg [2:0] jstate;reg [351:0] request;
reg [7:0] result_code;reg [127:0] ram_data;
wire [7:0] opcode=request[7:0];
wire [31:0] req_id=request[63:32],req_epoch=request[95:64],req_geometry=request[127:96],req_calibration=request[159:128];
wire [31:0] req_token=request[191:160],req_dims=request[223:192],req_roi0=request[255:224],req_roi1=request[287:256];
wire [31:0] req_role=request[319:288],req_offset=request[351:320];
wire [12:0] req_width=req_dims[12:0],req_height=req_dims[28:16];
wire [12:0] req_x0=req_roi0[12:0],req_y0=req_roi0[28:16],req_x1=req_roi1[12:0],req_y1=req_roi1[28:16];
wire [13:0] row_span={1'b0,req_y1}-{1'b0,req_y0};
wire [31:0] record_bound=({19'd0,req_x1}-{19'd0,req_x0})*33;
wire job_unavailable=!control_ready||!ext_enabled||o_recovery_required||
 bg_ext_transport_requires_reset||live_ext_transport_requires_reset;
wire job_bad=|req_dims[31:29]|| |req_dims[15:13]|| |req_roi0[31:29]|| |req_roi0[15:13]||
 |req_roi1[31:29]|| |req_roi1[15:13]||req_epoch==0||req_token==0||req_geometry==0||req_calibration==0||
 req_width!=bg_image_width||req_width!=live_image_width||req_height!=bg_image_height||req_height!=live_image_height||
 req_epoch!=bg_current_epoch||req_epoch!=live_current_epoch||req_geometry!=bg_current_geometry||req_geometry!=live_current_geometry||
 req_calibration!=bg_current_calibration||req_calibration!=live_current_calibration||
 req_x0>=req_x1||req_x1>req_width||req_x0[1:0]!=0||req_y0>=req_y1||req_y1>req_height||
 row_span<3||row_span>MAX_HEIGHT||record_bound>RESULT_DEPTH||
 req_offset[15:0]>=req_offset[31:16]||req_offset[31:16]>=row_span||
 (req_role!=3&&req_role!=5)||live_ext_active_role!=req_role[2:1]||bg_ext_active_role!=0||
 !bg_ext_active_valid||!live_ext_active_valid;
assign command_ready=jstate==J_IDLE&&!response_valid;
wire read_result=jstate==J_DECODE&&opcode==6&&result_valid&&!process_request&&!dma_busy&&
 req_offset[3:0]==0&&(req_offset>>4)<result_count;
// Both clients are mutually exclusive. Mux the address before the RAM so
// synthesis infers one synchronous read port, not two replicated memories.
wire [10:0] result_read_address=dma_ram_read?dma_ram_address:req_offset[14:4];
always @(posedge dclk)begin
 if(dma_ram_read||read_result)ram_data<=records[result_read_address];
 if(record_valid&&record_ready&&result_count<RESULT_DEPTH)records[result_count]<=record_data;
end
always @(posedge dclk or negedge dreset_n)begin
 if(!dreset_n)begin
  jstate<=J_IDLE;request<=0;result_code<=0;response_valid<=0;response_data<=0;
  queued<=0;job_cancel<=0;result_valid<=0;result_failed<=0;overflow<=0;
  job_bg_header<=0;job_on_header<=0;job_epoch<=0;job_token<=0;job_geometry<=0;job_calibration<=0;job_role<=0;
  job_width<=0;job_height<=0;job_x0<=0;job_x1<=0;job_y0<=0;job_rows<=0;job_left<=0;job_right<=0;
  result_count<=0;result_rows<=0;result_centers<=0;result_crc<=0;result_error<=0;cycles<=0;
 end else begin
  if(o_request_valid&&o_request_ready)queued<=0;
  if(process_request)begin
   if(cycles!=32'hffffffff)cycles<=cycles+1'b1;
   // 10 second absolute deadline at 100MHz. Never pretends to drain AXI.
   if(cycles>=1000000000)job_cancel<=1;
  end
  if(record_valid&&record_ready)begin
   if(result_count<RESULT_DEPTH)result_count<=result_count+1'b1;
   else begin overflow<=1;job_cancel<=1;end
  end
  if(pipeline_done&&pipeline_done_ready)begin
   result_rows<=pipeline_rows;result_centers<=pipeline_centers;result_crc<=pipeline_crc;
  end
  if(o_event_valid)begin
   result_valid<=o_event_ok&&!overflow&&!job_cancel&&!job_unavailable;
   result_failed<=!o_event_ok||overflow||job_cancel||job_unavailable;
   result_error<={o_event_pipeline_error,8'd0,o_event_error};
  end
  if(job_unavailable||o_memory_invalidated)result_valid<=0;
  case(jstate)
   J_IDLE:if(command_valid&&command_ready)begin request<=command_data;result_code<=0;jstate<=J_DECODE;end
   J_DECODE:case(opcode)
    1:jstate<=J_REPLY;
    3:begin job_cancel<=1;jstate<=J_REPLY;end
    5:begin
     if(job_unavailable)begin result_code<=6;jstate<=J_REPLY;end
     else if(dma_busy||process_request||!bg_arb_idle||!live_arb_idle||axi_owner!=0)begin result_code<=1;jstate<=J_REPLY;end
     else if(job_bad)begin result_code<=2;jstate<=J_REPLY;end
     else begin
      job_bg_header<=bg_ext_active_header;job_on_header<=live_ext_active_header;
      job_epoch<=req_epoch;job_token<=req_token;job_geometry<=req_geometry;job_calibration<=req_calibration;
      job_role<=req_role[2:1];job_width<=req_width;job_height<=req_height;
      job_x0<=req_x0;job_x1<=req_x1;job_y0<=req_y0;job_rows<=row_span[11:0];
      job_left<=req_offset[11:0];job_right<=req_offset[27:16];
      queued<=1;job_cancel<=0;result_valid<=0;result_failed<=0;overflow<=0;
      result_count<=0;result_rows<=0;result_centers<=0;result_crc<=0;result_error<=0;cycles<=0;jstate<=J_REPLY;
     end
    end
    6:begin
     if(read_result)jstate<=J_RAM_WAIT;
     else begin result_code<=process_request?1:4;jstate<=J_REPLY;end
    end
    7:begin
     if(!dma_start_valid)result_code<=dma_busy?1:4;
     jstate<=J_REPLY;
    end
    default:begin result_code<=2;jstate<=J_REPLY;end
   endcase
   J_RAM_WAIT:jstate<=J_REPLY;
   J_REPLY:begin
    response_data<=0;response_data[31:0]<={12'd0,o_recovery_required,result_failed,result_valid,process_request,result_code,opcode};
    response_data[63:32]<=req_id;response_data[95:64]<=job_epoch;
    response_data[127:96]<=result_count;response_data[159:128]<=result_rows;response_data[191:160]<=result_centers;
    response_data[223:192]<=result_crc;response_data[255:224]<=cycles;
    response_data[287:256]<=job_on_header[127:96];response_data[319:288]<=job_bg_header[127:96];
    response_data[351:320]<=result_error;response_data[383:352]<=job_token;
    if(opcode==6&&result_code==0&&result_valid&&!process_request)response_data[511:384]<=ram_data;
    else if(opcode==6&&result_code==0)response_data[15:8]<=5;
    response_valid<=1;jstate<=J_SEND;
   end
   J_SEND:if(response_valid&&response_ready)begin response_valid<=0;jstate<=J_IDLE;end
  endcase
 end
end


wire dma_busy,dma_start_ready,dma_ram_read;
wire [10:0] dma_ram_address;
wire dma_start_valid=jstate==J_DECODE&&opcode==7&&result_valid&&!process_request&&
 !job_unavailable&&dma_start_ready&&result_count<=RESULT_DEPTH;
wire [1023:0] dma_header={256'd0,
 {4'd0,job_right,4'd0,job_left},{3'd0,job_y0+{1'b0,job_rows},3'd0,job_x1},
 {3'd0,job_y0,3'd0,job_x0},{3'd0,job_height,3'd0,job_width},
 32'd0,32'h00060000,result_error,cycles,
 result_crc,result_centers,result_rows,result_count,
 job_bg_header[127:96],job_on_header[127:96],job_calibration,job_geometry,
 {30'd0,job_role},job_token,job_epoch,req_id,
 32'd128,32'd65536,32'h00010000,32'h51444d41};
afc03_result_dma result_dma(
 .dclk(dclk),.hclk(hclk),.reset_n(reset_n),
 .start_valid(dma_start_valid),.start_ready(dma_start_ready),.header(dma_header),.records(result_count),
 .ram_read(dma_ram_read),.ram_address(dma_ram_address),.ram_data(ram_data),.busy(dma_busy),
 .m_data(result_dma_data),.m_valid(result_dma_valid),.m_ready(result_dma_ready),.m_last(result_dma_last));

endmodule
