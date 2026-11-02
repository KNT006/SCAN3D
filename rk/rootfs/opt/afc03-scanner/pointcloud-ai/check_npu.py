"""Save one actual NPU prediction for numerical comparison with ONNX."""
from pathlib import Path
import argparse
import cv2
import numpy as np
from rknnlite.api import RKNNLite
from filter_cloud import preprocess

p = argparse.ArgumentParser()
p.add_argument('model'); p.add_argument('image'); p.add_argument('output')
a = p.parse_args()
image = cv2.rotate(cv2.imread(a.image), cv2.ROTATE_90_CLOCKWISE)[1000:1660, 140:880]
x = preprocess(image)
r = RKNNLite()
try:
    assert r.load_rknn(a.model) == 0
    assert r.init_runtime(core_mask=RKNNLite.NPU_CORE_0) == 0
    prediction = r.inference(inputs=[x[None]], data_format=['nhwc'])[0]
    np.savez(a.output, input=x, prediction=prediction)
finally:
    r.release()
