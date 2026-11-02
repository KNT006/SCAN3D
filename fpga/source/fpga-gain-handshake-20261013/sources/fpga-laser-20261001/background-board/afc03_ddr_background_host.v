// Derived snapshot-only host; original afc03_ddr_host.v is unchanged.
`timescale 1ns/1ps
// Passive monitor of the existing single-outstanding AXI-Lite slave.
// Register window 0x2000-0x20ff is outside existing SGDMA control banks.
// Commands require all byte strobes and a 32-bit key. No writes on boot.
module afc03_ddr_background_host #(parameter WATCHDOG=25000000)(
    input wire hclk, hrst_n,
    input wire [31:0] awaddr,wdata,araddr,
    input wire [3:0] wstrb,
    input wire awvalid,awready,wvalid,wready,arvalid,arready,
    output reg rd_select,
    output reg [31:0] rd_data,
    output reg reset_held,
    input wire dclk, drst_n, control_ready,
    input wire [447:0] status_words,
    input wire [19:0] init_status,
    output reg bist_start
);
    localparam HOLD=32'h44520000, RELEASE=32'h44520001,
               SNAP=32'h44520002, START=32'h44520003;
    reg aw_full,w_full;
    reg [31:0] aw_saved,w_saved;
    reg [3:0] strb_saved;
    wire ah=awvalid&&awready, wh=wvalid&&wready;
    wire commit=(aw_full||ah)&&(w_full||wh);
    wire [31:0] addr=aw_full?aw_saved:awaddr;
    wire [31:0] data=w_full?w_saved:wdata;
    wire [3:0] strobes=w_full?strb_saved:wstrb;
    wire command=commit && addr[15:0]==16'h2008;
    wire keyed=command && strobes==4'hf;
    reg rejected;
    reg [19:0] init_meta,init_sync;
    wire bridge_reset_n=hrst_n&&!reset_held&&drst_n;
    reg [1:0] host_reset_pipe;
    always @(posedge hclk or negedge bridge_reset_n)
        if(!bridge_reset_n) host_reset_pipe<=0;
        else host_reset_pipe<={host_reset_pipe[0],1'b1};
    wire host_bridge_reset_n=host_reset_pipe[1];
    reg [1:0] ddr_reset_pipe;
    always @(posedge dclk or negedge bridge_reset_n)
        if(!bridge_reset_n) ddr_reset_pipe<=0;
        else ddr_reset_pipe<={ddr_reset_pipe[0],1'b1};
    wire ddr_bridge_reset_n=ddr_reset_pipe[1];
    reg request,opcode,busy,valid,timed_out;
    reg [31:0] ticks,snapshot_seq;
    reg [479:0] snapshot;
    reg ack;
    reg [1:0] ack_sync,request_sync;
    reg [479:0] reply_hold;
    reg [1:0] dstate;
    reg [31:0] result_code;
    // Address and data may handshake in either order; pair each exactly once.
    always @(posedge hclk or negedge hrst_n) begin
        if(!hrst_n) begin
            aw_full<=0;w_full<=0;aw_saved<=0;w_saved<=0;strb_saved<=0;
            reset_held<=1;rejected<=0;init_meta<=0;init_sync<=0;
        end else begin
            init_meta<=init_status;init_sync<=init_meta;
            if(ah) begin aw_saved<=awaddr;aw_full<=1;end
            if(wh) begin w_saved<=wdata;strb_saved<=wstrb;w_full<=1;end
            if(commit) begin aw_full<=0;w_full<=0;end
            if(command) begin
                if(!keyed) rejected<=1;
                else case(data)
                    HOLD: begin reset_held<=1;rejected<=0;end
                    RELEASE: begin reset_held<=0;rejected<=0;end
                    SNAP: if(!host_bridge_reset_n||busy||timed_out) rejected<=1;
                    START: rejected<=1; // DDR belongs to background capture; explicit refusal.
                    default: rejected<=1;
                endcase
            end
        end
    end
    // Bundled-data toggle mailbox. Opcode is held until ack. Reply data is
    // captured in the destination before ack and held until the next command.
    // Timeout latches: reset the entire DDR domain before retrying.
    always @(posedge hclk or negedge host_bridge_reset_n) begin
        if(!host_bridge_reset_n) begin
            request<=0;opcode<=0;busy<=0;valid<=0;timed_out<=0;
            ticks<=0;snapshot_seq<=0;snapshot<=0;ack_sync<=0;
        end else begin
            ack_sync<={ack_sync[0],ack};
            if(busy) begin
                if(ack_sync[1]==request) begin
                    snapshot<=reply_hold;valid<=1;busy<=0;
                    snapshot_seq<=snapshot_seq+1'b1;ticks<=0;
                end else if(ticks==WATCHDOG-1) begin
                    timed_out<=1;busy<=0;valid<=0;
                end else ticks<=ticks+1'b1;
            end else if(keyed&&data==SNAP&&!timed_out) begin
                opcode<=0;request<=~request; // Snapshot-only legacy mailbox.
                busy<=1;valid<=0;ticks<=0;
            end
        end
    end
    always @(posedge dclk or negedge ddr_bridge_reset_n) begin
        if(!ddr_bridge_reset_n) begin
            request_sync<=0;ack<=0;reply_hold<=0;dstate<=0;
            result_code<=0;bist_start<=0;
        end else begin
            request_sync<={request_sync[0],request};
            bist_start<=0;
            case(dstate)
                0: if(request_sync[1]!=ack) begin
                    result_code<=0;
                    // No BIST start path in this external-owner candidate.
                    dstate<=1;
                end
                1: dstate<=2; // Let the BIST consume start before taking snapshot.
                2: begin
                    reply_hold<={result_code,status_words};
                    ack<=request_sync[1];dstate<=0;
                end
            endcase
        end
    end
    // Reads remain stable through AXI response backpressure. The parent mux
    // must retain this selection until the next accepted read address.
    always @(posedge hclk or negedge hrst_n) begin
        if(!hrst_n) begin rd_select<=0;rd_data<=0;end
        else if(arvalid&&arready) begin
            rd_select<=(araddr[15:8]==8'h20);
            case(araddr[7:0])
                8'h00: rd_data<=32'h44445232;
                8'h04: rd_data<={24'b0,2'b0,rejected,reset_held,timed_out,valid,busy,host_bridge_reset_n};
                8'h08: rd_data<=0;
                8'h0c: rd_data<=snapshot_seq;
                8'h10: rd_data<={12'b0,init_sync}; // advisory, not atomic MCU status
                8'h14: rd_data<=32'd65536;
                8'h18: rd_data<=32'h00010000; // Original snapshot ABI v1
                8'h1c: rd_data<=32'h00000001; // Capability: external-owner, START rejected
                default: begin
                    if(araddr[7:0]>=8'h40 && araddr[7:0]<=8'h78 && araddr[1:0]==0)
                        rd_data<=snapshot[((araddr[7:0]-8'h40)>>2)*32+:32];
                    else rd_data<=0;
                end
            endcase
        end
    end
endmodule

