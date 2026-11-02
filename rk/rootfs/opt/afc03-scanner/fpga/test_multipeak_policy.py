import numpy as np
from multipeak_policy import select_centers

def run(rows,signals,valid=None):
    uv=np.array(rows,float)
    return select_centers(uv,signals,np.ones(len(rows),bool) if valid is None else valid)

# The weak candidate is geometrically plausible, but only strong has advantage.
r=run([[10,0],[10,1],[10,2],[10,3],[40,3]],[100,100,100,248,59])
assert r['base_indices'].tolist()==[0,1,2] and r['recovered_indices'].tolist()==[3]
# Equal bright peaks, weak >=80, or insufficient ratio must remain unresolved.
for pair in [(100,100),(248,80),(100,40)]:
 assert len(run([[10,0],[10,1],[10,2],[10,3],[40,3]],[100,100,100,*pair])['recovered_indices'])==0
# Recovered row 3 must not become the third anchor for row 5.
r=run([[10,0],[10,1],[10,2],[10,3],[40,3],[10,5],[40,5]], [100,100,100,248,59,248,59])
assert r['recovered_indices'].tolist()==[3]
# Geometry-invalid single rows are not anchors; invalid strong points never return.
assert len(run([[10,0],[10,1],[10,2],[10,3],[40,3]],[100,100,100,248,59],[1,1,0,1,1])['recovered_indices'])==0
assert len(run([[10,0],[10,1],[10,2],[10,3],[40,3]],[100,100,100,248,59],[1,1,1,0,1])['recovered_indices'])==0
print('PASS: threshold boundaries, geometry, unchanged single rows, no recursive rescue')
