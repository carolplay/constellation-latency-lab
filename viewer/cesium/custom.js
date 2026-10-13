import {ConfigEditor,download,workerJob} from './shared/editor.js';
const dialog=document.getElementById('custom-dialog'),editor=new ConfigEditor(document.getElementById('custom-editor'));
const notice=document.getElementById('custom-notice'),button=document.getElementById('add-custom');
let job=null,last=null,saved=[];
try{saved=JSON.parse(localStorage.getItem('constellation-lab-custom')||'[]');}catch(_){}
document.getElementById('new-constellation').onclick=()=>dialog.showModal();
document.getElementById('close-custom').onclick=()=>{job?.cancel();dialog.close();};
document.getElementById('export-config').onclick=()=>{try{download('constellation.config.json',JSON.stringify(editor.read(),null,2));}catch(e){notice.textContent=e.message;}};
document.getElementById('export-czml').onclick=()=>{if(last)download('constellation.czml',JSON.stringify(last.packets));};
document.getElementById('import-config').onchange=async e=>{try{editor.set(JSON.parse(await e.target.files[0].text()));notice.textContent='配置已载入，可修改或直接加入。';}catch(error){notice.textContent=error.message;}e.target.value='';};
const ready=()=>new Promise((resolve,reject)=>{let attempts=0;const timer=setInterval(()=>{if(window.walkerApp?.ready){clearInterval(timer);resolve(window.walkerApp);}else if(++attempts>600){clearInterval(timer);reject(Error('三维视图尚未就绪'));}},100);});
async function generate(config){
  const app=await ready(),scene=await fetch('./data/scene.json').then(r=>r.json());
  button.disabled=true;notice.textContent='正在生成轨迹…';
  try{job=workerJob('coverage',config,{scene,sampleStep:60},x=>notice.textContent='生成轨迹 '+Math.round(x*100)+'%');last=await job.promise;
    await app.load(last.packets,true);const study=document.getElementById('study-summary');study.hidden=false;
    study.textContent='自定义几何方案 · 当前时刻计数；未运行全天可用率审核。配置仅保存在本机浏览器。';
    document.getElementById('export-czml').disabled=false;notice.textContent='已生成，可下载配置和 CZML。';return true;
  }finally{button.disabled=false;job=null;}
}
function addOption(item){const selector=document.getElementById('scenario');if(!selector.querySelector(`option[value="local:${item.id}"]`)){
  const option=document.createElement('option');option.value='local:'+item.id;option.textContent='本机 · '+item.config.name;selector.appendChild(option);}
  document.getElementById('scenario-control').hidden=false;
}
button.onclick=async()=>{try{
  const config=editor.read();await generate(config);
  const item={id:Date.now().toString(36),config};saved.push(item);localStorage.setItem('constellation-lab-custom',JSON.stringify(saved));addOption(item);
  document.getElementById('scenario').value='local:'+item.id;dialog.close();
}catch(error){notice.textContent=error.message;}};
ready().then(()=>{saved.forEach(addOption);const selector=document.getElementById('scenario'),original=selector.onchange;
  selector.onchange=async()=>{if(selector.value.startsWith('local:')){const item=saved.find(x=>'local:'+x.id===selector.value);try{editor.set(item.config);await generate(item.config);}catch(error){document.getElementById('status').textContent=error.message;}}else original?.();};
}).catch(error=>notice.textContent=error.message);
