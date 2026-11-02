// Shared deterministic helpers; never evaluate user text as JavaScript.
export function calculate(expression){
 if(typeof expression!=='string'||expression.length>160)throw Error('请使用不超过160字符的算式');
 const source=expression.replace(/[×xX]/g,'*').replace(/÷/g,'/').replace(/（/g,'(').replace(/）/g,')').replace(/\s/g,'');
 if(!source||!/^[\d.+\-*/()% ^]+$/.test(source))throw Error('支持数字、括号、加减乘除、百分比和乘方');
 const tokens=source.match(/(?:\d+(?:\.\d*)?|\.\d+)|[()+\-*/%^]/g)||[];
 if(tokens.join('')!==source)throw Error('算式格式不正确');
 let i=0,depth=0;
 const finite=n=>{if(!Number.isFinite(n)||Math.abs(n)>1e15)throw Error('结果超出基础计算范围');return n;};
 function atom(){
  if(++depth>24)throw Error('括号嵌套过多');
  let n;
  if(tokens[i]==='('){i++;n=sum();if(tokens[i++]!==')')throw Error('括号不匹配');}
  else{const token=tokens[i++];if(!token||!/^\d*\.?\d+$|^\d+\.$/.test(token))throw Error('缺少数字');n=finite(Number(token));}
  while(tokens[i]==='%'){i++;n/=100;}depth--;return n;
 }
 function power(){let n=atom();if(tokens[i]==='^'){i++;const exponent=unary();if(Math.abs(exponent)>100)throw Error('指数超出范围');n=finite(n**exponent);}return n;}
 function unary(){if(tokens[i]==='+'){i++;return unary();}if(tokens[i]==='-'){i++;return -unary();}return power();}
 function product(){let n=unary();while(['*','/'].includes(tokens[i])){const op=tokens[i++],v=unary();if(op==='/'&&v===0)throw Error('不能除以零');n=finite(op==='*'?n*v:n/v);}return n;}
 function sum(){let n=product();while(['+','-'].includes(tokens[i])){const op=tokens[i++],v=product();n=finite(op==='+'?n+v:n-v);}return n;}
 const value=sum();if(i!==tokens.length)throw Error('算式格式不正确');
 return {expression,result:Number(value.toPrecision(12)),approximate:true};
}
export function validDate(value){return typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;}
export function localDate(now=new Date(),timezone='Asia/Shanghai'){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
 const part=k=>parts.find(p=>p.type===k).value;return `${part('year')}-${part('month')}-${part('day')}`;
}
export function dateDifference(start,end=localDate()){
 if(!validDate(start)||!validDate(end))throw Error('请提供有效的年月日');
 const days=Math.round((Date.parse(end)-Date.parse(start))/86400000);
 if(days<0)throw Error('相遇日期还没有到');
 const a=start.split('-').map(Number),b=end.split('-').map(Number);
 let years=b[0]-a[0];if(b[1]<a[1]||(b[1]===a[1]&&b[2]<a[2]))years--;
 return {start,end,days,completedYears:years,birthday:start.slice(5),meaning:'从相遇日起的陪伴时间，不是制造年龄'};
}
export function offlineCalculation(question){
 const expression=question.trim().replace(/^(?:请)?(?:帮我)?(?:算一下|计算一下|计算|算算|算)[:：\s]*/,'').replace(/(?:等于多少|是多少|多少|等于)?[=？?。\s]*$/,'').trim();
 if(!/[+\-*/×÷%^]/.test(expression)||! /^[\d.\s+\-*/×÷%^()（）]+$/.test(expression))return null;
 try{const r=calculate(expression);return `${r.expression} = ${r.result}`;}catch(e){return e.message;}
}
