import {ConfigEditor,download,workerJob} from './shared/editor.js';
const editor=new ConfigEditor(document.getElementById('latency-editor')),progress=document.getElementById('progress');
let result=null,job=null,catalog=[];
const metric=(id,value,suffix)=>document.getElementById(id).textContent=value===null?'—':value.toFixed(2)+suffix;
try{catalog=await fetch('./data/catalog.json').then(r=>r.json());const select=document.getElementById('latency-preset');
  for(const entry of catalog){const option=document.createElement('option');option.value=entry.id;option.textContent=entry.label;select.appendChild(option);}
  const choose=async()=>{const item=catalog.find(x=>x.id===select.value);if(item)editor.set(await fetch(item.url).then(r=>r.json()));};
  select.value='candidate72';select.onchange=()=>choose().catch(e=>progress.textContent=e.message);await choose();
}catch(e){progress.textContent=e.message;}
document.getElementById('latency-config-file').onchange=async e=>{try{editor.set(JSON.parse(await e.target.files[0].text()));progress.textContent='配置已载入。';}catch(error){progress.textContent=error.message;}e.target.value='';};
document.getElementById('download-latency-config').onclick=()=>{try{download('constellation.config.json',JSON.stringify(editor.read(),null,2));}catch(e){progress.textContent=e.message;}};
function inspect(){if(!result)return;const f=result.frames[Number(document.getElementById('sample-index').value)];
  document.getElementById('sample-detail').textContent=`t=${f.time_s}s · ${f.rtt_ms===null?'未接通：'+f.outage_reason:'RTT '+f.rtt_ms.toFixed(3)+' ms · '+f.satellite_relays+'颗卫星转发'} · 可见星 ${f.source_visible}/${f.destination_visible} · 路径 ${f.path||'—'}`;}
function plot(){if(!result)return;const canvas=document.getElementById('latency-chart'),ratio=Math.min(window.devicePixelRatio||1,2),w=canvas.clientWidth,h=canvas.clientHeight;
  canvas.width=w*ratio;canvas.height=h*ratio;const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.clearRect(0,0,w,h);
  const values=result.frames.filter(f=>f.rtt_ms!==null).map(f=>f.rtt_ms),max=Math.max(1,...values)*1.12,left=46,top=22,width=w-left-16,height=h-top-32;
  ctx.strokeStyle='#294259';ctx.fillStyle='#a7bfd3';ctx.font='11px system-ui';for(let j=0;j<4;j++){const y=top+height*j/3;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-12,y);ctx.stroke();ctx.fillText((max*(1-j/3)).toFixed(0),5,y+4);}
  ctx.fillText('RTT ms',5,12);ctx.fillText('0h',left,h-8);ctx.fillText((result.configuration.simulation.duration_s/3600).toFixed(1)+'h',w-45,h-8);
  ctx.strokeStyle='#75c8eb';ctx.lineWidth=1.5;ctx.beginPath();let open=false;
  for(const f of result.frames){if(f.rtt_ms===null){open=false;continue;}const x=left+width*f.time_s/result.configuration.simulation.duration_s,y=top+height*(1-f.rtt_ms/max);if(open)ctx.lineTo(x,y);else ctx.moveTo(x,y);open=true;}ctx.stroke();
  if(!values.length){ctx.fillStyle='#e2a69b';ctx.fillText('没有可接通的快照',left+20,top+height/2);}
}
document.getElementById('sample-index').oninput=inspect;window.addEventListener('resize',plot);
document.getElementById('run-latency').onclick=async()=>{
  const run=document.getElementById('run-latency'),stop=document.getElementById('stop-latency');
  try{const cfg=editor.read();run.disabled=true;stop.disabled=false;progress.textContent='正在构建快照图…';
    const [stations,baselines]=await Promise.all([fetch('./data/stations.json').then(r=>r.json()),fetch('./data/baselines.json').then(r=>r.json())]);
    job=workerJob('latency',cfg,{stations,baselines},x=>progress.textContent='计算 '+Math.round(x*100)+'%');result=await job.promise;
    window.latencyResult=result;metric('availability',result.summary.availability*100,'%');metric('mean',result.summary.mean_rtt_ms,' ms');metric('p99',result.summary.p99_rtt_ms,' ms');metric('jitter',result.summary.p99_p1_jitter_ms,' ms');
    document.getElementById('outage').textContent=`中断 ${result.summary.outage_s}s · 最长中断 ${result.summary.longest_outage_s}s · 路径变化 ${result.summary.path_changes} 次（不等于实际切星次数）`;
    for(const id of ['download-csv','download-result','sample-index'])document.getElementById(id).disabled=false;
    const range=document.getElementById('sample-index');range.max=result.frames.length-1;range.value=0;inspect();plot();
    progress.textContent=`完成 ${result.frames.length} 个几何快照。结果仅在本机计算。`;
  }catch(error){progress.textContent=error.message;}finally{run.disabled=false;stop.disabled=true;job=null;}
};
document.getElementById('stop-latency').onclick=()=>job?.cancel();
document.getElementById('download-result').onclick=()=>download('latency.result.json',JSON.stringify(result,null,2));
document.getElementById('download-csv').onclick=()=>{const keys=Object.keys(result.frames[0]),quote=v=>v===null?'':typeof v==='string'?'"'+v.replaceAll('"','""')+'"':String(v);
  download('latency.timeseries.csv',keys.join(',')+'\n'+result.frames.map(row=>keys.map(k=>quote(row[k])).join(',')).join('\n'),'text/csv');};
