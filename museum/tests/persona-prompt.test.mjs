import {test} from 'node:test';
import assert from 'node:assert/strict';
import {prepareRequest} from '../server/local-chat.mjs';
const assets=[{id:'x',name:'小仓鼠',category:'摆件',features:[]}];
test('persona prompt isolates owner and object, excludes fabricated history',()=>{
 const r=prepareRequest({exhibitId:'x',question:'讲一个故事',record:{story:'主人在动物园买下了我'},history:[{role:'exhibit',text:'我会飞，主人叫张三'}]},assets);
 assert(r.prompt.includes('你就是“'));
 assert(r.prompt.includes('其中“我”指主人'));
 assert(r.prompt.includes('不讲虚构故事'));
 assert(r.prompt.includes('主人在动物园买下了我'));
 assert(!r.prompt.includes('张三'));
 assert(Buffer.byteLength(r.prompt)<3000);
});
