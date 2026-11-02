# Baseline DDR constraints; only constant removed START opcode crossing omitted.
# Only the first stages of explicit 2-FF synchronizers are asynchronous data
# endpoints. Keep stage-1 -> stage-2 paths timed. No whole-clock false paths.
set_false_path -from [get_regs {u_ddr_host/request}] -to [get_regs {u_ddr_host/request_sync[0]}]
set_false_path -from [get_regs {u_ddr_host/ack}] -to [get_regs {u_ddr_host/ack_sync[0]}]
set_false_path -to [get_regs {u_ddr_host/init_meta*}]
# Async reset may enter only the release synchronizer reset pins untimed.
# Their clocked outputs -> functional registers' resets remain timed.
set_false_path -to [get_pins {u_ddr_host/host_reset_pipe_reg*.*sr u_ddr_host/ddr_reset_pipe_reg*.*sr u_ddr_test/reset_pipe_reg*.*sr}]
# Bundled opcode precedes destination use by >=2 DFI periods (20ns).
# Bundled reply precedes host capture by >=2 host periods (16ns).
# Bound data flight to 12ns, rather than excluding these wide data buses.
# The TD datapath_only option also removes irrelevant asynchronous hold checks.
set_max_delay -datapath_only -from [get_pins -of [get_nets {u_ddr_host/reply_hold*}] -filter {DIRECTION == output}] -to [get_clocks {*/pcie_user_clk}] 12
