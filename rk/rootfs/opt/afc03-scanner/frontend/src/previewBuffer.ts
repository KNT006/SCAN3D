// Fixed angular quota assigned by the server, append once per position.
// Arrays never enter Vue deep reactivity. No repeated thinning of early angles.
export class PreviewBuffer {
 readonly xyz = new Float32Array(160000*3)
 readonly rgb = new Uint8Array(160000*3)
 readonly seen = new Set<number>()
 count=0
 append(chunk:{index:number,xyz:number[][],rgb:number[][]}) {
  if(this.seen.has(chunk.index))return
  if(!Number.isInteger(chunk.index)||chunk.index<0||chunk.index>3200||chunk.xyz.length!==chunk.rgb.length)throw Error('预览位置或颜色数据无效')
  if(this.count+chunk.xyz.length>160000)throw Error('预览预算超限，未丢弃已有点')
  for(let i=0;i<chunk.xyz.length;i++){
   if(chunk.xyz[i].length!==3||chunk.rgb[i].length!==3||!chunk.xyz[i].every(Number.isFinite)||!chunk.rgb[i].every(Number.isFinite))throw Error('预览坐标无效')
  }
  for(let i=0;i<chunk.xyz.length;i++){
   this.xyz.set(chunk.xyz[i],(this.count+i)*3);this.rgb.set(chunk.rgb[i],(this.count+i)*3)
  }
  this.count+=chunk.xyz.length;this.seen.add(chunk.index)
 }
}
