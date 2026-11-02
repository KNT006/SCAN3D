`timescale 1ns/1ps
// Diagnostic RGB sidecar. One elastic stage; never waits for MMIO or storage.
// Captures ORIGINAL {pad,R,G,B} words before pack4. Only an explicitly armed
// frame has its first four output pixels replaced by RGT1/token/frame_id.
// The ROI excludes these pixels. Coordinates are raw sensor/ISP coordinates.
module afc03_rgb_roi_probe #(parameter WAIT_DDR=0,parameter ADDR_BITS=11)(
    input wire clk,rst_n,stream_rst_n,
    input wire capture_pending,input wire [31:0] capture_token,
    input wire [12:0] image_width,image_height,
    input wire [127:0] s_data,input wire s_valid,s_last,s_user,
    output wire s_ready,
    output reg [127:0] m_data,output reg m_valid,m_last,m_user,
    input wire m_ready,
    input wire [31:0] awaddr,wdata,araddr,input wire [3:0] wstrb,
    input wire awvalid,awready,wvalid,wready,arvalid,arready,
    output reg rd_select,output reg [31:0] rd_data
);
    localparam WORDS=1<<ADDR_BITS;
    localparam ARM=32'h52470001,CANCEL=32'h52470000;
    reg aw_full,w_full;reg [31:0] aw_saved,w_saved;reg [3:0] st_saved;
    wire ah=awvalid&&awready,wh=wvalid&&wready;
    wire commit=(aw_full||ah)&&(w_full||wh);
    wire [31:0] addr=aw_full?aw_saved:awaddr;
    wire [31:0] value=w_full?w_saved:wdata;
    wire [3:0] strobes=w_full?st_saved:wstrb;
    // The PCIe bridge preserves the physical BAR base in upper address bits.
    // BAR0 is a 1 MiB aperture: decode its complete offset, not just low byte.
    wire write_hit=commit&&addr[19:8]==12'h021;
    wire aligned_full=(strobes==4'hf)&&(addr[1:0]==0);
    reg waiting,active,done,rejected;
    reg [7:0] fault;
    reg [31:0] token,frame_counter,captured_frame,words_written;
    reg [12:0] x0,y0,x1,y1,width_latched,height_latched;
    reg [31:0] expected_words;
    wire [25:0] config_words=((x1-x0)>>2)*(y1-y0);
    reg in_frame;reg [12:0] x,y;
    wire accept=s_valid&&s_ready;
    wire [12:0] px=s_user?13'd0:x,py=s_user?13'd0:y;
    wire starting=waiting&&s_user&&(!WAIT_DDR||(capture_pending&&capture_token==token));
    wire capturing=active||starting;
    wire inside_roi=(px>=x0)&&(px<x1)&&(py>=y0)&&(py<y1);
    wire [31:0] count_before=starting?32'd0:words_written;
    wire [31:0] count_after=count_before+(inside_roi?32'd1:32'd0);
    wire correct_line=(s_last==(px+13'd4==width_latched));
    wire final_beat=s_last&&(py+13'd1==height_latched);
    reg [127:0] memory [0:WORDS-1];
    reg [ADDR_BITS-1:0] read_index;
    reg read_pending,read_valid;
    reg [127:0] read_word;
    wire [95:0] marker={frame_counter+32'd1,token,32'h31544752};
    integer lane;

    assign s_ready=stream_rst_n&&(!m_valid||m_ready);
    // True synchronous read/write inference. Memory never reset/cleared.
    always @(posedge clk) begin
        if(accept&&capturing&&inside_roi&&count_before<WORDS&&stream_rst_n)
            memory[count_before[ADDR_BITS-1:0]]<=s_data;
        if(read_pending)read_word<=memory[read_index];
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            aw_full<=0;w_full<=0;aw_saved<=0;w_saved<=0;st_saved<=0;
            waiting<=0;active<=0;done<=0;fault<=0;rejected<=0;
            token<=0;frame_counter<=0;captured_frame<=0;words_written<=0;
            x0<=0;y0<=0;x1<=0;y1<=0;width_latched<=0;height_latched<=0;expected_words<=0;
            in_frame<=0;x<=0;y<=0;read_index<=0;read_pending<=0;read_valid<=0;
            m_data<=0;m_valid<=0;m_last<=0;m_user<=0;
        end else begin
            if(ah)begin aw_saved<=awaddr;aw_full<=1;end
            if(wh)begin w_saved<=wdata;st_saved<=wstrb;w_full<=1;end
            if(commit)begin aw_full<=0;w_full<=0;end
            read_pending<=0;
            if(read_pending)read_valid<=1;
            if(m_ready)m_valid<=0;
            if(accept)begin
                m_data<=s_data;m_valid<=1;m_last<=s_last;m_user<=s_user;
                if(starting&&stream_rst_n)begin
                    for(lane=0;lane<4;lane=lane+1)
                        m_data[lane*32+:32]<={8'b0,marker[lane*24+:8],marker[lane*24+8+:8],marker[lane*24+16+:8]};
                end
                if(s_user)begin frame_counter<=frame_counter+1'b1;in_frame<=1;end
                if(s_user||in_frame)begin
                    if(s_last)begin x<=0;y<=py+1'b1;end
                    else begin x<=px+13'd4;y<=py;end
                end
                if(starting)begin
                    waiting<=0;active<=1;captured_frame<=frame_counter+1'b1;
                    words_written<=0;fault<=0;
                end
                if(capturing)begin
                    if(inside_roi)begin
                        if(count_before<WORDS)words_written<=count_after;
                        else begin fault<=3;active<=0;done<=0;end
                    end
                    if(!correct_line||px>=width_latched||py>=height_latched)begin
                        fault<=2;active<=0;done<=0;
                    end else if(active&&s_user)begin
                        fault<=4;active<=0;done<=0;
                    end else if(final_beat)begin
                        active<=0;
                        if(fault==0&&count_after==expected_words)done<=1;
                        else begin fault<=5;done<=0;end
                    end
                end
            end
            // Reset only this stream state; the AXI-Lite response stays alive.
            if(!stream_rst_n)begin
                m_valid<=0;in_frame<=0;x<=0;y<=0;
                waiting<=0;active<=0;done<=0;read_valid<=0;read_pending<=0;
                if(waiting||active||done)fault<=6;
            end
            if(write_hit)begin
                if(!aligned_full)rejected<=1;
                else if(addr[7:0]==8'h08&&value==CANCEL)begin
                    waiting<=0;active<=0;done<=0;read_valid<=0;read_pending<=0;rejected<=0;fault<=0;
                end else if(waiting||active||(done&&addr[7:0]!=8'h28))rejected<=1;
                else case(addr[7:0])
                    8'h08:if(value==ARM)begin
                        if(!stream_rst_n||token==0||image_width==0||image_height==0||image_width[1:0]!=0||
                           x0[1:0]!=0||x1[1:0]!=0||x0>=x1||y0>=y1||x1>image_width||y1>image_height||
                           (y0==0&&x0<4)||config_words==0||config_words>WORDS)begin
                            rejected<=1;fault<=1;done<=0;
                        end else begin
                            waiting<=1;done<=0;fault<=0;rejected<=0;words_written<=0;read_valid<=0;
                            width_latched<=image_width;height_latched<=image_height;expected_words<=config_words;
                        end
                    end else rejected<=1;
                    8'h0c:token<=value;
                    8'h10:if(value[31:29]!=0||value[15:13]!=0)rejected<=1;
                          else begin x0<=value[12:0];y0<=value[28:16];end
                    8'h14:if(value[31:29]!=0||value[15:13]!=0)rejected<=1;
                          else begin x1<=value[12:0];y1<=value[28:16];end
                    8'h28:if(stream_rst_n&&done&&value<words_written)begin
                        read_index<=value[ADDR_BITS-1:0];read_pending<=1;read_valid<=0;
                    end else rejected<=1;
                    default:rejected<=1;
                endcase
            end
        end
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n)begin rd_select<=0;rd_data<=0;end
        else if(arvalid&&arready)begin
            rd_select<=(araddr[19:8]==12'h021);
            case(araddr[7:0])
                8'h00:rd_data<=32'h31544752;
                8'h04:rd_data<={24'b0,2'b0,read_valid,rejected,(fault!=0),done,active,waiting};
                8'h08:rd_data<=WAIT_DDR?32'h00020000:32'h00010000;
                8'h0c:rd_data<=token;
                8'h10:rd_data<={3'b0,y0,3'b0,x0};
                8'h14:rd_data<={3'b0,y1,3'b0,x1};
                8'h18:rd_data<=captured_frame;
                8'h1c:rd_data<=words_written;
                8'h20:rd_data<={3'b0,height_latched,3'b0,width_latched};
                8'h24:rd_data<={24'b0,fault};
                8'h28:rd_data<=WORDS;
                8'h2c:rd_data<=read_index;
                8'h30:rd_data<=expected_words;
                8'h34:rd_data<=frame_counter;
                8'h40:rd_data<=read_valid?read_word[31:0]:32'b0;
                8'h44:rd_data<=read_valid?read_word[63:32]:32'b0;
                8'h48:rd_data<=read_valid?read_word[95:64]:32'b0;
                8'h4c:rd_data<=read_valid?read_word[127:96]:32'b0;
                default:rd_data<=0;
            endcase
        end
    end
endmodule
