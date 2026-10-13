import {validateConfig} from './model.js';
export function download(name,content,type='application/json'){
  const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export const defaultConfig=()=>({schema_version:1,name:'自定义 Walker 星座',topology:'grid',
  simulation:{route:'LD4-TOKYO',duration_s:86400,step_s:60,epoch:'2026-10-12T00:00:00Z'},
  shells:[{pattern:'delta',planes:6,sats_per_plane:12,altitude_km:1180,inclination_deg:50,walker_f:5,raan_start_deg:0,phase_deg:0,j2:true}],
  physics:{min_elevation_deg:20,atmosphere_km:80,max_isl_range_km:6000,satellite_processing_us:5,ground_modem_ms:.5}});
export class ConfigEditor{
  constructor(element){
    this.element=element;this.original=defaultConfig();
    element.innerHTML=`<div class="fields"><label>方案名称<input name="name" maxlength="100"></label><label>历元（UTC）<input name="epoch" placeholder="2026-10-12T00:00:00Z"></label><label>时长（小时）<input name="hours" type="number" min="0.01" max="168" step="any"></label><label>统计快照步长（秒）<input name="step" type="number" min="0.1" step="any"></label><label>最低仰角（°）<input name="elevation" type="number" min="0" max="89" step="any"></label></div><div class="shells"></div><button type="button" class="add-shell">＋ 添加轨道层</button><details><summary>网络时延参数</summary><div class="fields"><label>航线<select name="route"><option value="LD4-TOKYO">伦敦—东京</option><option value="NY4-LD4">纽约—伦敦</option><option value="AURORA-NY4">Aurora—纽约</option></select></label><label>星间拓扑<select name="topology"><option value="grid">每层固定四邻居</option><option value="complete">任意几何选边（无限终端假设）</option></select></label><label>大气边界（km）<input name="atmosphere" type="number" min="0" step="any"></label><label>最大星间距离（km）<input name="range" type="number" min="1" step="any"></label><label>卫星处理（μs/星）<input name="processing" type="number" min="0" step="any"></label><label>星地调制解调（ms/腿/方向）<input name="modem" type="number" min="0" step="any"></label><label>地面对标 RTT（ms，可留空）<input name="reference" type="number" min="0.001" step="any"></label></div><p class="muted">网页时延估算未计入机械/光学跟踪、捕获和切星；工程模型请使用 Python 入口。</p></details>`;
    element.querySelector('.add-shell').onclick=()=>this.addShell({pattern:'delta',planes:6,sats_per_plane:12,altitude_km:1180,inclination_deg:50,walker_f:1,j2:true});
    this.set(defaultConfig());
  }
  field(name){return this.element.querySelector(`[name="${name}"]`);}
  addShell(c){
    const section=document.createElement('fieldset');section.className='shell';
    section.innerHTML=`<legend>轨道层</legend><div class="fields"><label>排布<select name="pattern"><option value="delta">Walker Delta · 360°</option><option value="star">Walker Star · 180°</option><option value="partial">部分轨道面</option></select></label><label>轨道面数 P<input name="planes" type="number" min="1" step="1"></label><label>每面星数 S<input name="sats_per_plane" type="number" min="1" step="1"></label><label>高度（km）<input name="altitude_km" type="number" min="1" step="any"></label><label>倾角（°）<input name="inclination_deg" type="number" min="0" max="180" step="any"></label><label>Walker 相位 F<input name="walker_f" type="number" min="0" step="1"></label><label>RAAN 原点（°）<input name="raan_start_deg" type="number" step="any"></label><label>初始相位（°）<input name="phase_deg" type="number" step="any"></label><label>部分跨度（°，含两端）<input name="raan_span_deg" type="number" min="0.001" max="360" step="any"></label><label class="check"><input name="j2" type="checkbox">长期 J2</label></div><button type="button" class="remove">移除此层</button>`;
    for(const name of ['pattern','planes','sats_per_plane','altitude_km','inclination_deg','walker_f','raan_start_deg','phase_deg','raan_span_deg'])section.querySelector(`[name="${name}"]`).value=c[name]??(['raan_start_deg','phase_deg'].includes(name)?0:name==='raan_span_deg'?120:'');
    section.querySelector('[name="j2"]').checked=c.j2!==false;
    const pattern=section.querySelector('[name="pattern"]'),span=section.querySelector('[name="raan_span_deg"]');
    const refresh=()=>span.disabled=pattern.value!=='partial';pattern.onchange=refresh;refresh();
    section.querySelector('.remove').onclick=()=>{if(this.element.querySelectorAll('.shell').length>1)section.remove();};
    this.element.querySelector('.shells').appendChild(section);
  }
  set(value){
    const p=validateConfig(value);this.original=structuredClone(p);
    const values={name:p.name||'自定义星座',epoch:p.simulation.epoch,hours:p.simulation.duration_s/3600,step:p.simulation.step_s,
      elevation:p.physics.min_elevation_deg,route:p.simulation.route,topology:p.topology,atmosphere:p.physics.atmosphere_km,
      range:p.physics.max_isl_range_km,processing:p.physics.satellite_processing_us,modem:p.physics.ground_modem_ms,reference:p.simulation.baseline_rtt_ms??''};
    for(const [name,value] of Object.entries(values))this.field(name).value=value;
    this.element.querySelector('.shells').replaceChildren();p.shells.forEach(c=>this.addShell(c));
  }
  read(){
    const p=structuredClone(this.original),num=n=>Number(this.field(n).value);
    p.name=this.field('name').value.trim()||'自定义星座';
    Object.assign(p.simulation,{epoch:this.field('epoch').value,route:this.field('route').value,duration_s:num('hours')*3600,step_s:num('step')});
    if(this.field('reference').value)p.simulation.baseline_rtt_ms=num('reference');else delete p.simulation.baseline_rtt_ms;
    Object.assign(p.physics,{min_elevation_deg:num('elevation'),atmosphere_km:num('atmosphere'),max_isl_range_km:num('range'),satellite_processing_us:num('processing'),ground_modem_ms:num('modem')});
    p.topology=this.field('topology').value;
    p.shells=[...this.element.querySelectorAll('.shell')].map(section=>{const c={pattern:section.querySelector('[name="pattern"]').value,j2:section.querySelector('[name="j2"]').checked};
      for(const n of ['planes','sats_per_plane','altitude_km','inclination_deg','walker_f','raan_start_deg','phase_deg','raan_span_deg'])c[n]=Number(section.querySelector(`[name="${n}"]`).value);return c;});
    return validateConfig(p);
  }
}
export function workerJob(type,config,extra={},progress=()=>{}){
  const worker=new Worker(new URL('./worker.js',import.meta.url),{type:'module'});
  let rejectJob;
  const promise=new Promise((resolve,reject)=>{rejectJob=reject;worker.onerror=e=>{worker.terminate();reject(Error(e.message||'计算失败'));};worker.onmessage=({data})=>{
    if(data.type==='progress')progress(data.value);
    if(data.type==='error'){worker.terminate();reject(Error(data.message));}
    if(data.type==='result'){worker.terminate();resolve(data.result);}
  };worker.postMessage({type,config,...extra});});
  return {promise,cancel:()=>{worker.terminate();rejectJob(Error('已停止计算'));}};
}
