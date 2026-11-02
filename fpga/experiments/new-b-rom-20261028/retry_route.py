"""Preserve first route and guide MIPI reset timing from placement onward."""
from pathlib import Path
import shutil,json,subprocess,sys
HERE=Path(__file__).resolve().parent
HOME=Path('D:/PCle/_b28/fpga-gain-handshake-20261013')
RUN=HOME/'board/fpga/imx415_pcie_4k_Runs/phy_1'
archive=HOME/'first-route-full';assert not archive.exists()
shutil.copytree(RUN,archive)
for n in ['build-result.json','timing-qualification.json','eco-result.json','strict-audit.log','inspect-reset.log','reset-mapping-validation.json','monitor-alias-validation.json']:
    if (HOME/n).exists():shutil.copy2(HOME/n,archive/n)
sample='u_cam_video_source/u_mipi_csi_rx/u_csi_rx_phy/gen_channel_wrapper[0]$u_csi_rx_hs_data_phy/gen_ph1a$sample_reset_n'
pins=' '.join(f'mipi_data_hs_p[{i}]_syn_2.rst' for i in range(4))
budget=HOME/'new-B-reset-placement.sdc'
budget.write_text('# Optimization-only budget for the measured MIPI reset release bottleneck.\n# Final audit removes this extra budget and retains normal recovery/removal checks.\nset_max_delay -from [get_regs {'+sample+'}] -to [get_pins {'+pins+'}] 3.2\n')
cfg=RUN/'settings.cfg';s=cfg.read_text();assert 'new-B-reset-placement.sdc' not in s
s+='\nset sp 1\nlappend SDCList {'+budget.as_posix()+'}\n'
cfg.write_text(s)
shutil.copy2(budget,HERE/budget.name)
print('Preserved first route; restarting placement with 3.2ns optimization budget.',flush=True)
raise SystemExit(subprocess.call([sys.executable,str(HERE/'route.py')]))
