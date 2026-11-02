"""Post-acquisition audit and portable result archive. Never accesses hardware."""
import hashlib
import json
from pathlib import Path
import zipfile
import cv2
import numpy as np
try:
    from .live_geometry import write_json, closure_passes
except ImportError:
    from live_geometry import write_json, closure_passes


def audit(p, check=lambda: None):
    p=Path(p); load=lambda name:json.loads((p/name).read_text(encoding='utf-8'))
    state=load('live.json'); cfg=load('scan_config.json'); tests=[]
    def record(name, passed, detail):
        tests.append(dict(name=name,passed=bool(passed),detail=detail))
    report=dict(schema_version=2,scan_id=p.name,checks=tests,phases={},absolute_accuracy_validated=False,watertight=False)
    try:
        summary=load('fine_summary.json')
        report['geometry_closure']=summary.get('closure',{})
        record('geometry_closure',closure_passes(report['geometry_closure']),report['geometry_closure'])
        n=cfg.get('intervals',180); phases=[('geometry',p,'laser_on')]
        if state.get('real_color'):phases.append(('color',p/'color','color'))
        angle_sets=[]
        for phase,folder,suffix in phases:
            angles=[]; pulses=0; frames=0; failures=[]
            for i in range(n+1):
                check(); label=f'position{i:03d}'
                r=json.loads((folder/(label+'_record.json')).read_text())
                if r.get('status')!='captured_and_verified':failures.append(label+' record')
                angles.append(r['motion']['after'])
                if i:
                    m=json.loads((folder/(label+'_motion.json')).read_text())
                    pulses+=m['pulses']
                    if m.get('status')!='settled' or abs(m['after']-angles[-1])>=.06:failures.append(label+' motion')
                    if abs(m['after']-m['before']+m['pulses']*360/3200)>.25:failures.append(label+' increment')
                if abs(angles[-1]-angles[0]+round(i*3200/n)*360/3200)>.35:failures.append(label+' cumulative')
                for tail in [suffix,suffix+'_repeat']:
                    f=folder/(label+'_'+tail+'.png')
                    # Decode every accepted original: a PNG signature alone is insufficient.
                    im=cv2.imread(str(f))
                    if im is None or im.shape!=(1080,1920,3):failures.append(label+' image '+tail)
                    frames+=1
            angle_sets.append(np.array(angles))
            detail=dict(positions=len(angles),frames=frames,pulses=pulses,start=angles[0],end=angles[-1],failures=failures)
            report['phases'][phase]=detail
            record(phase+'_records',not failures and pulses==3200 and abs(angles[-1]-angles[0]+360)<.35,detail)
        with np.load(p/'fine_cloud_arrays.npz') as geo,np.load(p/'fine_mesh_arrays.npz') as mesh:
            xyz=geo['camera_aligned_mm'];faces=mesh['faces'];verts=mesh['display_vertices_mm']
            report['counts']=dict(points=len(xyz),vertices=len(verts),triangles=len(faces))
            record('geometry_arrays',len(xyz)>0 and np.isfinite(xyz).all() and np.isfinite(verts).all() and (not len(faces) or (faces.min()>=0 and faces.max()<len(verts))),report['counts'])
            if state.get('real_color'):
                with np.load(p/'colored_cloud_arrays.npz') as colors:
                    rgb=colors['rgb']
                    record('color_preserves_geometry',np.array_equal(xyz,colors['camera_aligned_mm']) and rgb.shape==xyz.shape and np.isfinite(rgb).all() and ((rgb>=0)&(rgb<=255)).all(),{'point_count':len(rgb)})
        if state.get('real_color'):
            record('color_encoder_alignment',np.max(np.abs(angle_sets[1]-angle_sets[0]+360))<.35,{'max_error_degrees':float(np.max(np.abs(angle_sets[1]-angle_sets[0]+360)))})
            x0,y0,x1,y1=cfg['roi']; images=[]
            for i in (0,n):
                im=cv2.rotate(cv2.imread(str(p/'color'/f'position{i:03d}_color.png')),cv2.ROTATE_90_CLOCKWISE)
                images.append(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)[y0:y1,x0:x1].astype(np.float32))
            shift,response=cv2.phaseCorrelate(*images,cv2.createHanningWindow((x1-x0,y1-y0),cv2.CV_32F))
            detail=dict(shift_xy_px=shift,shift_norm_px=float(np.linalg.norm(shift)),response=response,limit_px=3)
            report['color_closure']=detail
            record('color_closure',response>=.4 and np.linalg.norm(shift)<3,detail)
        record('operator_validity',state.get('scan_valid') is not False,{'scan_valid':state.get('scan_valid')})
        annotation=p/'operator_annotation.json'
        if annotation.exists():
            note=json.loads(annotation.read_text(encoding='utf-8'))
            record('operator_annotation',note.get('scan_valid') is not False,note)
    except (OSError,ValueError,KeyError,cv2.error,TypeError) as exc:
        record('data_complete',False,{'error':str(exc)})
    report['passed']=bool(tests) and all(x['passed'] for x in tests)
    report['status']='passed' if report['passed'] else 'needs_review'
    report['color_acquired']=bool(state.get('real_color'))
    report['frame_pair_retries']=state.get('frame_retries',0)
    report['limits']='Repeatability and data consistency only; no absolute dimensional accuracy or watertightness certification.'
    write_json(p/'completion_verification.json',report)
    return report


def archive(p, check=lambda:None):
    """Keep original files in place; ZIP contains results/provenance and a hash manifest of raw PNGs."""
    p=Path(p);files=[]
    for f in sorted(p.rglob('*')):
        check()
        if not f.is_file() or f.suffix in ('.zip','.tmp') or f.name in ('archive_manifest.json','live.json','timing_events.jsonl','timing_summary.json') or 'attempts' in f.parts:continue
        digest=hashlib.sha256()
        with f.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):check();digest.update(block)
        files.append(dict(path=f.relative_to(p).as_posix(),bytes=f.stat().st_size,sha256=digest.hexdigest()))
    manifest=dict(scan_id=p.name,raw_images_included=False,originals_location=str(p),files=files)
    write_json(p/'archive_manifest.json',manifest)
    tmp=p/'result_archive.tmp'
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
        for item in files:
            check();f=p/item['path']
            if f.suffix in ('.json','.ply'):z.write(f,item['path'])
        z.write(p/'archive_manifest.json','archive_manifest.json')
    tmp.replace(p/'result_archive.zip')
    return dict(files=len(files),bytes=(p/'result_archive.zip').stat().st_size,raw_images_retained=True)


def finalize(p, check=lambda:None):
    result=audit(p,check)
    summary_path=Path(p)/'fine_summary.json'
    if summary_path.exists():
        summary=json.loads(summary_path.read_text(encoding='utf-8'))
        summary['completion_verification']=result
        write_json(summary_path,summary)
    return result,archive(p,check)
