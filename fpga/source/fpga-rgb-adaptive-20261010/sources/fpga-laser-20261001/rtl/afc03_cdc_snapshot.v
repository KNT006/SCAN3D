`timescale 1ns/1ps
// Source captures a whole bus on a synchronized request. Data stays fixed until
// the next request, issued only after the destination has consumed this reply.
module afc03_cdc_snapshot #(parameter WIDTH=32)(
    input wire src_clk,dst_clk,arst_n,
    input wire [WIDTH-1:0] src_data,
    output reg [WIDTH-1:0] dst_data
);
    wire srst_n,drst_n;
    afc03_reset_release u_src_reset(src_clk,arst_n,srst_n);
    afc03_reset_release u_dst_reset(dst_clk,arst_n,drst_n);
    reg req,ack;
    reg [1:0] req_sync,ack_sync;
    reg [WIDTH-1:0] held;
    reg waiting;
    always @(posedge src_clk or negedge srst_n)
        if(!srst_n) begin req_sync<=0;ack<=0;held<=0;end
        else begin
            req_sync<={req_sync[0],req};
            if(req_sync[1]!=ack) begin held<=src_data;ack<=req_sync[1];end
        end
    always @(posedge dst_clk or negedge drst_n)
        if(!drst_n) begin req<=0;ack_sync<=0;dst_data<=0;waiting<=0;end
        else begin
            ack_sync<={ack_sync[0],ack};
            if(!waiting) begin req<=~req;waiting<=1;end
            else if(ack_sync[1]==req) begin dst_data<=held;waiting<=0;end
        end
endmodule

// Falling-edge consumers must also release reset on their own active edge.
module afc03_reset_release_negedge(input wire clk,arst_n,output wire rst_n);
    reg [2:0] pipe;
    always @(negedge clk or negedge arst_n)
        if(!arst_n) pipe<=0;
        else pipe<={pipe[1:0],1'b1};
    assign rst_n=pipe[2];
endmodule

module afc03_reset_release(input wire clk,arst_n,output wire rst_n);
    reg [2:0] pipe;
    always @(posedge clk or negedge arst_n)
        if(!arst_n) pipe<=0;
        else pipe<={pipe[1:0],1'b1};
    assign rst_n=pipe[2];
endmodule
