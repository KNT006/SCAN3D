const KEY='scan3d-duck-pond-v1';
export function loadPet(){let p:any={};try{p=JSON.parse(localStorage.getItem(KEY)||'{}');}catch{}const n=(v:any,d:number,a=0,b=100)=>Number.isFinite(v)?Math.min(b,Math.max(a,v)):d;return{name:typeof p.name==='string'?p.name.slice(0,16):'小团',mood:n(p.mood,75),energy:n(p.energy,80),waterline:n(p.waterline,6,2,10),yaw:n(p.yaw,0,-180,180)};}
export function savePet(p:object){try{localStorage.setItem(KEY,JSON.stringify(p));return true;}catch{return false;}}
