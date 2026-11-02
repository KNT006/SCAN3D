`timescale 1ns/1ps
// Speculative, single-clock TILE transaction. No DDR ownership or frame footer.
// Caller commits/pins both frames; records remain speculative until TILE status,
// and even successful tiles require an external complete-frame CRC/commit.
module afc03_tile_laser_pipeline #(
 parameter MAX_HEIGHT=2048, parameter ADDR_WIDTH=28,
 parameter INPUT_TIMEOUT=1000000, parameter CORE_TIMEOUT=10000000
)(
 input wire clk,rst_n,cancel,
 input wire cfg_valid,output wire cfg_ready,
 input wire [ADDR_WIDTH-1:0] cfg_on_base,cfg_bg_base,
 input wire [31:0] cfg_on_region_bytes,cfg_bg_region_bytes,cfg_on_stride,cfg_bg_stride,
 input wire [12:0] cfg_image_width,cfg_image_height,cfg_x0,cfg_y0,
 input wire [4:0] cfg_cols,input wire [11:0] cfg_rows,cfg_roi_left,cfg_roi_right,
 input wire [127:0] cfg_on_header,cfg_bg_header,
 input wire [31:0] cfg_epoch,cfg_token,cfg_geometry,cfg_calibration,
 input wire cfg_on_committed,cfg_bg_committed,cfg_on_pinned,cfg_bg_pinned,
 input wire transport_busy,transport_requires_reset,
 output wire read_cmd_valid,input wire read_cmd_ready,
 output wire [ADDR_WIDTH-1:0] read_cmd_address,
 output wire [31:0] read_cmd_bytes,read_cmd_epoch,
 output wire [127:0] read_cmd_header,
 input wire read_valid,output wire read_ready,
 input wire [127:0] read_data,read_header,input wire [15:0] read_keep,
 input wire read_last,input wire [31:0] read_epoch,
 input wire read_status_valid,output wire read_status_ready,
 input wire read_status_ok,input wire [7:0] read_status_error,
 input wire [31:0] read_status_bytes,read_status_epoch,
 input wire [127:0] read_status_header,
 output wire record_valid,input wire record_ready,
 output wire [127:0] record_data,output wire [7:0] record_type,
 output wire busy,output reg tile_status_valid,input wire tile_status_ready,
 output reg tile_status_ok,output reg [15:0] tile_status_error,
 output reg [7:0] reader_error,output reg [15:0] transpose_error,row_error,
 output reg [31:0] tile_rows,tile_records,tile_centers,
 output reg [31:0] source_frame_id,background_frame_id,background_generation,
 output reg [31:0] epoch,token,geometry,calibration
);
 localparam IDLE=0,FILL=1,COMPUTE=2,FAIL_DRAIN=3,STATUS=4,RESET_PIPE=5;
 localparam [15:0] E_CONFIG=1,E_READER=2,E_KEEP=4,E_DIFF=8,
  E_TRANSPOSE=16,E_ROW=32,E_PACK=64,E_CANCEL=128;
 reg [2:0] state;
 reg [15:0] errors;
 reg [12:0] image_width,image_height,x0,y0,origin;
 reg [4:0] cols,next_row;
 reg [11:0] height,roi_left,roi_right;
 reg row_active,transpose_finished;
 reg pipe_release;
 wire pipe_reset_n=rst_n&&pipe_release;
 // Use a registered local reset enable, not a combinational state decode
 // on async reset pins. cfg_ready remains low until submodules leave reset.
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)pipe_release<=0;
  else if(state==FAIL_DRAIN||state==RESET_PIPE)pipe_release<=0;
  else if(state==IDLE)pipe_release<=1;
 end
 wire pr_cfg_ready,t_cfg_ready;
 wire config_bad=cfg_rows<3||cfg_rows>MAX_HEIGHT||cfg_roi_left>=cfg_roi_right||cfg_roi_right>=cfg_rows;
 assign cfg_ready=rst_n && state==IDLE && pr_cfg_ready && t_cfg_ready && !tile_status_valid;
 wire config_fire=cfg_valid&&cfg_ready;
 wire start_modules=config_fire&&!config_bad&&!cancel;
 assign busy=state!=IDLE;

 wire pr_busy,pr_fault,pr_valid,pr_ready,pr_sof,pr_eol,pr_eof;
 wire [7:0] pr_fault_code,pr_status_error;
 wire [127:0] pr_on,pr_bg;
 wire [15:0] pr_keep;
 wire [12:0] pr_x,pr_y;
 wire [31:0] pr_frame,pr_bg_frame,pr_gen,pr_geo,pr_cal,pr_epoch,pr_token;
 wire pr_status_valid,pr_status_ready,pr_status_ok;
 wire [31:0] pr_pixels,pr_commands;
 afc03_tile_pair_reader #(.ADDR_WIDTH(ADDR_WIDTH),.TIMEOUT_CYCLES(INPUT_TIMEOUT)) reader(
  .clk(clk),.rst_n(rst_n),.cfg_valid(start_modules),.cfg_ready(pr_cfg_ready),
  .cfg_on_base(cfg_on_base),.cfg_bg_base(cfg_bg_base),.cfg_on_region_bytes(cfg_on_region_bytes),
  .cfg_bg_region_bytes(cfg_bg_region_bytes),.cfg_on_stride(cfg_on_stride),.cfg_bg_stride(cfg_bg_stride),
  .cfg_image_width(cfg_image_width),.cfg_image_height(cfg_image_height),.cfg_x0(cfg_x0),.cfg_y0(cfg_y0),
  .cfg_cols(cfg_cols),.cfg_rows(cfg_rows),.cfg_on_header(cfg_on_header),.cfg_bg_header(cfg_bg_header),
  .cfg_epoch(cfg_epoch),.cfg_token(cfg_token),.cfg_geometry(cfg_geometry),.cfg_calibration(cfg_calibration),
  .cfg_on_committed(cfg_on_committed),.cfg_bg_committed(cfg_bg_committed),
  .cfg_on_pinned(cfg_on_pinned),.cfg_bg_pinned(cfg_bg_pinned),
  .cancel(cancel||state==FAIL_DRAIN),.transport_busy(transport_busy),.transport_requires_reset(transport_requires_reset),
  .busy(pr_busy),.fault_pending(pr_fault),.fault_code(pr_fault_code),
  .read_cmd_valid(read_cmd_valid),.read_cmd_ready(read_cmd_ready),.read_cmd_address(read_cmd_address),
  .read_cmd_bytes(read_cmd_bytes),.read_cmd_epoch(read_cmd_epoch),.read_cmd_header(read_cmd_header),
  .read_valid(read_valid),.read_ready(read_ready),.read_data(read_data),.read_header(read_header),
  .read_keep(read_keep),.read_last(read_last),.read_epoch(read_epoch),
  .read_status_valid(read_status_valid),.read_status_ready(read_status_ready),.read_status_ok(read_status_ok),
  .read_status_error(read_status_error),.read_status_bytes(read_status_bytes),.read_status_epoch(read_status_epoch),
  .read_status_header(read_status_header),.m_valid(pr_valid),.m_ready(pr_ready),
  .m_on_data(pr_on),.m_bg_data(pr_bg),.m_keep(pr_keep),.m_x(pr_x),.m_y(pr_y),
  .m_sof(pr_sof),.m_eol(pr_eol),.m_eof(pr_eof),.m_source_frame_id(pr_frame),
  .m_background_frame_id(pr_bg_frame),.m_background_generation(pr_gen),.m_geometry(pr_geo),
  .m_calibration(pr_cal),.m_epoch(pr_epoch),.m_token(pr_token),
  .tile_status_valid(pr_status_valid),.tile_status_ready(pr_status_ready),.tile_status_ok(pr_status_ok),
  .tile_status_error(pr_status_error),.tile_status_pixels(pr_pixels),.tile_status_commands(pr_commands));

 wire [3:0] pixel_keep;
 wire [3:0] partial_keep;
 genvar lane;
 generate for(lane=0;lane<4;lane=lane+1)begin:byte_to_pixel
  assign pixel_keep[lane]=&pr_keep[lane*4+:4];
  assign partial_keep[lane]=(|pr_keep[lane*4+:4])&&!(&pr_keep[lane*4+:4]);
 end endgenerate
 wire d_ready,d_valid,d_out_ready,d_sof,d_eol,d_eof;
 wire [31:0] d_signal,d_rawmax,d_frame,d_bg_frame,d_gen,d_geo;
 wire [3:0] d_keep;
 wire [12:0] d_x,d_y;
 wire [15:0] d_error;
 wire [7:0] d_up_error;
 // A poisoned upstream must keep draining; never deadlock while waiting status.
 assign pr_ready=state==FAIL_DRAIN ? 1'b1 : state==FILL && d_ready;
 wire pr_metadata_bad=pr_epoch!=epoch||pr_token!=token||pr_cal!=calibration;
 afc03_rgb_background_diff diff(
  .clk(clk),.rst_n(pipe_reset_n),.s_valid(pr_valid&&state==FILL),.s_ready(d_ready),
  .s_on(pr_on),.s_background(pr_bg),.s_keep(pixel_keep),.s_background_keep(pixel_keep),
  .s_sof(pr_sof),.s_eol(pr_eol),.s_eof(pr_eof),.s_frame_id(pr_frame),
  .s_expected_background_frame(background_frame_id),.s_expected_background_generation(background_generation),
  .s_geometry(geometry),.s_background_frame(pr_bg_frame),.s_background_generation(pr_gen),
  .s_background_geometry(pr_geo),.s_background_committed(1'b1),
  .s_x(pr_x),.s_y(pr_y),.s_background_x(pr_x),.s_background_y(pr_y),
  .s_width(image_width),.s_height(image_height),.s_background_width(image_width),.s_background_height(image_height),
  .s_upstream_error({6'd0,pr_metadata_bad,(|partial_keep)}),
  .m_valid(d_valid),.m_ready(d_out_ready),.m_signal(d_signal),.m_rawmax(d_rawmax),.m_keep(d_keep),
  .m_sof(d_sof),.m_eol(d_eol),.m_eof(d_eof),.m_frame_id(d_frame),.m_background_frame(d_bg_frame),
  .m_background_generation(d_gen),.m_geometry(d_geo),.m_x(d_x),.m_y(d_y),.m_error(d_error),.m_upstream_error(d_up_error));
 wire [63:0] diffword;
 generate for(lane=0;lane<4;lane=lane+1)begin:interleave
  assign diffword[lane*16+:16]={d_rawmax[lane*8+:8],d_signal[lane*8+:8]};
 end endgenerate

 wire t_commit_ready,t_valid,t_ready,t_done,t_busy;
 wire [15:0] t_error;
 wire [7:0] t_signal,t_rawmax;
 wire [12:0] t_row,t_origin;
 wire [11:0] t_x,t_width;
 wire t_sof,t_eol,t_tile_sof,t_tile_eof;
 wire [31:0] t_frame,t_gen,t_geo,t_token;
 // Successful reader status is held until the last elastic diff beat has
 // entered transpose. m_eof alone is NEVER a commit authorization.
 assign pr_status_ready=state==FAIL_DRAIN || (state==FILL&&(!pr_status_ok||t_commit_ready));
 wire commit_valid=state==FILL&&pr_status_valid&&pr_status_ok&&errors==0&&!cancel;
 afc03_diff_tile_transpose #(.MAX_HEIGHT(MAX_HEIGHT),.STALL_TIMEOUT(INPUT_TIMEOUT)) transpose(
  .clk(clk),.rst_n(pipe_reset_n),.abort(1'b0),.cfg_valid(start_modules),.cfg_ready(t_cfg_ready),
  .cfg_raw_width(cfg_image_width),.cfg_raw_height(cfg_image_height),.cfg_raw_x0(cfg_x0),.cfg_raw_y0(cfg_y0),
  .cfg_actual_cols(cfg_cols),.cfg_tile_height(cfg_rows),.cfg_frame_id(cfg_on_header[127:96]),
  .cfg_background_generation(cfg_bg_header[95:64]),.cfg_geometry(cfg_geometry),.cfg_request_id(cfg_token),
  .s_valid(d_valid),.s_ready(d_out_ready),.s_data(diffword),.s_keep(d_keep),.s_x(d_x),.s_y(d_y),
  .s_sof(d_sof),.s_eol(d_eol),.s_eot(d_eof),.s_frame_id(d_frame),.s_background_generation(d_gen),
  .s_geometry(d_geo),.s_error(d_error),.c_valid(commit_valid),.c_ready(t_commit_ready),
  .c_source_frame_committed(1'b1),.c_frame_id(source_frame_id),.c_background_generation(background_generation),
  .c_geometry(geometry),.c_request_id(token),.c_error(16'd0),
  .m_valid(t_valid),.m_ready(t_ready),.m_signal(t_signal),.m_rawmax(t_rawmax),
  .m_row(t_row),.m_global_x_origin(t_origin),.m_local_x(t_x),.m_width(t_width),
  .m_sof(t_sof),.m_eol(t_eol),.m_tile_sof(t_tile_sof),.m_tile_eof(t_tile_eof),
  .m_frame_id(t_frame),.m_background_generation(t_gen),.m_geometry(t_geo),.m_request_id(t_token),
  .busy(t_busy),.done(t_done),.error(t_error));

 wire r_cfg_ready,p_begin_ready,r_valid,r_ready,r_done,r_done_ready,r_tie,r_busy;
 wire [31:0] r_num,r_cycles,r_frame,r_gen,r_geo,r_token;
 wire [23:0] r_den;
 wire [15:0] r_peak,r_error;
 wire [7:0] r_record_error;
 wire [11:0] r_lo,r_hi;
 wire [12:0] r_row,r_origin;
 wire [1:0] r_count;
 wire row_cfg_valid=state==COMPUTE&&!row_active&&next_row<cols;
 wire row_cfg_fire=row_cfg_valid&&r_cfg_ready&&p_begin_ready;
 wire [12:0] expected_row=x0+next_row;
 laser_full_row_stream #(.MAX_WIDTH(MAX_HEIGHT),.INPUT_TIMEOUT(INPUT_TIMEOUT),.CORE_TIMEOUT(CORE_TIMEOUT)) rowcore(
  .clk(clk),.rst_n(pipe_reset_n),.abort(1'b0),.cfg_valid(row_cfg_valid&&p_begin_ready),.cfg_ready(r_cfg_ready),
  .cfg_width(height),.cfg_roi_left(roi_left),.cfg_roi_right(roi_right),.cfg_row(expected_row),.cfg_global_x_origin(origin),
  .cfg_frame_id(source_frame_id),.cfg_background_generation(background_generation),.cfg_geometry(geometry),.cfg_request_id(token),
  .s_valid(t_valid),.s_ready(t_ready),.s_signal(t_signal),.s_rawmax(t_rawmax),.s_local_x(t_x),.s_width(t_width),
  .s_row(t_row),.s_global_x_origin(t_origin),.s_sof(t_sof),.s_eol(t_eol),
  .s_frame_id(t_frame),.s_background_generation(t_gen),.s_geometry(t_geo),.s_request_id(t_token),
  .center_valid(r_valid),.center_ready(r_ready),.center_num(r_num),.center_den(r_den),.center_peak32(r_peak),
  .center_lo(r_lo),.center_hi(r_hi),.row_done_valid(r_done),.row_done_ready(r_done_ready),
  .row_center_count(r_count),.row_tie_conflict(r_tie),.row_error(r_error),.row_record_error(r_record_error),
  .row_id(r_row),.global_x_origin(r_origin),.frame_id(r_frame),.background_generation(r_gen),
  .geometry(r_geo),.request_id(r_token),.row_cycles(r_cycles),.busy(r_busy));
 assign r_done_ready=state==COMPUTE&&row_active;
 wire p_valid,p_emitted,p_busy,p_fault;
 wire [127:0] p_data;wire [7:0] p_type;
 reg output_valid;reg [127:0] output_data;reg [7:0] output_type;
 wire p_ready=state==COMPUTE&&!cancel&&(!output_valid||record_ready);
 assign record_valid=output_valid;
 assign record_data=output_data;
 assign record_type=output_type;
 // The externally offered beat survives a local pipeline abort. Once VALID
 // was offered it must drain unchanged, even though tile status will reject
 // the transaction. Only the global reset may retract that pending beat.
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin output_valid<=0;output_data<=0;output_type<=0;end
  else begin
   if(output_valid&&record_ready)output_valid<=0;
   if(p_valid&&p_ready)begin output_valid<=1;output_data<=p_data;output_type<=p_type;end
  end
 end
 row_record_packer packer(
  .clk(clk),.rst_n(pipe_reset_n),.row_begin_valid(row_cfg_valid&&r_cfg_ready),.row_begin_ready(p_begin_ready),
  .row_id({3'd0,expected_row}),.center_valid(r_valid),.center_ready(r_ready),.center_num(r_num),
  .center_den(r_den),.center_peak32(r_peak),.center_lo(r_lo),.center_hi(r_hi),
  .row_done(r_done&&r_done_ready),.row_center_count(r_count),.row_tie_conflict(r_tie),
  .row_error(r_record_error),.row_cycles(r_cycles),.record_data(p_data),.record_valid(p_valid),
  .record_ready(p_ready),.record_type(p_type),
  .row_emitted(p_emitted),.row_busy(p_busy),.protocol_fault(p_fault));

 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=RESET_PIPE;errors<=0;tile_status_valid<=0;tile_status_ok<=0;tile_status_error<=0;
   reader_error<=0;transpose_error<=0;row_error<=0;tile_rows<=0;tile_records<=0;tile_centers<=0;
   source_frame_id<=0;background_frame_id<=0;background_generation<=0;epoch<=0;token<=0;geometry<=0;calibration<=0;
   image_width<=0;image_height<=0;x0<=0;y0<=0;origin<=0;cols<=0;height<=0;roi_left<=0;roi_right<=0;
   next_row<=0;row_active<=0;transpose_finished<=0;
  end else begin
   if(record_valid&&record_ready)begin
    tile_records<=tile_records+1'b1;
    if(record_type==1)tile_centers<=tile_centers+1'b1;
   end
   case(state)
    RESET_PIPE:state<=IDLE;
    IDLE:if(config_fire)begin
     image_width<=cfg_image_width;image_height<=cfg_image_height;x0<=cfg_x0;y0<=cfg_y0;
     origin<=cfg_image_height-cfg_y0-cfg_rows;cols<=cfg_cols;height<=cfg_rows;
     roi_left<=cfg_roi_left;roi_right<=cfg_roi_right;next_row<=0;row_active<=0;transpose_finished<=0;
     source_frame_id<=cfg_on_header[127:96];background_frame_id<=cfg_bg_header[127:96];
     background_generation<=cfg_bg_header[95:64];epoch<=cfg_epoch;token<=cfg_token;
     geometry<=cfg_geometry;calibration<=cfg_calibration;
     reader_error<=0;transpose_error<=0;row_error<=0;tile_rows<=0;tile_records<=0;tile_centers<=0;
     errors<=config_bad?E_CONFIG:(cancel?E_CANCEL:16'd0);tile_status_ok<=0;tile_status_error<=0;
     state<=(config_bad||cancel)?FAIL_DRAIN:FILL;
    end
    FILL:begin
     if(pr_fault)begin errors<=errors|E_READER;reader_error<=pr_fault_code;state<=FAIL_DRAIN;end
     else if(pr_valid&&pr_ready&&((|partial_keep)||pr_metadata_bad))begin errors<=errors|E_KEEP;state<=FAIL_DRAIN;end
     else if(d_valid&&d_error!=0)begin errors<=errors|E_DIFF;state<=FAIL_DRAIN;end
     else if(t_done&&t_error!=0)begin errors<=errors|E_TRANSPOSE;transpose_error<=t_error;state<=FAIL_DRAIN;end
     else if(pr_status_valid&&pr_status_ready)begin
      if(!pr_status_ok)begin errors<=errors|E_READER;reader_error<=pr_status_error;state<=FAIL_DRAIN;end
      else state<=COMPUTE;
     end
     if(cancel)begin errors<=errors|E_CANCEL;state<=FAIL_DRAIN;end
    end
    COMPUTE:begin
     if(row_cfg_fire)row_active<=1;
     if(p_emitted)begin row_active<=0;next_row<=next_row+1'b1;tile_rows<=tile_rows+1'b1;end
     if(t_done)transpose_finished<=1;
     if(cancel)begin errors<=errors|E_CANCEL;state<=FAIL_DRAIN;end
     else if(t_done&&t_error!=0)begin errors<=errors|E_TRANSPOSE;transpose_error<=t_error;state<=FAIL_DRAIN;end
     else if(r_done&&r_done_ready&&r_error!=0)begin errors<=errors|E_ROW;row_error<=r_error;state<=FAIL_DRAIN;end
     else if(p_fault)begin errors<=errors|E_PACK;state<=FAIL_DRAIN;end
     else if(next_row==cols&&!row_active&&transpose_finished&&!p_busy&&!output_valid)begin
      tile_status_valid<=1;tile_status_ok<=1;tile_status_error<=0;state<=STATUS;
     end
    end
    FAIL_DRAIN:begin
     if(pr_fault)reader_error<=pr_fault_code;
     if(!pr_busy&&!pr_status_valid&&!transport_busy&&!output_valid)begin
      tile_status_valid<=1;tile_status_ok<=0;tile_status_error<=errors;state<=STATUS;
     end
    end
    STATUS:if(tile_status_valid&&tile_status_ready)begin tile_status_valid<=0;state<=RESET_PIPE;end
    default:state<=RESET_PIPE;
   endcase
  end
 end
endmodule
