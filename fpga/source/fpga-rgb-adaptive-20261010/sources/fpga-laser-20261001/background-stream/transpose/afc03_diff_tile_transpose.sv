`timescale 1ns/1ps
// Single-tile CW90 transpose for already paired/differenced raw RGB pixels.
// One synchronous 64-bit write port + one synchronous 64-bit read port.
// No memory clearing, asynchronous RAM reads, DDR operations or frame guessing.
module afc03_diff_tile_transpose #(
    parameter integer MAX_HEIGHT = 2048,
    parameter integer STALL_TIMEOUT = 1000000,
    parameter integer ADDR_WIDTH = $clog2(MAX_HEIGHT*4)
) (
    input wire clk, rst_n,
    input wire abort,
    input wire cfg_valid,
    output wire cfg_ready,
    input wire [12:0] cfg_raw_width, cfg_raw_height, cfg_raw_x0, cfg_raw_y0,
    input wire [4:0] cfg_actual_cols,
    input wire [11:0] cfg_tile_height,
    input wire [31:0] cfg_frame_id, cfg_background_generation, cfg_geometry, cfg_request_id,
    input wire s_valid,
    output wire s_ready,
    input wire [63:0] s_data, // lane i: [16*i+:16] = {rawmax8, signal8}
    input wire [3:0] s_keep,
    input wire [12:0] s_x, s_y, // RAW coordinates of lane 0
    input wire s_sof, s_eol, s_eot, // SOF here means start of this TILE
    input wire [31:0] s_frame_id, s_background_generation, s_geometry,
    input wire [15:0] s_error,
    // Full tile is staged, then a separate transaction authorizes publication.
    // Source-frame-committed must attest the WHOLE DDR source frame is valid.
    input wire c_valid,
    output wire c_ready,
    input wire c_source_frame_committed,
    input wire [31:0] c_frame_id, c_background_generation, c_geometry, c_request_id,
    input wire [15:0] c_error,
    output wire m_valid,
    input wire m_ready,
    output wire [7:0] m_signal, m_rawmax,
    output reg [12:0] m_row, m_global_x_origin,
    output reg [11:0] m_local_x, m_width,
    output reg m_sof, m_eol, m_tile_sof, m_tile_eof,
    output reg [31:0] m_frame_id, m_background_generation, m_geometry, m_request_id,
    output wire busy,
    output reg done,
    output reg [15:0] error
);
    localparam [2:0] IDLE=0, FILL=1, COMMIT=2, READ=3, DRAIN=4;
    localparam [15:0] E_CONFIG=16'h0001, E_COORD=16'h0002,
        E_ID=16'h0004, E_MARKER=16'h0008, E_INPUT=16'h0010,
        E_COMMIT=16'h0020, E_TIMEOUT=16'h0040, E_ABORT=16'h0080,
        E_EXTRA=16'h0100;
    reg [2:0] state;
    reg [12:0] x0,y0;
    reg [4:0] columns;
    reg [11:0] height,wr_y,rd_y;
    reg [2:0] groups;
    reg [1:0] wr_group;
    reg [3:0] rd_col;
    reg [31:0] frame_id,generation,geometry,request_id,idle_cycles;
    reg output_valid;
    reg [1:0] output_lane;
    reg [63:0] read_word;
    // Anlogic documented RAM inference hint. Actual mapping still requires TD.
    (* ram_style="bram" *) reg [63:0] memory [0:MAX_HEIGHT*4-1];

    assign cfg_ready = rst_n && !abort && state==IDLE;
    assign s_ready = rst_n && !abort && state==FILL;
    assign c_ready = rst_n && !abort && state==COMMIT;
    assign m_valid = rst_n && !abort && output_valid;
    assign busy = state!=IDLE;
    wire [15:0] output_pixel = read_word[output_lane*16+:16];
    assign m_signal = output_pixel[7:0];
    assign m_rawmax = output_pixel[15:8];

    wire last_group = ({1'b0,wr_group}+3'd1)==groups;
    wire last_input = last_group && wr_y==height-1'b1;
    wire first_input = wr_y==0 && wr_group==0;
    wire [4:0] cols_left = columns - {1'b0,wr_group,2'b00};
    wire [3:0] expected_keep = cols_left>=4 ? 4'hf :
        cols_left==3 ? 4'h7 : cols_left==2 ? 4'h3 : 4'h1;
    reg [15:0] beat_error;
    always @* begin
        beat_error=0;
        if ({1'b0,s_x} != ({1'b0,x0}+{10'b0,wr_group,2'b00}) ||
            {1'b0,s_y} != ({1'b0,y0}+{2'b0,wr_y}) || s_keep!=expected_keep)
            beat_error=beat_error|E_COORD;
        if (s_frame_id!=frame_id || s_background_generation!=generation || s_geometry!=geometry)
            beat_error=beat_error|E_ID;
        if (s_sof!=first_input || s_eol!=last_group || s_eot!=last_input)
            beat_error=beat_error|E_MARKER;
        if (s_error!=0) beat_error=beat_error|E_INPUT;
    end
    wire config_bad = cfg_raw_width==0 || cfg_raw_height==0 ||
        cfg_actual_cols==0 || cfg_actual_cols>16 || cfg_tile_height==0 ||
        cfg_tile_height>MAX_HEIGHT || cfg_raw_x0[1:0]!=0 ||
        ({1'b0,cfg_raw_x0}+{9'b0,cfg_actual_cols})>{1'b0,cfg_raw_width} ||
        ({1'b0,cfg_raw_y0}+{2'b0,cfg_tile_height})>{1'b0,cfg_raw_height};
    wire commit_bad = !c_source_frame_committed || c_error!=0 ||
        c_frame_id!=frame_id || c_background_generation!=generation ||
        c_geometry!=geometry || c_request_id!=request_id;
    wire [ADDR_WIDTH-1:0] write_address = {wr_y,wr_group};
    wire [ADDR_WIDTH-1:0] read_address = {rd_y,rd_col[3:2]};
    wire write_enable = s_valid && s_ready && beat_error==0;
    wire read_enable = rst_n && !abort && state==READ && (!output_valid || m_ready);

    // This process has no reset, no variable per-pixel write, and no async read.
    // Fill and read states cannot overlap. A single fixed-width mux follows RAM.
    always @(posedge clk) begin
        if (write_enable) memory[write_address] <= s_data;
        if (read_enable) read_word <= memory[read_address];
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state<=IDLE; done<=0; error<=0; output_valid<=0; output_lane<=0;
            x0<=0;y0<=0;columns<=0;height<=0;groups<=0;wr_y<=0;wr_group<=0;
            rd_y<=0;rd_col<=0;frame_id<=0;generation<=0;geometry<=0;request_id<=0;
            idle_cycles<=0;m_row<=0;m_global_x_origin<=0;m_local_x<=0;m_width<=0;
            m_sof<=0;m_eol<=0;m_tile_sof<=0;m_tile_eof<=0;
            m_frame_id<=0;m_background_generation<=0;m_geometry<=0;m_request_id<=0;
        end else begin
            done<=0;
            if (abort && state!=IDLE) begin
                state<=IDLE; output_valid<=0; error<=E_ABORT; done<=1; idle_cycles<=0;
            end else case(state)
                IDLE: begin
                    output_valid<=0; idle_cycles<=0;
                    if (cfg_valid && cfg_ready) begin
                        error<=0;
                        if (config_bad) begin error<=E_CONFIG;done<=1;end
                        else begin
                            state<=FILL;x0<=cfg_raw_x0;y0<=cfg_raw_y0;
                            columns<=cfg_actual_cols;height<=cfg_tile_height;
                            groups<=({1'b0,cfg_actual_cols}+6'd3)>>2;
                            frame_id<=cfg_frame_id;generation<=cfg_background_generation;
                            geometry<=cfg_geometry;request_id<=cfg_request_id;
                            wr_y<=0;wr_group<=0;
                            m_global_x_origin<=cfg_raw_height-cfg_raw_y0-cfg_tile_height;
                            m_width<=cfg_tile_height;
                            m_frame_id<=cfg_frame_id;m_background_generation<=cfg_background_generation;
                            m_geometry<=cfg_geometry;m_request_id<=cfg_request_id;
                        end
                    end
                end
                FILL: begin
                    if (s_valid && s_ready) begin
                        idle_cycles<=0;
                        if (beat_error!=0) begin state<=IDLE;error<=beat_error;done<=1;end
                        else if (last_input) state<=COMMIT;
                        else if (last_group) begin wr_group<=0;wr_y<=wr_y+1'b1;end
                        else wr_group<=wr_group+1'b1;
                    end else if (STALL_TIMEOUT>0 && idle_cycles>=STALL_TIMEOUT-1) begin
                        state<=IDLE;error<=E_TIMEOUT;done<=1;
                    end else idle_cycles<=idle_cycles+1'b1;
                end
                COMMIT: begin
                    // Extra input after accepted EOT is a malformed tile.
                    if (s_valid) begin state<=IDLE;error<=E_EXTRA;done<=1;end
                    else if (c_valid && c_ready) begin
                        idle_cycles<=0;
                        if (commit_bad) begin state<=IDLE;error<=E_COMMIT;done<=1;end
                        else begin state<=READ;rd_col<=0;rd_y<=height-1'b1;end
                    end else if (STALL_TIMEOUT>0 && idle_cycles>=STALL_TIMEOUT-1) begin
                        state<=IDLE;error<=E_TIMEOUT;done<=1;
                    end else idle_cycles<=idle_cycles+1'b1;
                end
                READ: begin
                    if (read_enable) begin
                        output_valid<=1;output_lane<=rd_col[1:0];
                        m_row<=x0+rd_col;m_local_x<=height-1'b1-rd_y;
                        m_sof<=rd_y==height-1'b1;m_eol<=rd_y==0;
                        m_tile_sof<=rd_col==0 && rd_y==height-1'b1;
                        m_tile_eof<=rd_col==columns-1'b1 && rd_y==0;
                        if (rd_y==0) begin
                            if (rd_col==columns-1'b1) state<=DRAIN;
                            else begin rd_col<=rd_col+1'b1;rd_y<=height-1'b1;end
                        end else rd_y<=rd_y-1'b1;
                    end
                end
                DRAIN: if (m_valid && m_ready) begin
                    output_valid<=0;state<=IDLE;done<=1;
                end
                default: begin state<=IDLE;output_valid<=0;error<=E_CONFIG;done<=1;end
            endcase
        end
    end
endmodule
