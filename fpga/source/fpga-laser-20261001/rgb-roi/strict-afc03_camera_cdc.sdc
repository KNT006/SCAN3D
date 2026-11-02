# Only asynchronous assertion pins of explicit release synchronizers.
set_false_path -to [get_pins {u_*snapshot/u_*_reset/pipe_reg*.*sr u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/u_byte_reset/pipe_reg*.*sr u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/gen_channel_wrapper*u_csi_rx_hs_data_phy/gen_ph1a*u_sample_reset/pipe_reg*.*sr u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/u_csi_rx_clock_det/u_watchdog/u_*_reset/pipe_reg*.*sr}]
set_false_path -from [get_regs {u_*snapshot/req}] -to [get_regs {u_*snapshot/req_sync[0]}]
set_false_path -from [get_regs {u_*snapshot/ack}] -to [get_regs {u_*snapshot/ack_sync[0]}]
# Data precedes capture by >=2 destination periods (minimum 16ns at 125MHz).
set_false_path -to [get_regs {u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/u_csi_rx_clock_det/u_watchdog/beat_sync[0] u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/u_csi_rx_clock_det/u_watchdog/enable_sync[0]}]
set_false_path -to [get_regs {cam_i2c_done_sync[0] cam_delay_done_sync[0] mipi_toggle_sync[0] dbg_link_up_sync[0]}]
set_false_path -to [get_pins {u_cam_video_source/u_mipi_csi_rx/u_input_reset/pipe_reg*.*sr u_cam_video_source/u_mipi_csi_rx/u_csi_rx_vid2stream/hs_data_fifo/asy_*_rst*_reg*.*sr}]
set_false_path -to [get_regs {u_cam_video_source/u_mipi_csi_rx/enable_sync[0]}]
# Async assertion only; release and all downstream functional resets stay timed.
set_false_path -to [get_pins {u_mipi_monitor_reset/pipe_reg*.*sr */u_al_pcie_ip_msi_pipeline/u_msi_negedge_reset/pipe_reg*.*sr}]
# Gray-coded FIFO pointers are registered, then sampled by two receiving FFs.
# Bound bus flight to < one fastest (125MHz) cycle. Clock selectors restrict
# this exception to the crossing, leaving both local synchronizer stages timed.
set_max_delay -datapath_only -from [get_clocks {*/pcie_user_clk}] -through [get_nets {u_cam_video_source/u_mipi_csi_rx/u_csi_rx_vid2stream/hs_data_fifo/rd_to_wr_cross_inst/primary_addr_gray_reg*}] -to [get_clocks {u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/u_rx_clk_gen/U_io_clk_div_1.clkdivout}] 6
set_max_delay -datapath_only -from [get_clocks {u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/u_rx_clk_gen/U_io_clk_div_1.clkdivout}] -through [get_nets {u_cam_video_source/u_mipi_csi_rx/u_csi_rx_vid2stream/hs_data_fifo/wr_to_rd_cross_inst/primary_addr_gray_reg*}] -to [get_clocks {*/pcie_user_clk}] 6
set_false_path -to [get_pins {u_cam_i2c_cfg/X_ui_i2c/u_i2c_reset/pipe_reg*.*sr}]
# TD packs these three 150MHz reset FFs beside FIFO LUTs and renames cells.
# Scope the PCIe-originating async reset to these synchronizer registers;
# their local 150MHz stage-to-stage and downstream release paths stay timed.
set_false_path -from [get_clocks {*/pcie_user_clk}] -to [get_regs {u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/u_csi_rx_clock_det/u_watchdog/u_ref_reset/pipe*}]
set_max_delay -datapath_only -from [get_pins -of [get_nets {u_dbg_snapshot/held*}] -filter {DIRECTION == output}] -to [get_clocks {u_sgdma_pll/pll_inst.clkc[1]}] 12
set_max_delay -datapath_only -from [get_pins -of [get_nets {u_cam_config_snapshot/held*}] -filter {DIRECTION == output}] -to [get_clocks {u_ui_pll/pll_inst.clkc[2]}] 12
set_max_delay -datapath_only -from [get_pins -of [get_nets {u_cam_status_snapshot/held*}] -filter {DIRECTION == output}] -to [get_clocks {*/pcie_user_clk}] 12
set_max_delay -datapath_only -from [get_pins -of [get_nets {u_cam_eye_snapshot/held*}] -filter {DIRECTION == output}] -to [get_clocks {*/pcie_user_clk}] 12
