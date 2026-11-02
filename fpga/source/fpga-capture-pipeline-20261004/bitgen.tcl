import_device ph1_90.db -package PH1A90SEG324 -speed 2
open_project imx415_pcie_4k.prj -noanalyze
import_db strict-laser-pr.db
bitgen -bit afc03-atomic-capture-overlap-v2.bit
exit 0
