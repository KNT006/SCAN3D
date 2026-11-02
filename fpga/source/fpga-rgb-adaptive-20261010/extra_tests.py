from pathlib import Path
H=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010')
s=(H/'test_core.py').read_text(encoding='utf-8-sig').replace('for idx in (0,17,34,59):','for idx in ():').replace('k*38','k*30').replace('core-vectors','capacity-vectors').replace('core-vector-manifest','capacity-vector-manifest').replace('tb_core.sv','tb_capacity.sv').replace('core.vvp','capacity.vvp').replace('core-test.log','capacity-test.log').replace('core-validation','capacity-validation')
(H/'test_capacity.py').write_text(s,encoding='utf-8');(H/'tb_capacity.sv').write_text((H/'tb_core.sv').read_text().replace('core-vectors','capacity-vectors'))
p=H/'test_replay.py';s=p.read_text(encoding='utf-8-sig');s=s.replace("  payload=b''.join(r.encode() for r in records_for_images(im(folder/label),off,h,adapter))", "  payload=(target/f'{index:03d}-{label}.bin').read_bytes() if '--cached' in sys.argv else b''.join(r.encode() for r in records_for_images(im(folder/label),off,h,adapter))")
p.write_text(s,encoding='utf-8')
