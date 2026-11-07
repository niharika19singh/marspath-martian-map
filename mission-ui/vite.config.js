import {defineConfig} from 'vite';
export default defineConfig({base:'/mission-control/',build:{outDir:'../dist/mission-control',emptyOutDir:true},worker:{format:'es'}});
