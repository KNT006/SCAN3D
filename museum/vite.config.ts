import {defineConfig} from 'vite';
import vue from '@vitejs/plugin-vue';
import {museumAIPlugin} from './server/museum-ai.mjs';
export default defineConfig({plugins:[museumAIPlugin(),vue()],server:{host:'127.0.0.1',port:8830,strictPort:true,proxy:{'/api/collection':{target:'http://192.168.1.89:8830',changeOrigin:true},'/museum/imports':{target:'http://192.168.1.89:8830',changeOrigin:true}}},preview:{host:'127.0.0.1',port:8831,strictPort:true},build:{chunkSizeWarningLimit:850}});
