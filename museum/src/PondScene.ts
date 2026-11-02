import * as T from 'three';
export class PondScene {
 scene=new T.Scene();water:T.Mesh;sun:T.DirectionalLight;ambient:T.HemisphereLight;
 constructor(){this.scene.background=new T.Color('#e5eee3');this.scene.fog=new T.Fog('#e5eee3',16,35);this.ambient=new T.HemisphereLight('#ffffff','#688979',2);this.sun=new T.DirectionalLight('#fff3db',2.2);this.sun.position.set(-4,9,5);this.scene.add(this.ambient,this.sun);
 const mesh=(g:T.BufferGeometry,c:string)=>new T.Mesh(g,new T.MeshStandardMaterial({color:c,roughness:.9}));
 const ground=mesh(new T.CircleGeometry(35,80),'#e5eee3');ground.rotation.x=-Math.PI/2;ground.position.y=-.48;this.scene.add(ground);
 const bank=mesh(new T.CylinderGeometry(4,4.25,.34,96),'#bcc5a3');bank.position.y=-.27;this.scene.add(bank);
 const rim=mesh(new T.TorusGeometry(3.75,.2,12,96),'#e1d8bd');rim.rotation.x=Math.PI/2;rim.position.y=-.055;this.scene.add(rim);
 this.water=new T.Mesh(new T.CircleGeometry(3.68,96),new T.MeshStandardMaterial({color:'#86c8c4',roughness:.32,metalness:.05,transparent:true,opacity:.94}));this.water.rotation.x=-Math.PI/2;this.water.position.y=0;this.scene.add(this.water);
 for(let i=0;i<13;i++){const a=i*2.3999,r=3.9+(i%3)*.12;const rock=mesh(new T.IcosahedronGeometry(.19+(i%3)*.06,1),['#b0b6a5','#d6d4bf','#c6c6b5'][i%3]);rock.position.set(Math.sin(a)*r,-.08,Math.cos(a)*r);rock.scale.set(1.4,.6,1);rock.rotation.y=a;this.scene.add(rock);}
 for(const a of [2.2,2.5,4.2]){for(let i=0;i<5;i++){const stem=mesh(new T.ConeGeometry(.06,.5+i*.07,5),'#779777');stem.position.set(Math.sin(a)*3.9+(i-2)*.09,.1,Math.cos(a)*3.9);stem.rotation.z=(i-2)*.08;this.scene.add(stem);}}
 for(const p of [[-2.6,-1.8],[2.6,-1.5],[-2.9,-.6]]){const leaf=mesh(new T.CircleGeometry(.32,28,0,Math.PI*1.85),'#699d7f');leaf.rotation.x=-Math.PI/2;leaf.position.set(p[0],.018,p[1]);this.scene.add(leaf);}
 }
 update(f:any,dt:number){const night=f.state==='sleep';this.ambient.intensity+=((night?.6:2)-this.ambient.intensity)*Math.min(1,dt*2);this.sun.intensity+=((night?.45:2.2)-this.sun.intensity)*Math.min(1,dt*2);}
 dispose(){this.scene.traverse(o=>{if(o instanceof T.Mesh){o.geometry.dispose();const ms=Array.isArray(o.material)?o.material:[o.material];ms.forEach(m=>m.dispose());}});}
}
