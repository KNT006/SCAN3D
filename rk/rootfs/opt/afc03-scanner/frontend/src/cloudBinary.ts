export type ResultCloud={xyz:Float32Array,rgb:Uint8Array,count:number,total:number}
export function parseResultCloud(buffer:ArrayBuffer):ResultCloud{
  if(buffer.byteLength<16)throw Error('点云数据不完整')
  const h=new DataView(buffer),count=h.getUint32(8,true),total=h.getUint32(12,true)
  if(h.getUint32(0,true)!==0x31443353||h.getUint32(4,true)!==1||count!==total||buffer.byteLength!==16+count*15)throw Error('点云文件格式或长度异常')
  return {xyz:new Float32Array(buffer,16,count*3),rgb:new Uint8Array(buffer,16+count*12,count*3),count,total}
}

// Reuse downloaded coordinates instead of decompressing the source archive twice.
export function summarizeResultCloud(cloud:ResultCloud){
  const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity]
  for(let i=0;i<cloud.xyz.length;i+=3)for(let axis=0;axis<3;axis++){const v=cloud.xyz[i+axis];if(v<min[axis])min[axis]=v;if(v>max[axis])max[axis]=v}
  return {count:cloud.total,bounds_mm:cloud.count?min.map((v,i)=>Math.round((max[i]-v)*1000)/1000):null,model_summary_loaded:true}
}
