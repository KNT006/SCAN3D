`timescale 1ns/1ps
// Paired RGB/background stream stage. Four {8'h00,R,G,B} pixels per beat.
// One registered elastic output; only advance on valid && ready.
// Error beats retain metadata but have keep=0 and zero numerical payload.
// The consumer MUST commit a frame only after an error-free EOF: a later fault
// cannot retract earlier beats. No DDR access or AXI scheduling lives here.
module afc03_rgb_background_diff (
    input wire clk, rst_n,
    input wire s_valid,
    output wire s_ready,
    input wire [127:0] s_on, s_background,
    input wire [3:0] s_keep, s_background_keep,
    input wire s_sof, s_eol, s_eof,
    input wire [31:0] s_frame_id,
    input wire [31:0] s_expected_background_frame,
    input wire [31:0] s_expected_background_generation,
    input wire [31:0] s_geometry,
    input wire [31:0] s_background_frame,
    input wire [31:0] s_background_generation,
    input wire [31:0] s_background_geometry,
    input wire s_background_committed,
    input wire [12:0] s_x, s_y, s_background_x, s_background_y,
    input wire [12:0] s_width, s_height,
    input wire [12:0] s_background_width, s_background_height,
    input wire [7:0] s_upstream_error,
    output reg m_valid,
    input wire m_ready,
    output reg [31:0] m_signal, m_rawmax,
    output reg [3:0] m_keep,
    output reg m_sof, m_eol, m_eof,
    output reg [31:0] m_frame_id,
    output reg [31:0] m_background_frame, m_background_generation,
    output reg [31:0] m_geometry,
    output reg [12:0] m_x, m_y,
    output reg [15:0] m_error,
    output reg [7:0] m_upstream_error
);
    // Error bits: 0 uncommitted background; 1 frame/generation mismatch;
    // 2 geometry/dimension mismatch; 3 coordinate/keep mismatch;
    // 4 upstream fault; 5 missing SOF/frame metadata changed;
    // 6 prior error in this frame; 7 new SOF before prior EOF.
    localparam [15:0] BAD_BACKGROUND=16'h0001, BAD_ID=16'h0002,
        BAD_GEOMETRY=16'h0004, BAD_COORDINATE=16'h0008,
        UPSTREAM=16'h0010, BAD_SEQUENCE=16'h0020,
        FRAME_POISONED=16'h0040, UNFINISHED_FRAME=16'h0080;
    reg frame_active, frame_poisoned;
    reg [31:0] frame_id, background_frame, background_generation, geometry;
    reg [12:0] width, height;
    reg [15:0] beat_error;
    integer i;

    function [7:0] positive_subtract;
        input [7:0] a, b;
        begin positive_subtract=(a>b)?a-b:8'd0; end
    endfunction
    function [7:0] max3;
        input [7:0] a,b,c;
        begin max3=(a>b)?((a>c)?a:c):((b>c)?b:c); end
    endfunction
    function [7:0] difference;
        input [31:0] a,b;
        begin difference=max3(positive_subtract(a[23:16],b[23:16]),
            positive_subtract(a[15:8],b[15:8]),
            positive_subtract(a[7:0],b[7:0])); end
    endfunction
    wire metadata_changed=(s_frame_id!=frame_id)||
        (s_expected_background_frame!=background_frame)||
        (s_expected_background_generation!=background_generation)||
        (s_geometry!=geometry)||(s_width!=width)||(s_height!=height);
    always @* begin
        beat_error=0;
        if(!s_background_committed) beat_error=beat_error|BAD_BACKGROUND;
        if(s_background_frame!=s_expected_background_frame ||
           s_background_generation!=s_expected_background_generation)
            beat_error=beat_error|BAD_ID;
        if(s_background_geometry!=s_geometry ||
           s_background_width!=s_width || s_background_height!=s_height ||
           s_width==0 || s_height==0)
            beat_error=beat_error|BAD_GEOMETRY;
        if(s_x!=s_background_x || s_y!=s_background_y ||
           s_y>=s_height || s_keep==0 || (s_keep & ~s_background_keep)!=0)
            beat_error=beat_error|BAD_COORDINATE;
        // Widen before adding the lane number so a right-edge overflow cannot
        // wrap around and appear valid.
        for(i=0;i<4;i=i+1)
            if(s_keep[i] && ({1'b0,s_x}+i >= {1'b0,s_width}))
                beat_error=beat_error|BAD_COORDINATE;
        if(s_upstream_error!=0) beat_error=beat_error|UPSTREAM;
        if(s_sof) begin
            if(frame_active) beat_error=beat_error|UNFINISHED_FRAME;
        end else begin
            if(!frame_active || metadata_changed) beat_error=beat_error|BAD_SEQUENCE;
            if(frame_poisoned) beat_error=beat_error|FRAME_POISONED;
        end
    end
    assign s_ready=rst_n && (!m_valid || m_ready);
    integer lane;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            m_valid<=0; m_signal<=0; m_rawmax<=0; m_keep<=0;
            m_sof<=0; m_eol<=0; m_eof<=0; m_frame_id<=0;
            m_background_frame<=0; m_background_generation<=0;
            m_geometry<=0; m_x<=0; m_y<=0; m_error<=0; m_upstream_error<=0;
            frame_active<=0; frame_poisoned<=0; frame_id<=0;
            background_frame<=0; background_generation<=0; geometry<=0;
            width<=0; height<=0;
        end else if(s_ready) begin
            m_valid<=s_valid;
            if(s_valid) begin
                m_sof<=s_sof; m_eol<=s_eol; m_eof<=s_eof;
                m_frame_id<=s_frame_id;
                m_background_frame<=s_expected_background_frame;
                m_background_generation<=s_expected_background_generation;
                m_geometry<=s_geometry; m_x<=s_x; m_y<=s_y;
                m_error<=beat_error; m_upstream_error<=s_upstream_error;
                m_keep<=(beat_error==0)?s_keep:4'b0;
                for(lane=0;lane<4;lane=lane+1) begin
                    m_signal[lane*8+:8]<=(beat_error==0 && s_keep[lane]) ?
                        difference(s_on[lane*32+:32],s_background[lane*32+:32]):8'd0;
                    m_rawmax[lane*8+:8]<=(beat_error==0 && s_keep[lane]) ?
                        max3(s_on[lane*32+16+:8],s_on[lane*32+8+:8],s_on[lane*32+:8]):8'd0;
                end
                if(s_sof) begin
                    frame_id<=s_frame_id; background_frame<=s_expected_background_frame;
                    background_generation<=s_expected_background_generation;
                    geometry<=s_geometry; width<=s_width; height<=s_height;
                end
                frame_active<=!s_eof;
                frame_poisoned<=!s_eof && beat_error!=0;
            end
        end
    end
endmodule
