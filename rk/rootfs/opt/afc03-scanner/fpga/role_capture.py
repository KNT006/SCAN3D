"""Same-frame camera -> DDR background readback, opt-in diagnostic only.

Requires the NEW BGC1 candidate and the already-installed RGB marker service.
Never adjusts exposure, controls a motor/laser, or programs Flash. The native
first four pixels carry the diagnostic marker and are excluded from ROI tests.
"""
import argparse,ctypes,dataclasses,json,struct,time
from capture_health import snapshot as video_health, next_frame_boundary
from pathlib import Path
from role_client import RoleClient,DiagnosticError,CommandRejected,BASE
from rk_rgb_roi_diag import (Probe,CameraAPI,ARM,CANCEL,MAGIC,allocate_token,
    parse_ppm,decode_snapshot,roi_from_raw,compare_rgb,scanner_idle,check_snapshot)

ROIS=[('center',[944,520,976,552]),('target',[1496,500,1528,532])]

class BackgroundMMIO:
    """Reuse the validated one-page BAR mapping; aligned 32-bit stores only."""
    def __init__(self,probe):self.probe=probe
    def read(self,offset):
        if offset&3 or not 0x2200<=offset<0x2600:raise ValueError('BGC1 read outside window')
        return ctypes.c_uint32.from_buffer(self.probe.mem,offset-0x2000).value
    def write(self,offset,value):
        if (offset&255) not in [8,12,*range(0x10,0x34,4)]:raise ValueError('BGC1 forbidden write')
        ctypes.c_uint32.from_buffer(self.probe.mem,offset-0x2000).value=value
        self.read((offset&~255)+4)

def wait_background_quiescent(client,timeout=3.0,poll_seconds=.01):
    """Observe actual DDR/source drain; never ARM, reset, or retry a command.

    A CANCEL reply only confirms acceptance. The polling deadline is bounded;
    an already-issued SNAP may additionally take the client's bounded command
    timeout. A watchdog/transport fault is not converted into successful drain.
    Historical event_committed may remain set after cancellation and does not
    imply rollback or prevent an otherwise quiescent state.
    """
    deadline=time.monotonic()+timeout
    polls=0;last=None
    while time.monotonic()<deadline:
        last=client.snapshot();polls+=1
        if last.flags&0xc0!=0xc0:
            raise DiagnosticError('DDR/EXT became unavailable during cleanup; coordinated recovery required')
        if last.flags&0x28:
            raise DiagnosticError('DDR transport/protocol fault during cleanup; coordinated recovery required')
        if not last.busy and not last.flags&0x14:
            return dict(quiescent=True,polls=polls,flags=last.flags,
                        event_seen=last.event_seen,event_token=last.event_token,
                        event_epoch=last.event_epoch,event_committed=last.event_committed)
        time.sleep(poll_seconds)
    flags='unavailable' if last is None else hex(last.flags)
    raise DiagnosticError('Cleanup drain timeout; capture/transport/readers not confirmed idle, flags='+flags)

def capture(probe,client,api,output,epoch,geometry,calibration,wait_seconds,*,verify_pixels=True,preflight_checked=False,overlap_job=None):
    output.mkdir(parents=True,exist_ok=False)
    report=dict(passed=False,stage='preflight',flash_modified=False,motor_operations=False,
                laser_operations=False,diagnostic_only=True,cleanup_errors=[])
    generation=None;probe_owned=False;capture_requested=False;capture_done=False
    try:
        report['scanner_idle']=dict(checked_by_lock_owner=True) if preflight_checked else scanner_idle('http://127.0.0.1:8081')
        if overlap_job is not None and not (overlap_job.capture_overlap and overlap_job.in_flight):
            raise DiagnosticError('No ABI5 extraction owns this overlap')
        state=client.snapshot()
        if state.busy or state.flags&(0x28 if overlap_job is not None else 0x2c):raise DiagnosticError('Capture/transport is not available')
        if state.flags&0xc0!=0xc0:raise DiagnosticError('DDR/EXT ownership is not ready')
        previous=probe.status()
        if previous['waiting'] or previous['active']:raise DiagnosticError('Another ROI probe capture is active')
        camera=api.request('/diagnostic/roi/status')
        if camera['state'] in ('waiting','copying','ready'):raise DiagnosticError('Another camera diagnostic is retained')
        if [camera['width'],camera['height']]!=[1920,1080]:raise DiagnosticError('Unexpected native geometry')
        token=allocate_token(Path('/run/afc03-rgb-roi-last-token'),
                             [previous['token'],camera.get('token'),state.event_token])
        report.update(token=token,epoch=epoch,geometry_revision=geometry,calibration_revision=calibration,
                      diagnostic_revisions_are_not_optical_calibration=True)
        report['stage']='arm_camera_marker'
        marker_wait=min(wait_seconds,1.0)
        report['marker_timeout_seconds']=marker_wait
        armed=api.request('/diagnostic/roi/arm',{'token':token,'timeout_s':marker_wait})
        generation=armed['generation'];report['camera_arm']=armed
        if armed['state']!='waiting' or armed['token']!=token:raise DiagnosticError('Camera arm identity mismatch')
        report['video_before']=video_health(probe)
        probe.write(8,CANCEL);probe_owned=True
        probe.write(0x0c,token);probe.write(0x10,4);probe.write(0x14,8|(1<<16))
        report['stage']='align_capture_boundary'
        report['arm_boundary']=(dict(hardware_atomic=True) if getattr(probe,'abi',0)==0x20000 else next_frame_boundary(probe))
        arm_started=time.monotonic()
        report['stage']='arm_background'
        # An ARM may reach hardware even when its acknowledgment is lost.
        # Cleanup must cover uncertain delivery, without issuing ARM again.
        capture_requested=True
        arm_deadline=time.monotonic()+1
        while True:
            try:
                client.arm(epoch=epoch,geometry=geometry,calibration=calibration,token=token,
                           width=1920,height=1080,roi=[0,0,1920,1080],operator_confirmed=True)
                break
            except CommandRejected as exc:
                # Retry ONLY a matched explicit BUSY rejection while pins are being acquired.
                # Timeout/torn/unknown-delivery errors never reissue ARM.
                if overlap_job is None or exc.result!=1 or time.monotonic()>=arm_deadline:raise
                time.sleep(.001)
        # ARM crossing and this write must land before the same SOF. If they
        # do not, the stored DDR marker below rejects the capture explicitly.
        probe.write(8,ARM)
        report['arm_pair_seconds']=time.monotonic()-arm_started
        report['stage']='wait_background_commit'
        identity=client.wait_capture(token,epoch,timeout=wait_seconds)
        capture_done=True;report['background']=dataclasses.asdict(identity)
        report['video_committed']=video_health(probe)
        if identity.geometry!=geometry or identity.calibration!=calibration or identity.pixels!=1920*1080 or identity.byte_count!=1920*1080*4:
            raise DiagnosticError('Committed background geometry/count mismatch')
        report['stage']='wait_raw_marker'
        deadline=time.monotonic()+wait_seconds
        while time.monotonic()<deadline:
            current=api.request('/diagnostic/roi/status');fpga=probe.status()
            report['camera_observed']=current;report['fpga_capture']=fpga
            if current['generation']!=generation or current['token']!=token or current['stream_id']!=armed['stream_id']:
                raise DiagnosticError('Camera frame identity changed')
            if current['state'] in ('expired','invalid','error','cancelled','idle'):
                raise DiagnosticError('Camera marker frame unavailable: '+str(current))
            if fpga['fault'] or fpga['rejected']:raise DiagnosticError('Probe rejected marked frame')
            if current['state']=='ready' and fpga['done']:break
            time.sleep(.01)
        else:raise DiagnosticError('No exact camera marker frame received')
        check_snapshot(fpga,token,[4,0,8,1],1,[1920,1080])
        report['stage']='read_raw_frame'
        ppm,headers=api.request('/diagnostic/roi/frame?generation='+str(generation),binary=True)
        normalized={k.lower():v for k,v in headers.items()}
        if int(normalized.get('x-roi-token','-1'))!=token or int(normalized.get('x-roi-generation','-1'))!=generation or normalized.get('x-raw-stream')!=armed['stream_id']:
            raise DiagnosticError('Raw HTTP identity mismatch')
        width,height,rgb=parse_ppm(ppm)
        marker=struct.unpack('<III',rgb[:12])
        if marker!=(MAGIC,token,fpga['frame_id']) or int(normalized.get('x-fpga-frame-id','-1'))!=marker[2]:
            raise DiagnosticError('RK marker frame mismatch')
        (output/'same-frame.ppm').write_bytes(ppm)
        report['stage']='check_ddr_marker'
        if overlap_job is not None:
            start=time.monotonic();overlap_job.wait_drained()
            report['wait_extractor_before_readback_s']=time.monotonic()-start
        first=client.read_word(0,identity)
        stored_marker=struct.unpack('<III',decode_snapshot(first))
        report['marker']=dict(rk=list(marker),ddr=list(stored_marker),capture_source_frame=identity.source_frame)
        if stored_marker!=marker or (getattr(probe,'abi',0)==0x20000 and identity.source_frame!=marker[2]):
            report['new_token_retry_permitted']=True
            raise DiagnosticError('DDR captured another frame; no nearest-frame substitution')
        comparisons=[]
        report['comparison']=comparisons
        report['stage']='read_ddr_regions';start=time.monotonic()
        report['pixel_readback_enabled']=bool(verify_pixels)
        for label,roi in (ROIS if verify_pixels else []):
            x0,y0,x1,y1=roi
            raw=b''.join(client.read_span((y*width+x0)*4,(x1-x0)*4,identity) for y in range(y0,y1))
            actual=decode_snapshot(raw);expected=roi_from_raw(rgb,width,roi)
            item=compare_rgb(actual,expected,roi);item.update(label=label,roi=roi)
            comparisons.append(item)
            (output/(label+'-ddr.bin')).write_bytes(raw)
            header=('P6\n%d %d\n255\n'%(x1-x0,y1-y0)).encode()
            (output/(label+'-ddr.ppm')).write_bytes(header+actual)
            if not item['passed']:raise DiagnosticError('DDR RGB mismatch: '+label)
        report.update(comparison= comparisons,readback_seconds=time.monotonic()-start,
                      compared_pixels=sum(item['compared_pixels'] for item in comparisons))
        after=client.snapshot()
        if not after.active or after.background!=identity or after.flags&0x2d:
            raise DiagnosticError('Background identity/fault changed after readback')
        report['passed']=True;report['stage']='complete'
    except Exception as exc:
        report['error']=type(exc).__name__+': '+str(exc)
        try:
            flow=api.request('/diagnostic/marker-flow?token='+str(report.get('token',0)))
            report['marker_flow']=flow
        except Exception as detail:report['marker_flow_error']=str(detail)

    finally:
        if capture_requested and not capture_done:
            try:client.cancel()
            except Exception as exc:report['cleanup_errors'].append('Capture cancel: '+str(exc))
        if probe_owned:
            try:probe.write(8,CANCEL)
            except Exception as exc:report['cleanup_errors'].append('Probe cancel: '+str(exc))
        if generation is not None:
            try:api.request('/diagnostic/roi/cancel',{'generation':generation})
            except Exception as exc:report['cleanup_errors'].append('Camera cancel: '+str(exc))
        # Also run after a committed capture: a later READ16 error may leave
        # an outstanding AXI request/reader pin even though capture_done=True.
        if capture_requested:
            try:
                if overlap_job is not None:overlap_job.wait_drained()
                report['cleanup_background']=wait_background_quiescent(client)
            except Exception as exc:
                report['cleanup_background']=dict(quiescent=False)
                report['requires_ddr_recovery']=True
                report['cleanup_errors'].append('Capture drain: '+str(exc))
        if probe_owned:
            try:
                current=probe.status()
                if current['waiting'] or current['active'] or current['rejected']:
                    raise DiagnosticError('Probe remains active or rejected after cancel')
                report['cleanup_probe_idle']=True
            except Exception as exc:report['cleanup_errors'].append('Probe idle check: '+str(exc))
        if generation is not None:
            try:
                current=api.request('/diagnostic/roi/status')
                if current['generation']!=generation or current['state'] in ('waiting','copying','ready'):
                    raise DiagnosticError('Owned camera diagnostic not confirmed released')
                report['cleanup_camera_released']=True
            except Exception as exc:report['cleanup_errors'].append('Camera idle check: '+str(exc))
        if report['cleanup_errors']:
            report['passed']=False
            if 'new_token_retry_permitted' in report:report['new_token_retry_permitted']=False
        try:report['video_after']=video_health(probe)
        except Exception as exc:report['video_health_error']=str(exc)
        (output/'report.json').write_text(json.dumps(report,indent=2))
    return report
