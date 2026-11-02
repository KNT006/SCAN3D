`timescale 1ns/1ps
// Single-clock, read-only scheduler for a half-duplex DDR mover.
// ON and background frames MUST already be committed and pinned by the caller.
// Every output is speculative until tile_status_ok, even after m_eof.
module afc03_tile_pair_reader #(
 parameter ADDR_WIDTH=28, parameter TIMEOUT_CYCLES=1000000
)(
 input wire clk,rst_n,
 input wire cfg_valid,output wire cfg_ready,
 input wire [ADDR_WIDTH-1:0] cfg_on_base,cfg_bg_base,
 input wire [31:0] cfg_on_region_bytes,cfg_bg_region_bytes,cfg_on_stride,cfg_bg_stride,
 input wire [12:0] cfg_image_width,cfg_image_height,cfg_x0,cfg_y0,
 input wire [4:0] cfg_cols,input wire [11:0] cfg_rows,
 input wire [127:0] cfg_on_header,cfg_bg_header,
 input wire [31:0] cfg_epoch,cfg_token,cfg_geometry,cfg_calibration,
 input wire cfg_on_committed,cfg_bg_committed,cfg_on_pinned,cfg_bg_pinned,
 input wire cancel,transport_busy,transport_requires_reset,
 output reg busy,output wire fault_pending,output reg [7:0] fault_code,
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
 output reg m_valid,input wire m_ready,
 output reg [127:0] m_on_data,m_bg_data,output reg [15:0] m_keep,
 output reg [12:0] m_x,m_y,output reg m_sof,m_eol,m_eof,
 output wire [31:0] m_source_frame_id,m_background_frame_id,m_background_generation,
 output wire [31:0] m_geometry,m_calibration,m_epoch,m_token,
 output reg tile_status_valid,input wire tile_status_ready,
 output reg tile_status_ok,output reg [7:0] tile_status_error,
 output reg [31:0] tile_status_pixels,tile_status_commands
);
 localparam IDLE=0,CMD_ON=1,DATA_ON=2,CMD_BG=3,DATA_BG=4,FINISH=5;
 localparam BAD_CONFIG=1,CANCELLED=2,TIMEOUT=3,TRANSPORT_FAULT=4,
  BAD_DATA_ID=5,BAD_KEEP=6,BAD_LAST=7,BAD_COUNT=8,
  BAD_STATUS_ID=9,BAD_STATUS=10;
 reg [2:0] state;
 reg [127:0] on_header,bg_header;
 reg [31:0] epoch,token,geometry,calibration,on_stride,bg_stride;
 reg [ADDR_WIDTH-1:0] on_row_address,bg_row_address;
 reg [12:0] x0,y0;
 reg [4:0] cols;
 reg [11:0] rows,row_index;
 reg [2:0] beats,beat_index;
 reg [31:0] command_bytes,observed_bytes,watchdog,output_pixels,command_count;
 reg status_seen,last_seen;
 // At most four 128-bit words (64 bytes); a small register buffer is deliberate.
 reg [127:0] on_words[0:3];
 wire reading=state==DATA_ON||state==DATA_BG;
 wire on_command=state==CMD_ON||state==DATA_ON;
 wire [127:0] expected_header=on_command?on_header:bg_header;
 wire [2:0] remaining_lanes={1'b0,cols[1:0]}==0?3'd4:{1'b0,cols[1:0]};
 wire last_beat=beat_index+1==beats;
 wire [2:0] valid_lanes=last_beat?remaining_lanes:3'd4;
 wire [15:0] expected_keep=(17'h1<<(valid_lanes*4))-1'b1;
 wire data_handshake=read_valid&&read_ready;
 wire status_handshake=read_status_valid&&read_status_ready;
 wire cmd_handshake=read_cmd_valid&&read_cmd_ready;
 wire output_handshake=m_valid&&m_ready;
 wire [31:0] bytes_after=observed_bytes+{27'b0,valid_lanes,2'b00};
 wire [63:0] on_region_end={36'b0,cfg_on_base}+{32'b0,cfg_on_region_bytes};
 wire [63:0] bg_region_end={36'b0,cfg_bg_base}+{32'b0,cfg_bg_region_bytes};
 wire [63:0] row_end_y={51'b0,cfg_y0}+{52'b0,cfg_rows}-1'b1;
 wire [63:0] row_end_x={51'b0,cfg_x0}+{59'b0,cfg_cols};
 wire [63:0] on_start={36'b0,cfg_on_base}+{32'b0,cfg_on_stride}*{51'b0,cfg_y0}+({51'b0,cfg_x0}<<2);
 wire [63:0] bg_start={36'b0,cfg_bg_base}+{32'b0,cfg_bg_stride}*{51'b0,cfg_y0}+({51'b0,cfg_x0}<<2);
 wire [63:0] on_last_end={36'b0,cfg_on_base}+{32'b0,cfg_on_stride}*row_end_y+(row_end_x<<2);
 wire [63:0] bg_last_end={36'b0,cfg_bg_base}+{32'b0,cfg_bg_stride}*row_end_y+(row_end_x<<2);
 wire [63:0] address_limit=64'h1<<ADDR_WIDTH;
 wire bad_config=ADDR_WIDTH!=28||TIMEOUT_CYCLES<2||cancel||transport_requires_reset||
  !cfg_on_committed||!cfg_bg_committed||!cfg_on_pinned||!cfg_bg_pinned||
  cfg_epoch==0||cfg_token==0||cfg_bg_header[95:64]==0||
  cfg_on_header[127:96]==0||cfg_bg_header[127:96]==0||
  cfg_on_header[63:32]!=cfg_geometry||cfg_bg_header[63:32]!=cfg_geometry||
  cfg_on_header[31:0]!=cfg_calibration||cfg_bg_header[31:0]!=cfg_calibration||
  cfg_image_width==0||cfg_image_height==0||cfg_cols==0||cfg_cols>16||cfg_rows==0||cfg_rows>2048||
  cfg_x0[1:0]!=0||row_end_x>{51'b0,cfg_image_width}||row_end_y>={51'b0,cfg_image_height}||
  cfg_on_base[3:0]!=0||cfg_bg_base[3:0]!=0||cfg_on_stride[3:0]!=0||cfg_bg_stride[3:0]!=0||
  {32'b0,cfg_on_stride}<({51'b0,cfg_image_width}<<2)||{32'b0,cfg_bg_stride}<({51'b0,cfg_image_width}<<2)||
  cfg_on_region_bytes==0||cfg_bg_region_bytes==0||on_region_end>address_limit||bg_region_end>address_limit||
  on_last_end>on_region_end||bg_last_end>bg_region_end||
  !((on_region_end<={36'b0,cfg_bg_base})||(bg_region_end<={36'b0,cfg_on_base}));
 assign cfg_ready=rst_n&&!busy&&!tile_status_valid;
 assign fault_pending=busy&&fault_code!=0;
 // Once offered, command VALID/address persist through cancel until accepted.
 assign read_cmd_valid=state==CMD_ON||state==CMD_BG;
 assign read_cmd_address=on_command?on_row_address:bg_row_address;
 assign read_cmd_bytes=command_bytes;assign read_cmd_header=expected_header;assign read_cmd_epoch=epoch;
 assign read_ready=reading&&(fault_code!=0||state==DATA_ON||!m_valid||m_ready);
 // Drain an illegal duplicate too, but poison the tile rather than allowing a
 // stale completion to be mistaken for the following row's transaction.
 assign read_status_ready=reading;
 assign m_source_frame_id=on_header[127:96];assign m_background_frame_id=bg_header[127:96];
 assign m_background_generation=bg_header[95:64];assign m_geometry=geometry;
 assign m_calibration=calibration;assign m_epoch=epoch;assign m_token=token;
 task fail;
  input [7:0] code;
  begin if(fault_code==0)fault_code<=code;end
 endtask
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=IDLE;busy<=0;fault_code<=0;on_header<=0;bg_header<=0;epoch<=0;token<=0;
   geometry<=0;calibration<=0;on_stride<=0;bg_stride<=0;on_row_address<=0;bg_row_address<=0;
   x0<=0;y0<=0;cols<=0;rows<=0;row_index<=0;beats<=0;beat_index<=0;command_bytes<=0;
   observed_bytes<=0;watchdog<=0;output_pixels<=0;command_count<=0;status_seen<=0;last_seen<=0;
   m_valid<=0;m_on_data<=0;m_bg_data<=0;m_keep<=0;m_x<=0;m_y<=0;m_sof<=0;m_eol<=0;m_eof<=0;
   tile_status_valid<=0;tile_status_ok<=0;tile_status_error<=0;tile_status_pixels<=0;tile_status_commands<=0;
  end else begin
   if(output_handshake)begin
    m_valid<=0;output_pixels<=output_pixels+((m_keep==16'hffff)?4:(m_keep==16'h0fff)?3:(m_keep==16'h00ff)?2:1);
   end
   if(tile_status_valid&&tile_status_ready)begin tile_status_valid<=0;busy<=0;state<=IDLE;end
   if(cfg_valid&&cfg_ready)begin
    busy<=1;fault_code<=bad_config?BAD_CONFIG:0;state<=bad_config?FINISH:CMD_ON;
    on_header<=cfg_on_header;bg_header<=cfg_bg_header;epoch<=cfg_epoch;token<=cfg_token;
    geometry<=cfg_geometry;calibration<=cfg_calibration;on_stride<=cfg_on_stride;bg_stride<=cfg_bg_stride;
    on_row_address<=on_start[ADDR_WIDTH-1:0];bg_row_address<=bg_start[ADDR_WIDTH-1:0];
    x0<=cfg_x0;y0<=cfg_y0;cols<=cfg_cols;rows<=cfg_rows;row_index<=0;
    beats<=(cfg_cols+5'd3)>>2;command_bytes<={25'b0,cfg_cols,2'b00};
    beat_index<=0;observed_bytes<=0;status_seen<=0;last_seen<=0;watchdog<=0;output_pixels<=0;command_count<=0;m_valid<=0;
   end else if(busy&&!tile_status_valid)begin
    if(cmd_handshake||data_handshake||status_handshake||output_handshake)watchdog<=0;
    else if(watchdog<TIMEOUT_CYCLES)watchdog<=watchdog+1'b1;
    if(cancel)fail(CANCELLED);
    else if(transport_requires_reset)fail(TRANSPORT_FAULT);
    else if(watchdog>=TIMEOUT_CYCLES-1)fail(TIMEOUT);
    if(cmd_handshake)begin
     state<=on_command?DATA_ON:DATA_BG;command_count<=command_count+1'b1;
     beat_index<=0;observed_bytes<=0;status_seen<=0;last_seen<=0;
    end
    if(data_handshake)begin
     if(read_header!=expected_header||read_epoch!=epoch)fail(BAD_DATA_ID);
     else if(beat_index>=beats||last_seen)fail(BAD_COUNT);
     else if(read_keep!=expected_keep)fail(BAD_KEEP);
     else if(read_last!=last_beat)fail(BAD_LAST);
     else if(fault_code==0&&!cancel&&!transport_requires_reset)begin
      if(state==DATA_ON)on_words[beat_index[1:0]]<=read_data;
      else begin
       m_valid<=1;m_on_data<=on_words[beat_index[1:0]];m_bg_data<=read_data;m_keep<=read_keep;
       m_x<=x0+{8'b0,beat_index,2'b00};m_y<=y0+row_index;
       m_sof<=row_index==0&&beat_index==0;m_eol<=last_beat;m_eof<=last_beat&&row_index+1==rows;
      end
     end
     if(beat_index<7)beat_index<=beat_index+1'b1;
     observed_bytes<=bytes_after; if(read_last)last_seen<=1;
    end
    if(status_handshake)begin
     status_seen<=1;
     if(status_seen||read_status_header!=expected_header||read_status_epoch!=epoch)fail(BAD_STATUS_ID);
     else if(!read_status_ok||read_status_error!=0||read_status_bytes!=command_bytes)fail(BAD_STATUS);
    end
    if(reading&&status_seen&&!transport_busy&&!m_valid&&!read_valid)begin
     if(fault_code!=0||cancel||transport_requires_reset||watchdog>=TIMEOUT_CYCLES-1)state<=FINISH;
     else if(observed_bytes!=command_bytes||beat_index!=beats||!last_seen)begin fail(BAD_COUNT);state<=FINISH;end
     else if(state==DATA_ON)state<=CMD_BG;
     else if(row_index+1==rows)state<=FINISH;
     else begin
      row_index<=row_index+1'b1;on_row_address<=on_row_address+on_stride;bg_row_address<=bg_row_address+bg_stride;state<=CMD_ON;
     end
    end
    if(state==FINISH&&!m_valid)begin
     tile_status_valid<=1;
     tile_status_ok<=fault_code==0&&!cancel&&!transport_requires_reset&&output_pixels==cols*rows&&command_count==rows*2;
     tile_status_error<=fault_code!=0?fault_code:cancel?CANCELLED:transport_requires_reset?TRANSPORT_FAULT:
      (output_pixels!=cols*rows||command_count!=rows*2)?BAD_COUNT:0;
     tile_status_pixels<=output_pixels;tile_status_commands<=command_count;
    end
   end
  end
 end
endmodule
