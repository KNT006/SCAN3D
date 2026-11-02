import {offlineCalculation,dateDifference,localDate,validDate} from '../../shared/exhibit-tools.mjs';
export interface ExhibitAsset {
 id:string;name:string;category:string;subtitle:string;regions:string[];palette:string[];
 faces:number;vertices:number;bounds_mm:number[];geometry_key:string;source_scan:string;
 source_stl_sha256:string;source_stl:string;features:string[];processing:string;
 segmentation_note:string;transform:any;asset_base:string;thumbnail:string;
 paint_key?:string;labels_file?:string;segmentation_mode?:'rgb'|'cloud'|'legacy';
 previous_color_segmentation?:ExhibitAsset['color_segmentation'];
 color_segmentation?:{version:string;regions:string[];palette:string[];labels_file:string;note:string;report_url:string;thumbnail?:string;region_count:number;measured_area_fraction:number;unknown_faces:number};
}
export type ExhibitAction='none'|'nod'|'turn'|'highlight'|'reset';
export interface Answer {text:string;source:string;action:ExhibitAction;region?:number}
export interface Message {role:'user'|'exhibit';text:string;source?:string;time:number}
export interface ExhibitRecord {name:string;category:string;features:string[];story:string;acquiredDate:string;acquiredPlace:string;tone:'warm'|'concise';updated:number;messages:Message[];versions:{story:string;time:number}[];yaw:number}
const KEY='scan3d-museum-v1:';
export const clean=(v:unknown,n:number)=>typeof v==='string'?v.trim().slice(0,n):'';
export function defaults(a:ExhibitAsset):ExhibitRecord{return {name:a.name,category:a.category,features:[...a.features],story:'',acquiredDate:'',acquiredPlace:'',tone:'warm',updated:0,messages:[],versions:[],yaw:0};}
export function validateRecord(a:ExhibitAsset,d:any):ExhibitRecord {
 if(!d||typeof d!=='object')throw Error('展品档案无效');
 const r=defaults(a);r.name=clean(d.name,32)||a.name;r.category=clean(d.category,64)||a.category;
 r.features=Array.isArray(d.features)?d.features.filter((s:any)=>typeof s==='string').slice(0,8).map((s:string)=>clean(s,100)):a.features;
 r.acquiredDate=validDate(d.acquiredDate)?d.acquiredDate:'';r.acquiredPlace=clean(d.acquiredPlace,100);
 r.story=clean(d.story,4000);r.tone=d.tone==='concise'?'concise':'warm';r.updated=Number.isFinite(d.updated)?d.updated:0;
 r.yaw=Number.isFinite(d.yaw)?Math.max(-180,Math.min(180,d.yaw)):0;
 r.messages=Array.isArray(d.messages)?d.messages.filter((m:any)=>m&&['user','exhibit'].includes(m.role)&&typeof m.text==='string').slice(-30).map((m:any)=>({role:m.role,text:clean(m.text,1600),source:clean(m.source,100),time:Number.isFinite(m.time)?m.time:0})):[];
 r.versions=Array.isArray(d.versions)?d.versions.filter((s:any)=>s&&typeof s.story==='string').slice(-8).map((s:any)=>({story:clean(s.story,4000),time:Number.isFinite(s.time)?s.time:0})):[];return r;
}
export function loadRecord(a:ExhibitAsset):ExhibitRecord {const raw=localStorage.getItem(KEY+a.id);return raw?validateRecord(a,JSON.parse(raw)):defaults(a);}
export function saveRecord(a:ExhibitAsset,r:ExhibitRecord){localStorage.setItem(KEY+a.id,JSON.stringify(validateRecord(a,r)));}
export function introduction(a:ExhibitAsset,r:ExhibitRecord):Answer {
 const feature=r.features.length?'你可以看看我'+r.features.slice(0,2).join('、')+'的样子。':'';
 if(r.story)return {text:`我是${r.name}，一件${r.category}。${feature}\n\n我的主人为我留下了这段记录：\n“${r.story}”\n\n${r.tone==='warm'?'谢谢你停下来听我的故事，也可以转一转，看看我的另一面。':'也可以继续问我，或转一转看看我的另一面。'}`,source:'主人档案 + 展品资料',action:'nod'};
 return {text:`你好，我是${r.name}，一件${r.category}。${feature}\n\n我通过真实物品的三维扫描来到这里。${r.tone==='warm'?'你可以绕着我看看，也可以为我换一种颜色。':'可以旋转查看和自选上色。'}${r.acquiredPlace?'我们在'+r.acquiredPlace+'相遇。':''}${r.acquiredDate?'我把'+r.acquiredDate+'当作我们的纪念日。':''}`,source:'展品类别与外形记录 · 无个人经历',action:'nod'};
}
export function answerQuestion(a:ExhibitAsset,r:ExhibitRecord,question:string):Answer {
 const q=clean(question,500); const no:ExhibitAction='none';
 const calculated=offlineCalculation(q);if(calculated)return {text:calculated,source:'本机计算',action:no};
 if(/天气|气温|下雨|下雪|降水/.test(q))return {text:'天气需要联网查询。连接恢复后，告诉我城市、日期和时刻就可以。',source:'离线档案',action:no};
 if(/几岁|年龄|生日|纪念日|陪.*多久|相遇.*多久/.test(q)){
  if(r.acquiredDate){try{const d=dateDifference(r.acquiredDate,localDate());return {text:`把相遇那天当作生日，我已经陪你 ${d.days} 天，满 ${d.completedYears} 周年了。我们的纪念日是 ${d.birthday.replace('-','月')}日。`,source:'相遇档案 · 本机日期计算',action:'nod'};}catch{}}
  return {text:'把我们相遇的日期写进档案，我就可以告诉你陪伴了多久。',source:'相遇档案',action:no};
 }
 if(/哪里.*相遇|在哪.*买|哪里.*买|相遇.*哪里/.test(q)&&r.acquiredPlace)return {text:`我们是在${r.acquiredPlace}相遇的。${r.acquiredDate?'我记得那一天：'+r.acquiredDate+'。':''}`,source:'相遇档案',action:'nod'};
 if(/原始.*颜色|真实.*颜色|测.*颜色|材质|材料/.test(q))return {text:'我现在穿的是可以自由修改的展示配色，不是实物测色结果。材质可以在档案中记录。',source:'展示边界',action:no};
 if(/获奖|第几|哪年|几岁|价格|价值|谁送|送给|购买|哪买|比赛/.test(q))return {text:r.story?`我只保存了主人这段原话：“${r.story}”。你也可以把更多回忆记入我的档案。`:'这件事我还不知道，你可以把它记进我的故事。',source:r.story?'主人原文':'尚无记录',action:no};
 if(/故事|经历|来历|回忆|记忆/.test(q))return r.story?{text:`这是主人留给我的故事：\n“${r.story}”\n\n谢谢你把这段回忆留给我。`,source:'主人原文',action:'nod'}:{text:'我们的故事可以从相遇开始。你还记得在哪里把我带回家吗？',source:'尚无个人经历',action:'nod'};
 if(/多大|尺寸|高度|多高|大小/.test(q))return {text:`我这份展示网格的包围盒约为 ${a.bounds_mm.map(n=>n.toFixed(1)).join(' × ')} mm（宽 × 高 × 深）。它受展示朝向和重建影响，不是经量具验证的实物精度。`,source:'模型几何元数据',action:no};
 if(/扫描|模型|怎么.*来|制作|重建|STL/.test(q))return {text:`我的几何来自扫描 ${a.source_scan}。${a.processing} 当前展示 ${a.faces.toLocaleString()} 个三角面。修改配色不会改变原始扫描文件。`,source:'模型来源记录',action:'turn'};
 if(/颜色|上色|换色|衣服/.test(q))return {text:'在「上色」里点选部位，再选喜欢的颜色。也可以使用自由画笔、橡皮擦和取色笔。我的原始外形会保留，自选颜色可以随 GLB 和展品包保存。',source:'展示功能',action:no};
 if(/转|背面|另一面/.test(q))return {text:'我慢慢转一圈。也可以拖动模型，停在你想看的角度。',source:'展品动作',action:'turn'};
 if(/你好|打招呼|点头|开心|活起来/.test(q))return {text:`你好，我是${r.name}。谢谢你来看我。`,source:'礼貌回应 · 展示动作',action:'nod'};
 if(/特点|哪里|头|嘴|身体|五官|眼|尾巴/.test(q)) {
 if((a.segmentation_mode==='rgb'||a.segmentation_mode==='cloud'))return {text:`我的外形记录是：${r.features.join('、')||'尚未填写'}。当前根据照片与点云颜色辅助分区，同色部分可能跨越头部和身体；色区不等于五官识别。可在「自由上色」中点选并查看高亮范围。`,source:'外形记录 + RGB 色区说明',action:no};
 const region=a.regions[0]==='整体'?0:/嘴/.test(q)&&a.id==='duck'?2:/尾/.test(q)&&a.id==='duck'?6:1;
 return {text:`我的外形记录是：${r.features.join('、')||'尚未填写'}。我标出了${a.regions[region]}附近；这只是可修改的几何候选分区，不代表自动语义识别已经准确完成。`,source:'外形记录 + 候选分区',action:'highlight',region};
 }
 if(/是谁|介绍|叫什么|名字|物品|类别/.test(q))return introduction(a,r);
 return {text:'现在是离线模式，我可以讲档案里的故事，也能做简单算术。联网后，我们还可以聊日常、查天气。',source:'离线档案问答',action:no};
}
