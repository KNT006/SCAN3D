"""Derive the unchanged logical-net proof checks for the extra COLOR bank.

Writes only into the candidate work directory. The qualified checker and
constraints remain untouched; this does not declare whole-design timing valid.
"""
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1] / 'source/fpga-gain-handshake-20261013'


def prepare(work):
    work = Path(work).resolve()
    assert (work / 'color-cache-candidate.json').is_file()
    out = work / 'fpga-gain-handshake-20261013'
    catalog = '''"""Candidate FIFO inventory: host=125MHz, DDR=100MHz."""
HOST = '*/pcie_user_clk'
DDR = 'u_ddr_test/u_ddr/dfi_clk'
FIFOS = []
for bank in ('bg', 'live', 'color'):
    for suffix, wr, rd in (
        ('bridge/commands', HOST, DDR), ('bridge/responses', DDR, HOST),
        ('capture/commands', DDR, HOST), ('capture/descriptors', HOST, DDR),
        ('capture/pixels', HOST, DDR), ('capture/final_status', HOST, DDR)):
        FIFOS.append((bank + '/' + suffix, wr, rd))
FIFOS += [('bridge/commands', HOST, DDR), ('bridge/responses', DDR, HOST),
          ('result_dma/queue', DDR, HOST)]

def pointer_query(name,direction,kind):
    inst='u_laser/'+name
    n=5 if name=='result_dma/queue' else 9 if name.endswith('capture/pixels') else 2
    if kind=='launch':
        return 'get_regs {'+' '.join(f'{inst}/{direction}_{e}[{i}]' for i in range(n) for e in ['gray','binary'])+'}'
    return 'get_regs {'+' '.join(f'{inst}/{direction}_gray_{kind}[{i}]' for i in range(n))+'}'
'''
    source = (BASE / 'check_cdc.py').read_text()
    edits = {
        'len(groups) != 30': 'len(groups) != 42',
        'count != 94': 'count != 132',
        'Required 30 groups / 94 cross / 94 local setup / 94 local hold':
            'Required 42 groups / 132 cross / 132 local setup / 132 local hold',
        'Only the 94 explicit-net Gray crossings': 'Only the 132 explicit-net Gray crossings',
        "sdc_sha256=sha(H / 'laser-cdc.sdc'),":
            "sdc_sha256=sha(H / 'laser-cdc.sdc'), color_sdc_sha256=sha(H / 'color-cdc.sdc'),",
    }
    for old, new in edits.items():
        assert source.count(old) == 1, ('Review baseline checker changes', old)
        source = source.replace(old, new)
    (out / 'cdc_catalog.py').write_text(catalog)
    (out / 'check_color_cdc.py').write_text(source)
    print(out / 'check_color_cdc.py')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', required=True, type=Path)
    prepare(parser.parse_args().work)
