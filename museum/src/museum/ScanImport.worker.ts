import {STLLoader} from 'three/addons/loaders/STLLoader.js';

// Geometry and colour preparation run off the UI thread. Coordinates stay in mm.
export function prepareScan(d:any){
 if(!(d.stl instanceof ArrayBuffer)||d.stl.byteLength>24*1024*1024)throw Error('STL 文件过大，请选择较低重建深度的模型');
 const g=new STLLoader().parse(d.stl),p=g.getAttribute('position');
 const count=p.count/3;
 if(!Number.isInteger(count)||count<1||count>200000){g.dispose();throw Error('模型需包含 1 至 200000 个三角面，请选择较低重建深度的模型');}
 const vertices:number[]=[],faces=new Uint32Array(p.count),lookup=new Map<string,number>();
 const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
 for(let i=0;i<p.count;i++){
  const v=[p.getX(i),p.getY(i),p.getZ(i)];if(!v.every(Number.isFinite))throw Error('STL 坐标无效');
  const key=v.map(x=>Math.round(x*10000)).join(',');let n=lookup.get(key);
  if(n===undefined){n=vertices.length/3;lookup.set(key,n);vertices.push(...v);}
  faces[i]=n;v.forEach((x,k)=>{lo[k]=Math.min(lo[k],x);hi[k]=Math.max(hi[k],x);});
 }
 g.dispose();const bounds=hi.map((x,i)=>x-lo[i]);if(bounds[1]<.001||Math.max(...bounds)>10000)throw Error('STL 尺寸无效');
 const labels=new Uint8Array(count),adj=new Int32Array(count*3).fill(-1),edges=new Map<string,[number,number]>();
 for(let i=0;i<count;i++)for(let j=0;j<3;j++){
  const a=faces[i*3+j],b=faces[i*3+(j+1)%3],key=a<b?`${a},${b}`:`${b},${a}`;
  const other=edges.get(key);if(other){adj[i*3+j]=other[0];adj[other[0]*3+other[1]]=i;edges.delete(key);}else edges.set(key,[i,j]);
 }
 const palette=Array(8).fill('#e7dfd0'),regions=['整体','自定色区 2','自定色区 3','自定色区 4','自定色区 5','自定色区 6','自定色区 7','未覆盖表面'];
 let matched=0,totalArea=0,colouredArea=0;
 if(d.mode==='cloud'){
  const xyz=new Float32Array(d.xyz),rgb=new Uint8Array(d.rgb),n=xyz.length/3;
  if(!n||n>100000||rgb.length!==xyz.length||!xyz.every(Number.isFinite))throw Error('点云颜色数据无效');
  // Deterministic colour clustering; no semantic labels are inferred.
  const colors:number[][]=[];for(let i=0;i<n;i+=Math.max(1,Math.floor(n/8000)))colors.push(Array.from(rgb.slice(i*3,i*3+3)));
  const centers=[colors[0].slice()];
  const dist=(a:number[],b:number[])=>a.reduce((s,x,k)=>s+(x-b[k])**2,0);
  while(centers.length<7){let best=colors[0],max=0;for(const c of colors){const delta=Math.min(...centers.map(k=>dist(c,k)));if(delta>max){max=delta;best=c;}}if(max<225)break;centers.push(best.slice());}
  const nearest=(c:number[])=>{let b=0;for(let k=1;k<centers.length;k++)if(dist(c,centers[k])<dist(c,centers[b]))b=k;return b;};
  for(let pass=0;pass<8;pass++){const sums=centers.map(()=>[0,0,0,0]);for(const c of colors){const s=sums[nearest(c)];c.forEach((x,k)=>s[k]+=x);s[3]++;}sums.forEach((s,k)=>{if(s[3])centers[k]=s.slice(0,3).map(x=>x/s[3]);});}
  centers.forEach((c,k)=>{palette[k]='#'+c.map(x=>Math.round(x).toString(16).padStart(2,'0')).join('');regions[k]=`色区 ${k+1}`;});
  const cell=2,grid=new Map<string,number[]>();
  for(let i=0;i<n;i++){const key=[0,1,2].map(k=>Math.floor(xyz[i*3+k]/cell)).join(',');const bin=grid.get(key)||[];if(bin.length<64)bin.push(i);grid.set(key,bin);}
  for(let i=0;i<count;i++){
   const a=faces[i*3]*3,b=faces[i*3+1]*3,c=faces[i*3+2]*3;
   const center=[0,1,2].map(k=>(vertices[a+k]+vertices[b+k]+vertices[c+k])/3),base=center.map(x=>Math.floor(x/cell));
   let best=-1,dd=4;
   for(let x=-1;x<=1;x++)for(let y=-1;y<=1;y++)for(let z=-1;z<=1;z++)for(const q of grid.get(`${base[0]+x},${base[1]+y},${base[2]+z}`)||[]){
    let delta=0;for(let k=0;k<3;k++)delta+=(xyz[q*3+k]-center[k])**2;if(delta<dd){dd=delta;best=q;}
   }
   const u=[0,1,2].map(k=>vertices[b+k]-vertices[a+k]),v=[0,1,2].map(k=>vertices[c+k]-vertices[a+k]);
   const area=Math.hypot(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])/2;totalArea+=area;
   labels[i]=best<0?7:nearest(Array.from(rgb.slice(best*3,best*3+3)));if(best>=0){matched++;colouredArea+=area;}
  }
  if(!matched)throw Error('未找到与 STL 对齐的点云颜色，请改用素色导入');
 }
 const origin=[(lo[0]+hi[0])/2,lo[1],(lo[2]+hi[2])/2];
 const v=Float32Array.from(vertices,(x,i)=>x-origin[i%3]);
 return {meta:{name:String(d.name||'新展品').slice(0,32),source_scan:String(d.run).slice(0,120),source_task:String(d.task).slice(0,120),mode:d.mode,faces:count,vertices:v.length/3,bounds_mm:bounds,palette,regions,transform:{origin},matched,measured_area_fraction:totalArea?colouredArea/totalArea:0},buffers:[v.buffer,faces.buffer,labels.buffer,adj.buffer]};
}
if(typeof self!=='undefined'&&typeof Window==='undefined')self.onmessage=(event)=>{try{const result=prepareScan(event.data);self.postMessage(result,{transfer:result.buffers});}catch(e:any){self.postMessage({error:/[\u4e00-\u9fff]/.test(e.message||'')?e.message:'STL 文件无法解析，请重新生成模型'});}};
