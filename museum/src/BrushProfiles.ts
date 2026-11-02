export type BrushStyle='soft'|'pen'|'pencil'|'marker'|'airbrush';
export type BrushOptions={style?:BrushStyle;opacity?:number;pressure?:number};
export const BRUSHES=[
 {id:'pen' as const,name:'钢笔',radius:1.2,tip:'边缘清晰，适合描线'},
 {id:'pencil' as const,name:'铅笔',radius:1.8,tip:'颗粒浅色，重复落笔可加深'},
 {id:'marker' as const,name:'马克笔',radius:4,tip:'宽幅半透明，适合铺色'},
 {id:'airbrush' as const,name:'喷笔',radius:5,tip:'柔和渐变，适合晕染'},
];
const clamp=(x:number)=>Math.min(1,Math.max(0,x));
function falloff(t:number,hard:number){const q=clamp((t-hard)/(1-hard));return 1-q*q*(3-2*q);}
/** Stable surface-space grain. No random flicker or camera-dependent pattern. */
export function brushWeight(t:number,x:number,y:number,z:number,options:BrushOptions={}){
 if(t<0||t>=1||![t,x,y,z].every(Number.isFinite))return 0;
 const opacity=Number.isFinite(options.opacity)?clamp(options.opacity!):1;
 const pressure=Number.isFinite(options.pressure)?clamp(options.pressure!):1;
 let weight:number;
 switch(options.style){
  case 'pen':weight=falloff(t,.985);break;
  case 'pencil':{
   const n=Math.sin(Math.floor(x*5)*127.1+Math.floor(y*5)*311.7+Math.floor(z*5)*74.7)*43758.5453;
   const grain=n-Math.floor(n);weight=falloff(t,.2)*(.12+.6*grain*grain);break;
  }
  case 'marker':weight=falloff(t,.76)*.48;break;
  case 'airbrush':weight=(Math.exp(-4*t*t)-Math.exp(-4))/(1-Math.exp(-4))*.25;break;
  default:weight=falloff(t,.5);
 }
 // A pen lays solid ink even with light stylus pressure; pressure still changes density.
 const inkPressure=options.style==='pen'&&pressure>0?.8+.2*Math.sqrt(pressure):pressure;
 return clamp(weight*opacity*inkPressure);
}
