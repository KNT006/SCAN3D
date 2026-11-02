`timescale 1ns/1ps
// Observe a divided heartbeat rather than sampling the raw external clock.
// Ref clock may continue when camera clock stops. Reset asserts on timeout;
// each receiving domain separately synchronizes its reset release.
module afc03_clock_watchdog #(parameter TIMEOUT=250)(
    input wire ref_clk,ext_clk,enable,arst_n,
    output wire alive
);
    wire rrst_n,erst_n;
    afc03_reset_release u_ref_reset(ref_clk,arst_n,rrst_n);
    afc03_reset_release u_ext_reset(ext_clk,arst_n,erst_n);
    reg [4:0] heartbeat;
    reg [1:0] beat_sync,enable_sync;
    reg last_beat,detected;
    reg [7:0] silence;
    always @(posedge ext_clk or negedge erst_n)
        if(!erst_n) heartbeat<=0;else heartbeat<=heartbeat+1'b1;
    always @(posedge ref_clk or negedge rrst_n)
        if(!rrst_n) begin
            beat_sync<=0;enable_sync<=0;last_beat<=0;silence<=0;detected<=0;
        end else begin
            beat_sync<={beat_sync[0],heartbeat[4]};
            enable_sync<={enable_sync[0],enable};
            last_beat<=beat_sync[1];
            if(!enable_sync[1]) begin silence<=0;detected<=0;end
            else if(last_beat!=beat_sync[1]) begin silence<=0;detected<=1;end
            else if(silence<TIMEOUT) silence<=silence+1'b1;
            else detected<=0;
        end
    assign alive=detected && enable_sync[1] && rrst_n;
endmodule
