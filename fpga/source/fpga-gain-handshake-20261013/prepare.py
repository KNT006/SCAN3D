from pathlib import Path
import shutil,json,hashlib
H=Path(__file__).parent;OLD=H.parent/'fpga-rgb-adaptive-20261010'
assert not (H/'sources').exists(),'Candidate already prepared'
for rel in ['rtl','sources','board/fpga/uisrc','board/fpga/al_ip']:
 shutil.copytree(OLD/rel,H/rel)
for stage in ['syn_1','phy_1']:
 src=OLD/'board/fpga/imx415_pcie_4k_Runs'/stage;dst=H/'board/fpga/imx415_pcie_4k_Runs'/stage;dst.mkdir(parents=True)
 for p in src.iterdir():
  if p.name in ['afc03_ddr_cfg_rom.txt','afc03_ddr_mcu_rom.txt']:
   shutil.copy2(p,dst/p.name)
  if p.suffix in ['.prj','.tcl','.cfg','.sdc','.adc']:
   (dst/p.name).write_bytes(p.read_bytes().replace(OLD.as_posix().encode(),H.as_posix().encode()).replace(str(OLD).encode(),str(H).encode()))
for p in OLD.iterdir():
 if p.suffix in ['.sdc'] or p.name in ['audit.py','audit-routed.tcl','cdc_catalog.py','check_cdc.py','inspect_reset.py','validate_reset_mapping.py','bitgen.py','bitgen.tcl','copy_roms.py']:
  (H/p.name).write_bytes(p.read_bytes().replace(OLD.as_posix().encode(),H.as_posix().encode()).replace(str(OLD).encode(),str(H).encode()))
rel=Path('sources/fpga-capture-pipeline-20261004/board/fpga/uisrc/03_ip/ui_imx415_cfg/ui_cfg_imx415.v')
p=H/rel;s=p.read_bytes();(H/'ui_cfg_imx415.before.v').write_bytes(s)
# Keep initial camera mode configuration and its existing start-register refresh.
# Serialize gain transactions with that refresh, and acknowledge only a real gain transaction.
s=s.replace(b'wire \t\tic_busy',b'wire \t\tiic_busy')
s=s.replace(b'assign      O_bus_error = O_iic_bus_error;',b'''reg ae_active;
reg ae_error;
reg [7:0] ae_data_latched;
assign      O_bus_error = O_iic_bus_error | ae_error;''')
s=s.replace(b"        O_ae_cfg_done <= 1'b1;",b"        O_ae_cfg_done <= 1'b1;\n        ae_active <= 1'b0;\n        ae_error <= 1'b0;\n        ae_data_latched <= 8'd0;",1)
s=s.replace(b'    else begin\r\n        // ---',b'    else begin\r\n        if (ae_active && O_iic_bus_error) ae_error <= 1\'b1;\r\n        // ---')
s=s.replace(b"            O_ae_cfg_done<= 1'b1;",b"            O_ae_cfg_done<= 1'b1;\n            ae_active <= 1'b0;\n            ae_error <= 1'b0;")
start=s.index(b'        else if(cnt== 1000_000)begin')
end=s.index(b'        else if((O_cfg_done&O_cfg_done_r&O_ae_cfg_done)',start)
s=s[:start]+b'''        else if(I_ae_req && O_ae_cfg_done && O_cfg_done && O_cfg_done_r &&
                REG_SIZE == REG_SIZE_AE) begin
            // Only accept after startup register selection has settled to AE.
            // Latch the value: a later host write must not change this transaction.
            O_ae_cfg_done <= 1'b0;
            ae_active <= 1'b1;
            ae_error <= 1'b0;
            ae_data_latched <= I_ae_data;
            reg_index <= 0;
        end
        else if(cnt == 1000_000 && O_ae_cfg_done && !I_ae_req) begin
            // Never preempt an accepted or pending gain request with startup refresh.
            O_cfg_done_r <= 1'b0;
            reg_index <= 0;
        end
'''+s[end:]
needle=b"\t\t\treg_index<= reg_index + 1'b1;"
assert needle in s
s=s.replace(needle,b'''            if (ae_active) begin
                // This state follows the actual I2C busy assertion/deassertion.
                // No startup/config completion is allowed to acknowledge gain.
                O_ae_cfg_done <= 1'b1;
                ae_active <= 1'b0;
            end
'''+needle)
s=s.replace(b"{16'h3090, I_ae_data}",b"{16'h3090, ae_data_latched}")
assert b"ae_active <= 1'b0" in s and b'if (ae_active && O_iic_bus_error)' in s
p.write_bytes(s)
# The prj selects the source above. Mirror the editable board-tree copy for consistency.
mirror=H/'board/fpga/uisrc/03_ip/ui_imx415_cfg/ui_cfg_imx415.v';mirror.write_bytes(s)
(H/'change-manifest.json').write_text(json.dumps(dict(baseline=str(OLD),modified_source=str(p),before_sha256=hashlib.sha256((H/'ui_cfg_imx415.before.v').read_bytes()).hexdigest(),after_sha256=hashlib.sha256(s).hexdigest(),production_modified=False),indent=2))
print(p)
