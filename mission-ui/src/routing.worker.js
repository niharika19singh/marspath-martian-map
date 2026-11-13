import{plan}from'./engine.js';
self.onmessage=e=>{try{self.postMessage({id:e.data.id,result:plan(e.data.raw,e.data.request)})}catch(error){self.postMessage({id:e.data.id,error:error.message})}};
