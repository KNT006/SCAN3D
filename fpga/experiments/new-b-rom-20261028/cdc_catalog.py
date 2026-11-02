"""Candidate FIFO inventory: host=125MHz, DDR=100MHz."""
HOST = '*/pcie_user_clk'
DDR = 'u_ddr_test/u_ddr/dfi_clk'
FIFOS = []
for bank in ('bg', 'live'):
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
