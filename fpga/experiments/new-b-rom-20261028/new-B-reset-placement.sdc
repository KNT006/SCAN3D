# Optimization-only budget for the measured MIPI reset release bottleneck.
# Final audit removes this extra budget and retains normal recovery/removal checks.
set_max_delay -from [get_regs {u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/gen_channel_wrapper[0]$u_csi_rx_hs_data_phy/gen_ph1a$sample_reset_n}] -to [get_pins {mipi_data_hs_p[0]_syn_2.rst mipi_data_hs_p[1]_syn_2.rst mipi_data_hs_p[2]_syn_2.rst mipi_data_hs_p[3]_syn_2.rst}] 3.2
