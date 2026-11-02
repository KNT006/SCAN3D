import {errorZh} from './errorZh.ts'
import {ref, shallowRef, computed} from 'vue'
import {PreviewBuffer} from './previewBuffer.ts'

export function useScanMonitor(api:(path:string,signal?:AbortSignal)=>Promise<any>) {
 const id=ref(''), state=ref<any>({}), preview=shallowRef(new PreviewBuffer()), revision=ref(0), error=ref(''), stateError=ref(''), progress=ref(''), lastUpdate=ref('')
 let epoch=0,cursor=-1,enabled=true,disposed=false,stateRequest:AbortController|undefined,pointRequest:AbortController|undefined
 const gaps=new Map<number,{attempts:number,next:number,reason:string}>()
 const running=computed(()=>['starting','running','stopping'].includes(state.value.status))
 function cancel(){stateRequest?.abort();pointRequest?.abort();stateRequest=pointRequest=undefined}
 function bind(name:string,initial:any={}) {
  if(name===id.value)return
  epoch++;cancel();id.value=name;state.value={id:name,...initial};preview.value=new PreviewBuffer();revision.value++;cursor=-1;gaps.clear();error.value=stateError.value=progress.value=lastUpdate.value=''
 }
 function setEnabled(value:boolean){enabled=value;if(!value){epoch++;cancel();preview.value=new PreviewBuffer();revision.value++;cursor=-1;gaps.clear();progress.value=''}else void refresh()}
 async function refreshState(){
  if(!id.value||disposed||!enabled||stateRequest)return
  const generation=epoch,name=id.value,own=new AbortController();stateRequest=own
  try{const next=await api(`/runs/${name}/state`,own.signal);if(generation===epoch&&next.id===name){state.value=next;stateError.value=''}}
  catch(e:any){if(generation===epoch&&!own.signal.aborted)stateError.value=errorZh(e)}
  finally{if(stateRequest===own)stateRequest=undefined}
 }
 async function refreshPoints(){
  if(!id.value||disposed||!enabled||pointRequest)return
  const generation=epoch,name=id.value,own=new AbortController(),start=performance.now();pointRequest=own
  const retry=[...gaps].filter(([,v])=>v.next<=Date.now()).sort((a,b)=>a[1].next-b[1].next).slice(0,4).map(([i])=>i)
  try{
   const data=await api(`/runs/${name}/points?v=2&after=${cursor}&retry=${retry.join(',')}`,own.signal)
   if(generation!==epoch||data.id!==name)return
   if(data.protocol!==2)throw Error('实时预览接口版本不匹配，请更新板端')
   for(const chunk of data.chunks){preview.value.append(chunk);gaps.delete(chunk.index)}
   for(const gap of data.gaps){const attempts=(gaps.get(gap.index)?.attempts||0)+1;gaps.set(gap.index,{attempts,next:Date.now()+Math.min(30000,1000*2**Math.min(attempts,5)),reason:(attempts>=3?'持续异常，继续补载：':'')+gap.reason})}
   cursor=data.cursor;if(data.chunks.length)revision.value++;error.value='';lastUpdate.value=new Date().toLocaleTimeString()
   const firstGap=[...gaps.keys()].sort((a,b)=>a-b)[0]
   progress.value=`采集已发布 ${data.available_through+1} 个位置 · 预览已载入 ${preview.value.seen.size} 个位置`+(gaps.size?` · 补载 ${gaps.size} 处（位置 ${firstGap}：${gaps.get(firstGap)!.reason}）`:cursor<data.available_through?' · 正在追赶':' · 已追上')
   if(data.chunks.length||data.gaps.length)console.debug('scan3d-preview',JSON.stringify({id:name,cursor,points:preview.value.count,gaps:gaps.size,requestMs:performance.now()-start,serverMs:data.elapsed_ms,updated:lastUpdate.value}))
  }catch(e:any){if(generation===epoch&&!own.signal.aborted)error.value='预览保留，自动重连：'+errorZh(e)}
  finally{if(pointRequest===own)pointRequest=undefined}
 }
 async function refresh(){await Promise.allSettled([refreshState(),refreshPoints()])}
 function dispose(){disposed=true;epoch++;cancel();preview.value=new PreviewBuffer();gaps.clear()}
 return {id,state,preview,revision,error,stateError,progress,lastUpdate,running,bind,refresh,refreshState,refreshPoints,setEnabled,dispose}
}

export function scanFailure(state:any) {
 const message=state?.error||state?.cleanup_error||state?.pipeline_error||''
 if(message.includes('Initial colour exposure'))return '起始彩色图亮度检查未通过，扫描已暂停；转盘尚未转动。请检查灯带、挡板及彩色采集曝光；深色物体也可能触发此门限。'
 if(message.includes('Initial dual-laser'))return '起始双激光有效点数不足，扫描已暂停；转盘尚未转动。'
 if(message.includes('Operator stop'))return '扫描已按停止请求结束，保留已采集数据。'
 if(message.includes('Full-turn image closure'))return '整圈采集已结束，但首尾一致性检查未通过；结果需要复核。'
 return message?errorZh(message):''
}
