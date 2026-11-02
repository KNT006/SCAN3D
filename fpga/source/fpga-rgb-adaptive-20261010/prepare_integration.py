from pathlib import Path
H=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010')
p=H/'rtl/afc03_laser_csr_bridge.sv';s=p.read_text().replace("8'h0c:rd_data<=request_id;", "8'h0c:rd_data<=request_id;\n    8'h34:rd_data<=(PAGE==12'h024)?32'h9c744450:32'd0;\n    8'h38:rd_data<=(PAGE==12'h024)?32'h0046000b:32'd0;");p.write_text(s)
base=H.parent/'fpga-capture-pipeline-20261004'
s=(base/'tb_board.sv').read_text().replace('32\'h00050000','32\'h00060000').replace('.RESULT_DEPTH(64)','.RESULT_DEPTH(512)').replace('count!=16','count!=24');(H/'tb_board.sv').write_text(s)
s=(base/'test_integration.py').read_text();a=s.index('t=(OLD/');b=s.index("ss.append(H/'tb_board.sv')");s=s[:a]+s[b:];s=s.replace('(16,8,8)','(24,8,8)').replace('0x50000','0x60000');(H/'test_integration.py').write_text(s)
