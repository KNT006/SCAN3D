# Exact asynchronous assertion pins only; release paths remain timed.
set_false_path -to [get_pins {u_dbg_snapshot/arst_n_syn_38.asr u_cam_config_snapshot/arst_n_syn_38.asr u_sgdma_subsys/u_sgdma_ip/u_rq_mux/u_rqinfo_fifo/empty_flag_n1_syn_9.asr u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/u_csi_rx_clock_det/u_watchdog/u_ext_reset/pipe_reg[2]_syn_2.asr}]
