import {deletePaintFamily} from '../DuckPaint';
import {deletePreview} from './CabinetCache';
export async function clearLocalExhibit(a:{id:string;geometry_key:string}){
 localStorage.removeItem('scan3d-museum-v1:'+a.id);
 if(localStorage.getItem('scan3d-museum-active')===a.id)localStorage.removeItem('scan3d-museum-active');
 for(const key of Object.keys(localStorage))if(key.startsWith('scan3d-paint-revision:'+a.geometry_key))localStorage.removeItem(key);
 await Promise.all([deletePaintFamily(a.geometry_key),deletePreview(a.id)]);
}
