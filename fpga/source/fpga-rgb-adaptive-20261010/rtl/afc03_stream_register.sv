`timescale 1ns/1ps
// One elastic beat, all payload and sidebands stay together under backpressure.
// Breaks asynchronous FIFO read -> geometry/line-check combinational paths.
module afc03_stream_register #(parameter WIDTH=130)(
 input wire clk,reset_n,
 input wire [WIDTH-1:0] s_data,input wire s_valid,output wire s_ready,
 output reg [WIDTH-1:0] m_data,output reg m_valid,input wire m_ready
);
 assign s_ready=reset_n&&(!m_valid||m_ready);
 always @(posedge clk or negedge reset_n)begin
  if(!reset_n)m_valid<=0;
  else if(s_ready)m_valid<=s_valid;
 end
 // Payload deliberately not reset; m_valid gates every consumer.
 always @(posedge clk)if(s_ready&&s_valid)m_data<=s_data;
endmodule
