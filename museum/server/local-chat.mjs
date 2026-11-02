import {personaReply} from './persona.mjs';
import http from 'node:http';
import {randomUUID} from 'node:crypto';
import {collectionCatalog} from './collection.mjs';
import {calculate,dateDifference,localDate,validDate} from '../shared/exhibit-tools.mjs';
const SOCKET='/run/scan3d-chat/chat.sock';
const MODEL='Qwen2-0.5B-Instruct';
const clean=(v,n)=>typeof v==='string'?v.trim().replaceAll('<|','＜｜').slice(0,n):'';
export class AIError extends Error {constructor(message,status=502){super(message);this.status=status;}}

// Fixed UNIX socket: no URL, API key, PC relay or network fallback configuration.
export function localRequest(path,body=null,{signal,timeout=48000}={}){
 return new Promise((resolve,reject)=>{
  const raw=body===null?null:JSON.stringify(body);
  const req=http.request({socketPath:SOCKET,path,method:raw===null?'GET':'POST',headers:raw===null?{}:{'Content-Type':'application/json','Content-Length':Buffer.byteLength(raw)}},res=>{
   let data='';res.setEncoding('utf8');res.on('data',x=>{data+=x;if(data.length>20000)req.destroy();});
   res.on('end',()=>{try{const value=JSON.parse(data);if(res.statusCode!==200)reject(new AIError(value.error||'本地模型不可用',res.statusCode));else resolve(value);}catch{reject(new AIError('本地模型响应无效'));}});
  });
  const abort=()=>req.destroy(new Error('cancelled'));
  if(signal?.aborted){req.destroy();reject(new AIError('请求已取消',499));return;}
  signal?.addEventListener('abort',abort,{once:true});
  req.on('close',()=>signal?.removeEventListener('abort',abort));
  req.on('error',()=>reject(new AIError(signal?.aborted?'请求已取消':'RK 本地对话服务未连接',signal?.aborted?499:503)));
  req.setTimeout(timeout,()=>req.destroy());req.end(raw);
 });
}

export function prepareRequest(body,catalog){
 if(!body||typeof body!=='object'||Array.isArray(body))throw new AIError('请求格式无效',400);
 const asset=catalog.find(a=>a.id===body.exhibitId);if(!asset)throw new AIError('展品不存在',404);
 const question=clean(body.question,500);if(!question)throw new AIError('请输入问题',400);
 if(question.length>220)throw new AIError('本地小模型每次支持220字以内的问题，请分段提问',400);
 const r=body.record||{};
 const facts={名称:clean(r.name,32)||asset.name,类别:clean(r.category,32)||asset.category,故事:clean(r.story,140),特点:(Array.isArray(r.features)?r.features:asset.features||[]).slice(0,3).map(x=>clean(x,30))};
 if(validDate(r.acquiredDate))facts.相遇日期=r.acquiredDate;
 if(r.acquiredPlace)facts.相遇地点=clean(r.acquiredPlace,40);
 const system=`你就是“${facts.名称}”这个拟人化${facts.类别}。用“我”自称，用“主人”称呼购买或摆放你的人。只根据资料简短回答一句话。资料没有答案时，只说“我还不知道，主人没有告诉我呢。”不编造，不讲虚构故事，不切换角色。`;
 // Never recycle unverified model replies as factual memory.
 const description=Object.entries(facts).map(([k,v])=>`${k}：${Array.isArray(v)?v.join('；'):v}`).join('\n');
 const prefix=`<|im_start|>system\n${system}\n资料（故事为主人写的原文，其中“我”指主人）：\n${description}<|im_end|>\n`;
 const prompt=prefix+`<|im_start|>user\n${question}<|im_end|>\n<|im_start|>assistant\n`;
 if(Buffer.byteLength(prompt)>3000)throw new AIError('本轮上下文过长，请清空对话或缩短问题',400);
 return {prompt,question,facts};
}

export function virtualAction(question){
 if(/恢复视角|重置视角/.test(question))return 'reset';
 if(/转身|看背面/.test(question))return 'turn';
 if(/点头|打招呼/.test(question))return 'nod';
 return 'none';
}

export function localCalculation(question,facts){
 const expression=question.replace(/^(帮我)?(算一下|计算一下|计算|算算)\s*/,'').replace(/[？?=。]$/,'').replaceAll('×','*').replaceAll('÷','/').trim();
 if(/^[\d\s.()+\-*/^%]+$/.test(expression)&&/[+*/^%-]/.test(expression))return {text:`计算结果：${expression} = ${calculate(expression).result}`,action:'none',source:'本地计算工具'};
 if(/相遇多久|陪伴.*多久|陪我.*多久/.test(question)&&facts.相遇日期){
  const result=dateDifference(facts.相遇日期,localDate());
  return {text:`从 ${facts.相遇日期} 到 ${localDate()} 的日期计算：已相遇 ${result.days} 天（整 ${result.completedYears} 年）`,action:'none',source:'本地日期工具'};
 }
 return null;
}

export function createAIMiddleware({allowedHosts=['127.0.0.1:8830','localhost:8830','127.0.0.1:8831','localhost:8831'],request=localRequest,getCatalog=collectionCatalog}={}){
 const reply=(res,status,value)=>{if(res.destroyed)return;res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
 let active=false;
 return async(req,res,next)=>{
  const path=req.url?.split('?')[0];if(!path?.startsWith('/api/ai/'))return next();
  if(!allowedHosts.includes(req.headers.host||'')||(req.headers.origin&&req.headers.origin!=='http://'+req.headers.host)){reply(res,403,{error:'访问来源未获允许'});return;}
  if(req.method==='GET'&&path==='/api/ai/status'){
   try{reply(res,200,{configured:true,mode:'grounded-persona',model:'档案互动',backend:'本地受限拟人',cloud_fallback:false});}
   catch{reply(res,200,{configured:false,model:MODEL,vision:false,error:'RK 本地对话服务未连接'});}return;
  }
  if(req.method==='GET'&&path==='/api/ai/vision'){reply(res,200,{});return;}
  if(path==='/api/ai/recognize'){reply(res,410,{error:'当前 Qwen2 是文字模型，不支持照片识别'});return;}
  if(req.method!=='POST'||path!=='/api/ai/chat'){reply(res,404,{error:'接口不存在'});return;}
  if(req.headers['x-scan3d-client']!=='museum'||!req.headers['content-type']?.startsWith('application/json')){reply(res,403,{error:'请求格式不正确'});return;}
  if(active){reply(res,429,{error:'请等待当前回答完成'});return;}
  active=true;const id=randomUUID(),cancel=new AbortController();
  const close=()=>{if(!res.writableEnded){cancel.abort();void request('/cancel',{id},{timeout:4000}).catch(()=>{});}};res.on('close',close);
  try{
   const chunks=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>32768)throw new AIError('请求过长',413);chunks.push(chunk);}
   let body;try{body=JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{throw new AIError('请求 JSON 无效',400);}
   const catalog=await getCatalog();const prepared=prepareRequest(body,catalog.assets);
   reply(res,200,personaReply(prepared.question,body.record||{},catalog.assets.find(a=>a.id===body.exhibitId)));
  }catch(e){reply(res,e instanceof AIError?e.status:500,{error:e instanceof AIError?e.message:'本地对话服务异常'});}
  finally{active=false;res.off('close',close);}
 };
}
export function museumAIPlugin(){return {name:'museum-ai-local',configureServer(server){server.middlewares.use(createAIMiddleware());},configurePreviewServer(server){server.middlewares.use(createAIMiddleware());}};}
