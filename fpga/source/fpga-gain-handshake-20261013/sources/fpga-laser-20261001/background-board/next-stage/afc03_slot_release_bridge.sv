`timescale 1ns/1ps
// One release in flight. Attach the accepted immutable identity to the legacy
// slots' one-cycle release_ok. A protocol_error is sticky until common reset.
// No timeout replay: owner retains its pin claim until a matching success ACK.
module afc03_slot_release_bridge #(
 parameter TIMEOUT_CYCLES=1000
)(
 input wire clk,rst_n,
 input wire release_valid,output wire release_ready,
 input wire release_slot,input wire [127:0] release_header,
 input wire [31:0] release_epoch,
 output wire slots_release_valid,slots_release_slot,
 output wire [127:0] slots_release_header,output wire [31:0] slots_release_epoch,
 input wire slots_release_ok,slots_protocol_error,
 output reg ack_valid,ack_ok,ack_slot,output reg [127:0] ack_header,
 output reg [31:0] ack_epoch,output reg recovery_required
);
 reg pending;
 reg saved_slot;
 reg [127:0] saved_header;
 reg [31:0] saved_epoch,watchdog;
 assign release_ready=rst_n&&!pending&&!ack_valid&&!recovery_required;
 assign slots_release_valid=release_valid&&release_ready;
 assign slots_release_slot=release_slot;
 assign slots_release_header=release_header;
 assign slots_release_epoch=release_epoch;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   pending<=0;saved_slot<=0;saved_header<=0;saved_epoch<=0;watchdog<=0;
   ack_valid<=0;ack_ok<=0;ack_slot<=0;ack_header<=0;ack_epoch<=0;recovery_required<=0;
  end else begin
   ack_valid<=0;
   if(slots_release_valid)begin
    pending<=1;saved_slot<=release_slot;saved_header<=release_header;saved_epoch<=release_epoch;watchdog<=0;
   end
   if(pending)begin
    if(slots_release_ok||slots_protocol_error||watchdog>=TIMEOUT_CYCLES-1)begin
     ack_valid<=1;ack_ok<=slots_release_ok&&!slots_protocol_error;
     ack_slot<=saved_slot;ack_header<=saved_header;ack_epoch<=saved_epoch;pending<=0;
     if(!slots_release_ok||slots_protocol_error)recovery_required<=1;
    end else watchdog<=watchdog+1'b1;
   end
   if(slots_protocol_error)recovery_required<=1;
   if(slots_release_ok&&!pending)recovery_required<=1;
  end
 end
endmodule
