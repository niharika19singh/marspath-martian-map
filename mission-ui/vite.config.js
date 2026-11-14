import {defineConfig} from 'vite';
export default defineConfig({
  base:'/mission-control/',
  build:{outDir:'../dist/mission-control',emptyOutDir:true},
  worker:{format:'es'},
  server:{
    proxy:{
      '/api':'http://127.0.0.1:8000',
      '/health':'http://127.0.0.1:8000',
      '/openapi.json':'http://127.0.0.1:8000'
    }
  }
});
