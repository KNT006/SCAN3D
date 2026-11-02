if {[catch {
connect_cable -host_name 127.0.0.1:5555
download -bit {F:/AAA_FPGA/afc03-esp32-motor/fpga-gain-handshake-20261013/qualified-20261013-141151/afc03-gain-handshake-v1.bit} -mode program_spi -v -spd 6 -cable 0
} reason]} {puts stderr $reason; exit 1}
exit 0
