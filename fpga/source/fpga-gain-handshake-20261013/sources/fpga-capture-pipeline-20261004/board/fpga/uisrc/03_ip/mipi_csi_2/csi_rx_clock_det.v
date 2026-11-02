module csi_rx_clock_det (
    input I_ref_clock,I_ext_clock,I_enable,I_reset_in,
    output O_reset_out
);
afc03_clock_watchdog u_watchdog (
    .ref_clk(I_ref_clock),.ext_clk(I_ext_clock),.enable(I_enable),
    .arst_n(I_reset_in),.alive(O_reset_out)
);
endmodule
