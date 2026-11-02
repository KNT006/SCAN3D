"""One bounded new-frame attempt, never a replay of a motor or transport command."""
from row_results import require

def retryable(report):
    if report.get('passed') or report.get('cleanup_errors') or report.get('requires_ddr_recovery'):return False
    if not (report.get('cleanup_background',{}).get('quiescent') is True and
            report.get('cleanup_probe_idle') is True and report.get('cleanup_camera_released') is True):return False
    cam=report.get('camera_observed',{});armed=report.get('camera_arm',{});fpga=report.get('fpga_capture',{})
    if not (fpga.get('done') is True and fpga.get('fault')==0 and
            fpga.get('fault_present') is False and fpga.get('rejected') is False and
            fpga.get('waiting') is False and fpga.get('active') is False and
            fpga.get('token')==report.get('token') and armed.get('token')==report.get('token')):return False
    if report.get('new_token_retry_permitted') is True and report.get('stage')=='check_ddr_marker':return True
    return (report.get('stage')=='wait_raw_marker' and cam.get('state')=='expired' and
            cam.get('error')=='capture_timeout' and cam.get('generation')==armed.get('generation') and
            cam.get('stream_id')==armed.get('stream_id') and cam.get('token')==armed.get('token'))

def capture_with_retry(path,acquire,check):
    """acquire creates path and returns its report; check verifies physical command state.

    Keep the failed attempt intact under a distinct name. A fresh token and the
    original camera stream are mandatory even after a successful second capture.
    """
    check();first=acquire(path);check()
    if first.get('passed') or not retryable(first):return first
    rejected=path.with_name(path.name+'-rejected-01')
    require(not rejected.exists(),'Rejected-capture archive already exists')
    path.rename(rejected)
    check();second=acquire(path);check()
    require(second.get('token')!=first.get('token'),'Capture retry reused token')
    require(second.get('camera_arm',{}).get('stream_id')==first['camera_arm']['stream_id'],
            'Camera restarted between capture attempts')
    second['capture_attempts']=2;second['rejected_capture_directory']=rejected.name
    return second
