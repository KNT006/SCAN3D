<template>
 <div class="settings-layout">
  <section class="panel settings-device">
   <div class="panel-title"><h2>设备与存储</h2></div>
   <svg class="desk-sketch" viewBox="0 0 360 165" aria-hidden="true"><path class="wash" d="M31 119q43-25 100-9t164-6l26 41H27Z"/><g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m48 32 74-3 2 60-76 3Z M55 39l60-2 1 45-61 2Z M81 92l-2 24m-15 2 40-1M157 133q43-17 94-1q-32 15-94 1Zm0 0v10q44 14 94-1v-10M189 108l1-31 24-2 4 34m-28-32 11-13 13 11M275 40l34 2 1 26-36-2Zm16 29-2 48m-13 4 28-1M21 148q157-5 316 0"/><path stroke-dasharray="4 5" d="m271 62-46 32M128 57l48 37"/></g><circle cx="294" cy="54" r="7" fill="#65b8a2"/><path d="m196 83 11-1 1 18-12 1Z" fill="#d6aec1"/></svg>
   <dl class="device-readings">
    <div><dt>上位机服务</dt><dd :class="online?'status-good':'status-bad'">{{online?'已连接':'连接中断'}}</dd></div>
    <div><dt>板端主机</dt><dd>{{online?(device.host||'RK3576'):'未连接'}}</dd></div>
    <div><dt>相机采集</dt><dd :class="online&&camera.online?'status-good':'status-bad'">{{!online?'未知':camera.online?'在线':'无实时画面'}}</dd></div>
    <div><dt>硬件控制服务</dt><dd>{{!online?'未知':(device.controller_available??device.serial_present)===true?'已检测到':(device.controller_available??device.serial_present)===false?'未检测到':'读取中'}}</dd></div>
    <div><dt>可用内存</dt><dd>{{online&&device.memory_available_mib!==undefined?device.memory_available_mib+' MiB':'—'}}</dd></div>
    <div><dt>可用空间</dt><dd>{{online?(state.storage?.free_gib??'—'):'—'}} / {{online?(state.storage?.total_gib??'—'):'—'}} GiB</dd></div>
    <div><dt>扫描存储</dt><dd>{{!online?'未知':state.storage?.sd_configured?'SD 卡直存':'未就绪'}}</dd></div>
    <div><dt>服务版本</dt><dd>{{online?(device.version||'—'):'—'}}</dd></div>
   </dl>
   <div class="settings-path"><span>扫描数据目录</span><code>{{state.storage?.path||'—'}}</code></div>
  </section>
  <section class="panel settings-guide">
   <div class="panel-title"><h2>使用说明</h2></div>
   <div class="settings-tabs" role="tablist" aria-label="说明分类"><button v-for="(v,i) in guides" :key="v.title" :class="{chosen:guide===i}" @click="guide=i" role="tab" :aria-selected="guide===i">{{v.title}}</button></div>
   <div class="guide-body" role="tabpanel">
    <span class="notebook-number">0{{guide+1}}</span><h3>{{guides[guide].heading}}</h3>
    <div v-for="item in guides[guide].items" :key="item[0]" class="guide-entry"><b>{{item[0]}}</b><p>{{item[1]}}</p></div>
    <div class="settings-illustration" aria-hidden="true"><img :src="settingsSketch" alt="" /></div>
   </div>
  </section>
  <section class="panel settings-algorithm">
   <div class="panel-title"><h2>算法与预览</h2></div>
   <div class="settings-model">
    <h3>颜色校正</h3><p>实时监控显示同帧原图和FPGA颜色校正预览。点云使用同角度矫正图像取色；</p>
    <p v-if="color?.profile">参考条件：白灯 {{color.profile.led}}、相机增益 {{color.profile.gain}}、激光关闭。{{color.profile.patch_count}} 块采样，{{color.profile.fit_patch_count}} 块参与拟合。</p>
    <p v-if="error" role="alert" class="status-bad">{{error}}</p><button :disabled="loading" @click="refresh">{{loading?'读取中…':'刷新算法信息'}}</button>
   </div>
  </section>
 </div>
</template>
<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount} from 'vue'
import settingsSketch from './assets/settings-lineart-generated.png'
defineProps<{online:boolean,state:any,camera:any,device:any}>()
const guide=ref(0),color=ref<any>(),error=ref(''),loading=ref(false)
let controller:AbortController|undefined
const guides=[
 {title:'扫描与光源',heading:'从取景到整圈扫描',items:[['扫描前','固定物体，保持相机和激光支架不动，打开镜头挡板并接通电机电源。'],['角度步长','步长是电机指令角度。整圈为 3200 脉冲，非整数脉冲角度按累计取整执行。'],['补光与激光','补光灯与激光 A、B 可独立开关，也可同时开启。正式扫描由程序控制光源，顶部停止按钮会停止转动并关闭所有光源。'],['手动转盘','从上往下看，正角度为顺时针。选角后点击转动，按 0.1125° 脉冲取整；“方向反向”用于调整方向。']]},
 {title:'条纹与空间',heading:'区分回放参数与扫描参数',items:[['候选参数','峰、亮核、连续性与多峰参数用于 RK 同帧回放，A/B 共用。'],['空间范围','转盘直径 140 mm，默认半径 70 mm、余量 0。先剔除越界候选，再复核连续性和多峰。当前范围固定为半径 70 mm，由 FPGA ROM 与 RK 配置共同保证。'],['逐行曲线','点击条纹图选行。绿色点为保留，红色点为舍弃；黄色区域表示亮核。判定数值和筛除原因保留在流程页。'],['差分定义','差分曲线取 RGB 各通道正差分的最大值；开、关帧曲线分别取各自 RGB 最大值。']]},
 {title:'点云与 STL',heading:'理解模型与尺寸',items:[['点云显示','扫描中显示本任务已保存位置的增量预览。扫描结束后，结果页一次载入完整实测点云。'],['包围盒','报告尺寸来自实测点云在转盘坐标系中的 X/Y/Z 包围盒，离群点与缺口会影响结果。'],['重建参数','标准采样为 0.4 mm，精细为 0.25 mm。Poisson 深度越高越保留细节，也可能保留噪声；曲面降噪会抑制起伏并削弱细节。'],['曲面来源','STL 采用 RK 几何重建。补洞和封底包含估计表面，应结合封闭性、边界边与报告检查。']]},
 {title:'归档与并行',heading:'管理扫描资料',items:[['归档内容','导出包含模型、标定与报告，不包含原始照片，也不会自动删除原照片。PC 校验归档的照片以该次扫描报告为准。'],['扫描时','可以查看、分析或删除其他已保存扫描；当前扫描和正在分析的数据受保护。'],['删除范围','可只删原始照片，或删除整次扫描。删除原照片后无法再做这些帧的回放；永久删除前会显示具体范围与确认。'],['SD 卡','扫描原始照片、点云和 STL 直接保存在 SD 卡。关机后再拔卡；插回原卡后可继续查看和扫描。']]}
]
async function refresh(){if(loading.value)return;loading.value=true;error.value='';controller=new AbortController();try{const results=await Promise.allSettled(['/api/scan3d/color-preview/status'].map(async u=>{const r=await fetch(u,{cache:'no-store',signal:controller!.signal});if(!r.ok)throw Error();return r.json()}));color.value=results[0].status==='fulfilled'?results[0].value:null;if(results.some(r=>r.status==='rejected'))error.value='部分算法信息暂不可用，可重新刷新。'}finally{loading.value=false}}
onMounted(refresh);onBeforeUnmount(()=>controller?.abort())
</script>
