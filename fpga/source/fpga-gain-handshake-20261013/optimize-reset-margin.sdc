# Optimization-only stricter budget; final audit removes this constraint.
set_max_delay -from [get_pins {u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/gen_channel_wrapper[0]$u_csi_rx_hs_data_phy/gen_ph1a$u_sample_reset/pipe_reg[2]_syn_2.clk}] -to [get_pins {mipi_data_hs_p[0]_syn_2.rst mipi_data_hs_p[1]_syn_2.rst mipi_data_hs_p[2]_syn_2.rst mipi_data_hs_p[3]_syn_2.rst}] 3.8
