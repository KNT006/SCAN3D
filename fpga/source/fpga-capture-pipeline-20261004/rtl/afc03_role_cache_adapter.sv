`timescale 1ns/1ps
// Minimal single-clock wiring of slot ownership and the real AXI mover.
// A reader MUST first acquire/pin a matching slot, retain its grant metadata,
// then release only after read completion AND all speculative outputs drain.
// No CDC, transpose, camera buffering, automatic laser control or DDR IP here.
module afc03_role_cache_adapter #(
 parameter [3:0] ALLOWED_ROLES=4'b0001,
 parameter ADDR_WIDTH=28,
 parameter [ADDR_WIDTH-1:0] SLOT0_BASE=28'h0100000,
 parameter [ADDR_WIDTH-1:0] SLOT1_BASE=28'h0900000,
 parameter SLOT_BYTES=8388608,
 parameter MOVER_TIMEOUT=1000000,
 parameter FRAME_TIMEOUT=100000000
)(
 input wire clk,rst_n,transport_rst_n,
 input wire [31:0] config_epoch,config_geometry,config_calibration,
 input wire memory_invalidated,
 input wire begin_valid,output wire begin_ready,
 input wire [31:0] begin_frame_id,
 input wire [12:0] begin_roi_width,begin_roi_height,
 input wire [31:0] begin_expected_pixels,begin_expected_bytes,
 input wire [1:0] begin_role,
 input wire cancel_update,
 input wire source_frame_status_valid,output wire source_frame_status_ready,
 input wire source_frame_status_complete,source_frame_status_ok,
 input wire [7:0] source_frame_status_error,
 input wire [31:0] source_frame_status_frame_id,source_frame_status_epoch,
 input wire [127:0] source_frame_status_header,
 // Stable while update_busy; capture-owner may bind its token to this header.
 output wire [127:0] pending_write_header,output wire [31:0] pending_write_epoch,
 input wire sample_valid,output wire sample_ready,
 input wire [127:0] sample_data,input wire [15:0] sample_keep,
 input wire [2:0] sample_pixels,input wire [4:0] sample_bytes,
 input wire sample_sof,sample_eof,input wire [31:0] sample_frame_id,
 input wire [1:0] sample_lasers,input wire [7:0] sample_error,
 output wire writer_abort,writer_quiescent,update_busy,
 output wire update_event_valid,input wire update_event_ready,
 output wire update_event_ok,output wire [7:0] update_event_error,
 output wire [127:0] update_event_header,output wire [31:0] update_event_epoch,
 output wire [1:0] active_role,grant_role,
 output wire active_valid,active_slot,
 output wire [127:0] active_header,output wire [31:0] active_epoch,
 output wire [31:0] active_pixels,active_bytes,
 output wire invalidate_readers,
 input wire acquire_valid,output wire acquire_ready,
 output wire grant_valid,grant_slot,output wire [ADDR_WIDTH-1:0] grant_address,
 output wire [127:0] grant_header,output wire [31:0] grant_epoch,grant_pixels,grant_bytes,
 input wire release_valid,release_slot,input wire [127:0] release_header,
 input wire [31:0] release_epoch,
 output wire release_ok,protocol_error,blocked_by_readers,
 input wire read_cmd_valid,output wire read_cmd_ready,
 input wire [ADDR_WIDTH-1:0] read_cmd_address,
 input wire [31:0] read_cmd_bytes,read_cmd_epoch,input wire [127:0] read_cmd_header,
 output wire read_valid,input wire read_ready,
 output wire [127:0] read_data,read_header,output wire [15:0] read_keep,
 output wire read_last,output wire [31:0] read_epoch,
 output wire read_status_valid,input wire read_status_ready,
 output wire read_status_ok,output wire [7:0] read_status_error,
 output wire [31:0] read_status_bytes,read_status_epoch,
 output wire [127:0] read_status_header,
 output wire transport_busy,transport_requires_reset,
 output wire read_transport_busy,write_transport_busy,
 output wire [3:0] awid,output wire [ADDR_WIDTH-1:0] awaddr,
 output wire [7:0] awlen,output wire [2:0] awsize,
 output wire [1:0] awburst,output wire awvalid,input wire awready,
 output wire [127:0] wdata,output wire [15:0] wstrb,
 output wire wlast,wvalid,input wire wready,
 input wire [3:0] bid,input wire [1:0] bresp,input wire bvalid,output wire bready,
 output wire [3:0] arid,output wire [ADDR_WIDTH-1:0] araddr,
 output wire [7:0] arlen,output wire [2:0] arsize,
 output wire [1:0] arburst,output wire arvalid,input wire arready,
 input wire [3:0] rid,input wire [127:0] rdata,input wire [1:0] rresp,
 input wire rlast,rvalid,output wire rready
);
 wire slots_begin_ready,write_cmd_valid,write_cmd_ready;
 wire [ADDR_WIDTH-1:0] write_cmd_address;
 wire [31:0] write_cmd_bytes,write_cmd_epoch;
 wire [127:0] write_cmd_header;
 wire transport_reset=rst_n&&transport_rst_n;
 wire w_reset_required,r_reset_required,w_status_valid,w_status_ok;
 wire [7:0] w_status_error;
 wire [31:0] w_status_bytes;
 wire [127:0] w_status_header;
 reg [31:0] write_epoch,read_epoch_latched;
 wire read_command_ready,write_command_ready;
 assign transport_busy=read_transport_busy||write_transport_busy;
 assign transport_requires_reset=w_reset_required||r_reset_required;
 assign write_cmd_ready=write_command_ready&&!transport_requires_reset;
 assign read_cmd_ready=read_command_ready&&!transport_requires_reset;
 assign begin_ready=slots_begin_ready&&transport_reset&&!transport_requires_reset;
 assign pending_write_header=write_cmd_header;
 assign pending_write_epoch=write_cmd_epoch;
 assign read_epoch=read_epoch_latched;
 assign read_status_epoch=read_epoch_latched;
 // A reader may run concurrently with writes into a DIFFERENT, unpinned slot.
 // An early write timeout still retains the physical write channel until drain.
 assign writer_quiescent=transport_reset&&!write_transport_busy&&!w_status_valid;
 always @(posedge clk or negedge transport_reset)begin
  if(!transport_reset)begin write_epoch<=0;read_epoch_latched<=0;end
  else begin
   if(write_cmd_valid&&write_cmd_ready)write_epoch<=write_cmd_epoch;
   if(read_cmd_valid&&read_cmd_ready)read_epoch_latched<=read_cmd_epoch;
  end
 end
 afc03_role_frame_slots #(.ALLOWED_ROLES(ALLOWED_ROLES),.ADDR_WIDTH(ADDR_WIDTH),.SLOT0_BASE(SLOT0_BASE),
  .SLOT1_BASE(SLOT1_BASE),.SLOT_BYTES(SLOT_BYTES),.TIMEOUT_CYCLES(FRAME_TIMEOUT)) slots(
  .clk(clk),.rst_n(rst_n),.config_epoch(config_epoch),.config_geometry(config_geometry),
  .config_calibration(config_calibration),.memory_invalidated(memory_invalidated),
  .begin_valid(begin_valid&&transport_reset&&!transport_requires_reset),.begin_ready(slots_begin_ready),
  .begin_frame_id(begin_frame_id),.begin_roi_width(begin_roi_width),.begin_roi_height(begin_roi_height),
  .begin_expected_pixels(begin_expected_pixels),.begin_expected_bytes(begin_expected_bytes),
  .begin_role(begin_role),.cancel_update(cancel_update),
  .sample_valid(sample_valid&&sample_ready),.sample_pixels(sample_pixels),.sample_bytes(sample_bytes),
  .sample_sof(sample_sof),.sample_eof(sample_eof),.sample_frame_id(sample_frame_id),
  .sample_lasers(sample_lasers),.sample_error(sample_error),
  .write_cmd_valid(write_cmd_valid),.write_cmd_ready(write_cmd_ready),
  .write_cmd_address(write_cmd_address),.write_cmd_bytes(write_cmd_bytes),
  .write_cmd_header(write_cmd_header),.write_cmd_epoch(write_cmd_epoch),
  .write_status_valid(w_status_valid),.write_status_ready(),
  .write_status_ok(w_status_ok),.write_status_error(w_status_error),.write_status_bytes(w_status_bytes),
  .write_status_header(w_status_header),.write_status_epoch(write_epoch),
  .source_frame_status_valid(source_frame_status_valid),.source_frame_status_ready(source_frame_status_ready),
  .source_frame_status_complete(source_frame_status_complete),.source_frame_status_ok(source_frame_status_ok),
  .source_frame_status_error(source_frame_status_error),.source_frame_status_frame_id(source_frame_status_frame_id),
  .source_frame_status_header(source_frame_status_header),.source_frame_status_epoch(source_frame_status_epoch),
  .writer_quiescent(writer_quiescent),.writer_abort(writer_abort),.update_busy(update_busy),
  .update_event_valid(update_event_valid),.update_event_ready(update_event_ready),
  .update_event_ok(update_event_ok),.update_event_error(update_event_error),
  .update_event_header(update_event_header),.update_event_epoch(update_event_epoch),
  .active_role(active_role),.grant_role(grant_role),.active_valid(active_valid),.active_slot(active_slot),.active_header(active_header),
  .active_epoch(active_epoch),.invalidate_readers(invalidate_readers),
  .active_pixels(active_pixels),.active_bytes(active_bytes),
  .acquire_valid(acquire_valid),.acquire_ready(acquire_ready),.grant_valid(grant_valid),
  .grant_slot(grant_slot),.grant_address(grant_address),.grant_header(grant_header),
  .grant_epoch(grant_epoch),.grant_pixels(grant_pixels),.grant_bytes(grant_bytes),
  .release_valid(release_valid),.release_slot(release_slot),.release_header(release_header),
  .release_epoch(release_epoch),.release_ok(release_ok),.protocol_error(protocol_error),
  .blocked_by_readers(blocked_by_readers)
 );
 afc03_axi_burst_mover #(.ADDR_WIDTH(ADDR_WIDTH),.TIMEOUT_CYCLES(MOVER_TIMEOUT)) writer(
  .clk(clk),.rst_n(transport_reset),.cmd_valid(write_cmd_valid&&!transport_requires_reset),
  .cmd_ready(write_command_ready),.cmd_write(1'b1),.cmd_address(write_cmd_address),
  .cmd_bytes(write_cmd_bytes),.cmd_header(write_cmd_header),
  .s_valid(sample_valid),.s_ready(sample_ready),.s_data(sample_data),.s_keep(sample_keep),.s_last(sample_eof),
  .m_valid(),.m_ready(1'b1),.m_data(),.m_keep(),.m_last(),.m_header(),
  .status_valid(w_status_valid),.status_ready(1'b1),.status_ok(w_status_ok),
  .status_error(w_status_error),.status_bytes(w_status_bytes),.status_header(w_status_header),
  .busy(write_transport_busy),.requires_reset(w_reset_required),
  .awid(awid),.awaddr(awaddr),.awlen(awlen),.awsize(awsize),.awburst(awburst),.awvalid(awvalid),.awready(awready),
  .wdata(wdata),.wstrb(wstrb),.wlast(wlast),.wvalid(wvalid),.wready(wready),
  .bid(bid),.bresp(bresp),.bvalid(bvalid),.bready(bready),
  .arid(),.araddr(),.arlen(),.arsize(),.arburst(),.arvalid(),.arready(1'b0),
  .rid(4'd0),.rdata(128'd0),.rresp(2'd0),.rlast(1'b0),.rvalid(1'b0),.rready());
 afc03_axi_burst_mover #(.ADDR_WIDTH(ADDR_WIDTH),.TIMEOUT_CYCLES(MOVER_TIMEOUT)) reader(
  .clk(clk),.rst_n(transport_reset),.cmd_valid(read_cmd_valid&&!transport_requires_reset),
  .cmd_ready(read_command_ready),.cmd_write(1'b0),.cmd_address(read_cmd_address),
  .cmd_bytes(read_cmd_bytes),.cmd_header(read_cmd_header),
  .s_valid(1'b0),.s_ready(),.s_data(128'd0),.s_keep(16'd0),.s_last(1'b0),
  .m_valid(read_valid),.m_ready(read_ready),.m_data(read_data),.m_keep(read_keep),.m_last(read_last),.m_header(read_header),
  .status_valid(read_status_valid),.status_ready(read_status_ready),.status_ok(read_status_ok),
  .status_error(read_status_error),.status_bytes(read_status_bytes),.status_header(read_status_header),
  .busy(read_transport_busy),.requires_reset(r_reset_required),
  .awid(),.awaddr(),.awlen(),.awsize(),.awburst(),.awvalid(),.awready(1'b0),
  .wdata(),.wstrb(),.wlast(),.wvalid(),.wready(1'b0),.bid(4'd0),.bresp(2'd0),.bvalid(1'b0),.bready(),
  .arid(arid),.araddr(araddr),.arlen(arlen),.arsize(arsize),.arburst(arburst),.arvalid(arvalid),.arready(arready),
  .rid(rid),.rdata(rdata),.rresp(rresp),.rlast(rlast),.rvalid(rvalid),.rready(rready));
endmodule
