"""Mirror calibration activation without replacing unrelated local algorithms."""
from pathlib import Path
import hashlib, json, shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FPGA = ROOT / 'rk/rootfs/opt/afc03-scanner/fpga'
OLD = '4c1c3e00a5bbb2ae41355cfeefa6100081813846b8bca1e2b3da9be7ec5ab0a9'
NEW = '4219e460decd036b1d0afd9049601c4bb8e18f151a776e9e32b9afb9aa319d61'
bundle = FPGA / 'new-strategy-bundle'
source = FPGA / 'rgb_adaptive_strategy.py'
assert hashlib.sha256((bundle / 'planes.json').read_bytes()).hexdigest() == OLD
assert hashlib.sha256((HERE / 'bundle/planes.json').read_bytes()).hexdigest() == NEW
assert source.read_bytes().count(OLD.encode()) == 1
backup = HERE / 'local-before-native'
backup.mkdir(exist_ok=False)
for p in (source, bundle / 'planes.json', bundle / 'config.json'):
    shutil.copy2(p, backup / p.name)
source.write_bytes(source.read_bytes().replace(OLD.encode(), NEW.encode()))
shutil.copyfile(HERE / 'bundle/planes.json', bundle / 'planes.json')
config = json.loads((bundle / 'config.json').read_text(encoding='utf-8'))
assert config['sha256']['planes.json'] == OLD
config['sha256']['planes.json'] = NEW
(bundle / 'config.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
print('Local native B binding updated; unrelated algorithms and settings retained.')
