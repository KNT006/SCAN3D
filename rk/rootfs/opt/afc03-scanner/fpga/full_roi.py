"""Atomic full-ROI receiver over the qualified FPGA mailbox, no motion control.

The current bitstream transposes native columns into clockwise-90 image rows.
Each bounded job is CRC checked by JobClient; no partial ROI is published.
"""
import dataclasses
import time
import zlib
from row_results import FrameReceiver, PROTOCOL, RowDone, Center, decode_record, require


def batch_rois(geometry, maximum_rows=640):
    require(geometry['rotation_cw'] == 90, 'This FPGA build supports clockwise 90 only')
    require(geometry['raw_size_wh'] == [1920,1080], 'Unsupported native size')
    require(geometry['global_x_origin'] == 0 and geometry['row_input_width'] == 1080,
            'FPGA must process full native-height rows')
    x0,y0,x1,y1 = geometry['roi_xyxy']
    require(4 <= x0 < x1 <= 1076 and 0 <= y0 < y1 <= 1920, 'ROI outside supported margins')
    require(type(maximum_rows) is int and 4 <= maximum_rows <= 680 and maximum_rows % 4 == 0,
            'Batch exceeds bounded result RAM')
    start = y0 // 4 * 4
    while start < y1:
        end = min(start + maximum_rows, y1)
        yield [start,0,end,1080]
        start = end


def receive_full_roi(job, snapshot, context, angle, background, on, epoch, geometry_revision,
                     calibration_revision, token, check=lambda: None, maximum_rows=640,during_last=None):
    """snapshot(role) returns a RoleClient reply. All identities remain pinned logically.

The caller holds the common hardware locks across capture and all batches.
FrameReceiver additionally validates row order, counts, centers and final CRC.
"""
    if getattr(job,'spatial_candidates',False):
        from rgb_adaptive_strategy import validate_profile
        validate_profile(context)
        maximum_rows=min(maximum_rows,60)
    role = {'A':1,'B':2}[context['laser_id']]
    require(context['background_generation'] == background.generation, 'Wrong background context')
    for identity in (background,on):
        require((identity.epoch,identity.geometry,identity.calibration) ==
                (epoch,geometry_revision,calibration_revision), 'Unbound frame revisions')
    overlapped=False
    def stable():
        check()
        for r,identity in ((0,background),(role,on)):
            state = snapshot(r)
            same=(state.background==identity) if not overlapped else ((state.background.epoch,state.background.geometry,state.background.calibration)==(epoch,geometry_revision,calibration_revision))
            require(state.active and same and not state.flags & 0x2d,
                    'Frame changed, busy, or faulted; discard whole ROI')
    stable()
    g = context['geometry'];x0,y0,x1,y1 = g['roi_xyxy']
    payloads=[];reports=[];started=time.perf_counter()
    rois=list(batch_rois(g, maximum_rows))
    for index,roi in enumerate(rois):
        stable()
        callback=during_last if index==len(rois)-1 else None
        def during():
            nonlocal overlapped
            overlapped=True
            callback()
        summary,payload=job.run(role=role,epoch=epoch,geometry=geometry_revision,
            calibration=calibration_revision,token=token+index,width=1920,height=1080,
            roi=roi,left=x0,right=x1-1,expected_bg=background,expected_on=on,
            **(dict(during=during) if callback is not None else {}))
        require(summary['epoch']==epoch and summary['on_frame']==on.source_frame and
                summary['bg_frame']==background.source_frame and summary['token']==token+index,
                'Batch frame identity mismatch')
        require(len(payload)%16==0 and summary['records']==len(payload)//16 and
                summary['crc32']==zlib.crc32(payload),'Batch CRC/count mismatch')
        # Validate ALL batch rows, including the aligned prefix outside requested ROI.
        bc=dict(context,geometry=dict(g,roi_xyxy=[x0,roi[0],x1,roi[2]]))
        batch=commit_payload(bc,angle,token+index,on.source_frame,payload)
        require(len(batch.rows)==summary['rows'] and len(batch.centers)==summary['centers'],
                'Batch counters do not match decoded records')
        payloads.append(b''.join(payload[i:i+16] for i in range(0,len(payload),16)
                                 if y0<=decode_record(payload[i:i+16]).row<y1))
        reports.append(dict(summary,roi=roi,receive_seconds=getattr(job,'last_receive_seconds',None),overlap_callback_seconds=getattr(job,'last_overlap_seconds',0)))
        stable()
    payload=b''.join(payloads)
    frame=commit_payload(context,angle,token,on.source_frame,payload)
    stable()
    return frame,dict(passed=True,batches=reports,rows=len(frame.rows),centers=len(frame.centers),
                      payload_crc32=frame.payload_crc32,seconds=time.perf_counter()-started,
                      transport=getattr(job,'transport','unspecified_result_transport'),
                      hardware_seconds=sum(r['cycles'] for r in reports)/1e8)


def commit_payload(context,angle,request_id,source_frame_id,payload):
    receiver=FrameReceiver(context,timeout_s=60)
    receiver.register(request_id,angle,source_frame_id)
    receiver.begin(dict(context,protocol=PROTOCOL,request_id=request_id,angle=angle,
                        source_frame_id=source_frame_id,complete=False,error=0))
    count=0
    for offset in range(0,len(payload),16):
        record=decode_record(payload[offset:offset+16]);receiver.push(record)
        if isinstance(record,Center):count+=1
    g=context['geometry']
    return receiver.finish(dict(stream_epoch=context['stream_epoch'],request_id=request_id,
        source_frame_id=source_frame_id,complete=True,error=0,row_count=g['roi_xyxy'][3]-g['roi_xyxy'][1],
        center_count=count,record_count=len(payload)//16,payload_crc32=zlib.crc32(payload)))
