`timescale 1ns/1ps
// Whole-frame admission BEFORE the marker/DDR fork. A rejected SOF never
// consumes a capture token. Once admitted, readiness cannot revoke a frame.
// One elastic output stage; payload/sidebands remain stable under backpressure.
module afc03_capture_admission(
 input wire clk,reset_n,frame_sink_ready,
 input wire [127:0] s_data,input wire s_valid,s_sof,s_eol,
 output wire s_ready,
 output reg [127:0] m_data,output reg m_valid,m_sof,m_eol,
 input wire m_ready,
 output reg [31:0] pass_count,drop_count
);
 reg passing;
 wire selected=s_sof?frame_sink_ready:passing;
 assign s_ready=reset_n&&(!m_valid||m_ready);
 always @(posedge clk or negedge reset_n)begin
  if(!reset_n)begin
   passing<=0;m_data<=0;m_valid<=0;m_sof<=0;m_eol<=0;
   pass_count<=0;drop_count<=0;
  end else begin
   if(m_ready)m_valid<=0;
   if(s_valid&&s_ready)begin
    if(s_sof)begin
     passing<=frame_sink_ready;
     if(frame_sink_ready)pass_count<=pass_count+1'b1;
     else drop_count<=drop_count+1'b1;
    end
    if(selected)begin m_data<=s_data;m_valid<=1;m_sof<=s_sof;m_eol<=s_eol;end
   end
  end
 end
endmodule
