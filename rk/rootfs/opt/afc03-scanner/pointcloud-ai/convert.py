"""Convert the pinned U2NETP ONNX for RK3576; run with RKNN Toolkit2."""
from pathlib import Path
from rknn.api import RKNN

root = Path(__file__).parent
rknn = RKNN(verbose=False)
try:
    rknn.config(target_platform='rk3576', optimization_level=3)
    assert rknn.load_onnx(model=str(root/'model/u2netp.onnx'), outputs=['1959']) == 0
    assert rknn.build(do_quantization=False) == 0
    assert rknn.export_rknn(str(root/'model/u2netp-rk3576.rknn')) == 0
finally:
    rknn.release()
