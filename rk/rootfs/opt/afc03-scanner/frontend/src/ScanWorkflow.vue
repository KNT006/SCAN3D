<template>
 <div class="scan-workflow" aria-label="建议扫描顺序">
  <button v-for="(item,i) in steps" :key="item.title" :class="{current:current===i}" @click="emit('navigate',i)"><span>{{String(i+1).padStart(2,'0')}}</span><div><b>{{item.title}}</b><small>{{item.short}}</small></div><i v-if="i<steps.length-1">›</i></button>
  <button class="workflow-help" @click="guide?.showModal()">流程说明</button>
 </div>
 <Teleport to="body"><dialog ref="guide" class="workflow-guide"><header><div><small>SCAN3D · 操作指引</small><h2>从物体到三维模型</h2></div><button aria-label="关闭扫描流程说明" @click="guide?.close()">×</button></header><div class="workflow-guide-grid"><article v-for="(item,i) in steps" :key="item.title"><span>0{{i+1}}</span><div><h3>{{item.title}}</h3><p>{{item.detail}}</p><button @click="guide?.close();emit('navigate',i)">{{item.action}} →</button></div></article></div><div class="workflow-parallel"><b>扫描过程中，哪些环节并行？</b><p>每个角度的运动、停稳和光源切换按顺序执行，A/B 激光分时采集。FPGA 提取条纹并经 DMA 传递结果；RK 使用结果队列，将已采集位置的重建与存储和后续采集交叠。实时预览是显示支路，不能用预览点数代替完整扫描验收。</p></div></dialog></Teleport>
</template>
<script setup lang="ts">
import {ref} from 'vue'
defineProps<{current:number}>()
const emit=defineEmits<{navigate:[step:number]}>(),guide=ref<HTMLDialogElement>()
const steps=[
 {title:'准备与取景',short:'固定物体 · 白灯观察',action:'检查光源与取景',detail:'固定物体，保持相机和激光支架不动；物体不超出直径 140 mm 的转盘。打开镜头挡板，确认驱动供电。先在白灯、激光关闭的条件下观察实时画面，避免全黑和过曝。'},
 {title:'确认参数',short:'名称 · 步长 · 范围',action:'确认扫描参数',detail:'填写名称，选择步长；新物体建议先 6° 粗扫，检查覆盖后再细扫。核对空间范围及固定情况。条纹候选参数用于同帧回放，是否用于正式扫描以页面说明为准。'},
 {title:'采集与重建',short:'起始检查 · 双激光扫描',action:'查看实时监控',detail:'点击开始后，系统先采集起始图并检查亮度和数据，再按步长转动，分时取得 A/B 激光结果和颜色图。扫描控制光源切换，实时监控显示本任务进度、重试和点云。暂停或预览有点不代表扫描完成。'},
 {title:'验收与导出',short:'完整性 · 点云 · STL',action:'进入扫描结果',detail:'扫描结束后检查任务是否完成、首尾一致性、缺口、离群点及耗时报告，再生成 STL。按需要去除悬空部分和封闭底部；补全曲面属于估计几何。点云包围盒与修剪、封闭后的 STL 尺寸可能不同，角度步长不等于测量精度。'}
]
</script>
<style scoped>
.scan-workflow{display:flex;align-items:stretch;gap:6px;flex:none;padding:8px;background:#f6f6ef;border:1px solid #e0e2d5;border-radius:12px}.scan-workflow>button{display:flex;align-items:center;gap:10px;flex:1;background:transparent;border:0;padding:8px 12px;text-align:left;min-width:0}.scan-workflow>button>span{font-size:16px;color:#919a85;font-variant-numeric:tabular-nums}.scan-workflow b{font-size:13px;font-weight:600;color:#394537}.scan-workflow small{display:block;max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10px;margin-top:5px;color:#808675}.scan-workflow i{margin-left:auto;font-style:normal;color:#b6baa8}.scan-workflow>button.current{background:#e5eadc;border-radius:8px}.scan-workflow>button.current>span{color:#627449}.scan-workflow>.workflow-help{flex:none;font-size:12px;border-left:1px solid #dcdfd1;border-radius:0;color:#6c775e}.workflow-guide{width:min(1050px,94vw);max-height:90vh;padding:0;border:1px solid #d9ddce;border-radius:18px;color:#333f31;background:#fafbf6;box-shadow:0 24px 90px #0004}.workflow-guide::backdrop{background:#17271e80}.workflow-guide header{display:flex;justify-content:space-between;align-items:center;padding:22px 28px;border-bottom:1px solid #e3e5d9}.workflow-guide header small{font-size:11px;color:#7e8871}.workflow-guide header h2{font-size:23px;margin-top:8px}.workflow-guide header button{font-size:22px;border:0;background:none}.workflow-guide-grid{padding:20px 28px;display:grid;grid-template-columns:1fr 1fr;gap:20px}.workflow-guide article{display:flex;gap:14px}.workflow-guide article>span{font-size:22px;color:#9eab87}.workflow-guide h3{font-size:15px}.workflow-guide p{font-size:13px;line-height:1.8;color:#717967;margin-top:7px}.workflow-guide article button{margin-top:9px;padding:6px 10px;font-size:11px}.workflow-guide article:last-child{grid-column:1/3}.workflow-parallel{margin:0 28px 18px;padding:15px 18px;background:#edf0e4;border-radius:10px;font-size:14px}.workflow-guide footer{font-size:12px;padding:13px 28px;background:#e7ebdd;color:#6b795a}@media(max-width:1500px){.scan-workflow>button{padding:7px;gap:6px}.scan-workflow small{max-width:170px}}
</style>
