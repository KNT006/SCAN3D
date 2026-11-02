import_device ph1_90.db -package PH1A90SEG324 -speed 2
open_project imx415_pcie_4k.prj -noanalyze
import_db imx415_pcie_4k_pr.db
clear_sdc -user
read_sdc -ip afc03_ddr {F:/AAA_FPGA/afc03-esp32-motor/fpga-laser-20261001/vendor-ip/afc03_ddr/afc03_ddr.sdc}
read_sdc -ip al_pcie_ip ../../al_ip/PH1_LOGIC_PCIE.sdc
read_sdc ref100.sdc
read_sdc ../../uisrc/04_pin/imx415_pcie.sdc
read_sdc {F:/AAA_FPGA/afc03-esp32-motor/fpga-laser-20261001/background-board/strict-background-legacy-host.sdc}
read_sdc {F:/AAA_FPGA/afc03-esp32-motor/fpga-laser-20261001/rgb-roi/strict-afc03_camera_cdc.sdc}
read_sdc {F:/AAA_FPGA/afc03-esp32-motor/fpga-gain-handshake-20261013/laser-cdc.sdc}
read_sdc {F:/AAA_FPGA/afc03-esp32-motor/fpga-gain-handshake-20261013/mapped-reset.sdc}
read_sdc {F:/AAA_FPGA/afc03-esp32-motor/fpga-gain-handshake-20261013/optimize-reset-margin.sdc}
update_timing -mode final
report_timing_summary -file laser-before-eco.timing
phys_opt -post_route -effort ultra
fix_hold
update_timing -mode final
report_timing_summary -file laser-after-eco.timing
report_area -io_info -file laser-after-eco.area
check_timing -verbose -file laser-after-eco-check.timing
export_db imx415_pcie_4k_eco.db
exit 0
