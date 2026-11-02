import {requestAI} from './museum-ai.mjs';
try{
 const r=await requestAI([{role:'system',content:'只输出 JSON：{"reply":"你好，连接成功。","action":"none"}。'},{role:'user',content:'你好。'}]);
 console.log(JSON.stringify({ok:true,model:r.model,elapsedMs:r.elapsedMs,reply:r.text}));
}catch(e){console.log(JSON.stringify({ok:false,error:e.message}));process.exitCode=1;}
