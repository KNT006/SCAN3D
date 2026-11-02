from pathlib import Path
import json,shutil,xml.etree.ElementTree as ET
H=Path(__file__).resolve().parent;R=H.parent;B=R/'fpga-capture-pipeline-20261004'
(H/'rtl').mkdir(exist_ok=True);(H/'host').mkdir(exist_ok=True)
custom=['laser_full_row_stream.v','row_record_packer.v','afc03_tile_laser_pipeline.sv','afc03_pinned_frame_pipeline.sv','afc03_frame_tile_sequencer.sv']
for p in (B/'rtl').iterdir():
 if p.is_file():shutil.copy2(p,H/'rtl'/p.name)
for stage in ('syn_1','phy_1'):
 src=B/'board/fpga/imx415_pcie_4k_Runs'/stage;dst=H/'board/fpga/imx415_pcie_4k_Runs'/stage;dst.mkdir(parents=True,exist_ok=True)
 tree=ET.fromstring((src/'imx415_pcie_4k.prj').read_text(encoding='latin1').replace('&','&amp;'))
 for e in tree.iter('File'):
  p=Path(e.attrib['Path']);p=p if p.is_absolute() else (src/p).resolve()
  if p.name in custom and not (H/'rtl'/p.name).exists():shutil.copy2(p,H/'rtl'/p.name)
  if (H/'rtl'/p.name).exists():e.attrib['Path']=(H/'rtl'/p.name).as_posix()
  else:
   target=H/'sources'/p.relative_to(R);target.parent.mkdir(parents=True,exist_ok=True)
   if not target.exists():shutil.copy2(p,target)
   e.attrib['Path']=target.as_posix()
 (dst/'imx415_pcie_4k.prj').write_text(ET.tostring(tree,encoding='unicode').replace('&amp;','&'),encoding='latin1')
 for p in src.iterdir():
  if p.suffix in ('.tcl','.cfg','.sdc','.adc'):
   (dst/p.name).write_text(p.read_text(encoding='latin1').replace(B.as_posix(),H.as_posix()),encoding='latin1')
for name in ['laser-cdc.sdc','mapped-reset.sdc','optimize-reset-margin.sdc']:
 if (B/name).exists():shutil.copy2(B/name,H/name)
for p in (B/'host').glob('*.py'):shutil.copy2(p,H/'host'/p.name)
(H/'work-state.json').write_text(json.dumps(dict(status='implementing',baseline=str(B),plan=['ABI6 all qualified candidates, limit16 with explicit overflow','FPGA calibrated conservative pre-distance spatial mask; minimum25','RK local RGB100..160 ->25..40; protect fixed40 branch','archive exact comparison, compile, timing, SRAM, Flash'],production_unchanged=True),indent=2))
print(H)
