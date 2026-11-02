"""Read-only task presentation. Never resumes work or changes stored evidence."""
import json
import time


def load(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def task_state(path, process_alive=False, now=None):
    state = load(path / 'status.json')
    if not state:
        state = (dict(status='starting', phase='preflight', elapsed_seconds=0,
                      completed_positions=0) if process_alive else
                 dict(status='failed', phase='stopped', completed_positions=0,
                      error='扫描进程未产生状态记录，请检查任务日志。'))
    elif state.get('status') == 'running' and not process_alive:
        state = dict(state, status='interrupted', phase='stopped',
                     error=state.get('error') or '扫描进程已退出，未自动续扫。')
    state = dict(state, id=path.name)
    if process_alive and state.get('status') == 'running' and 'started_monotonic' in state:
        state['elapsed_seconds'] = max(0, (time.monotonic() if now is None else now) - state['started_monotonic'])
    if state.get('phase') == 'stopped' and state.get('completed_positions', 0) == 0:
        initial = load(path / 'position-000/status.json')
        if initial:
            state['initial_capture'] = dict(color=initial.get('color'),
                retained_points={k:v.get('retained_points', 0) for k,v in initial.get('lasers', {}).items()},
                scope='起始位置预览；不代表整圈通过')
    return state
