export type State='idle'|'swim'|'react'|'pet'|'celebrate'|'sleep';
export type Pt={x:number,z:number};
const priority:Record<State,number>={idle:0,swim:1,react:2,pet:3,celebrate:6,sleep:9};
export function bound(p:Pt,r=2.15):Pt {const k=Math.min(1,r/Math.max(.001,Math.hypot(p.x,p.z)));return{x:p.x*k,z:p.z*k};}
export class DuckStateMachine {
 state:State='idle';elapsed=0;clock=0;x=0;z=0;yaw=0;target:Pt={x:0,z:0};events:{type:string,x:number,z:number}[]=[];
 mood=75;energy=80;lastClick=-10;nextWander=8;lastWave=0;reason='点击水面，邀请它游过来';
 emit(type:string,p:Pt=this){this.events.push({type,...{x:p.x,z:p.z}});if(this.events.length>30)this.events.shift();}
 exit(){ /* Current actions have no retained scene objects. */ }
 enter(s:State){this.state=s;this.elapsed=0;if(s==='idle')this.nextWander=8+Math.random()*8;if(s==='react')this.emit('ripple');if(s==='pet'||s==='celebrate')this.emit('heart');}
 change(s:State,force=false){if(!force&&priority[s]<priority[this.state]){this.reason='先让它完成眼前的小事吧';return false;}this.exit();this.enter(s);return true;}
 request(action:string,p?:Pt){
  if(action==='wake'||action==='stop'){this.change('idle',true);this.reason='醒来啦，继续一起玩';return true;}
  if(action==='sleep'){this.change('sleep',true);this.reason='轻轻漂着，做个好梦';return true;}
  if(this.state==='sleep'){this.reason='它睡着了，先点唤醒';return false;}
  if(action==='react'){if(this.clock-this.lastClick<.8)return false;if(!this.change('react'))return false;this.lastClick=this.clock;this.mood=Math.min(100,this.mood+1);}
  else if(action==='pet'){if(this.state==='pet'||!this.change('pet'))return false;this.mood=Math.min(100,this.mood+4);}
  else if(action==='swim'){if(!p||!this.change('swim'))return false;this.target=bound(p);}
  else if(action==='celebrate'){if(this.state==='celebrate'||!this.change('celebrate'))return false;}
  else return false;
  this.reason={react:'嘎！很高兴见到你',pet:'这个轻轻的抚摸，我喜欢',swim:'向你指的方向游去',celebrate:'今天也是开心的一天'}[action]||'';return true;
 }
 travel(dt:number,t:Pt,stop=.05){const dx=t.x-this.x,dz=t.z-this.z,d=Math.hypot(dx,dz);if(d<.001)return true;const a=Math.atan2(dx,dz),da=Math.atan2(Math.sin(a-this.yaw),Math.cos(a-this.yaw));this.yaw+=da*(1-Math.exp(-4*dt));if(d<stop)return Math.abs(da)<.15;const speed=Math.min(.55,Math.max(.025,(d-stop)*1.2))*(Math.abs(da)>.6?0:Math.max(.05,Math.cos(da)));const step=Math.min(speed*dt,Math.max(0,d-stop*.75));const p=bound({x:this.x+dx/d*step,z:this.z+dz/d*step});this.x=p.x;this.z=p.z;return false;}
 update(raw:number){const dt=Math.min(.05,Math.max(0,raw));this.clock+=dt;this.elapsed+=dt;this.mood=Math.max(0,this.mood-dt*.008);this.energy=Math.max(0,Math.min(100,this.energy+dt*(this.state==='sleep'?1.1:-.015)));
  if(this.state==='idle'&&this.elapsed>this.nextWander)this.request('swim',bound({x:this.x+(Math.random()-.5)*2,z:this.z+(Math.random()-.5)*2}));
  if(this.state==='swim'&&this.travel(dt,this.target))this.change('idle',true);
  const duration:Partial<Record<State,number>>={react:1.2,pet:2.7,celebrate:2.4};if(duration[this.state]&&this.elapsed>duration[this.state]!){if(this.state==='celebrate')this.emit('splash');this.change('idle',true);}
  if(this.clock-this.lastWave>(this.state==='swim'?.55:2)){this.lastWave=this.clock;this.emit('ripple');}
 }
 pose(){const t=this.elapsed,c=this.clock;let y=Math.sin(c*1.7)*.022+Math.sin(c*.73)*.009,pitch=Math.sin(c*.9)*.016,roll=Math.sin(c*1.13)*.02;
  if(this.state==='sleep'){y*=.25;roll*=.25;pitch=.03;}if(this.state==='swim')pitch+=.035;
  if(this.state==='react')y-=Math.sin(Math.PI*Math.min(1,t/1.2))*.1;if(this.state==='pet')roll+=Math.sin(t*5)*.065*Math.sin(Math.PI*Math.min(1,t/2.7));if(this.state==='celebrate')y+=Math.sin(Math.PI*Math.min(1,t/2.4))*.48;
  return{y,pitch,roll,scale:1};}
}
