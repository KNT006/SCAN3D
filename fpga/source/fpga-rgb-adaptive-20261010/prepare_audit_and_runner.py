from pathlib import Path
H=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010');B=H.parent/'fpga-capture-pipeline-20261004'
for name in ('audit.py','audit-routed.tcl','inspect_reset.py','validate_reset_mapping.py','check_cdc.py','program.py'):
 s=(B/name).read_text();s=s.replace(B.as_posix(),H.as_posix())
 if name=='check_cdc.py':s=s.replace('from prepare_build import','from cdc_catalog import')
 (H/name).write_text(s)
s=(B/'prepare_build.py').read_text().split("if __name__=='__main__':")[0];(H/'cdc_catalog.py').write_text(s)
p=H/'rk-before-scan3d/runner.py';s=p.read_text(encoding='utf-8');s=s.replace("final_extraction='fpga-brightcore-rk-ground-branch-v2'", "final_extraction='pending-hardware-version'")
s=s.replace("        if index==0:\n            require(report['scan_ready']", "        if index==0:\n            versions={r['strategy']['version'] for r in report['lasers'].values()}\n            require(len(versions)==1,'A/B strategy versions differ')\n            state['final_extraction']=next(iter(versions))\n            cfg['final_extraction']=state['final_extraction'];cfg['stripe_settings']=report['lasers']['A']['strategy']['stripe_settings'];write(output/'bundle/config.json',cfg)\n            require(report['scan_ready']")
s=s.replace("saturated=f['saturated'],position=", "saturated=f['saturated'],adaptive_origin=f['adaptive_origin'] if 'adaptive_origin' in f.files else np.zeros(len(f['uv']),np.uint8),threshold=f['threshold'] if 'threshold' in f.files else np.full(len(f['uv']),40,np.uint8),position=")
(H/'scan3d').mkdir(exist_ok=True);(H/'scan3d/runner.py').write_text(s,encoding='utf-8')
