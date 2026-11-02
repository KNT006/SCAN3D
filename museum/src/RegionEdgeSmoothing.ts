import * as T from 'three';

/** Narrow, surface-local color feathering. Does not move geometry or change labels. */
export class RegionEdgeSmoothing {
  enabled={value:1};paintEnabled={value:1}; width={value:.16};
  neighbors:Int32Array; heights:Float32Array; boundary:Uint8Array;
  geometry:T.BufferGeometry;
  constructor(geometry:T.BufferGeometry,adj:Int32Array){
    this.geometry=geometry;
    const p=geometry.getAttribute('position'),n=p.count/3;
    this.neighbors=new Int32Array(n*3).fill(-1);this.heights=new Float32Array(n*3);this.boundary=new Uint8Array(n);
    const bary=new Float32Array(n*9),height=new Float32Array(n*9);
    const a=new T.Vector3(),b=new T.Vector3(),c=new T.Vector3();
    const equal=(i:number,j:number)=>Math.abs(p.getX(i)-p.getX(j))+Math.abs(p.getY(i)-p.getY(j))+Math.abs(p.getZ(i)-p.getZ(j))<1e-5;
    for(let f=0;f<n;f++){
      a.fromBufferAttribute(p,f*3);b.fromBufferAttribute(p,f*3+1);c.fromBufferAttribute(p,f*3+2);
      const area2=b.clone().sub(a).cross(c.clone().sub(a)).length();
      const lengths=[b.distanceTo(c),c.distanceTo(a),a.distanceTo(b)];
      for(let e=0;e<3;e++){
        this.heights[f*3+e]=area2/Math.max(lengths[e],1e-9);
        // Match the shared edge explicitly; do not depend on adjacency ordering.
        const u=f*3+(e+1)%3,v=f*3+(e+2)%3;
        for(let j=0;j<3;j++){
          const other=adj[f*3+j];if(other<0)continue;
          if([0,1,2].some(k=>equal(u,other*3+k))&&[0,1,2].some(k=>equal(v,other*3+k)))this.neighbors[f*3+e]=other;
        }
      }
      for(let j=0;j<3;j++){bary[f*9+j*3+j]=1;height.set(this.heights.subarray(f*3,f*3+3),f*9+j*3);}
    }
    geometry.setAttribute('regionBary',new T.BufferAttribute(bary,3));
    geometry.setAttribute('regionHeight',new T.BufferAttribute(height,3));
    for(let i=0;i<3;i++)geometry.setAttribute('regionNeighbor'+i,new T.BufferAttribute(new Float32Array(n*9),3));
  }
  update(labels:Uint8Array,paint?:Int32Array){
    const colors=this.geometry.getAttribute('color').array as Float32Array;
    this.boundary.fill(0);
    for(let e=0;e<3;e++){
      const attr=this.geometry.getAttribute('regionNeighbor'+e),arr=attr.array as Float32Array;
      for(let f=0;f<labels.length;f++){
        const other=this.neighbors[f*3+e];
        const active=other>=0&&(labels[f]!==7||(paint?.[f]??-1)>=0)&&(labels[other]!==7||(paint?.[other]??-1)>=0)&&[0,1,2].some(k=>Math.abs(colors[f*9+k]-colors[other*9+k])>1e-6);
        if(active)this.boundary[f]=1;
        const src=(active?other:f)*9;
        for(let j=0;j<3;j++)arr.set(colors.subarray(src,src+3),f*9+j*3);
      }
      attr.needsUpdate=true;
    }
  }
  install(material:T.MeshStandardMaterial){
    material.onBeforeCompile=shader=>{
      shader.uniforms.surfacePaintEnabled=this.paintEnabled;shader.uniforms.regionSmoothEnabled=this.enabled;shader.uniforms.regionSmoothWidth=this.width;
      const varying='varying vec4 vSurfacePaint; varying vec3 vRegionBary; varying vec3 vRegionHeight; varying vec3 vRegionN0; varying vec3 vRegionN1; varying vec3 vRegionN2;';
      shader.vertexShader='attribute vec4 surfacePaint; attribute vec3 regionBary; attribute vec3 regionHeight; attribute vec3 regionNeighbor0; attribute vec3 regionNeighbor1; attribute vec3 regionNeighbor2;'+varying+'\n'+shader.vertexShader;
      shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\nvSurfacePaint=surfacePaint; vRegionBary=regionBary; vRegionHeight=regionHeight; vRegionN0=regionNeighbor0; vRegionN1=regionNeighbor1; vRegionN2=regionNeighbor2;');
      shader.fragmentShader=varying+'\nuniform float surfacePaintEnabled; uniform float regionSmoothEnabled; uniform float regionSmoothWidth;\n'+shader.fragmentShader;
      shader.fragmentShader=shader.fragmentShader.replace('#include <color_fragment>',`
        #ifdef USE_COLOR
          float rw=min(regionSmoothWidth, .18*min(vRegionHeight.x,min(vRegionHeight.y,vRegionHeight.z)));
          vec3 rd=max(vec3(0.),vRegionBary)*vRegionHeight;
          vec3 wt=(vec3(1.)-smoothstep(vec3(0.),vec3(max(rw,.00001)),rd))*regionSmoothEnabled;
          vec3 edgeColor=(vColor.rgb+wt.x*vRegionN0+wt.y*vRegionN1+wt.z*vRegionN2)/(1.+wt.x+wt.y+wt.z);
          diffuseColor.rgb*=edgeColor*(1.-vSurfacePaint.a*surfacePaintEnabled)+vSurfacePaint.rgb*surfacePaintEnabled;
        #endif
      `);
    };
    material.customProgramCacheKey=()=> 'scan3d-region-edge-surface-v2';
    material.needsUpdate=true;
  }
  sampleColor(face:number,bary:number[]):number[]{
    const own=this.geometry.getAttribute('color'),base=face*3;
    const color=[own.getX(base),own.getY(base),own.getZ(base)];
    const h=Array.from(this.heights.subarray(face*3,face*3+3));
    const width=Math.max(.00001,Math.min(this.width.value,.18*Math.min(...h)));
    let total=1;
    for(let e=0;e<3;e++){
      const t=T.MathUtils.clamp(bary[e]*h[e]/width,0,1),w=this.enabled.value*(1-t*t*(3-2*t));
      const c=this.geometry.getAttribute('regionNeighbor'+e);
      color[0]+=w*c.getX(base);color[1]+=w*c.getY(base);color[2]+=w*c.getZ(base);total+=w;
    }
    const paint=this.geometry.getAttribute('surfacePaint'),layer=[0,0,0,0];
    if(paint&&this.paintEnabled.value)for(let j=0;j<3;j++)for(let k=0;k<4;k++)layer[k]+=paint.array[(base+j)*4+k]*bary[j];
    return color.map((c,k)=>c/total*(1-layer[3])+layer[k]);
  }
  /** Bake the same transition into export vertex colors; only split boundary faces. */
  bake():T.BufferGeometry{
    const p=this.geometry.getAttribute('position'),normal=this.geometry.getAttribute('normal');
    const positions:number[]=[],normals:number[]=[],colors:number[]=[];
    const emit=(f:number,b:number[])=>{
      for(let axis=0;axis<3;axis++){
        const get=(a:T.BufferAttribute|T.InterleavedBufferAttribute,j:number)=>axis===0?a.getX(j):axis===1?a.getY(j):a.getZ(j);
        positions.push(b.reduce((s,x,j)=>s+x*get(p,f*3+j),0));
        normals.push(b.reduce((s,x,j)=>s+x*get(normal,f*3+j),0));
      }
      colors.push(...this.sampleColor(f,b));
    };
    for(let f=0;f<this.boundary.length;f++){
      if(!this.enabled.value||!this.boundary[f]){emit(f,[1,0,0]);emit(f,[0,1,0]);emit(f,[0,0,1]);continue;}
      const h=Array.from(this.heights.subarray(f*3,f*3+3));
      const width=Math.max(.00001,Math.min(this.width.value,.18*Math.min(...h)));
      let polygons:number[][][]=[[[1,0,0],[0,1,0],[0,0,1]]];
      // Split at physical feather widths, not an arbitrary whole-face grid.
      // This avoids broadening color bleed when the source face is long/thin.
      for(let axis=0;axis<3;axis++)for(const fraction of [.5,1]){
        const threshold=fraction*width/Math.max(h[axis],1e-9),next:number[][][]=[];
        for(const polygon of polygons){
          const values=polygon.map(p=>p[axis]-threshold);
          if(values.every(x=>x>=-1e-8)||values.every(x=>x<=1e-8)){next.push(polygon);continue;}
          for(const sign of [-1,1]){
            const clipped:number[][]=[];
            for(let i=0;i<polygon.length;i++){
              const a=polygon[i],b=polygon[(i+1)%polygon.length];
              const da=(a[axis]-threshold)*sign,db=(b[axis]-threshold)*sign;
              if(da>=0)clipped.push(a);
              if((da>0&&db<0)||(da<0&&db>0)){
                const t=da/(da-db);clipped.push(a.map((v,k)=>v+t*(b[k]-v)));
              }
            }
            if(clipped.length>=3)next.push(clipped);
          }
        }
        polygons=next;
      }
      for(const polygon of polygons){
        const center=[0,1,2].map(k=>polygon.reduce((s,p)=>s+p[k],0)/polygon.length);
        for(let j=0;j<polygon.length;j++){emit(f,center);emit(f,polygon[j]);emit(f,polygon[(j+1)%polygon.length]);}
      }
    }
    const g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(positions,3));g.setAttribute('normal',new T.Float32BufferAttribute(normals,3));g.normalizeNormals();g.setAttribute('color',new T.Float32BufferAttribute(colors,3));return g;
  }
}
