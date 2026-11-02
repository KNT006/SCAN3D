"""Download the upstream pretrained model, checking its published checksum."""
import hashlib
from pathlib import Path
from urllib.request import urlopen

url = 'https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx'
path = Path(__file__).parent/'model/u2netp.onnx'
content = path.read_bytes() if path.exists() else urlopen(url, timeout=120).read()
if hashlib.md5(content).hexdigest() != '8e83ca70e441ab06c318d82300c84806':
    raise RuntimeError('Upstream model checksum mismatch')
path.parent.mkdir(exist_ok=True)
if not path.exists():
    path.write_bytes(content)
print('SHA256', hashlib.sha256(content).hexdigest())
