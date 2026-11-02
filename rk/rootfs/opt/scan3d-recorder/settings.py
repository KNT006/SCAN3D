#!/usr/bin/python3
"""Small native desktop controller for timed screen recording."""
import json
import subprocess
import threading
import time
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib
import recorder

class RecorderApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.scan3d.ScreenRecorder')
        self.window=None
        self.busy=False

    def do_activate(self):
        if self.window:self.window.present();return
        self.window=Gtk.ApplicationWindow(application=self,title='SCAN3D 屏幕录制')
        self.window.set_default_size(470,330)
        self.window.set_border_width(22)
        self.window.connect('destroy',self.closed)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
        self.window.add(box)
        self.status=Gtk.Label(label='准备录屏',xalign=0)
        box.pack_start(self.status,False,False,0)
        self.timed=Gtk.CheckButton(label='定时停止并保存')
        seconds=recorder.duration_setting()
        self.timed.set_active(seconds>0)
        box.pack_start(self.timed,False,False,0)
        row=Gtk.Box(spacing=8)
        self.minutes=Gtk.SpinButton.new_with_range(0,1440,1)
        self.seconds=Gtk.SpinButton.new_with_range(0,59,1)
        self.minutes.set_value((seconds or 30)//60)
        self.seconds.set_value((seconds or 30)%60)
        for widget in (self.minutes,Gtk.Label(label='分'),self.seconds,Gtk.Label(label='秒')):row.pack_start(widget,False,False,0)
        box.pack_start(row,False,False,0)
        presets=Gtk.Box(spacing=8)
        for label,value in [('30 秒',30),('1 分钟',60),('5 分钟',300)]:
            button=Gtk.Button(label=label)
            button.connect('clicked',lambda _,v=value:self.preset(v))
            presets.pack_start(button,True,True,0)
        box.pack_start(presets,False,False,0)
        self.controls=[self.timed,row,presets]
        name_row=Gtk.Box(spacing=8)
        name_row.pack_start(Gtk.Label(label='视频文件名'),False,False,0)
        self.filename=Gtk.Entry()
        self.filename.set_placeholder_text('留空使用日期时间，同名自动编号')
        name_row.pack_start(self.filename,True,True,0)
        name_row.pack_start(Gtk.Label(label='.mkv'),False,False,0)
        box.pack_start(name_row,False,False,0)
        self.controls.append(name_row)
        tip=Gtk.Label(label='Ctrl + Alt + R：按已保存时长开始，或提前停止\n取消勾选“定时停止”即可手动结束；不录声音。',xalign=0)
        tip.set_line_wrap(True)
        box.pack_start(tip,False,False,0)
        actions=Gtk.Box(spacing=8)
        self.save=Gtk.Button(label='保存设置')
        self.start=Gtk.Button(label='开始录屏')
        self.stop=Gtk.Button(label='停止并保存')
        self.save.connect('clicked',lambda _:self.run_action('settings'))
        self.start.connect('clicked',lambda _:self.run_action('start'))
        self.stop.connect('clicked',lambda _:self.run_action('stop'))
        for b in (self.save,self.start,self.stop):actions.pack_start(b,True,True,0)
        box.pack_start(actions,False,False,0)
        folder=Gtk.Button(label='打开视频文件夹（SD 卡）')
        folder.connect('clicked',lambda _:subprocess.Popen(['exo-open',str(Path.home()/'Videos/SCAN3D-recordings')]))
        box.pack_start(folder,False,False,0)
        self.feedback=Gtk.Label(label='',xalign=0)
        self.feedback.set_line_wrap(True)
        box.pack_start(self.feedback,False,False,0)
        self.timed.connect('toggled',lambda _:self.tick())
        self.window.show_all()
        self.tick()
        GLib.timeout_add(500,self.tick)

    def closed(self,*_):self.window=None

    def preset(self,value):
        self.timed.set_active(True)
        self.minutes.set_value(value//60);self.seconds.set_value(value%60)

    def selected(self):
        if not self.timed.get_active():return 0
        value=self.minutes.get_value_as_int()*60+self.seconds.get_value_as_int()
        if not 1<=value<=86400:raise ValueError('请设置 1 秒至 24 小时的录屏时长。')
        return value

    def run_action(self,action):
        try:value=self.selected() if action!='stop' else None
        except ValueError as e:self.feedback.set_text(str(e));return
        filename=self.filename.get_text().strip() if action=='start' else ''
        if filename:
            try:recorder.available(recorder.OUTPUT,filename)
            except ValueError as e:self.feedback.set_text(str(e));return
        self.busy=True;self.tick()
        def work():
            try:
                tool=['/usr/bin/python3',str(Path(__file__).with_name('recorder.py'))]
                if action!='stop':subprocess.run(tool+['settings',str(value)],check=True,capture_output=True,text=True,timeout=10)
                if action!='settings':
                    args=tool+['start',str(value),filename] if action=='start' else tool+[action]
                    r=subprocess.run(args,capture_output=True,text=True,timeout=40)
                    if r.returncode:raise RuntimeError(r.stderr.strip() or '操作失败')
                message='设置已保存：'+('手动停止' if value==0 else '%d 秒后自动停止'%value) if action=='settings' else ('正在录屏，窗口将最小化。' if action=='start' else '视频已保存到 SD 卡。')
                GLib.idle_add(self.done,action,message,True)
            except subprocess.CalledProcessError as e:
                detail=(e.stderr or e.stdout or str(e)).strip()
                if 'No space left on device' in detail:
                    detail='系统分区空间不足，无法保存录屏设置；请清理系统分区后重试。'
                GLib.idle_add(self.done,action,detail,False)
            except Exception as e:GLib.idle_add(self.done,action,str(e),False)
        threading.Thread(target=work,daemon=True).start()

    def done(self,action,message,success):
        self.busy=False
        if self.window:
            self.feedback.set_text(message)
            if success and action=='start':self.window.iconify()
            self.tick()
        return False

    def tick(self):
        if not self.window:return False
        state=recorder.active()
        if state:
            elapsed=max(0,int(time.monotonic()-state.get('started_monotonic',time.monotonic())))
            limit=state.get('duration_seconds',0)
            tail=('，约剩 %d 秒'%max(0,limit-elapsed)) if limit else '，手动停止'
            self.status.set_text('● 正在录屏：已录 %d 秒%s'%(elapsed,tail))
        else:self.status.set_text('准备录屏 · 保存到 SD 卡')
        can_edit=not state and not self.busy
        for widget in self.controls:widget.set_sensitive(can_edit)
        self.controls[1].set_sensitive(can_edit and self.timed.get_active())
        self.save.set_sensitive(can_edit);self.start.set_sensitive(can_edit)
        self.stop.set_sensitive(bool(state) and not self.busy)
        return True

if __name__=='__main__':RecorderApp().run()
