"""Opt-in geometry bridge to the existing project math, no hardware operations."""
import hashlib
import importlib.util
import json
from pathlib import Path
import cv2
import numpy as np
from turntable_filter import load_filter,filter_mask
from spatial_filter import load as load_spatial
from row_results import ProtocolError,angle_degrees,require


def load_existing_geometry(project_path):
    """Load the audited pure geometry_candidates function, not scan controllers."""
    path=Path(project_path)/'dual-laser-20260930/dual_identity.py'
    spec=importlib.util.spec_from_file_location('_afc03_existing_geometry',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.geometry_candidates


class PointCloudAdapter:
    def __init__(self,bundle,geometry_candidates):
        self.bundle=Path(bundle);self.geometry_candidates=geometry_candidates
        self.hashes={};objects={}
        for name in ('camera','planes','axis'):
            data=(self.bundle/(name+'.json')).read_bytes()
            self.hashes[name+'_sha256']=hashlib.sha256(data).hexdigest()
            objects[name]=json.loads(data)
        self.camera=objects['camera'];self.planes=objects['planes']['planes'];self.axis=objects['axis']
        self.turntable_filter=load_filter(self.bundle,self.hashes)
        self.spatial_filter=load_spatial(self.bundle,self.hashes["axis_sha256"])

    def reconstruct(self,frame):
        header=frame.header;calibration=header['calibration'];g=header['geometry']
        require(header['complete'] is True and header['error']==0,'Only a committed complete frame may reconstruct')
        require(all(calibration[k]==value for k,value in self.hashes.items()),'Calibration bundle hash mismatch')
        require(self.camera['input_raw_size_wh']==g['raw_size_wh'] and
                self.camera['calibration_image_size_wh']==g['processing_size_wh'],
                'Camera calibration image geometry mismatch')
        preprocessing=self.camera['preprocessing']
        require(preprocessing['rotate_clockwise_degrees']==g['rotation_cw'] and
                preprocessing.get('crop') is False and preprocessing.get('resize') is False,
                'Calibration preprocessing mismatch')
        label=header['laser_id']
        require(label in ('A','B') and header['laser_control']!='unassigned',
                'Unassigned simultaneous-laser peaks cannot be triangulated as A or B by peak order')
        source=header['angle']['source']
        axis_key={'commanded_pulses_no_encoder':'axis_direction_for_positive_pulses_camera',
                  'encoder_observed':'axis_direction_for_positive_encoder_camera'}[source]
        require(axis_key in self.axis,'Axis calibration does not match angle source')
        # geometry_candidates currently names its common direction argument
        # positive_pulses; explicitly adapt the independently checked source.
        direction=np.asarray(self.axis[axis_key],float)
        require(np.isfinite(direction).all() and np.linalg.norm(direction)>0,'Invalid axis direction')
        direction=direction/np.linalg.norm(direction)
        axis_for_math=dict(self.axis,axis_direction_for_positive_pulses_camera=direction.tolist())
        uv=np.asarray(frame.processing_uv(),float).reshape(-1,2)
        if len(uv):
            labels,clouds=self.geometry_candidates(uv,self.camera,self.planes,axis_for_math,**({"max_radius_mm":None} if self.spatial_filter["enabled"] else {}))
            keep=np.array([label in candidate for candidate in labels],bool)
            xyz=clouds[label][keep]
        else:
            keep=np.zeros(0,dtype=bool);xyz=np.empty((0,3))
        center=np.asarray(self.axis['axis_point_closest_to_camera_origin_mm'],float)
        degrees=angle_degrees(header['angle'])
        # Same row-vector inverse rotation as reconstruct_manual_round.align_to_zero.
        rotation=cv2.Rodrigues(direction*np.deg2rad(degrees))[0]
        aligned=(xyz-center)@rotation+center
        ex=np.array([1.,0.,0.]);ex-=direction*(ex@direction)
        require(np.linalg.norm(ex)>1e-8,'Axis frame basis is degenerate')
        ex/=np.linalg.norm(ex);ez=np.cross(ex,direction)
        delta=aligned-center
        axis_frame=np.c_[delta@ex,delta@direction,delta@ez]
        ground_keep,ground_report=filter_mask(axis_frame,self.turntable_filter)
        record_indices=np.flatnonzero(keep)[ground_keep]
        xyz=xyz[ground_keep];aligned=aligned[ground_keep];axis_frame=axis_frame[ground_keep]
        return dict(uv=uv[record_indices],camera_xyz_mm=xyz,camera_aligned_mm=aligned,
                    axis_frame_mm=axis_frame,kept_record_indices=record_indices,turntable_filter=ground_report,
                    spatial_profile=self.spatial_filter,source_frame_id=header['source_frame_id'],request_id=header['request_id'],
                    laser_id=label,angle_deg=degrees,angle_source=source,
                    angle_is_measured=(source=='encoder_observed'),
                    input_centers=len(uv),retained_points=len(xyz),
                    absolute_accuracy_validated=False)
