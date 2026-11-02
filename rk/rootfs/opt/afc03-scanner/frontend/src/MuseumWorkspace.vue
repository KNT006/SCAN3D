<template>
 <section class="museum-workspace" aria-label="物品陈列馆">
  <iframe :key="revision" :src="museumUrl" title="物品陈列馆" @load="loaded=true" allow="fullscreen" />
  <div v-if="!loaded" class="museum-loading"><span>正在打开陈列馆…</span><button @click="revision++">重新加载</button><a :href="museumUrl" target="_blank" rel="noopener">独立打开</a></div>
 </section>
</template>
<script setup lang="ts">
import {ref} from 'vue'
const props=defineProps<{exhibit?:string}>()
const loaded=ref(false),revision=ref(0)
// RK HDMI may use localhost; development uses the same RK museum service.
const host=location.port==='8834'?'192.168.1.89':location.hostname
const museumUrl=`${location.protocol}//${host}:8830/${props.exhibit?'#exhibit/'+encodeURIComponent(props.exhibit):''}`
</script>
