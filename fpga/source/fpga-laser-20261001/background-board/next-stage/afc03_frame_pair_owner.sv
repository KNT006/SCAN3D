`timescale 1ns/1ps
// One-clock, one-pair lease owner. Acquisition/grants and matching release
// acknowledgements are REAL allocator transactions, never cfg_pinned hints.
// Neither camera capture nor the shared DDR command arbiter lives here.
module afc03_frame_pair_owner #(
 parameter ADDR_WIDTH=28, parameter TIMEOUT_CYCLES=100000000
)(
 input wire clk,rst_n,
 input wire request_valid,output wire request_ready,
 input wire [127:0] request_bg_header,request_on_header,
 input wire [31:0] request_epoch,request_token,request_geometry,request_calibration,
 input wire [1:0] request_role,
 input wire [12:0] request_image_width,request_image_height,
 input wire [31:0] request_stride,
 input wire [31:0] current_epoch,current_geometry,current_calibration,
 input wire cancel,memory_invalidated,transport_requires_reset,
 output wire busy,fault_pending,output reg recovery_required,
 output reg [7:0] error_code,output reg [15:0] pipeline_error,
 output reg bg_pinned,on_pinned,
 output wire bg_acquire_valid,input wire bg_acquire_ready,
 input wire bg_grant_valid,bg_grant_slot,bg_grant_committed,
 input wire [1:0] bg_grant_role,
 input wire [ADDR_WIDTH-1:0] bg_grant_address,
 input wire [127:0] bg_grant_header,
 input wire [31:0] bg_grant_epoch,bg_grant_pixels,bg_grant_bytes,
 output wire on_acquire_valid,input wire on_acquire_ready,
 input wire on_grant_valid,on_grant_slot,on_grant_committed,
 input wire [1:0] on_grant_role,
 input wire [ADDR_WIDTH-1:0] on_grant_address,
 input wire [127:0] on_grant_header,
 input wire [31:0] on_grant_epoch,on_grant_pixels,on_grant_bytes,
 input wire bg_protocol_error,on_protocol_error,
 output wire bg_release_valid,input wire bg_release_ready,
 output wire bg_release_slot,output wire [127:0] bg_release_header,
 output wire [31:0] bg_release_epoch,
 input wire bg_ack_valid,bg_ack_ok,bg_ack_slot,
 input wire [127:0] bg_ack_header,input wire [31:0] bg_ack_epoch,
 output wire on_release_valid,input wire on_release_ready,
 output wire on_release_slot,output wire [127:0] on_release_header,
 output wire [31:0] on_release_epoch,
 input wire on_ack_valid,on_ack_ok,on_ack_slot,
 input wire [127:0] on_ack_header,input wire [31:0] on_ack_epoch,
 // Claim/release a transaction scheduler, NOT the DDR PHY owner lock.
 // Arbiter changes owner only at these handshakes, and only when drained.
 output wire read_claim_valid,input wire read_claim_ready,
 output wire read_release_valid,input wire read_release_ready,
 output wire [31:0] read_owner_token,output reg read_exclusive,
 input wire read_port_drained,downstream_drained,
 output wire session_valid,input wire session_ready,
 output wire session_cancel,
 output wire [ADDR_WIDTH-1:0] session_bg_base,session_on_base,
 output wire [31:0] session_bg_bytes,session_on_bytes,
 output wire [127:0] session_bg_header,session_on_header,
 output wire [31:0] session_epoch,session_token,session_geometry,session_calibration,
 output wire [1:0] session_role,
 output wire [12:0] session_image_width,session_image_height,
 output wire [31:0] session_stride,
 input wire session_progress,
 input wire session_done_valid,output wire session_done_ready,
 input wire session_done_ok,input wire [15:0] session_done_error,
 input wire [127:0] session_done_bg_header,session_done_on_header,
 input wire [31:0] session_done_epoch,session_done_token,
 output reg event_valid,input wire event_ready,
 output reg event_ok,output reg [7:0] event_error,
 output reg [15:0] event_pipeline_error,
 output reg [31:0] event_epoch,event_token
);
 localparam IDLE=0,BG_REQ=1,BG_WAIT=2,ON_REQ=3,ON_WAIT=4,
  CLAIM=5,OFFER=6,RUN=7,DRAIN=8,PORT_RELEASE=9,
  ON_RELEASE=10,ON_ACK=11,BG_RELEASE=12,BG_ACK=13,FINISH=14,HOLD=15;
 localparam BAD_REQUEST=1,BAD_BG=2,BAD_ON=3,CANCELLED=4,
  CONFIG_CHANGED=5,MEMORY_INVALID=6,TRANSPORT_FAULT=7,
  PIPELINE_FAILED=8,DONE_IDENTITY=9,RELEASE_IDENTITY=10,
  TIMEOUT=11,POOL_PROTOCOL=12,ORPHAN_RESPONSE=13;
 reg [3:0] state;
 reg [127:0] expected_bg,expected_on,bg_header,on_header;
 reg [31:0] epoch,token,geometry,calibration,stride;
 reg [12:0] image_width,image_height;
 reg [1:0] role;
 reg [ADDR_WIDTH-1:0] bg_base,on_base;
 reg [31:0] bg_bytes,on_bytes,bg_epoch,on_epoch;
 reg bg_slot,on_slot,session_finished,session_success;
 reg [31:0] watchdog;
 wire cfg_changed=current_epoch!=epoch||current_geometry!=geometry||current_calibration!=calibration;
 wire [7:0] immediate_error=memory_invalidated?MEMORY_INVALID:
  cfg_changed?CONFIG_CHANGED:transport_requires_reset?TRANSPORT_FAULT:
  (bg_protocol_error||on_protocol_error)?POOL_PROTOCOL:cancel?CANCELLED:0;
 wire bad_now=error_code!=0||immediate_error!=0;
 wire [25:0] expected_pixels=image_width*image_height;
 wire [31:0] expected_bytes={6'b0,expected_pixels}<<2;
 wire [63:0] requested_pixels={51'b0,request_image_width}*{51'b0,request_image_height};
 wire request_bad=ADDR_WIDTH!=28||TIMEOUT_CYCLES<2||request_epoch==0||request_token==0||
  (request_role!=1&&request_role!=2)||request_image_width==0||request_image_height==0||
  request_image_width[1:0]!=0||request_stride!=({19'b0,request_image_width}<<2)||
  requested_pixels*4>32'hffffffff||
  request_bg_header[127:96]==0||request_on_header[127:96]==0||
  request_bg_header[127:96]==request_on_header[127:96]||
  request_bg_header[95:64]==0||request_on_header[95:64]==0||
  request_bg_header[63:32]!=request_geometry||request_on_header[63:32]!=request_geometry||
  request_bg_header[31:0]!=request_calibration||request_on_header[31:0]!=request_calibration||
  request_epoch!=current_epoch||request_geometry!=current_geometry||request_calibration!=current_calibration||
  memory_invalidated||transport_requires_reset||cancel||bg_protocol_error||on_protocol_error;
 wire bg_bad=!bg_grant_committed||bg_grant_role!=0||bg_grant_header!=expected_bg||
  bg_grant_epoch!=epoch||bg_grant_pixels!={6'b0,expected_pixels}||bg_grant_bytes!=expected_bytes||
  bg_grant_address[3:0]!=0||({36'b0,bg_grant_address}+bg_grant_bytes)>(64'd1<<ADDR_WIDTH);
 wire [63:0] bg_end={36'b0,bg_base}+bg_bytes;
 wire [63:0] on_end={36'b0,on_grant_address}+on_grant_bytes;
 wire on_bad=!on_grant_committed||on_grant_role!=role||on_grant_header!=expected_on||
  on_grant_epoch!=epoch||on_grant_pixels!={6'b0,expected_pixels}||on_grant_bytes!=expected_bytes||
  on_grant_address[3:0]!=0||on_end>(64'd1<<ADDR_WIDTH)||
  !(bg_end<={36'b0,on_grant_address}||on_end<={36'b0,bg_base});
 wire bg_ack_match=bg_ack_ok&&bg_ack_slot==bg_slot&&bg_ack_header==bg_header&&bg_ack_epoch==bg_epoch;
 wire on_ack_match=on_ack_ok&&on_ack_slot==on_slot&&on_ack_header==on_header&&on_ack_epoch==on_epoch;
 wire done_match=session_done_epoch==epoch&&session_done_token==token&&
  session_done_bg_header==bg_header&&session_done_on_header==on_header;
 wire progress=(state==RUN&&session_progress)||
  (bg_acquire_valid&&bg_acquire_ready)||bg_grant_valid||
  (on_acquire_valid&&on_acquire_ready)||on_grant_valid||
  (read_claim_valid&&read_claim_ready)||(session_valid&&session_ready)||
  (session_done_valid&&session_done_ready)||(read_release_valid&&read_release_ready)||
  (bg_release_valid&&bg_release_ready)||bg_ack_valid||
  (on_release_valid&&on_release_ready)||on_ack_valid;
 wire timeout_now=busy&&!event_valid&&state!=HOLD&&!progress&&watchdog>=TIMEOUT_CYCLES-1;
 wire terminal_response=state==FINISH||event_valid;
 wire orphan_response=(bg_grant_valid&&!(state==BG_WAIT||(state==BG_REQ&&bg_acquire_ready)))||
  (on_grant_valid&&!(state==ON_WAIT||(state==ON_REQ&&on_acquire_ready)))||
  (bg_ack_valid&&!(state==BG_ACK||(state==BG_RELEASE&&bg_release_ready)))||
  (on_ack_valid&&!(state==ON_ACK||(state==ON_RELEASE&&on_release_ready)));
 assign request_ready=rst_n&&state==IDLE&&!event_valid&&!recovery_required;
 assign busy=state!=IDLE;
 assign fault_pending=busy&&(bad_now||recovery_required);
 assign bg_acquire_valid=state==BG_REQ;
 assign on_acquire_valid=state==ON_REQ;
 assign bg_release_valid=state==BG_RELEASE;
 assign on_release_valid=state==ON_RELEASE;
 assign bg_release_slot=bg_slot;assign bg_release_header=bg_header;assign bg_release_epoch=bg_epoch;
 assign on_release_slot=on_slot;assign on_release_header=on_header;assign on_release_epoch=on_epoch;
 assign read_claim_valid=state==CLAIM;
 assign read_release_valid=state==PORT_RELEASE;
 assign read_owner_token=token;
 assign session_valid=state==OFFER;
 assign session_done_ready=state==RUN;
 assign session_cancel=busy&&bad_now;
 assign session_bg_base=bg_base;assign session_on_base=on_base;
 assign session_bg_bytes=bg_bytes;assign session_on_bytes=on_bytes;
 assign session_bg_header=bg_header;assign session_on_header=on_header;
 assign session_epoch=epoch;assign session_token=token;
 assign session_geometry=geometry;assign session_calibration=calibration;
 assign session_role=role;assign session_image_width=image_width;
 assign session_image_height=image_height;assign session_stride=stride;
 task fail;
  input [7:0] code;
  begin if(error_code==0)error_code<=code;end
 endtask
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=IDLE;expected_bg<=0;expected_on<=0;bg_header<=0;on_header<=0;
   epoch<=0;token<=0;geometry<=0;calibration<=0;stride<=0;image_width<=0;image_height<=0;role<=0;
   bg_base<=0;on_base<=0;bg_bytes<=0;on_bytes<=0;bg_epoch<=0;on_epoch<=0;bg_slot<=0;on_slot<=0;
   bg_pinned<=0;on_pinned<=0;read_exclusive<=0;session_finished<=0;session_success<=0;
   recovery_required<=0;error_code<=0;pipeline_error<=0;watchdog<=0;
   event_valid<=0;event_ok<=0;event_error<=0;event_pipeline_error<=0;event_epoch<=0;event_token<=0;
  end else begin
   if(!busy||progress)watchdog<=0;
   else if(watchdog<TIMEOUT_CYCLES)watchdog<=watchdog+1'b1;
   if(busy&&!terminal_response&&immediate_error!=0)fail(immediate_error);
   if(timeout_now)begin fail(TIMEOUT);recovery_required<=1;end
   if(event_valid&&event_ready)begin event_valid<=0;state<=IDLE;end
   case(state)
    IDLE:if(request_valid&&request_ready)begin
     expected_bg<=request_bg_header;expected_on<=request_on_header;
     epoch<=request_epoch;token<=request_token;geometry<=request_geometry;calibration<=request_calibration;
     role<=request_role;image_width<=request_image_width;image_height<=request_image_height;stride<=request_stride;
     session_finished<=0;session_success<=0;pipeline_error<=0;watchdog<=0;
     error_code<=request_bad?BAD_REQUEST:0;state<=request_bad?FINISH:BG_REQ;
    end
    BG_REQ:if(bg_acquire_ready)begin
     state<=BG_WAIT;
     if(bg_grant_valid)begin
      bg_pinned<=1;bg_slot<=bg_grant_slot;bg_header<=bg_grant_header;bg_epoch<=bg_grant_epoch;
      bg_base<=bg_grant_address;bg_bytes<=bg_grant_bytes;
      if(bg_bad)fail(BAD_BG);
      state<=bad_now||bg_bad||timeout_now?DRAIN:ON_REQ;
     end
    end
    BG_WAIT:if(bg_grant_valid)begin
     bg_pinned<=1;bg_slot<=bg_grant_slot;bg_header<=bg_grant_header;bg_epoch<=bg_grant_epoch;
     bg_base<=bg_grant_address;bg_bytes<=bg_grant_bytes;
     if(bg_bad)fail(BAD_BG);
     state<=bad_now||bg_bad||timeout_now?DRAIN:ON_REQ;
    end
    ON_REQ:if(on_acquire_ready)begin
     state<=ON_WAIT;
     if(on_grant_valid)begin
      on_pinned<=1;on_slot<=on_grant_slot;on_header<=on_grant_header;on_epoch<=on_grant_epoch;
      on_base<=on_grant_address;on_bytes<=on_grant_bytes;
      if(on_bad)fail(BAD_ON);
      state<=bad_now||on_bad||timeout_now?DRAIN:CLAIM;
     end
    end
    ON_WAIT:if(on_grant_valid)begin
     on_pinned<=1;on_slot<=on_grant_slot;on_header<=on_grant_header;on_epoch<=on_grant_epoch;
     on_base<=on_grant_address;on_bytes<=on_grant_bytes;
     if(on_bad)fail(BAD_ON);
     state<=bad_now||on_bad||timeout_now?DRAIN:CLAIM;
    end
    CLAIM:if(read_claim_ready)begin
     read_exclusive<=1;state<=bad_now||timeout_now?DRAIN:OFFER;
    end
    // Cancel cannot retract an already offered session. The consumer accepts
    // it with session_cancel high and returns a failed completion after drain.
    OFFER:if(session_ready)state<=RUN;
    RUN:if(session_done_valid)begin
     session_finished<=1;
     session_success<=session_done_ok&&session_done_error==0&&done_match&&!bad_now;
     pipeline_error<=session_done_error;
     if(!done_match)fail(DONE_IDENTITY);
     else if(!session_done_ok||session_done_error!=0)fail(PIPELINE_FAILED);
     state<=DRAIN;
    end
    DRAIN:if(read_port_drained&&downstream_drained)begin
     if(read_exclusive)state<=PORT_RELEASE;
     else if(on_pinned)state<=ON_RELEASE;
     else if(bg_pinned)state<=BG_RELEASE;
     else state<=FINISH;
    end
    PORT_RELEASE:if(read_release_ready)begin
     read_exclusive<=0;
     state<=on_pinned?ON_RELEASE:bg_pinned?BG_RELEASE:FINISH;
    end
    ON_RELEASE:if(on_release_ready)begin
     state<=ON_ACK;
     if(on_ack_valid)begin
      if(on_ack_match)begin on_pinned<=0;state<=bg_pinned?BG_RELEASE:FINISH;end
      else begin fail(RELEASE_IDENTITY);recovery_required<=1;state<=HOLD;end
     end
    end
    ON_ACK:if(on_ack_valid)begin
     if(on_ack_match)begin on_pinned<=0;state<=bg_pinned?BG_RELEASE:FINISH;end
     else begin fail(RELEASE_IDENTITY);recovery_required<=1;state<=HOLD;end
    end
    BG_RELEASE:if(bg_release_ready)begin
     state<=BG_ACK;
     if(bg_ack_valid)begin
      if(bg_ack_match)begin bg_pinned<=0;state<=FINISH;end
      else begin fail(RELEASE_IDENTITY);recovery_required<=1;state<=HOLD;end
     end
    end
    BG_ACK:if(bg_ack_valid)begin
     if(bg_ack_match)begin bg_pinned<=0;state<=FINISH;end
     else begin fail(RELEASE_IDENTITY);recovery_required<=1;state<=HOLD;end
    end
    FINISH:if(!event_valid&&!orphan_response)begin
     event_valid<=1;event_ok<=session_finished&&session_success&&!bad_now&&!recovery_required;
     event_error<=error_code!=0?error_code:immediate_error;
     event_pipeline_error<=pipeline_error;event_epoch<=epoch;event_token<=token;
    end
    HOLD:begin end
    default:begin recovery_required<=1;state<=HOLD;end
   endcase
   // An unpaired grant/ack is evidence of a lost ownership transaction. Never
   // guess its lease or clear pins. A common allocator/mover reset is needed.
   if(orphan_response)begin
    fail(ORPHAN_RESPONSE);recovery_required<=1;state<=HOLD;
   end
  end
 end
endmodule
