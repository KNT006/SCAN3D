import * as T from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {DuckPaint,loadPaint,storePaint} from '../DuckPaint';
import {DuckInteraction} from '../DuckInteraction';
import {loadAsset} from './MuseumAssets';
import {paintKey} from './MuseumSegmentation';
import type {ExhibitAsset,ExhibitAction} from './MuseumData';
import type {BrushStyle} from '../BrushProfiles';
export class ExhibitScene {
 scene=new T.Scene();camera=new T.PerspectiveCamera(36,1,.1,80);renderer:T.WebGLRenderer;controls:OrbitControls;
 root=new T.Group();actionRoot=new T.Group();paint?:DuckPaint;mesh?:T.Mesh;interaction?:DuckInteraction;
 buffers:ArrayBuffer[]=[];loadMs=0;fps=0;ready=false;disposed=false;resize:ResizeObserver;
 abort=new AbortController();raf=0;last=0;nextRender=0;elapsed=0;frames=0;fpsStart=0;action:ExhibitAction='none';actionTime=0;turnStart=0;
 yaw=0;spin=false;editing=false;tool='select';brushColor='#e895b3';selected=0;radius=3;highlight=false;saveTimer:any;noticeTimer:any;
 brushStyle:BrushStyle='pen';brushOpacity=1;
 lights:T.Light[]=[];height=2.5;generation=0;sampled:(color:string)=>void=()=>{};
 constructor(public host:HTMLDivElement,public asset:ExhibitAsset,public notify:(s:string)=>void,public picked:(n:number)=>void,public changed:()=>void){
  this.renderer=new T.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power',preserveDrawingBuffer:true});
  this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));this.renderer.outputColorSpace=T.SRGBColorSpace;
  this.renderer.toneMapping=T.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.05;
  this.renderer.domElement.setAttribute('aria-label',asset.name+'三维展品，可拖动旋转');host.appendChild(this.renderer.domElement);
  this.controls=new OrbitControls(this.camera,this.renderer.domElement);this.controls.enableDamping=true;this.controls.enablePan=false;
  this.controls.minDistance=3.4;this.controls.maxDistance=10;this.controls.minPolarAngle=.35;this.controls.maxPolarAngle=1.5;
  this.controls.addEventListener('start',()=>{if(this.action==='turn'){this.action='none';}this.spin=false;});
  this.resetView();this.scene.add(this.root);this.root.position.y=.35;this.root.add(this.actionRoot);
  const hemi=new T.HemisphereLight('#fff9ef','#b2c5c6',1.5);this.scene.add(hemi);
  const key=new T.DirectionalLight('#fff5e5',2.3);key.position.set(-3,6,5);this.scene.add(key);
  const rim=new T.DirectionalLight('#e8f5f5',1);rim.position.set(4,3,-3);this.scene.add(rim);
  this.lights=[hemi,key,rim];
  const base=new T.Mesh(new T.CylinderGeometry(1.86,1.89,.32,96),new T.MeshStandardMaterial({color:'#e5dfd2',roughness:.85}));base.position.y=.16;this.scene.add(base);
  const top=new T.Mesh(new T.CylinderGeometry(1.83,1.83,.015,96),new T.MeshStandardMaterial({color:'#f5f0e5',roughness:1}));top.position.y=.33;this.scene.add(top);
  const edge=new T.Mesh(new T.TorusGeometry(1.84,.009,8,100),new T.MeshStandardMaterial({color:'#a6a193',metalness:.3,roughness:.7}));edge.rotation.x=Math.PI/2;edge.position.y=.315;this.scene.add(edge);
  const c=document.createElement('canvas');c.width=c.height=128;const ctx=c.getContext('2d')!;const grad=ctx.createRadialGradient(64,64,2,64,64,64);grad.addColorStop(0,'rgba(44,50,42,.22)');grad.addColorStop(1,'rgba(44,50,42,0)');ctx.fillStyle=grad;ctx.fillRect(0,0,128,128);
  const shadow=new T.Mesh(new T.PlaneGeometry(3.5,3.5),new T.MeshBasicMaterial({map:new T.CanvasTexture(c),transparent:true,depthWrite:false}));shadow.rotation.x=-Math.PI/2;shadow.position.y=.344;this.scene.add(shadow);
  this.resize=new ResizeObserver(()=>{const w=Math.max(1,host.clientWidth),h=Math.max(1,host.clientHeight);this.renderer.setSize(w,h);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();});this.resize.observe(host);
  this.last=this.fpsStart=performance.now();this.raf=requestAnimationFrame(this.tick);
 }
 async load(){const start=performance.now();const d=await loadAsset(this.asset,this.abort.signal);if(this.disposed){d.geometry.dispose();return;}
  this.buffers=d.buffers;this.paint=new DuckPaint(d.geometry,d.labels,d.adj);this.paint.palette=[...this.asset.palette];this.paint.refresh();
  try{const s=await loadPaint(paintKey(this.asset));if(s)this.paint.restore(s);}catch{this.notify('本机上色读取失败，可从展品包恢复');}
  if(this.disposed){this.paint.geometry.dispose();return;}
  const material=new T.MeshStandardMaterial({vertexColors:true,roughness:.72,metalness:0,side:T.DoubleSide});this.paint.enableEdgeSmoothing(material);
  this.mesh=new T.Mesh(this.paint.geometry,material);
  this.mesh.scale.setScalar(this.height/this.asset.bounds_mm[1]);this.actionRoot.add(this.mesh);
  this.interaction=new DuckInteraction(this.renderer.domElement,this.camera,this.root,new T.Group(),this.handle);
  this.ready=true;this.sync();this.loadMs=Math.round(performance.now()-start);
 }
 handle=(s:string,p?:any)=>{if(!this.paint)return;
  if(s==='paint:sample'){const c=this.paint.colorAt(p.face,p.point);if(c){this.brushColor=c;this.sampled(c);}return;}
  if(s==='paint:start'){this.paint.begin();return;}if(s==='paint:move'){this.paint.smoothPaint(p.face,this.radius,this.tool==='erase'?null:this.brushColor,p.point,{style:this.brushStyle,opacity:this.brushOpacity,pressure:p.pressure??1});return;}
  if(s==='paint:end'){this.paint.commit();this.scheduleSave();this.changed();return;}
  if(s==='paint:select'||s==='react'){this.selected=this.paint.labels[p.face];this.picked(this.selected);if(!this.editing){this.perform('nod');this.notify('你碰到了「'+this.asset.regions[this.selected]+'」附近 · 候选分区');}return;}
 };
 sync(){if(!this.paint||!this.interaction)return;this.interaction.paintMode=this.editing?(this.tool==='eyedropper'?'eyedropper':(this.tool==='brush'||this.tool==='erase')?'brush':'select'):'off';this.controls.mouseButtons.LEFT=this.editing&&(this.tool==='brush'||this.tool==='erase')?null:T.MOUSE.ROTATE;this.controls.mouseButtons.RIGHT=T.MOUSE.ROTATE;this.renderer.domElement.style.cursor=this.editing&&this.tool==='eyedropper'?'crosshair':'';this.paint.selected=this.selected;this.paint.highlight=this.highlight;this.paint.refresh();}
 color(index:number,c:string){if(!this.paint||!/^#[0-9a-f]{6}$/i.test(c)||index<0||index>7)return;this.paint.palette[index]=c;this.paint.refresh();this.scheduleSave();}
 preset(p:string[]){if(!this.paint)return;this.paint.palette=[...p];this.paint.refresh();this.scheduleSave();}
 saveTask?:Promise<void>;savePending=false;
 scheduleSave(){this.savePending=true;clearTimeout(this.saveTimer);this.saveTimer=setTimeout(()=>void this.save(),250);}
 async save(){if(!this.paint||!this.savePending)return;this.savePending=false;try{this.saveTask=storePaint(paintKey(this.asset),this.paint.snapshot());await this.saveTask;if(!this.disposed)this.notify('配色已自动保存在本机');}catch{this.savePending=true;if(!this.disposed)this.notify('本机保存失败，请导出展品包备份');}}
 restore(data:any){if(!this.paint)return;this.paint.restore(data);this.paint.history=[];this.scheduleSave();this.changed();}
 setNeutral(v:boolean){if(this.paint){this.paint.neutral=v;this.paint.refresh();}}
 resetView(){this.camera.position.set(4.1,2.85,6.1);this.controls.target.set(0,1.38,0);this.controls.update();}
 perform(a:ExhibitAction,region?:number){if(!['none','nod','turn','highlight','reset'].includes(a))return;this.action=a;this.actionTime=0;this.turnStart=this.root.rotation.y;
  if(a==='reset'){this.root.rotation.y=this.yaw*Math.PI/180;this.action='none';this.resetView();}
  if(a==='highlight'&&this.paint){clearTimeout(this.noticeTimer);this.selected=region??0;this.picked(this.selected);this.paint.selected=this.selected;this.paint.highlight=true;this.paint.refresh();this.noticeTimer=setTimeout(()=>{if(!this.disposed)this.sync();},3500);this.action='none';}
 }
 tick=(now:number)=>{if(this.disposed)return;this.raf=requestAnimationFrame(this.tick);if(document.hidden){this.last=now;this.nextRender=now;this.fpsStart=now;this.frames=0;return;}if(now<this.nextRender)return;this.nextRender=Math.max(this.nextRender+1000/60,now);const dt=Math.min(.05,Math.max(0,(now-this.last)/1000));this.last=now;
  this.elapsed+=dt;this.actionTime+=dt;this.actionRoot.position.set(0,0,0);this.actionRoot.rotation.set(0,0,0);
  if(this.action==='nod'){const t=Math.min(1,this.actionTime/1.7);this.actionRoot.rotation.x=Math.sin(t*Math.PI*2)*.08*Math.sin(t*Math.PI);this.actionRoot.position.y=Math.sin(t*Math.PI)*.035;if(t===1)this.action='none';}
  if(this.action==='turn'){const t=Math.min(1,this.actionTime/5);this.root.rotation.y=this.turnStart+(t*t*(3-2*t))*Math.PI*2;if(t===1){this.root.rotation.y=this.turnStart;this.action='none';}}
  else if(this.spin&&!this.editing)this.root.rotation.y+=dt*.2;
  this.controls.update();this.renderer.render(this.scene,this.camera);this.frames++;if(now-this.fpsStart>1000){this.fps=Math.round(this.frames*1000/(now-this.fpsStart));this.frames=0;this.fpsStart=now;}
 };
 setYaw(v:number){this.yaw=v;this.root.rotation.y=v*Math.PI/180;this.action='none';}
 async screenshot(){this.renderer.render(this.scene,this.camera);return new Promise<Blob>((resolve,reject)=>this.renderer.domElement.toBlob(b=>b?resolve(b):reject(Error('截图失败')),'image/png'));}
 dispose(){if(this.disposed)return;this.disposed=true;this.abort.abort();cancelAnimationFrame(this.raf);clearTimeout(this.saveTimer);clearTimeout(this.noticeTimer);if(this.paint)void this.save();this.resize.disconnect();this.interaction?.dispose();this.controls.dispose();
  this.scene.traverse((o:any)=>{o.geometry?.dispose();if(o.material){const ms=Array.isArray(o.material)?o.material:[o.material];ms.forEach((m:any)=>{m.map?.dispose();m.dispose();});}});this.renderer.dispose();this.renderer.forceContextLoss();this.renderer.domElement.remove();}
}
