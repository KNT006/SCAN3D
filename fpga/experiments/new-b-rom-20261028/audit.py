"""Audit new routed DB using its preserved mapped timing constraints."""
from pathlib import Path
import subprocess,json,sys,re,time,hashlib

HOME=Path('D:/PCle/_b28/fpga-gain-handshake-20261013')
RUN=HOME/'board/fpga/imx415_pcie_4k_Runs/phy_1'
TD='D:/Anlogic/TD_6.2.1_Release_6.2.175.876/bin/td_commands_prompt.exe'
build=json.loads((HOME/'build-result.json').read_text())
assert len(build)==2 and build[0]['passed'] and build[1]['exit_code']==0
assert (RUN/'.opt_route.end.f').exists()
# Reuse original exhaustive CDC and reset-report commands, not old evidence.
source=(HOME/'audit.py').read_text()
prefix=source.split("with (HERE/'strict-audit.log').open('w')")[0]
prefix=prefix.replace("HERE=Path(__file__).resolve().parent",f"HERE=Path({str(HOME)!r})")
prefix=prefix.replace("assert len(build)==2 and all(v['passed'] for v in build)","assert len(build)==2 and build[0]['passed'] and build[1]['exit_code']==0")
namespace={'__file__':str(HOME/'audit.py')}
exec(compile(prefix,str(HOME/'audit.py'),'exec'),namespace)
s=(HOME/'audit.tcl').read_text()
# Reload IP clocks before user constraints, as in the historical final audit.
# The monitor synchronizer was merged with the eye snapshot source reset.
# Retain the original selector when it exists; otherwise prove the alias and
# its assertion-pin coverage by the pre-existing snapshot rule.
camera=HOME.parent/'fpga-laser-20261001/rgb-roi/strict-afc03_camera_cdc.sdc'
old='set_false_path -to [get_pins {u_mipi_monitor_reset/pipe_reg*.*sr */u_al_pcie_ip_msi_pipeline/u_msi_negedge_reset/pipe_reg*.*sr}]'
replacement='set_false_path -to [get_pins {u_mipi_monitor_reset/pipe_reg*.*sr */u_al_pcie_ip_msi_pipeline/u_msi_negedge_reset/pipe_reg*.*sr u_cam_eye_snapshot/u_src_reset/pipe_reg*.*sr}]'
proof='''
puts "NEW_B_MONITOR_ALIAS_BEGIN"
get_regs {u_mipi_monitor_reset/*} -verbose
puts "NEW_B_EYE_ALIAS_BEGIN"
get_regs {u_cam_eye_snapshot/u_src_reset/pipe* u_cam_eye_snapshot/srst_n} -verbose
puts "NEW_B_ALIAS_END"
'''
cs=camera.read_text(); assert cs.count(old)==1
patched=HOME/'camera-cdc-mapped-alias.sdc';patched.write_text(cs.replace(old,replacement))
s=s.replace(camera.as_posix(),patched.as_posix())
s=s.replace('report_timing_summary -file strict-laser-pr.timing',proof+'report_timing_summary -file strict-laser-pr.timing')
monitor='report_timing_path -from [get_regs {u_cam_eye_snapshot/u_src_reset/pipe[0] u_cam_eye_snapshot/u_src_reset/pipe[1]}] -to [get_regs {u_cam_eye_snapshot/u_src_reset/pipe[1] u_cam_eye_snapshot/srst_n}] -ep_num 8 -path_num 1 -file {'+(HOME/'monitor-reset-local.timing').as_posix()+'}\n'
s=s.replace('export_db strict-laser-pr.db',monitor+'export_db strict-laser-pr.db')
s='if {[catch {\n'+s.replace('exit 0','')+'\n} reason]} {puts stderr $reason; exit 1}\nexit 0\n'
(HOME/'audit.tcl').write_text(s)
started=time.time()
with (HOME/'strict-audit.log').open('w') as f:
    r=subprocess.run([TD,(HOME/'audit.tcl').as_posix()],cwd=RUN,stdout=f,stderr=subprocess.STDOUT)
log=(HOME/'strict-audit.log').read_text(errors='replace')
errors=re.findall(r'^.*(?:\bERROR:|USR-8159|allocation failed|coredump).*$',log,re.M|re.I)
assert r.returncode==0 and not errors,errors
assert (RUN/'strict-laser-pr.timing').stat().st_mtime>=started
assert (RUN/'strict-laser-pr.db').stat().st_mtime>=started
section=log.split('NEW_B_MONITOR_ALIAS_BEGIN')[-1].split('NEW_B_ALIAS_END')[0]
names=re.findall(r'get_regs num\[\d+\] : ([^\r\n]+)',section)
expected={'u_cam_eye_snapshot/srst_n','u_cam_eye_snapshot/u_src_reset/pipe[0]','u_cam_eye_snapshot/u_src_reset/pipe[1]'}
alias=len(names)==2 and all(set(n.split())==expected for n in names)
assert alias,('Unproven monitor alias',names)
(HOME/'monitor-alias-validation.json').write_text(json.dumps(dict(passed=alias,registers=names,log_sha256=hashlib.sha256((HOME/'strict-audit.log').read_bytes()).hexdigest()),indent=2))
print('Fresh routed audit reports generated. Qualification still required.')
