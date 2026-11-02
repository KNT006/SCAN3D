if {[catch {
connect_cable -host_name 127.0.0.1:5555
download -bit {D:/PCle/FPGA_SCAN3D/fpga/experiments/new-b-rom-20261028/candidate-20261028-205122/afc03-new-B-rom-20261028.bit} -mode JTAG -spd 6 -cable 0
} reason]} {puts stderr $reason; exit 1}
exit 0
