"""Allow only known archive calibration pairs, without relaxing live ROM binding."""
from pathlib import Path
import hashlib, json

HERE = Path(__file__).resolve().parent
source = HERE / 'rk-replay-before.py'
text = source.read_text(encoding='utf-8')
anchor = '\n\ndef load_archive(folder,laser):'
helper = '''

ARCHIVE_PLANES = frozenset((
    '4c1c3e00a5bbb2ae41355cfeefa6100081813846b8bca1e2b3da9be7ec5ab0a9',
    '4219e460decd036b1d0afd9049601c4bb8e18f151a776e9e32b9afb9aa319d61'))

def validate_archive_hashes(hashes):
    # Archive-only: raw candidates are already captured under their original ROM.
    require(all(hashes.get(k)==HASHES[k] for k in ('camera_sha256','axis_sha256'))
            and hashes.get('planes_sha256') in ARCHIVE_PLANES,'未知存档标定组合')

def validate_archive_profile(header):
    validate_archive_hashes(header['calibration'])
    # Reuse unchanged algorithm/image-geometry/laser checks without changing
    # the original header or the strict live-capture HASHES binding.
    context=dict(header,calibration=dict(header['calibration'],planes_sha256=HASHES['planes_sha256']))
    validate_profile(context)
'''
assert text.count(anchor) == 1
text = text.replace(anchor, helper + anchor)
replacements = {
    '    validate_profile(h)': '    validate_archive_profile(h)',
    "    require(adapter.hashes==HASHES,'历史标定不兼容当前 FPGA 空间 ROM')": '    validate_archive_hashes(adapter.hashes)',
    "    require(adapter.hashes==HASHES,'标定哈希不匹配')": "    require(all(adapter.hashes[k]==h['calibration'].get(k) for k in HASHES),'存档 bundle 与采集帧标定哈希不匹配')",
}
for before, after in replacements.items():
    assert text.count(before) == 1, before
    text = text.replace(before, after)
compile(text, 'rk-replay-native.py', 'exec')
target = HERE / 'rk-replay-native.py'
target.write_text(text, encoding='utf-8')
(HERE / 'archive-patch.json').write_text(json.dumps(dict(
    before_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    after_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    scope='Known archive planes only; live-capture validation unchanged'),indent=2))
print(target)
