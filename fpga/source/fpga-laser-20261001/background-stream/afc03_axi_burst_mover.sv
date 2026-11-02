`timescale 1ns/1ps
// Single-clock, half-duplex, single-outstanding-burst AXI4 mover.
// This is a transactional building block, not a frame-store/CDC controller.
// All read data is speculative until status_valid && status_ok commits it.
// Any fault locks new commands until a COMMON master/controller reset. On a
// timeout, already offered AXI VALID signals remain stable and the current
// burst continues draining if the peer recovers; status reports the fault now.
module afc03_axi_burst_mover #(
    parameter ADDR_WIDTH=28,
    parameter MAX_BURST=16,
    parameter TIMEOUT_CYCLES=1000000
)(
    input wire clk,rst_n,
    input wire cmd_valid,output wire cmd_ready,
    input wire cmd_write,
    input wire [ADDR_WIDTH-1:0] cmd_address,
    input wire [31:0] cmd_bytes,
    input wire [127:0] cmd_header,
    input wire s_valid,output wire s_ready,
    input wire [127:0] s_data,input wire [15:0] s_keep,input wire s_last,
    output wire m_valid,input wire m_ready,
    output wire [127:0] m_data,output wire [15:0] m_keep,output wire m_last,
    output wire [127:0] m_header,
    output reg status_valid,input wire status_ready,
    output reg status_ok,output reg [7:0] status_error,
    output reg [31:0] status_bytes,output reg [127:0] status_header,
    output wire busy,output reg requires_reset,
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
    localparam IDLE=0,W_FILL=1,W_SEND=2,W_RESP=3,R_ADDR=4,
               R_RECV=5,R_OUTPUT=6,R_DRAIN=7,HALTED=8;
    localparam BAD_COMMAND=1,BAD_INPUT=2,WRITE_RESPONSE=3,READ_RESPONSE=4,
               READ_BOUNDARY=5,TIMEOUT=6;
    reg [3:0] state;
    reg write_transaction;
    reg [ADDR_WIDTH-1:0] address;
    reg [31:0] remaining_bytes,completed_bytes,total_bytes,watchdog;
    reg [127:0] header;
    reg [8:0] burst_beats,fill_index,send_index,receive_index,output_index;
    reg [31:0] burst_bytes;
    reg aw_sent;
    reg [127:0] buffer_data[0:MAX_BURST-1];
    reg [15:0] buffer_keep[0:MAX_BURST-1];

    function [8:0] planned_beats;
        input [ADDR_WIDTH-1:0] a;
        input [31:0] n;
        reg [32:0] remaining_words;
        reg [8:0] boundary_words;
        reg [8:0] choice;
        begin
            remaining_words=({1'b0,n}+15)>>4;
            boundary_words=9'd256-{1'b0,a[11:4]};
            choice=MAX_BURST;
            if(boundary_words<choice)choice=boundary_words;
            if(remaining_words<choice)choice=remaining_words[8:0];
            planned_beats=choice;
        end
    endfunction
    function [31:0] planned_bytes;
        input [ADDR_WIDTH-1:0] a;
        input [31:0] n;
        reg [31:0] length;
        begin
            length=planned_beats(a,n)*16;
            planned_bytes=(n<length)?n:length;
        end
    endfunction
    function [15:0] expected_keep;
        input [31:0] bytes_left;
        input [8:0] index;
        reg [31:0] offset;
        reg [31:0] n;
        begin
            offset=index*16;
            n=bytes_left-offset;
            expected_keep=(n>=16)?16'hffff:((17'd1<<n)-1'b1);
        end
    endfunction
    wire last_burst=(remaining_bytes==burst_bytes);
    wire input_final=last_burst && fill_index+1'b1==burst_beats;
    wire [32:0] request_end={1'b0,cmd_bytes}+cmd_address;
    wire command_bad=cmd_bytes==0 || cmd_address[3:0]!=0 ||
                     request_end>(33'd1<<ADDR_WIDTH);
    assign busy=state!=IDLE && state!=HALTED;
    assign cmd_ready=rst_n && state==IDLE && !status_valid && !requires_reset;
    assign s_ready=rst_n && state==W_FILL && !requires_reset;
    assign m_valid=rst_n && state==R_OUTPUT;
    assign m_data=buffer_data[output_index];
    assign m_keep=expected_keep(remaining_bytes,output_index);
    assign m_last=last_burst && output_index+1'b1==burst_beats;
    assign m_header=header;
    assign awid=0;assign awaddr=address;assign awlen=burst_beats-1'b1;
    assign awsize=3'd4;assign awburst=2'b01;
    assign awvalid=rst_n && state==W_SEND && !aw_sent;
    assign wdata=buffer_data[send_index];assign wstrb=buffer_keep[send_index];
    assign wlast=send_index+1'b1==burst_beats;
    assign wvalid=rst_n && state==W_SEND && send_index<burst_beats;
    assign bready=rst_n && state==W_RESP;
    assign arid=0;assign araddr=address;assign arlen=burst_beats-1'b1;
    assign arsize=3'd4;assign arburst=2'b01;
    assign arvalid=rst_n && state==R_ADDR;
    assign rready=rst_n && (state==R_RECV || state==R_DRAIN);
    wire progress=(s_valid&&s_ready)||(m_valid&&m_ready)||
        (awvalid&&awready)||(wvalid&&wready)||(bvalid&&bready)||
        (arvalid&&arready)||(rvalid&&rready);
    wire timeout_now=busy && !requires_reset && !progress && watchdog>=TIMEOUT_CYCLES-1;
    wire read_response_bad=(rresp!=0 || rid!=0);
    wire read_last_bad=(rlast!=(receive_index+1'b1==burst_beats));

    task fault;
        input [7:0] code;
        begin
            if(!requires_reset)begin
                requires_reset<=1;status_valid<=1;status_ok<=0;
                status_error<=code;status_bytes<=completed_bytes;status_header<=header;
            end
        end
    endtask
    task finish_burst;
        reg [ADDR_WIDTH-1:0] next_address;
        reg [31:0] next_bytes;
        begin
            if(requires_reset)state<=HALTED;
            else begin
                completed_bytes<=completed_bytes+burst_bytes;
                if(last_burst)begin
                    status_valid<=1;status_ok<=1;status_error<=0;
                    status_bytes<=total_bytes;status_header<=header;state<=IDLE;
                end else begin
                    next_address=address+burst_beats*16;
                    next_bytes=remaining_bytes-burst_bytes;
                    address<=next_address;remaining_bytes<=next_bytes;
                    burst_beats<=planned_beats(next_address,next_bytes);
                    burst_bytes<=planned_bytes(next_address,next_bytes);
                    fill_index<=0;send_index<=0;receive_index<=0;output_index<=0;aw_sent<=0;
                    state<=write_transaction?W_FILL:R_ADDR;
                end
            end
        end
    endtask
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)begin
            state<=IDLE;write_transaction<=0;address<=0;remaining_bytes<=0;
            completed_bytes<=0;total_bytes<=0;watchdog<=0;header<=0;
            burst_beats<=0;burst_bytes<=0;fill_index<=0;send_index<=0;
            receive_index<=0;output_index<=0;aw_sent<=0;requires_reset<=0;
            status_valid<=0;status_ok<=0;status_error<=0;status_bytes<=0;status_header<=0;
        end else begin
            if(status_valid&&status_ready)status_valid<=0;
            if(!busy || progress)watchdog<=0;
            else if(!requires_reset)watchdog<=watchdog+1'b1;
            if(timeout_now)begin
                fault(TIMEOUT);
                // No bus transaction exists while collecting a write burst.
                if(state==W_FILL)state<=HALTED;
            end
            case(state)
                IDLE:if(cmd_valid&&cmd_ready)begin
                    header<=cmd_header;total_bytes<=cmd_bytes;completed_bytes<=0;
                    address<=cmd_address;remaining_bytes<=cmd_bytes;
                    write_transaction<=cmd_write;
                    fill_index<=0;send_index<=0;receive_index<=0;output_index<=0;aw_sent<=0;
                    burst_beats<=planned_beats(cmd_address,cmd_bytes);
                    burst_bytes<=planned_bytes(cmd_address,cmd_bytes);
                    if(command_bad)begin
                        requires_reset<=1;status_valid<=1;status_ok<=0;
                        status_error<=BAD_COMMAND;status_bytes<=0;
                        status_header<=cmd_header;state<=HALTED;
                    end else state<=cmd_write?W_FILL:R_ADDR;
                end
                W_FILL:if(s_valid&&s_ready)begin
                    if(s_keep!=expected_keep(remaining_bytes,fill_index)||s_last!=input_final)begin
                        fault(BAD_INPUT);state<=HALTED;
                    end else begin
                        buffer_data[fill_index]<=s_data;buffer_keep[fill_index]<=s_keep;
                        fill_index<=fill_index+1'b1;
                        if(fill_index+1'b1==burst_beats)begin aw_sent<=0;send_index<=0;state<=W_SEND;end
                    end
                end
                W_SEND:begin
                    if(awvalid&&awready)aw_sent<=1;
                    if(wvalid&&wready)send_index<=send_index+1'b1;
                    if((aw_sent||(awvalid&&awready)) &&
                       (send_index==burst_beats||(wvalid&&wready&&wlast)))state<=W_RESP;
                end
                W_RESP:if(bvalid&&bready)begin
                    if(bresp!=0||bid!=0)begin fault(WRITE_RESPONSE);state<=HALTED;end
                    else finish_burst;
                end
                R_ADDR:if(arvalid&&arready)begin receive_index<=0;state<=R_RECV;end
                R_RECV:if(rvalid&&rready)begin
                    if(read_response_bad)fault(READ_RESPONSE);
                    else if(read_last_bad)fault(READ_BOUNDARY);
                    buffer_data[receive_index]<=rdata;
                    receive_index<=receive_index+1'b1;
                    if(rlast)begin
                        if(requires_reset||read_response_bad||read_last_bad)state<=HALTED;
                        else begin output_index<=0;state<=R_OUTPUT;end
                    end else if(receive_index+1'b1==burst_beats)state<=R_DRAIN;
                end
                R_DRAIN:if(rvalid&&rready&&rlast)state<=HALTED;
                R_OUTPUT:if(m_valid&&m_ready)begin
                    if(output_index+1'b1==burst_beats)finish_burst;
                    else output_index<=output_index+1'b1;
                end
                HALTED:begin end
                default:begin fault(BAD_COMMAND);state<=HALTED;end
            endcase
        end
    end
endmodule
