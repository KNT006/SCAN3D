import * as T from 'three';
export class DuckInteraction {
 ray=new T.Raycaster();pointer=new T.Vector2();down:any=null;petMode=false;paintMode:'off'|'select'|'brush'|'eyedropper'='off';lastStroke=0;lastBrush=0;distance=0;clean:(()=>void)[]=[];
 constructor(el:HTMLCanvasElement,camera:T.Camera,duck:T.Object3D,water:T.Object3D,callback:(s:string,p?:any)=>void){
 const hit=(e:PointerEvent,obj:T.Object3D)=>{const r=el.getBoundingClientRect();this.pointer.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);this.ray.setFromCamera(this.pointer,camera);return this.ray.intersectObject(obj,true).find(h=>h.object.visible);};
 const on=(n:string,fn:any)=>{el.addEventListener(n,fn);this.clean.push(()=>el.removeEventListener(n,fn));};
 const finish=()=>{if(this.down&&this.paintMode==='brush')callback('paint:end');this.down=null;};
 const dab=(e:PointerEvent,x=e.clientX,y=e.clientY)=>{const h=hit({clientX:x,clientY:y} as PointerEvent,duck);if(h)callback('paint:move',{face:h.faceIndex,point:h.object.worldToLocal(h.point.clone()),pressure:e.pointerType==='pen'?Math.max(.05,e.pressure):1});};
 on('pointerdown',(e:PointerEvent)=>{if(e.button!==0)return;this.down={x:e.clientX,y:e.clientY,lx:e.clientX,ly:e.clientY,id:e.pointerId};this.distance=0;if(this.paintMode==='brush'){callback('paint:start');dab(e);}});
 on('pointermove',(e:PointerEvent)=>{if(!this.down||this.down.id!==e.pointerId)return;const d=Math.hypot(e.clientX-this.down.lx,e.clientY-this.down.ly);const px=this.down.lx,py=this.down.ly;this.down.lx=e.clientX;this.down.ly=e.clientY;if(this.paintMode==='brush'){if(d<.5)return;const steps=Math.min(12,Math.max(1,Math.ceil(d/4)));for(let i=1;i<=steps;i++)dab(e,px+(e.clientX-px)*i/steps,py+(e.clientY-py)*i/steps);return;}if(this.petMode&&hit(e,duck)){this.distance+=d;if(this.distance>35&&performance.now()-this.lastStroke>900){this.lastStroke=performance.now();this.distance=0;callback('pet');}}});
 on('pointerup',(e:PointerEvent)=>{if(!this.down)return;const distance=Math.hypot(e.clientX-this.down.x,e.clientY-this.down.y);if(this.paintMode==='brush'){finish();return;}this.down=null;if(distance>6||this.petMode)return;const d=hit(e,duck);if(this.paintMode==='eyedropper'){if(d)callback('paint:sample',{face:d.faceIndex,point:d.object.worldToLocal(d.point.clone())});return;}if(this.paintMode==='select'){if(d)callback('paint:select',{face:d.faceIndex});return;}if(d)callback('react',{face:d.faceIndex});else{const h=hit(e,water);if(h)callback('swim',{x:h.point.x,z:h.point.z});}});
 on('pointercancel',finish);on('pointerleave',finish);
 }
 dispose(){this.clean.forEach(f=>f());}
}
