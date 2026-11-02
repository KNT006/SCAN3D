import {createApp} from 'vue';
if(new URLSearchParams(location.search).has('import')){
 const {mountImportBridge}=await import('./museum/ScanImportBridge');mountImportBridge();
}else if(new URLSearchParams(location.search).has('pond')){
 const [{default:App}]=await Promise.all([import('./DuckPetScene.vue'),import('./style.css')]);createApp(App).mount('#app');
}else{
 const [{default:App}]=await Promise.all([import('./museum/MuseumApp.vue'),import('./museum/museum.css')]);createApp(App).mount('#app');
 document.title='物品陈列馆 · SCAN3D';
}
