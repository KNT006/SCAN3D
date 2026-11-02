"""Offline RGB/NPU filtering job; inherited scan/read locks live until exit."""
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time


def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


from chat_priority import priority_operation

@priority_operation
def main(folder):
    request = json.loads((folder/'request.json').read_text())
    def state(status, **extra):
        write(folder/'state.json', dict(status=status, **extra))
    try:
        state('running', stage='prepare')
        source = Path(request['source_path'])
        shutil.copyfile(source, folder/'source.npz')
        scripts = Path(request['scripts'])
        sys.path.insert(0, str(scripts))
        runtime = request.get('runtime')
        if runtime:
            sys.path.insert(0, runtime)
        scan = Path(request['scan_path'])
        stride = '1' if len(list(scan.glob('position-*/COLOR/same-frame.png'))) < 8 else '2'
        sys.argv = ['prepare_manifest.py', '--scan', str(scan), '--bundle', str(scan/'bundle'),
                    '--output', str(folder/'manifest.json'), '--rotation', '90', '--stride', stride]
        runpy.run_path(str(scripts/'prepare_manifest.py'), run_name='__main__')
        state('running', stage='filter')
        sys.argv = ['filter_cloud.py', '--cloud', str(folder/'source.npz'),
                    '--manifest', str(folder/'manifest.json'), '--backend', 'rknn',
                    '--model', request['model'], '--output', str(folder/'output')]
        runpy.run_path(str(scripts/'filter_cloud.py'), run_name='__main__')
        report = json.loads((folder/'output/report.json').read_text())
        if not report.get('output_accepted') or not (folder/'output/combined.npz').is_file():
            raise ValueError('过滤结果需要人工检查，未生成可用点云')
        from cloud_binary import build_cloud
        build_cloud(folder/'output', folder/'output/combined.npz')
        state('complete', stage='complete', elapsed_seconds=time.time()-request['created'])
    except Exception as error:
        state('failed', error=str(error), elapsed_seconds=time.time()-request['created'])
        raise


if __name__ == '__main__':
    main(Path(sys.argv[1]))
