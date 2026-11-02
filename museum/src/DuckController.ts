import * as T from 'three';
import {DuckPaint,REGION_NAMES} from './DuckPaint';
import type {DuckStateMachine} from './DuckStateMachine';
export class DuckController {
 root=new T.Group();float=new T.Group();action=new T.Group();asset=new T.Group();mesh:T.Mesh;paint:DuckPaint;waterline=6;yawOffset=0;
 constructor(data:any){this.root.name='duck_root';this.float.name='float_root';this.action.name='action_root';this.asset.name='scanned_duck';this.root.add(this.float);this.float.add(this.action);this.action.add(this.asset);this.asset.scale.setScalar(.038);this.paint=new DuckPaint(data.meshGeometry,data.labels,data.adjacency);this.mesh=new T.Mesh(this.paint.geometry,new T.MeshStandardMaterial({vertexColors:true,roughness:.68,metalness:0,side:T.DoubleSide}));this.asset.add(this.mesh);}
 partAt(face:number){return REGION_NAMES[this.paint.labels[face]]||'身体';}
 update(f:DuckStateMachine){const p=f.pose();this.root.position.set(f.x,-this.waterline*.038,f.z);this.root.rotation.set(0,f.yaw,0);this.float.position.set(0,p.y,0);this.float.rotation.set(0,0,0);this.action.position.set(0,0,0);this.action.rotation.set(p.pitch,0,p.roll);this.asset.rotation.set(0,this.yawOffset*Math.PI/180,0);this.asset.scale.setScalar(.038);}
 mode(v:string){this.paint.neutral=v==='stl';this.paint.refresh();}
 dispose(){this.mesh.geometry.dispose();(this.mesh.material as T.Material).dispose();}
}
