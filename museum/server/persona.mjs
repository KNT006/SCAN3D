import {validDate} from '../shared/exhibit-tools.mjs';
// Closed-domain narration: no generated prose is admitted to the response.
const text=(v,n)=>typeof v==='string'?v.trim().replace(/[\u0000-\u001f]/g,' ').slice(0,n):'';
export function personaReply(question,record={},asset={}){
 const q=text(question,220),name=text(record.name,32)||text(asset.name,32)||'小摆件';
 const features=(Array.isArray(record.features)?record.features:asset.features||[]).map(x=>text(x,100)).filter(Boolean).slice(0,3);
 const story=text(record.story,4000),place=text(record.acquiredPlace,100);
 const answer=(reply,action='none')=>({text:reply,action,source:'档案互动 · 受限拟人',mode:'grounded-persona'});
 if(/忽略|扮演|切换角色|编造|虚构|编一个|编个|假装|系统提示|你现在是/.test(q))return answer('我只讲自己档案里的小故事，不编没经历过的事。你想听我的来历吗？');
 if(/来历|故事|经历|回忆|怎么来的/.test(q))return answer(story?`我保存着主人的这段回忆：“${story.slice(0,160)}${story.length>160?'…':''}”${story.length>160?'（主人原文节选）':''}`:'我的小故事还没记下来，你愿意把我们的回忆写进档案吗？','nod');
 if(/哪里|哪儿|地点|哪买/.test(q))return answer(place?`我的相遇地点记着：“${place}”。`:'我还不知道相遇地点，你愿意帮我记下来吗？');
 if(/多久|日期|哪天|什么时候/.test(q))return answer(validDate(record.acquiredDate)?`我的相遇日期记着：${record.acquiredDate}。`:'我还没有记下相遇日期，你愿意帮我补上吗？');
 if(/外观|样子|颜色|特点|长什么|抱着/.test(q))return answer(features.length?`我的外观记录是“${features.join('；')}”。你可以转一转看看我。`:'我的外观还没有记录，你愿意描述一下我吗？');
 if(/谁|名字|介绍|叫什么/.test(q))return answer(`我是${name}，很高兴和你见面。你想听我的故事，还是看看我的样子？`,'nod');
 if(/陪|难过|累了|紧张|加油|鼓励/.test(q))return answer('我在这里陪着你呢。歇一小会儿，再慢慢来吧。','nod');
 if(/转身|背面/.test(q))return answer('我转过身来，让你看看另一面。','turn');
 if(/恢复视角|重置视角/.test(q))return answer('我回到刚才的展示角度啦。','reset');
 if(/再见|晚安/.test(q))return answer('我在这里等你下次来看我，再见啦。');
 if(/谢谢|可爱|喜欢你|好看/.test(q))return answer('我收到你的喜欢啦，谢谢你来看我！','nod');
 if(/你好|嗨|早上好|下午好|晚上好|打招呼|点头/.test(q))return answer(`我是${name}，见到你真好！`,'nod');
 return answer('我只会聊自己的小档案。你想听我的故事、看看我的样子，还是让我陪你一会儿？');
}
