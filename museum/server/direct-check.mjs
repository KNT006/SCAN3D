import {configuration} from '/userdata/scan3d-museum/server/museum-ai.mjs';
const c=configuration();
try{const r=await fetch(c.base+'/models',{headers:{Authorization:'Bearer '+c.key},redirect:'error',signal:AbortSignal.timeout(20000)});let models=[];if(r.ok){const d=await r.json();models=d.data?.map(x=>x.id)||[];}console.log(JSON.stringify({status:r.status,configuredModel:c.model,modelAvailable:models.includes(c.model)}));if(!r.ok||!models.includes(c.model))process.exitCode=1;}catch{console.log(JSON.stringify({error:'API reachability check failed'}));process.exitCode=1;}
