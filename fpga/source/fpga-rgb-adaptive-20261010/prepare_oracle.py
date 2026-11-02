from pathlib import Path
import ast
H=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010');p=H.parent/'pc-adaptive-stripes-20261009/adaptive.py';s=p.read_text(encoding="utf-8");tree=ast.parse(s)
wanted={'suppress','evaluate','core','spatial_lut','certainly_outside'}
body='"""Frozen PC oracle helpers; verification only, never production extraction."""\nimport cv2,numpy as np\n\n'
for n in tree.body:
 if isinstance(n,ast.FunctionDef) and n.name in wanted:body+=ast.get_source_segment(s,n)+'\n\n'
(H/'host/spatial_reference.py').write_text(body,encoding="utf-8")

