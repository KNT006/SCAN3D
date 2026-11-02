import type {ExhibitAsset,ExhibitRecord,Answer} from './MuseumData';
export interface AIStatus {configured:boolean;model?:string;error?:string}
export async function getAIStatus():Promise<AIStatus>{
 try{const r=await fetch('/api/ai/status',{signal:AbortSignal.timeout(5000)});if(!r.ok)throw Error();return await r.json();}
 catch{return {configured:false,error:'AI 服务未连接'};}
}
export async function askAI(a:ExhibitAsset,r:ExhibitRecord,question:string,signal:AbortSignal):Promise<Answer>{
 const response=await fetch('/api/ai/chat',{method:'POST',headers:{'Content-Type':'application/json','X-SCAN3D-Client':'museum'},signal,body:JSON.stringify({exhibitId:a.id,question,record:{name:r.name,category:r.category,features:r.features,story:r.story,acquiredDate:r.acquiredDate,acquiredPlace:r.acquiredPlace,tone:r.tone},history:r.messages.slice(-8)})});
 const data=await response.json();if(!response.ok)throw Error(typeof data.error==='string'?data.error:'AI 暂不可用');
 if(typeof data.text!=='string'||!data.text.trim()||data.text.length>1600||!['none','nod','turn','reset'].includes(data.action))throw Error('AI 回答格式无效');
 return {text:data.text,action:data.action,source:typeof data.source==='string'?data.source:'Qwen2 本地 NPU'};
}
