`timescale 1ns/1ps
// Single-clock frame sequencer. Caller must obtain real frame pins and a read
// port claim before cfg. Records are SPECULATIVE until a successful done.
// This is not a production DMA frame header/footer formatter.
module afc03_frame_tile_sequencer #(
 parameter MAX_HEIGHT=2048
)(
 input wire clk,rst_n,cancel,memory_invalidated,
 input wire cfg_valid,output wire cfg_ready,
 input wire [12:0] cfg_width,cfg_height,cfg_x0,cfg_x1,cfg_y0,
 input wire [11:0] cfg_rows,cfg_roi_left,cfg_roi_right,
 input wire [127:0] cfg_on_header,cfg_bg_header,
 input wire [31:0] cfg_epoch,cfg_token,cfg_geometry,cfg_calibration,
 input wire transport_busy,transport_requires_reset,
 output wire tile_cfg_valid,input wire tile_cfg_ready,
 output reg [12:0] tile_width,tile_height,tile_x0,tile_y0,
 output reg [4:0] tile_cols,
 output reg [11:0] tile_rows,tile_roi_left,tile_roi_right,
 output reg [127:0] on_header,bg_header,
 output reg [31:0] epoch,token,geometry,calibration,
 output wire tile_cancel,
 input wire tile_record_valid,output wire tile_record_ready,
 input wire [127:0] tile_record_data,input wire [7:0] tile_record_type,
 input wire tile_status_valid,output wire tile_status_ready,
 input wire tile_status_ok,input wire [15:0] tile_status_error,
 input wire [31:0] tile_status_rows,tile_status_records,tile_status_centers,
 input wire [31:0] tile_status_frame,tile_status_background_frame,
 input wire [31:0] tile_status_generation,tile_status_epoch,tile_status_token,
 input wire [31:0] tile_status_geometry,tile_status_calibration,
 output reg record_valid,input wire record_ready,
 output reg [127:0] record_data,output reg [7:0] record_type,
 output reg done_valid,input wire done_ready,
 output reg done_ok,output reg [15:0] done_error,
 output reg [31:0] done_rows,done_records,done_centers,done_crc32,
 output wire busy,output wire downstream_drained
);
 localparam IDLE=0,OFFER=1,RUN=2,CHECK=3,FINISH=4,REPORT=5;
 localparam [15:0] E_CONFIG=1,E_CANCEL=2,E_MEMORY=4,E_TRANSPORT=8,
  E_TILE=16,E_IDENTITY=32,E_COUNT=64,E_RECORD=128;
 reg [2:0] state;
 reg [15:0] errors;
 reg [12:0] end_x,next_row;
 reg [1:0] centers_in_row;
 reg [31:0] rows_count,records_count,centers_count;
 reg [31:0] part_rows,part_records,part_centers;
 reg [31:0] reported_rows,reported_records,reported_centers;
 reg crc_busy;reg [4:0] crc_index;reg [127:0] crc_payload;
 reg [31:0] crc;
 wire active=state!=IDLE&&state!=REPORT;
 wire abort_now=cancel||memory_invalidated||transport_requires_reset;
 assign cfg_ready=state==IDLE&&!done_valid;
 assign busy=state!=IDLE;
 assign tile_cfg_valid=state==OFFER;
 // A previously offered cfg/record is never withdrawn by cancellation.
 assign tile_cancel=active&&(abort_now||errors!=0);
 assign tile_record_ready=(state==RUN||state==OFFER)&&!record_valid&&!crc_busy;
 assign tile_status_ready=state==RUN;
 assign downstream_drained=!record_valid&&!crc_busy&&(state==IDLE||state==REPORT);
 wire [13:0] requested_end_y={1'b0,cfg_y0}+{2'b0,cfg_rows};
 wire bad_config=cfg_width==0||cfg_height==0||cfg_x0>=cfg_x1||cfg_x1>cfg_width||
  cfg_x0[1:0]!=0||cfg_rows<3||cfg_rows>MAX_HEIGHT||requested_end_y>cfg_height||
  cfg_roi_left>=cfg_roi_right||cfg_roi_right>=cfg_rows||
  cfg_epoch==0||cfg_token==0||cfg_geometry==0||cfg_calibration==0||
  cfg_on_header[127:96]==0||cfg_bg_header[127:96]==0||cfg_bg_header[95:64]==0||
  cfg_on_header[63:32]!=cfg_geometry||cfg_bg_header[63:32]!=cfg_geometry||
  cfg_on_header[31:0]!=cfg_calibration||cfg_bg_header[31:0]!=cfg_calibration;
 wire status_identity_bad=tile_status_frame!=on_header[127:96]||
  tile_status_background_frame!=bg_header[127:96]||tile_status_generation!=bg_header[95:64]||
  tile_status_epoch!=epoch||tile_status_token!=token||
  tile_status_geometry!=geometry||tile_status_calibration!=calibration;
 wire [12:0] record_row=record_data[28:16];
 wire row_id_bad=record_data[31:29]!=0||record_row!=next_row;
 wire center_bad=record_type!=1||record_data[7:0]!=1||row_id_bad||
  centers_in_row>=2||record_data[15:8]!={6'd0,centers_in_row}||
  record_data[87:64]==0||record_data[115:104]>record_data[127:116]||
  record_data[127:116]>=tile_rows;
 wire rowdone_bad=record_type!=2||record_data[7:0]!=2||row_id_bad||
  record_data[15:9]!=0||record_data[39:32]!={6'd0,centers_in_row}||
  record_data[63:40]!=0||record_data[127:96]!=0;
 wire record_bad=(record_type==1)?center_bad:(record_type==2)?rowdone_bad:1'b1;
 function [31:0] crc_byte;
  input [31:0] c;input [7:0] b;
  reg [31:0] v;integer k;
  begin
   v=c^{24'd0,b};
   for(k=0;k<8;k=k+1)v=v[0]?(v>>1)^32'hedb88320:(v>>1);
   crc_byte=v;
  end
 endfunction
 wire pop=record_valid&&record_ready;
 wire [31:0] crc_next=crc_byte(crc,crc_payload[7:0]);
 wire count_bad=reported_rows!={27'd0,tile_cols}||reported_rows!=part_rows||
  reported_records!=part_records||reported_centers!=part_centers||
  part_records!=part_rows+part_centers||centers_in_row!=0||
  next_row!=tile_x0+tile_cols;
 wire [12:0] advanced_x=tile_x0+tile_cols;
 wire [12:0] remaining_x=end_x-advanced_x;
 wire [15:0] async_errors=(cancel?E_CANCEL:16'd0)|
  (memory_invalidated?E_MEMORY:16'd0)|(transport_requires_reset?E_TRANSPORT:16'd0);
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=IDLE;errors<=0;end_x<=0;next_row<=0;centers_in_row<=0;
   tile_width<=0;tile_height<=0;tile_x0<=0;tile_y0<=0;tile_cols<=0;
   tile_rows<=0;tile_roi_left<=0;tile_roi_right<=0;
   on_header<=0;bg_header<=0;epoch<=0;token<=0;geometry<=0;calibration<=0;
   rows_count<=0;records_count<=0;centers_count<=0;
   part_rows<=0;part_records<=0;part_centers<=0;
   reported_rows<=0;reported_records<=0;reported_centers<=0;
   record_valid<=0;record_data<=0;record_type<=0;
   done_valid<=0;done_ok<=0;done_error<=0;done_rows<=0;done_records<=0;done_centers<=0;done_crc32<=0;
   crc_busy<=0;crc_index<=0;crc_payload<=0;crc<=32'hffffffff;
  end else begin
   if(active)errors<=errors|async_errors;
   if(tile_record_valid&&tile_record_ready)begin
    record_valid<=1;record_data<=tile_record_data;record_type<=tile_record_type;
    if(state!=RUN)errors<=errors|async_errors|E_RECORD;
   end
   if(pop)begin
    record_valid<=0;crc_payload<=record_data;crc_busy<=1;crc_index<=0;
    records_count<=records_count+1'b1;part_records<=part_records+1'b1;
    if(record_type==1)begin
     centers_in_row<=centers_in_row+1'b1;centers_count<=centers_count+1'b1;part_centers<=part_centers+1'b1;
    end else if(record_type==2)begin
     centers_in_row<=0;next_row<=next_row+1'b1;rows_count<=rows_count+1'b1;part_rows<=part_rows+1'b1;
    end
    if(record_bad)errors<=errors|async_errors|E_RECORD;
   end
   if(crc_busy)begin
    crc<=crc_next;crc_payload<=crc_payload>>8;
    if(crc_index==15)crc_busy<=0;else crc_index<=crc_index+1'b1;
   end
   case(state)
    IDLE:if(cfg_valid&&cfg_ready)begin
     tile_width<=cfg_width;tile_height<=cfg_height;tile_x0<=cfg_x0;end_x<=cfg_x1;tile_y0<=cfg_y0;
     tile_cols<=(cfg_x1-cfg_x0>16)?5'd16:cfg_x1-cfg_x0;
     tile_rows<=cfg_rows;tile_roi_left<=cfg_roi_left;tile_roi_right<=cfg_roi_right;
     on_header<=cfg_on_header;bg_header<=cfg_bg_header;
     epoch<=cfg_epoch;token<=cfg_token;geometry<=cfg_geometry;calibration<=cfg_calibration;
     next_row<=cfg_x0;centers_in_row<=0;rows_count<=0;records_count<=0;centers_count<=0;
     part_rows<=0;part_records<=0;part_centers<=0;crc<=32'hffffffff;
     errors<=(bad_config?E_CONFIG:16'd0)|async_errors|(transport_busy?E_TRANSPORT:16'd0);
     state<=(bad_config||abort_now||transport_busy)?FINISH:OFFER;
    end
    OFFER:if(tile_cfg_valid&&tile_cfg_ready)state<=RUN;
    RUN:if(tile_status_valid&&tile_status_ready)begin
     reported_rows<=tile_status_rows;reported_records<=tile_status_records;reported_centers<=tile_status_centers;
     errors<=errors|async_errors|((!tile_status_ok||tile_status_error!=0)?E_TILE:16'd0)|
       (status_identity_bad?E_IDENTITY:16'd0)|((pop&&record_bad)?E_RECORD:16'd0);
     state<=CHECK;
    end
    CHECK:if(!record_valid&&!crc_busy&&!transport_busy)begin
     if(errors!=0||abort_now||count_bad)begin
      errors<=errors|async_errors|(count_bad?E_COUNT:16'd0);state<=FINISH;
     end else if(advanced_x==end_x)state<=FINISH;
     else begin
      tile_x0<=advanced_x;tile_cols<=(remaining_x>16)?5'd16:remaining_x;
      part_rows<=0;part_records<=0;part_centers<=0;state<=OFFER;
     end
    end
    FINISH:if(!record_valid&&!crc_busy&&!transport_busy)begin
     done_valid<=1;done_ok<=errors==0&&!abort_now;done_error<=errors|async_errors;
     done_rows<=rows_count;done_records<=records_count;done_centers<=centers_count;done_crc32<=~crc;
     state<=REPORT;
    end
    REPORT:if(done_valid&&done_ready)begin done_valid<=0;state<=IDLE;end
    default:state<=IDLE;
   endcase
  end
 end
endmodule
