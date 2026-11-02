<template>
 <svg viewBox="0 0 300 120" class="workbench-sketch" aria-hidden="true">
<template v-if="kind==='results'">
   <path d="m52 91 81-27 89 27-85 23Z" fill="#cae1e2"/><path d="m91 17 51-6 38 34-44 25-49-15Z" fill="#f2e8e2"/>
   <g class="ink"><path d="M53 89 134 63 222 91 137 115Z M53 89v11l84 15 85-24M92 18l51-7 36 34-44 25-47-16Z M92 18l42 28 45-1M134 46l1 24M92 18l-5 70 48 21 43-25 1-39M135 70v39"/><path d="m26 27 6-10 5 12m204 37q25-13 27-37m-9 4 9-5 6 10"/></g>
  </template>
  <template v-else>
   <path d="M30 95q74-20 238-5l-7 20H32Z" fill="#cae1e2"/><path d="m114 57 22-26 31 9 11 47-64 5Z" fill="#f2e8e2"/>
   <g class="ink"><path d="M38 22l41 3 1 37-40-4Z m2 3 32 2 1 22-30-3ZM57 60l-2 38m-12 2 30 1M219 24l37-3 2 30-38 3Zm19 30 1 44m-12 3 27-2"/><ellipse cx="145" cy="91" rx="45" ry="11"/><path d="M100 91v9q42 21 90 0v-9M118 79l-3-22 20-27 31 10 9 39m-60-22 30 5 21-22m-22 22v22M24 111q133 4 248-2"/><circle cx="238" cy="37" r="7"/><path class="ray" d="m80 41 26 19m108-21-32 22"/></g>
   <path d="m44 31 27 3 1 17-28-3Z" fill="#65b8a2"/><path d="m120 62 18 4v15l-16-5Z" fill="#d6aec1"/>
  </template>
 </svg>
</template>
<script setup lang="ts">withDefaults(defineProps<{kind?:string}>(),{kind:'scanner'})</script>
<style scoped>.workbench-sketch{display:block;width:250px;height:100px;flex:none}.ink{fill:none;stroke:#231e21;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}.ray{stroke:#1c5d5f;stroke-dasharray:4 5}</style>
