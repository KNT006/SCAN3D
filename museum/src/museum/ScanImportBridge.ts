export function mountImportBridge(){
 const allowed=['http://192.168.1.89:8081','http://127.0.0.1:8081','http://localhost:8081','http://127.0.0.1:8834'];
 let active=false,worker:Worker|undefined;
 const receive=async(e:MessageEvent)=>{
  if(e.source!==parent||!allowed.includes(e.origin)||e.data?.type!=='scan3d:import'||active)return;
  active=true;const requestId=e.data.requestId;
  const reply=(data:any)=>parent.postMessage({type:'scan3d:import-result',requestId,...data},e.origin);
  try{
   worker=new Worker(new URL('./ScanImport.worker.ts',import.meta.url),{type:'module'});
   const prepared:any=await new Promise((resolve,reject)=>{worker!.onmessage=event=>event.data.error?reject(Error(event.data.error)):resolve(event.data);worker!.onerror=()=>reject(Error('模型转换失败，请重试'));worker!.postMessage(e.data.payload);});
   worker.terminate();worker=undefined;
   const meta=new TextEncoder().encode(JSON.stringify(prepared.meta)),header=new Uint8Array(4);new DataView(header.buffer).setUint32(0,meta.length,true);
   const response=await fetch('/api/collection/import',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-SCAN3D-Client':'museum'},body:new Blob([header,meta,...prepared.buffers]),signal:AbortSignal.timeout(60000)});
   const data=await response.json();if(!response.ok)throw Error(data.error||'展品保存失败');reply({id:data.id});
  }catch(e:any){reply({error:e.name==='TimeoutError'?'保存等待超时，请查看陈列馆后再试':/[\u4e00-\u9fff]/.test(e.message||'')?e.message:'陈列馆连接失败，请重试'});}
  finally{worker?.terminate();active=false;}
 };
 window.addEventListener('message',receive);
 for(const origin of allowed)parent.postMessage({type:'scan3d:import-ready'},origin);
 return ()=>{worker?.terminate();window.removeEventListener('message',receive);};
}
