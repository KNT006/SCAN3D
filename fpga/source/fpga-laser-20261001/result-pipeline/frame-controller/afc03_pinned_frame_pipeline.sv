`timescale 1ns/1ps
// One complete ROI frame using real tile reader/diff/transpose/row logic.
// Ownership/DDR pins are supplied by afc03_frame_pair_owner, not allocated here.
module afc03_pinned_frame_pipeline #(
 parameter ADDR_WIDTH=28,MAX_HEIGHT=2048,INPUT_TIMEOUT=1000000,CORE_TIMEOUT=10000000
)(
 input wire clk,rst_n,cancel,memory_invalidated,ownership_valid,read_exclusive,
 input wire cfg_valid,output wire cfg_ready,
 input wire [ADDR_WIDTH-1:0] cfg_on_base,cfg_bg_base,
 input wire [31:0] cfg_on_region_bytes,cfg_bg_region_bytes,cfg_on_stride,cfg_bg_stride,
 input wire [12:0] cfg_width,cfg_height,cfg_x0,cfg_x1,cfg_y0,
 input wire [11:0] cfg_rows,cfg_roi_left,cfg_roi_right,
 input wire [127:0] cfg_on_header,cfg_bg_header,
 input wire [31:0] cfg_epoch,cfg_token,cfg_geometry,cfg_calibration,
 input wire transport_busy,transport_requires_reset,
 output wire read_cmd_valid,input wire read_cmd_ready,
 output wire [ADDR_WIDTH-1:0] read_cmd_address,
 output wire [31:0] read_cmd_bytes,read_cmd_epoch,output wire [127:0] read_cmd_header,
 input wire read_valid,output wire read_ready,
 input wire [127:0] read_data,read_header,input wire [15:0] read_keep,
 input wire read_last,input wire [31:0] read_epoch,
 input wire read_status_valid,output wire read_status_ready,
 input wire read_status_ok,input wire [7:0] read_status_error,
 input wire [31:0] read_status_bytes,read_status_epoch,
 input wire [127:0] read_status_header,
 output wire record_valid,input wire record_ready,
 output wire [127:0] record_data,output wire [7:0] record_type,
 output wire done_valid,input wire done_ready,
 output wire done_ok,output wire [15:0] done_error,
 output wire [31:0] done_rows,done_records,done_centers,done_crc32,
 output wire [127:0] on_header,bg_header,
 output wire [31:0] epoch,token,geometry,calibration,
 output wire busy,downstream_drained,progress
);
 reg [ADDR_WIDTH-1:0] on_base,bg_base;
 reg [31:0] on_bytes,bg_bytes,on_stride,bg_stride;
 wire seq_ready;
 assign cfg_ready=seq_ready&&ownership_valid&&read_exclusive;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin on_base<=0;bg_base<=0;on_bytes<=0;bg_bytes<=0;on_stride<=0;bg_stride<=0;end
  else if(cfg_valid&&cfg_ready)begin
   on_base<=cfg_on_base;bg_base<=cfg_bg_base;on_bytes<=cfg_on_region_bytes;bg_bytes<=cfg_bg_region_bytes;
   on_stride<=cfg_on_stride;bg_stride<=cfg_bg_stride;
  end
 end
 wire tile_cfg_valid,tile_cfg_ready,tile_cancel;
 wire [12:0] tile_width,tile_height,tile_x0,tile_y0;
 wire [4:0] tile_cols;
 wire [11:0] tile_rows,tile_roi_left,tile_roi_right;
 wire tile_record_valid,tile_record_ready;
 wire [127:0] tile_record_data;wire [7:0] tile_record_type;
 wire tile_status_valid,tile_status_ready,tile_status_ok;
 wire [15:0] tile_status_error;
 wire [31:0] tile_status_rows,tile_status_records,tile_status_centers;
 wire [31:0] tile_status_frame,tile_status_background_frame,tile_status_generation;
 wire [31:0] tile_status_epoch,tile_status_token,tile_status_geometry,tile_status_calibration;
 wire invalidated=memory_invalidated||!ownership_valid||!read_exclusive;
 // Real accepted transfers only. This is an inactivity watchdog heartbeat,
 // never a substitute for an outer bound on total frame execution time.
 assign progress=busy&&((read_cmd_valid&&read_cmd_ready)||(read_valid&&read_ready)||
  (read_status_valid&&read_status_ready)||(record_valid&&record_ready));
 afc03_frame_tile_sequencer #(.MAX_HEIGHT(MAX_HEIGHT)) sequencer(
  .clk(clk),.rst_n(rst_n),.cancel(cancel),.memory_invalidated(invalidated),
  .cfg_valid(cfg_valid&&ownership_valid&&read_exclusive),.cfg_ready(seq_ready),
  .cfg_width(cfg_width),.cfg_height(cfg_height),.cfg_x0(cfg_x0),.cfg_x1(cfg_x1),.cfg_y0(cfg_y0),
  .cfg_rows(cfg_rows),.cfg_roi_left(cfg_roi_left),.cfg_roi_right(cfg_roi_right),
  .cfg_on_header(cfg_on_header),.cfg_bg_header(cfg_bg_header),.cfg_epoch(cfg_epoch),.cfg_token(cfg_token),
  .cfg_geometry(cfg_geometry),.cfg_calibration(cfg_calibration),
  .transport_busy(transport_busy),.transport_requires_reset(transport_requires_reset),
  .tile_cfg_valid(tile_cfg_valid),.tile_cfg_ready(tile_cfg_ready),.tile_cancel(tile_cancel),
  .tile_width(tile_width),.tile_height(tile_height),.tile_x0(tile_x0),.tile_y0(tile_y0),
  .tile_cols(tile_cols),.tile_rows(tile_rows),.tile_roi_left(tile_roi_left),.tile_roi_right(tile_roi_right),
  .on_header(on_header),.bg_header(bg_header),.epoch(epoch),.token(token),.geometry(geometry),.calibration(calibration),
  .tile_record_valid(tile_record_valid),.tile_record_ready(tile_record_ready),
  .tile_record_data(tile_record_data),.tile_record_type(tile_record_type),
  .tile_status_valid(tile_status_valid),.tile_status_ready(tile_status_ready),.tile_status_ok(tile_status_ok),
  .tile_status_error(tile_status_error),.tile_status_rows(tile_status_rows),.tile_status_records(tile_status_records),
  .tile_status_centers(tile_status_centers),.tile_status_frame(tile_status_frame),
  .tile_status_background_frame(tile_status_background_frame),.tile_status_generation(tile_status_generation),
  .tile_status_epoch(tile_status_epoch),.tile_status_token(tile_status_token),
  .tile_status_geometry(tile_status_geometry),.tile_status_calibration(tile_status_calibration),
  .record_valid(record_valid),.record_ready(record_ready),.record_data(record_data),.record_type(record_type),
  .done_valid(done_valid),.done_ready(done_ready),.done_ok(done_ok),.done_error(done_error),
  .done_rows(done_rows),.done_records(done_records),.done_centers(done_centers),.done_crc32(done_crc32),
  .busy(busy),.downstream_drained(downstream_drained));
 afc03_tile_laser_pipeline #(.ADDR_WIDTH(ADDR_WIDTH),.MAX_HEIGHT(MAX_HEIGHT),
  .INPUT_TIMEOUT(INPUT_TIMEOUT),.CORE_TIMEOUT(CORE_TIMEOUT)) tile(
  .clk(clk),.rst_n(rst_n),.cancel(tile_cancel),.cfg_valid(tile_cfg_valid),.cfg_ready(tile_cfg_ready),
  .cfg_on_base(on_base),.cfg_bg_base(bg_base),.cfg_on_region_bytes(on_bytes),.cfg_bg_region_bytes(bg_bytes),
  .cfg_on_stride(on_stride),.cfg_bg_stride(bg_stride),.cfg_image_width(tile_width),.cfg_image_height(tile_height),
  .cfg_x0(tile_x0),.cfg_y0(tile_y0),.cfg_cols(tile_cols),.cfg_rows(tile_rows),
  .cfg_roi_left(tile_roi_left),.cfg_roi_right(tile_roi_right),
  .cfg_on_header(on_header),.cfg_bg_header(bg_header),.cfg_epoch(epoch),.cfg_token(token),
  .cfg_geometry(geometry),.cfg_calibration(calibration),
  .cfg_on_committed(ownership_valid),.cfg_bg_committed(ownership_valid),
  .cfg_on_pinned(ownership_valid),.cfg_bg_pinned(ownership_valid),
  .transport_busy(transport_busy),.transport_requires_reset(transport_requires_reset),
  .read_cmd_valid(read_cmd_valid),.read_cmd_ready(read_cmd_ready),.read_cmd_address(read_cmd_address),
  .read_cmd_bytes(read_cmd_bytes),.read_cmd_epoch(read_cmd_epoch),.read_cmd_header(read_cmd_header),
  .read_valid(read_valid),.read_ready(read_ready),.read_data(read_data),.read_header(read_header),
  .read_keep(read_keep),.read_last(read_last),.read_epoch(read_epoch),
  .read_status_valid(read_status_valid),.read_status_ready(read_status_ready),.read_status_ok(read_status_ok),
  .read_status_error(read_status_error),.read_status_bytes(read_status_bytes),
  .read_status_epoch(read_status_epoch),.read_status_header(read_status_header),
  .record_valid(tile_record_valid),.record_ready(tile_record_ready),.record_data(tile_record_data),.record_type(tile_record_type),
  .busy(),.tile_status_valid(tile_status_valid),.tile_status_ready(tile_status_ready),.tile_status_ok(tile_status_ok),
  .tile_status_error(tile_status_error),.reader_error(),.transpose_error(),.row_error(),
  .tile_rows(tile_status_rows),.tile_records(tile_status_records),.tile_centers(tile_status_centers),
  .source_frame_id(tile_status_frame),.background_frame_id(tile_status_background_frame),
  .background_generation(tile_status_generation),.epoch(tile_status_epoch),.token(tile_status_token),
  .geometry(tile_status_geometry),.calibration(tile_status_calibration));
endmodule
