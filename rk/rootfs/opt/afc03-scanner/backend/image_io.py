"""Identical OpenCV PNG defaults, batched writes for the board's sync filesystem."""
import os
from pathlib import Path
import cv2


def save_png(path,image):
    path=Path(path)
    if path.exists():raise FileExistsError('Refusing to overwrite a raw acquisition: '+str(path))
    ok,encoded=cv2.imencode('.png',image)
    if not ok:raise OSError('PNG encode failed')
    temporary=path.with_name(path.name+'.writing')
    # On failure retain our incomplete file for diagnosis; never publish partial PNGs.
    with temporary.open('xb') as f:
        if f.write(encoded)!=encoded.nbytes:raise OSError('Short PNG write')
        f.flush();os.fsync(f.fileno())
    os.link(temporary,path)  # Atomic no-overwrite publication on the same filesystem.
    temporary.unlink()
