"""Opt-in archive postprocessing; never replaces source scans or their acceptance."""
import fcntl
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from common import DATA, CODE, read, job, active
from run_access import acquire
from ai_filter_worker import write

SOURCE_PATHS = ('combined.npz', 'current-strategy/combined.npz', 'review/combined.npz', 'tail-repaired-v1/combined.npz')


def input_cloud(root):
    for relative in SOURCE_PATHS:
        path = root/relative
        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()):
            return path
    raise ValueError('没有合并点云；请先完成合并或生成审阅点云')


def completed_sources(name):
    result = []
    for folder in (DATA/'ai-filter-tasks').glob('*'):
        request = read(folder/'request.json')
        path = folder/'output/combined.npz'
        if request.get('run') == name and read(folder/'state.json').get('status') == 'complete' and path.is_file():
            result.append(dict(id='ai-'+folder.name, label='AI 去离群点 · '+folder.name[:8], path=str(path), run=name))
    return result


def install(app, guard, busy):
    store = DATA/'ai-filter-tasks'
    store.mkdir(exist_ok=True)
    processes = {}
    scripts = CODE.parent/'pointcloud-ai'
    model = Path(os.environ.get('SCAN3D_AI_MODEL', str(scripts/'model/u2netp-rk3576.rknn')))
    runtime = os.environ.get('SCAN3D_AI_RUNTIME', '/opt/afc03-scanner/pointcloud-ai/runtime-python')

    def folder(identifier):
        if not re.fullmatch('[a-f0-9]{32}', identifier):
            raise HTTPException(400, '无效 AI 任务编号')
        path = store/identifier
        if not (path/'request.json').is_file():
            raise HTTPException(404, 'AI 任务不存在')
        return path

    def state(path):
        request = read(path/'request.json')
        value = read(path/'state.json', {'status': 'interrupted'})
        if value['status'] in ('queued', 'running'):
            proc = processes.get(path.name)
            if proc is None or proc.poll() is not None:
                # A previous server's worker may still own the shared scan lock.
                value = dict(status='interrupted', error='任务进程已退出或服务已重启；请检查运行日志')
            else:
                value['elapsed_seconds'] = time.time()-request['created']
        public = {k: request[k] for k in ('run', 'created', 'source')}
        return dict(value, id=path.name, request=public,
                    report=read(path/'output/report.json') if value['status'] == 'complete' else None)

    def running():
        return any(proc.poll() is None for proc in processes.values())

    @app.middleware('http')
    async def exclusion(request, call_next):
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and running():
            if not request.url.path.endswith('/stop') and request.url.path != '/api/scan3d/control':
                return JSONResponse({'detail': 'AI 点云过滤正在运行，请完成或取消后再操作'}, status_code=409)
        return await call_next(request)

    @app.get('/api/scan3d/runs/{name}/ai-filter')
    def list_tasks(name: str):
        try:
            root = job(name)
            input_cloud(root)
            reason = ''
            if not model.is_file(): reason = 'RKNN 模型尚未安装'
            elif len(list(root.glob('position-*/COLOR/same-frame.png'))) < 4: reason = '保存的彩色照片不足 4 张'
            elif not (root/'bundle/config.json').is_file(): reason = '缺少本次扫描的标定配置'
        except ValueError as error:
            reason = str(error)
        rows = [state(p) for p in store.iterdir() if read(p/'request.json').get('run') == name]
        return dict(available=not reason, reason=reason, tasks=sorted(rows, key=lambda r:r['request']['created'], reverse=True)[:20])

    @app.post('/api/scan3d/runs/{name}/ai-filter', status_code=202)
    def start(name: str):
        with guard:
            if active() or busy() or running():
                raise HTTPException(409, '已有扫描或处理任务')
            if not model.is_file():
                raise HTTPException(503, 'RKNN 模型尚未安装，请配置 SCAN3D_AI_MODEL')
            lock = None
            run_fd = None
            try:
                root = job(name)
                source = input_cloud(root)
                if source.stat().st_size > 128*1024**2:
                    raise ValueError('点云超过板端处理上限 128 MB')
                if shutil.disk_usage(DATA).free < 1024**3:
                    raise ValueError('至少需要 1 GB 可用空间')
                lock = open('/run/lock/afc03-fpga-scan.lock', 'r')
                fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
                run_fd = acquire(name)
                identifier = uuid.uuid4().hex
                path = store/identifier
                path.mkdir()
                write(path/'request.json', dict(run=name, created=time.time(), source=str(source.relative_to(root)),
                      source_path=str(source), scan_path=str(root), scripts=str(scripts), model=str(model), runtime=runtime))
                write(path/'state.json', dict(status='queued'))
                env = dict(os.environ, OPENBLAS_NUM_THREADS='2', OMP_NUM_THREADS='2')
                with (path/'worker.log').open('wb') as log:
                    processes[identifier] = subprocess.Popen([sys.executable, str(CODE/'ai_filter_worker.py'), str(path)],
                        env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                        start_new_session=True, pass_fds=(lock.fileno(), run_fd))
                return dict(id=identifier)
            except (OSError, ValueError) as error:
                raise HTTPException(409, '无法启动 AI 过滤：'+str(error))
            finally:
                if lock: lock.close()
                if run_fd is not None: os.close(run_fd)

    @app.post('/api/scan3d/ai-filter/{identifier}/stop')
    def stop(identifier: str):
        with guard:
            path = folder(identifier)
            proc = processes.get(identifier)
            if proc and proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=10)
                write(path/'state.json', dict(status='cancelled'))
            return state(path)

    @app.get('/api/scan3d/ai-filter/{identifier}/files/{kind}')
    def files(identifier: str, kind: str):
        path = folder(identifier)
        if kind == 'log':
            return FileResponse(path/'worker.log', media_type='text/plain')
        if state(path)['status'] != 'complete':
            raise HTTPException(409, 'AI 处理尚未完成')
        options = {'cloud': 'result-cloud-v1.bin', 'npz': 'combined.npz', 'report': 'report.json'}
        if kind not in options: raise HTTPException(404)
        return FileResponse(path/'output'/options[kind])

    return running
