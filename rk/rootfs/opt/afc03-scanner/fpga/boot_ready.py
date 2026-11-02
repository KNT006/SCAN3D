"""Initialize the qualified FPGA DDR once after PCIe, before camera startup."""
import json,subprocess,time
from pathlib import Path
from contextlib import ExitStack
from rk_laser_ready import load_hardware_helpers,diagnostic_locks,inspect_or_release

def idle():
    from rk_rgb_roi_diag import scanner_idle
    active=subprocess.run(['systemctl','is-active','--quiet','afc03-scanner']).returncode==0
    if active:return scanner_idle('http://127.0.0.1:8081')
    return dict(active_scans=[],active_jobs=[],active_calibrations=[],scanner_service_inactive=True)

def main():
    path=Path('/run/afc03-fpga-ready.json');report=dict(passed=False)
    try:
        DDR,Probe,MMIO,_=load_hardware_helpers()
        with ExitStack() as stack:
            diagnostic_locks(stack);idle();probe=Probe();stack.callback(probe.close)
            ddr=DDR(probe.node.name);stack.callback(ddr.close);mmio=MMIO(probe)
            report=inspect_or_release(ddr,probe,mmio,release=False,scanner_check=idle)
            state=report['legacy_before']
            if state['reset_held']:
                report=inspect_or_release(ddr,probe,mmio,release=True,scanner_check=idle)
            elif not(state['bridge_ready'] and state['init_advisory']['control_ready'] and
                     not state['timeout'] and not state['rejected']):
                raise RuntimeError('DDR unexpectedly unavailable; refusing automatic live reset')
            report['boot_initialization_passed']=True
    except Exception as e:
        report.update(passed=False,error=str(e));raise
    finally:
        report['recorded_unix']=time.time();path.write_text(json.dumps(report,indent=2));path.chmod(0o644)
    print(json.dumps(report))
if __name__=='__main__':main()
