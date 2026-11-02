`timescale 1ns/1ps
// Derived explicit-role allocator: OFF=0, A=1, B=2; AB rejected.
// ALLOWED_ROLES 0001=OFF-only, 0110=LIVE A/B; every sample matches the latched role.
// Metadata/ownership manager only. All ports use clk; no CDC or pixel storage.
// One complete contiguous ROI is one write-mover command. A successful DDR
// write alone NEVER commits a background: independent accepted-pixel framing,
// counts AND physical source-frame completion must pass. ROI EOF is not EOF
// of the physical camera frame. Readers pin slots until a matching release.
module afc03_role_frame_slots #(
    parameter [3:0] ALLOWED_ROLES=4'b0001,
    parameter ADDR_WIDTH=28,
    parameter [ADDR_WIDTH-1:0] SLOT0_BASE=28'h0100000,
    parameter [ADDR_WIDTH-1:0] SLOT1_BASE=28'h0900000,
    parameter SLOT_BYTES=8388608,
    parameter MAX_READERS=65535,
    parameter TIMEOUT_CYCLES=100000000
)(
    input wire clk,rst_n,
    input wire [31:0] config_epoch,config_geometry,config_calibration,
    input wire memory_invalidated,
    input wire begin_valid,output wire begin_ready,
    input wire [31:0] begin_frame_id,
    input wire [12:0] begin_roi_width,begin_roi_height,
    input wire [31:0] begin_expected_pixels,begin_expected_bytes,
    input wire [1:0] begin_role,
    input wire cancel_update,
    // Observer of pixels actually accepted by the write-stream frontend.
    input wire sample_valid,input wire [2:0] sample_pixels,
    input wire [4:0] sample_bytes,input wire sample_sof,sample_eof,
    input wire [31:0] sample_frame_id,input wire [1:0] sample_lasers,
    input wire [7:0] sample_error,
    // Direct descriptor handshake to afc03_axi_burst_mover (cmd_write=1).
    output wire write_cmd_valid,input wire write_cmd_ready,
    output wire [ADDR_WIDTH-1:0] write_cmd_address,
    output wire [31:0] write_cmd_bytes,output wire [127:0] write_cmd_header,
    output wire [31:0] write_cmd_epoch,
    input wire write_status_valid,output wire write_status_ready,
    input wire write_status_ok,input wire [7:0] write_status_error,
    input wire [31:0] write_status_bytes,input wire [127:0] write_status_header,
    input wire [31:0] write_status_epoch,
    // Final physical camera-frame confirmation, joined by the capture owner
    // to this exact write transaction header. Never tie to unconditional OK.
    input wire source_frame_status_valid,output wire source_frame_status_ready,
    input wire source_frame_status_complete,source_frame_status_ok,
    input wire [7:0] source_frame_status_error,
    input wire [31:0] source_frame_status_frame_id,
    input wire [127:0] source_frame_status_header,
    input wire [31:0] source_frame_status_epoch,
    // Must describe ALL pending writes, including a timed-out mover draining.
    input wire writer_quiescent,output wire writer_abort,
    output reg update_busy,
    output reg update_event_valid,input wire update_event_ready,
    output reg update_event_ok,output reg [7:0] update_event_error,
    output reg [127:0] update_event_header,output reg [31:0] update_event_epoch,
    output wire active_valid,output reg active_slot,
    output wire [127:0] active_header,output wire [31:0] active_epoch,
    output wire [31:0] active_pixels,active_bytes,
    output reg invalidate_readers,
    input wire acquire_valid,output wire acquire_ready,
    output reg grant_valid,output reg grant_slot,
    output reg [ADDR_WIDTH-1:0] grant_address,
    output reg [127:0] grant_header,output reg [31:0] grant_epoch,
    output reg [31:0] grant_pixels,grant_bytes,
    input wire release_valid,input wire release_slot,
    input wire [127:0] release_header,input wire [31:0] release_epoch,
    output reg release_ok,output reg protocol_error,
    output wire blocked_by_readers,
    output wire [1:0] active_role,output reg [1:0] grant_role
);
    reg [1:0] transaction_role,slot_role[0:1];
    assign active_role=slot_role[active_slot];
    // Role accompanies the same slot generation; it cannot be relabelled by
    // a new request while a reader still holds the old slot.
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)begin transaction_role<=0;slot_role[0]<=0;slot_role[1]<=0;grant_role<=0;end
        else begin
            if(begin_valid&&begin_ready&&!descriptor_bad)begin
                transaction_role<=begin_role;slot_role[choose_slot]<=begin_role;
            end
            if(acquire)grant_role<=slot_role[active_slot];
        end
    end
    localparam BAD_DESCRIPTOR=1,BAD_SAMPLE=2,BAD_FRAMING=3,COUNT_MISMATCH=4,
        DDR_FAILED=5,DDR_IDENTITY=6,CANCELLED=7,CONFIG_CHANGED=8,
        MEMORY_INVALIDATED=9,UPDATE_TIMEOUT=10,SOURCE_FAILED=11,SOURCE_IDENTITY=12;
    reg [31:0] saved_epoch,saved_geometry,saved_calibration,generation;
    reg [1:0] slot_valid;
    reg [127:0] slot_header[0:1];
    reg [31:0] slot_epoch[0:1],slot_pixels[0:1],slot_bytes[0:1];
    reg [15:0] references[0:1];
    reg staging,failed,frame_complete,write_complete,source_complete,source_seen,seen_sof,seen_eof;
    reg command_pending,command_issued;
    reg [31:0] expected_pixels,expected_bytes,observed_pixels,observed_bytes;
    reg [31:0] transaction_frame,transaction_epoch,watchdog;
    reg [127:0] transaction_header;
    wire configuration_changed=(config_epoch!=saved_epoch)||
        (config_geometry!=saved_geometry)||(config_calibration!=saved_calibration);
    assign active_header=slot_header[active_slot];
    assign active_epoch=slot_epoch[active_slot];
    assign active_pixels=slot_pixels[active_slot];
    assign active_bytes=slot_bytes[active_slot];
    assign active_valid=slot_valid[active_slot] && !memory_invalidated &&
        !configuration_changed && slot_epoch[active_slot]==config_epoch &&
        slot_header[active_slot][63:32]==config_geometry &&
        slot_header[active_slot][31:0]==config_calibration;
    wire choose_slot=active_valid ? !active_slot : (references[0]!=0);
    wire slot_available=active_valid ? references[!active_slot]==0 :
                         references[0]==0 || references[1]==0;
    assign blocked_by_readers=!slot_available;
    wire [25:0] rectangle_pixels=begin_roi_width*begin_roi_height;
    wire [33:0] requested_pixel_bytes={2'b0,begin_expected_pixels}<<2;
    wire [32:0] chosen_end=(choose_slot?SLOT1_BASE:SLOT0_BASE)+{1'b0,begin_expected_bytes};
    wire [32:0] slot0_end={1'b0,SLOT0_BASE}+SLOT_BYTES;
    wire [32:0] slot1_end={1'b0,SLOT1_BASE}+SLOT_BYTES;
    wire layout_bad=SLOT_BYTES<=0 || (SLOT_BYTES%16)!=0 ||
        SLOT0_BASE[3:0]!=0 || SLOT1_BASE[3:0]!=0 ||
        slot0_end>(33'd1<<ADDR_WIDTH) || slot1_end>(33'd1<<ADDR_WIDTH) ||
        ((SLOT0_BASE<SLOT1_BASE)?slot0_end>SLOT1_BASE:slot1_end>SLOT0_BASE);
    wire descriptor_bad=layout_bad || (ALLOWED_ROLES!=4'b0001&&ALLOWED_ROLES!=4'b0110) || !ALLOWED_ROLES[begin_role] || begin_role==3 || begin_roi_width==0 || begin_roi_height==0 ||
        begin_expected_pixels==0 || begin_expected_bytes==0 ||
        begin_expected_pixels!={6'b0,rectangle_pixels} ||
        requested_pixel_bytes!={2'b0,begin_expected_bytes} ||
        begin_expected_bytes>SLOT_BYTES || chosen_end>(33'd1<<ADDR_WIDTH) ||
        generation==32'hffffffff;
    wire resources_ready=!update_busy&&!update_event_valid&&slot_available&&
        writer_quiescent&&!configuration_changed&&!memory_invalidated;
    wire [127:0] candidate_header={begin_frame_id,generation+32'd1,config_geometry,config_calibration};
    assign begin_ready=rst_n&&resources_ready;
    // Register the descriptor before offering it. Configuration changes and
    // cancellations must not withdraw/change a VALID command under backpressure.
    assign write_cmd_valid=rst_n&&command_pending;
    assign write_cmd_address=staging?SLOT1_BASE:SLOT0_BASE;
    assign write_cmd_bytes=expected_bytes;
    assign write_cmd_header=transaction_header;
    assign write_cmd_epoch=transaction_epoch;
    assign write_status_ready=1'b1;
    assign source_frame_status_ready=1'b1;
    assign writer_abort=update_busy&&failed;
    assign acquire_ready=rst_n&&active_valid&&references[active_slot]<MAX_READERS;
    wire acquire=acquire_valid&&acquire_ready;
    wire release_good=release_valid&&references[release_slot]!=0&&
        release_header==slot_header[release_slot]&&release_epoch==slot_epoch[release_slot];
    wire [32:0] next_pixels={1'b0,observed_pixels}+sample_pixels;
    wire [32:0] next_bytes={1'b0,observed_bytes}+sample_bytes;
    wire sample_bad=!command_issued || sample_pixels==0 || sample_pixels>4 ||
        sample_bytes!=({2'b0,sample_pixels}<<2) || sample_frame_id!=transaction_frame ||
        sample_lasers!=transaction_role || sample_error!=0;
    wire framing_bad=seen_eof || (!seen_sof&&!sample_sof) || (seen_sof&&sample_sof);
    wire counts_bad=next_pixels>{1'b0,expected_pixels} || next_bytes>{1'b0,expected_bytes} ||
        (sample_eof&&(next_pixels!={1'b0,expected_pixels}||next_bytes!={1'b0,expected_bytes}));
    wire completion_identity_bad=!command_issued || write_status_header!=transaction_header ||
        write_status_epoch!=transaction_epoch || write_complete;
    wire completion_bad=!write_status_ok || write_status_error!=0 ||
        write_status_bytes!=expected_bytes;
    wire source_identity_bad=source_seen ||
        source_frame_status_frame_id!=transaction_frame ||
        source_frame_status_header!=transaction_header ||
        source_frame_status_epoch!=transaction_epoch;
    wire source_failed=!source_frame_status_complete || !source_frame_status_ok ||
        source_frame_status_error!=0;
    wire timeout_now=update_busy&&!failed&&!sample_valid&&!write_status_valid&&!source_frame_status_valid&&
        watchdog>=TIMEOUT_CYCLES-1;
    // Commit is forbidden on a cycle carrying any new observation/error event.
    wire commit_allowed=update_busy&&!failed&&frame_complete&&write_complete&&source_complete&&writer_quiescent&&
        !sample_valid&&!write_status_valid&&!source_frame_status_valid&&!cancel_update&&!configuration_changed&&!memory_invalidated;
    integer k;
    task fail_update;
        input [7:0] code;
        begin
            if(!failed)begin
                failed<=1;update_event_valid<=1;update_event_ok<=0;update_event_error<=code;
                update_event_header<=transaction_header;update_event_epoch<=transaction_epoch;
            end
        end
    endtask
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)begin
            saved_epoch<=0;saved_geometry<=0;saved_calibration<=0;generation<=0;
            slot_valid<=0;active_slot<=0;
            staging<=0;failed<=0;frame_complete<=0;write_complete<=0;source_complete<=0;source_seen<=0;seen_sof<=0;seen_eof<=0;
            command_pending<=0;command_issued<=0;
            expected_pixels<=0;expected_bytes<=0;observed_pixels<=0;observed_bytes<=0;
            transaction_frame<=0;transaction_epoch<=0;transaction_header<=0;watchdog<=0;
            update_busy<=0;update_event_valid<=0;update_event_ok<=0;update_event_error<=0;
            update_event_header<=0;update_event_epoch<=0;invalidate_readers<=0;
            grant_valid<=0;grant_slot<=0;grant_address<=0;grant_header<=0;grant_epoch<=0;
            grant_pixels<=0;grant_bytes<=0;release_ok<=0;protocol_error<=0;
            for(k=0;k<2;k=k+1)begin
                slot_header[k]<=0;slot_epoch[k]<=0;slot_pixels[k]<=0;slot_bytes[k]<=0;references[k]<=0;
            end
        end else begin
            grant_valid<=0;release_ok<=0;invalidate_readers<=0;
            saved_epoch<=config_epoch;saved_geometry<=config_geometry;saved_calibration<=config_calibration;
            if(update_event_valid&&update_event_ready)update_event_valid<=0;
            if(write_cmd_valid&&write_cmd_ready)begin command_pending<=0;command_issued<=1;end
            if(!update_busy||sample_valid||write_status_valid||source_frame_status_valid)watchdog<=0;
            else if(!failed)watchdog<=watchdog+1'b1;
            // Configuration invalidation never clears reader ownership. Old
            // clients must release before those physical addresses are reused.
            if(configuration_changed||memory_invalidated)begin
                slot_valid<=0;invalidate_readers<=1;
            end
            if(acquire)begin
                grant_valid<=1;grant_slot<=active_slot;
                grant_address<=active_slot?SLOT1_BASE:SLOT0_BASE;
                grant_header<=slot_header[active_slot];grant_epoch<=slot_epoch[active_slot];
                grant_pixels<=slot_pixels[active_slot];grant_bytes<=slot_bytes[active_slot];
            end
            if(release_valid)begin
                if(release_good)release_ok<=1;else protocol_error<=1;
            end
            for(k=0;k<2;k=k+1)begin
                case({acquire&&(active_slot==k),release_good&&(release_slot==k)})
                    2'b10:references[k]<=references[k]+1'b1;
                    2'b01:references[k]<=references[k]-1'b1;
                    default:begin end
                endcase
            end
            if(begin_valid&&begin_ready)begin
                if(descriptor_bad)begin
                    update_event_valid<=1;update_event_ok<=0;update_event_error<=BAD_DESCRIPTOR;
                    update_event_header<=candidate_header;update_event_epoch<=config_epoch;
                end else begin
                    update_busy<=1;staging<=choose_slot;failed<=0;
                    command_pending<=1;command_issued<=0;
                    frame_complete<=0;write_complete<=0;source_complete<=0;source_seen<=0;seen_sof<=0;seen_eof<=0;
                    expected_pixels<=begin_expected_pixels;expected_bytes<=begin_expected_bytes;
                    observed_pixels<=0;observed_bytes<=0;watchdog<=0;
                    transaction_frame<=begin_frame_id;transaction_epoch<=config_epoch;
                    transaction_header<=candidate_header;generation<=generation+1'b1;
                    slot_valid[choose_slot]<=0;
                    slot_header[choose_slot]<=candidate_header;slot_epoch[choose_slot]<=config_epoch;
                    slot_pixels[choose_slot]<=begin_expected_pixels;slot_bytes[choose_slot]<=begin_expected_bytes;
                end
            end
            if(sample_valid&&!update_busy)protocol_error<=1;
            if(write_status_valid&&!update_busy)protocol_error<=1;
            if(source_frame_status_valid&&!update_busy)protocol_error<=1;
            if(update_busy)begin
                if(failed&&writer_quiescent&&!command_pending)update_busy<=0;
                if(!failed)begin
                    if(memory_invalidated)fail_update(MEMORY_INVALIDATED);
                    else if(configuration_changed)fail_update(CONFIG_CHANGED);
                    else if(cancel_update)fail_update(CANCELLED);
                    else if(timeout_now)fail_update(UPDATE_TIMEOUT);
                    else if(sample_valid&&(sample_bad||framing_bad||counts_bad))begin
                        if(sample_bad)fail_update(BAD_SAMPLE);
                        else if(framing_bad)fail_update(BAD_FRAMING);
                        else fail_update(COUNT_MISMATCH);
                    end else if(write_status_valid&&(completion_identity_bad||completion_bad))begin
                        if(completion_identity_bad)fail_update(DDR_IDENTITY);
                        else fail_update(DDR_FAILED);
                    end else if(source_frame_status_valid&&(source_identity_bad||source_failed))begin
                        if(source_identity_bad)fail_update(SOURCE_IDENTITY);
                        else fail_update(SOURCE_FAILED);
                    end else begin
                        if(sample_valid)begin
                            observed_pixels<=next_pixels[31:0];observed_bytes<=next_bytes[31:0];
                            seen_sof<=1;
                            if(sample_eof)begin seen_eof<=1;frame_complete<=1;end
                        end
                        if(write_status_valid)write_complete<=1;
                        if(source_frame_status_valid)begin source_seen<=1;source_complete<=1;end
                        if(commit_allowed)begin
                            slot_valid[staging]<=1;active_slot<=staging;update_busy<=0;
                            update_event_valid<=1;update_event_ok<=1;update_event_error<=0;
                            update_event_header<=transaction_header;update_event_epoch<=transaction_epoch;
                        end
                    end
                end
            end
        end
    end
endmodule
