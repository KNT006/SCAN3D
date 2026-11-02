import {localDate,validDate} from '../shared/exhibit-tools.mjs';
const DAY=86400000;
const description=code=>({0:'晴',1:'大部晴朗',2:'局部多云',3:'阴',45:'雾',48:'雾凇',51:'小毛毛雨',53:'毛毛雨',55:'强毛毛雨',56:'冻毛毛雨',57:'强冻毛毛雨',61:'小雨',63:'中雨',65:'大雨',66:'冻雨',67:'强冻雨',71:'小雪',73:'中雪',75:'大雪',77:'雪粒',80:'小阵雨',81:'阵雨',82:'强阵雨',85:'小阵雪',86:'强阵雪',95:'雷暴',96:'雷暴伴冰雹',99:'强雷暴伴冰雹'}[code]||'天气状况未知');
export async function lookupWeather(args,{fetcher=fetch,signal,now=new Date()}={}){
 const location=typeof args?.location==='string'?args.location.trim():'';
 if(!location||location.length>80)return {error:'请补充要查询的城市或地区。'};
 const get=async url=>{
  const r=await fetcher(url,{redirect:'error',signal:signal?AbortSignal.any([signal,AbortSignal.timeout(12000)]):AbortSignal.timeout(12000)});
  if(!r.ok)throw Error('天气服务暂时未返回数据，请稍后再试。');return r.json();
 };
 try{
  const geoURL=new URL('https://geocoding-api.open-meteo.com/v1/search');
  geoURL.search=new URLSearchParams({name:location,count:'5',language:'zh',format:'json'}).toString();
  const geo=await get(geoURL);let candidates=(geo.results||[]).filter(p=>Number.isFinite(p.latitude)&&Number.isFinite(p.longitude)&&p.timezone);
  if(args.countryCode)candidates=candidates.filter(p=>p.country_code===String(args.countryCode).toUpperCase());
  if(args.region)candidates=candidates.filter(p=>[p.admin1,p.admin2,p.admin3].some(v=>v?.toLowerCase().includes(String(args.region).toLowerCase())));
  if(!candidates.length)return {error:'没有找到这个地点，请补充城市及省份/国家，或使用城市英文名。'};
  candidates.sort((a,b)=>(b.population||0)-(a.population||0));
  if(candidates.length>1&&(candidates[0].population||0)<(candidates[1].population||0)*5)return {error:'地点有重名，请明确省份或国家。',candidates:candidates.slice(0,3).map(p=>[p.name,p.admin1,p.country].filter(Boolean).join('，'))};
  const p=candidates[0],today=localDate(now,p.timezone);
  const relative={yesterday:-1,today:0,tomorrow:1,day_after_tomorrow:2};
  const requested=args.date||'today';
  const date=Object.hasOwn(relative,requested)?new Date(Date.parse(today)+relative[requested]*DAY).toISOString().slice(0,10):requested;
  if(!validDate(date))return {error:'请提供有效日期，例如明天或2026-10-12。'};
  const distance=Math.round((Date.parse(date)-Date.parse(today))/DAY);
  if(distance>15)return {error:'目前可以查询当地今天起16天内的预报，请换一个较近日期。',today};
  if(date<'1940-01-01')return {error:'历史天气最早支持1940年起的日期。'};
  const hour=args.hour==null?null:Number(args.hour);
  if(hour!==null&&(!Number.isInteger(hour)||hour<0||hour>23))return {error:'请提供0至23点之间的小时。'};
  const historical=distance < -5;
  const url=new URL(historical?'https://archive-api.open-meteo.com/v1/archive':'https://api.open-meteo.com/v1/forecast');
  url.search=new URLSearchParams({latitude:String(p.latitude),longitude:String(p.longitude),timezone:p.timezone,start_date:date,end_date:date,hourly:'temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m',daily:'temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code'}).toString();
  const data=await get(url),base={location:[p.name,p.admin1,p.country].filter(Boolean).join('，'),timezone:p.timezone,date,type:historical?'历史再分析数据':distance<0?'近期历史预报数据':'天气预报',source:'Open-Meteo',sourceUrl:'https://open-meteo.com/',retrievedAt:now.toISOString()};
  if(hour!==null){
   const index=data.hourly?.time?.indexOf(`${date}T${String(hour).padStart(2,'0')}:00`);
   if(index==null||index<0||data.hourly.temperature_2m[index]==null)return {...base,error:'这个时刻暂无可用天气数据。'};
   return {...base,time:data.hourly.time[index],temperatureC:data.hourly.temperature_2m[index],humidityPercent:data.hourly.relative_humidity_2m[index],precipitationMm:data.hourly.precipitation[index],windKmh:data.hourly.wind_speed_10m[index],weather:description(data.hourly.weather_code[index]),timeResolution:'每小时，非分钟级观测'};
  }
  const d=data.daily;if(d?.temperature_2m_max?.[0]==null||d?.temperature_2m_min?.[0]==null)return {...base,error:'这一天暂无可用天气数据。'};
  return {...base,temperatureMinC:d.temperature_2m_min[0],temperatureMaxC:d.temperature_2m_max[0],precipitationMm:d.precipitation_sum[0],weather:description(d.weather_code[0])};
 }catch(e){if(signal?.aborted)throw e;return {error:'天气查询暂时连接不上，请稍后重试。'};}
}
