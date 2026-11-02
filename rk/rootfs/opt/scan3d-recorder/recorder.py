#!/usr/bin/python3
"""Toggle this user's full-desktop recorder; never signal unrelated ffmpeg jobs."""
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from recording_name import available

MOUNT = Path('/mnt/scan3d_sd')
OUTPUT = MOUNT / 'screen-recordings'
STATE_DIR = Path('/run/user') / str(os.getuid()) / 'scan3d-recorder'
STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
STATE = STATE_DIR / 'recording.json'
LAST = STATE_DIR / 'last-recording.json'
CONFIG = Path.home() / '.config/scan3d-recorder/settings.json'
ENV = dict(os.environ)
ENV.setdefault('DISPLAY', ':0')
ENV.setdefault('XAUTHORITY', str(Path.home() / '.Xauthority'))
ENV.setdefault('DBUS_SESSION_BUS_ADDRESS', 'unix:path=/run/user/%s/bus' % os.getuid())

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False))
    temp.replace(path)

def duration_setting():
    try:
        value = json.loads(CONFIG.read_text())['duration_seconds']
        if type(value) is int and 0 <= value <= 86400:return value
    except (OSError, ValueError, KeyError, TypeError):pass
    return 30

def set_duration(value):
    if type(value) is not int or not 0 <= value <= 86400:raise ValueError('时长应为 1 秒至 24 小时；0 表示手动停止。')
    write_json(CONFIG, {'duration_seconds':value})

def read_state():
    try:return json.loads(STATE.read_text())
    except (OSError, ValueError):return None

def notify(title, message, replace=0, timeout=6000):
    try:
        r = subprocess.run(['/usr/bin/gdbus','call','--session','--dest','org.freedesktop.Notifications',
            '--object-path','/org/freedesktop/Notifications','--method','org.freedesktop.Notifications.Notify',
            'SCAN3D 录屏',str(replace),'media-record',title,message,'[]','{}',str(timeout)],
            env=ENV, capture_output=True, text=True, timeout=3)
        found = re.search(r'uint32 (\d+)', r.stdout)
        return int(found.group(1)) if found else 0
    except (OSError, subprocess.TimeoutExpired):return 0

def identity(pid):
    try:
        text = Path('/proc/%d/stat' % pid).read_text()
        fields = text[text.rfind(')')+2:].split()
        return None if fields[0] == 'Z' else fields[19]
    except (OSError, ValueError, IndexError):return None

def active():
    try:
        state = json.loads(STATE.read_text())
        cmd = Path('/proc/%d/cmdline' % state['pid']).read_bytes().split(b'\0')
        if identity(state['pid']) == state['start_ticks'] and state['file'].encode() in cmd and b'/usr/bin/ffmpeg' in cmd:
            return state
    except (OSError, ValueError, KeyError, TypeError):pass
    return None

def start(duration, filename=None):
    if not os.path.ismount(MOUNT):raise RuntimeError('SD 卡未挂载，请插入并挂载后重试。')
    if not OUTPUT.is_dir() or not os.access(OUTPUT, os.W_OK):raise RuntimeError('SD 卡录屏目录不可写。')
    space = os.statvfs(OUTPUT)
    if space.f_bavail * space.f_frsize < 512 * 1024**2:raise RuntimeError('SD 卡可用空间不足 512 MB。')
    name = available(OUTPUT, filename or ('SCAN3D-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')))
    dest = OUTPUT / (name + '.mkv')
    logs = OUTPUT / '.logs';logs.mkdir(exist_ok=True)
    logfile = logs / (name + '.log')
    command = ['/usr/bin/ffmpeg','-hide_banner','-nostdin','-n','-f','x11grab',
        '-framerate','15','-draw_mouse','1','-i',ENV['DISPLAY'],'-an',
        '-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-filter_threads','1',
        '-c:v','libx264','-preset','ultrafast','-crf','23','-threads','2','-pix_fmt','yuv420p']
    if duration:command += ['-t',str(duration)]
    command.append(str(dest))
    with logfile.open('xb') as log:
        proc = subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=ENV,start_new_session=True)
    state = {'pid':proc.pid,'start_ticks':identity(proc.pid),'file':str(dest),'log':str(logfile),'started_at':datetime.now().isoformat(),'started_monotonic':time.monotonic(),'duration_seconds':duration}
    write_json(STATE,state)
    time.sleep(.8)
    if proc.poll() is not None:
        STATE.unlink(missing_ok=True)
        raise RuntimeError('录屏启动失败，请查看 '+str(logfile))
    ending = ('%d 秒后自动停止，也可按 Ctrl + Alt + R 提前结束。' % duration) if duration else '按 Ctrl + Alt + R 停止并保存。'
    state['notification'] = notify('录屏已开始', ending+'\n保存到 SD 卡 / screen-recordings', timeout=5000)
    write_json(STATE,state)
    subprocess.Popen(['/usr/bin/python3',str(Path(__file__).resolve()),'watch',str(proc.pid),state['start_ticks']],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=ENV,start_new_session=True)
    print(json.dumps({'recording':True,**state},ensure_ascii=False))

def finish(state):
    current=read_state()
    if not current or (current['pid'],current['start_ticks']) != (state['pid'],state['start_ticks']):return
    r = subprocess.run(['/usr/bin/ffprobe','-v','error','-show_entries','format=duration,size',
                        '-of','json',state['file']],capture_output=True,text=True,timeout=10)
    if r.returncode:
        STATE.unlink(missing_ok=True)
        raise RuntimeError('视频写入异常，请保留日志：'+state['log'])
    info = json.loads(r.stdout)['format']
    result={'recording':False,'file':state['file'],**info}
    write_json(LAST,result)
    STATE.unlink(missing_ok=True)
    notify('录屏已保存', Path(state['file']).name+'\n主目录 → Videos → SCAN3D-recordings', state.get('notification',0))
    print(json.dumps(result,ensure_ascii=False))

def stop(state):
    # Match process creation time and output path immediately before signalling.
    if not active():raise RuntimeError('录屏进程已经结束。')
    os.kill(state['pid'], signal.SIGINT)
    deadline = time.monotonic()+20
    while identity(state['pid']) == state['start_ticks'] and time.monotonic()<deadline:time.sleep(.1)
    if identity(state['pid']) == state['start_ticks']:raise RuntimeError('正在完成视频写入，请稍后再检查。')
    finish(state)

def watch(pid, ticks):
    while identity(pid)==ticks:time.sleep(.3)
    with (STATE_DIR/'control.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=read_state()
        if state and state['pid']==pid and state['start_ticks']==ticks:finish(state)

def main():
    action = sys.argv[1] if len(sys.argv)>1 else 'toggle'
    if action=='watch':watch(int(sys.argv[2]),sys.argv[3]);return
    if action not in ('toggle','start','stop','status','settings'):raise RuntimeError('未知操作')
    with (STATE_DIR/'control.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current = active()
        if action=='settings':
            if len(sys.argv)>2:set_duration(int(sys.argv[2]))
            print(json.dumps({'duration_seconds':duration_setting()}));return
        if action=='status':print(json.dumps({'recording':bool(current),'state':current,'duration_seconds':duration_setting()},ensure_ascii=False));return
        stale=read_state()
        if not current and stale:finish(stale)
        if current and action in ('toggle','stop'):stop(current)
        elif not current and action in ('toggle','start'):
            duration=int(sys.argv[2]) if len(sys.argv)>2 else duration_setting()
            if not 0 <= duration <= 86400:raise ValueError('时长超出范围')
            start(duration, sys.argv[3] if len(sys.argv)>3 else None)
        elif current:notify('正在录屏','按 Ctrl + Alt + R 停止并保存。')
        else:notify('当前未在录屏','按 Ctrl + Alt + R 开始录屏。')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        notify('录屏提示',str(exc));print(str(exc),file=sys.stderr);sys.exit(1)
