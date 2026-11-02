import type {ExhibitAsset} from './MuseumData';
/** Only the current photo-assisted labels are active in the museum. */
export function resolveSegmentation(a:ExhibitAsset):ExhibitAsset{
 const s=a.color_segmentation;
 if(!s)throw Error('展品缺少照片辅助分区：'+a.id);
 return {...a,segmentation_mode:'rgb',paint_key:a.geometry_key+':'+s.version,
  labels_file:s.labels_file,regions:[...s.regions],palette:[...s.palette],segmentation_note:s.note,thumbnail:s.thumbnail||a.thumbnail};
}
export function paintKey(a:ExhibitAsset){return a.paint_key||a.geometry_key;}
