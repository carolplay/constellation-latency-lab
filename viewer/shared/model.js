/* Circular mean-elements Kepler + secular J2; same conventions as hftsim. */
export const RE=6378.137,C=299792.458,MU=398600.4418,J2=1.08262668e-3,OMEGA=7.292115e-5;
const rad=Math.PI/180;
export const norm=a=>Math.hypot(...a);
export const dot=(a,b)=>a.reduce((s,x,i)=>s+x*b[i],0);
export const sub=(a,b)=>a.map((x,i)=>x-b[i]);
export const unit=a=>{const n=norm(a);return a.map(x=>x/Math.max(n,1e-15));};
export const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const rz=(v,a)=>[Math.cos(a)*v[0]-Math.sin(a)*v[1],Math.sin(a)*v[0]+Math.cos(a)*v[1],v[2]];
export function ground(s){
  const lat=s.lat_deg*rad,lon=s.lon_deg*rad,e2=6.69437999014e-3,n=RE/Math.sqrt(1-e2*Math.sin(lat)**2),h=s.height_km||0;
  return [(n+h)*Math.cos(lat)*Math.cos(lon),(n+h)*Math.cos(lat)*Math.sin(lon),(n*(1-e2)+h)*Math.sin(lat)];
}
export function up(s){return [Math.cos(s.lat_deg*rad)*Math.cos(s.lon_deg*rad),Math.cos(s.lat_deg*rad)*Math.sin(s.lon_deg*rad),Math.sin(s.lat_deg*rad)];}
export function validateConfig(input){
  const p=structuredClone(input);
  if(p.schema_version!==1||!Array.isArray(p.shells)||!p.shells.length)throw Error('需要 schema_version=1 和至少一个轨道层');
  const sim=p.simulation||{};p.simulation={route:'LD4-TOKYO',duration_s:86400,step_s:60,epoch:'2026-10-12T00:00:00Z',...sim};
  const s=p.simulation;
  if(!Number.isFinite(s.duration_s)||s.duration_s<=0||s.duration_s>604800||!Number.isFinite(s.step_s)||s.step_s<=0||s.step_s>s.duration_s||s.duration_s/s.step_s>20000)throw Error('浏览器支持最多7天、20000个快照；请调整时间步长');
  if(!Number.isFinite(Date.parse(s.epoch))||!/(Z|[+-]\d\d:\d\d)$/.test(s.epoch))throw Error('历元必须含 UTC 时区');
  for(const c of p.shells){
    Object.assign(c,{pattern:c.pattern||'delta',walker_f:c.walker_f??1,raan_start_deg:c.raan_start_deg??0,phase_deg:c.phase_deg??0,j2:c.j2??true});
    if(!Number.isInteger(c.planes)||c.planes<1||!Number.isInteger(c.sats_per_plane)||c.sats_per_plane<1||!Number.isInteger(c.walker_f)||c.walker_f<0||c.walker_f>=c.planes)throw Error('轨道面、每面星数应为正整数，且 0 ≤ F < 面数');
    if(![c.altitude_km,c.inclination_deg,c.raan_start_deg,c.phase_deg].every(Number.isFinite)||c.altitude_km<=0||c.inclination_deg<0||c.inclination_deg>180)throw Error('高度应大于0，倾角应在0–180°');
    if(!['delta','star','partial'].includes(c.pattern))throw Error('未知轨道面排布');
    if(c.pattern==='partial'&&!(c.raan_span_deg>0&&c.raan_span_deg<=360))throw Error('部分轨道面跨度应在0–360°');
    if(c.eccentricity)throw Error('浏览器入口目前支持圆轨道');
  }
  const count=p.shells.reduce((s,c)=>s+c.planes*c.sats_per_plane,0);
  if(count>500)throw Error('浏览器入口最多500星；更大规模请使用Python入口');
  p.physics={min_elevation_deg:20,atmosphere_km:80,max_isl_range_km:6000,satellite_processing_us:5,ground_modem_ms:.5,...p.physics};
  const ph=p.physics;
  if(!Object.values(ph).filter(x=>typeof x==='number').every(Number.isFinite)||ph.min_elevation_deg<0||ph.min_elevation_deg>=90||ph.atmosphere_km<0||ph.max_isl_range_km<=0||ph.satellite_processing_us<0||ph.ground_modem_ms<0)throw Error('仰角、链路距离或处理开销不合法');
  p.topology=p.topology||'grid';
  if(!['grid','complete'].includes(p.topology))throw Error('未知拓扑');
  if(p.topology==='complete'&&count>150)throw Error('任意选边模式最多150星，且假设无限终端');
  return p;
}
export function ephemeris(payload){
  const p=validateConfig(payload),date=Date.parse(p.simulation.epoch)/1000,jd=date/86400+2440587.5,t=(jd-2451545)/36525;
  const theta0=((280.46061837+360.98564736629*(jd-2451545)+.000387933*t*t-t*t*t/38710000)%360)*rad;
  const elements=[];
  p.shells.forEach((c,k)=>{
    const a=RE+c.altitude_km,inc=c.inclination_deg*rad,n=Math.sqrt(MU/a**3),j=c.j2?J2*n*(RE/a)**2:0;
    const span=c.pattern==='delta'?360:c.pattern==='star'?(c.planes>1?180*(c.planes-1)/c.planes:360):c.raan_span_deg;
    const spacing=span===360?span/c.planes:span/Math.max(c.planes-1,1);
    for(let plane=0;plane<c.planes;plane++)for(let slot=0;slot<c.sats_per_plane;slot++)elements.push({
      a,inc,shell:k,plane,slot,raan:(c.raan_start_deg+plane*spacing)*rad,
      m:(c.phase_deg+360*slot/c.sats_per_plane+360*c.walker_f*plane/(c.planes*c.sats_per_plane))*rad,
      rr:-1.5*j*Math.cos(inc),ar:.75*j*(5*Math.cos(inc)**2-1),mr:n+.75*j*(3*Math.cos(inc)**2-1)});
  });
  function eci(e,time){const angle=e.m+(e.mr+e.ar)*time;return rz([e.a*Math.cos(angle),e.a*Math.sin(angle)*Math.cos(e.inc),e.a*Math.sin(angle)*Math.sin(e.inc)],e.raan+e.rr*time);}
  return {config:p,elements,count:elements.length,positions:time=>elements.map(e=>rz(eci(e,time),-theta0-OMEGA*time))};
}
export function candidates(payload){
  const p=validateConfig(payload),n=p.shells.reduce((s,c)=>s+c.planes*c.sats_per_plane,0);
  if(p.topology==='complete'){const edges=[];for(let a=0;a<n;a++)for(let b=a+1;b<n;b++)edges.push([a,b]);return edges;}
  const found=new Map();let offset=0;
  const add=(a,b)=>{if(a>b)[a,b]=[b,a];found.set(a+':'+b,[a,b]);};
  for(const c of p.shells){for(let plane=0;plane<c.planes;plane++)for(let slot=0;slot<c.sats_per_plane;slot++){
    const a=offset+plane*c.sats_per_plane+slot;
    if(c.sats_per_plane>1)add(a,offset+plane*c.sats_per_plane+(slot+1)%c.sats_per_plane);
    if(plane+1<c.planes)add(a,a+c.sats_per_plane);
    else if((c.pattern==='delta'||(c.pattern==='partial'&&c.raan_span_deg===360))&&c.planes>2)add(a,offset+slot);
  }offset+=c.planes*c.sats_per_plane;}
  return [...found.values()].sort((x,y)=>x[0]-y[0]||x[1]-y[1]);
}
export function clearSegment(a,b,radius){const d=sub(b,a),q=Math.max(0,Math.min(1,-dot(a,d)/Math.max(dot(d,d),1e-30)));return norm(a.map((x,i)=>x+q*d[i]))>=radius;}
class Heap{
  constructor(){this.items=[];}
  push(v){const a=this.items;a.push(v);let i=a.length-1;while(i){const j=(i-1)>>1;if(a[j][0]<=v[0])break;a[i]=a[j];i=j;}a[i]=v;}
  pop(){const a=this.items,result=a[0],last=a.pop();if(a.length){let i=0;while(i*2+1<a.length){let j=i*2+1;if(j+1<a.length&&a[j+1][0]<a[j][0])j++;if(a[j][0]>=last[0])break;a[i]=a[j];i=j;}a[i]=last;}return result;}
}
function shortest(adj,start,end){const cost=Array(adj.length).fill(Infinity),previous=Array(adj.length).fill(-1),heap=new Heap();cost[start]=0;heap.push([0,start]);
  while(heap.items.length){const [d,a]=heap.pop();if(d!==cost[a])continue;if(a===end)break;for(const [b,w] of adj[a])if(d+w<cost[b]){cost[b]=d+w;previous[b]=a;heap.push([cost[b],b]);}}
  if(!Number.isFinite(cost[end]))return null;const path=[];for(let n=end;n>=0;n=previous[n]){path.push(n);if(n===start)break;}return {owtt:cost[end],path:path.reverse()};
}
const percentile=(sorted,q)=>{if(!sorted.length)return null;const at=(sorted.length-1)*q,lo=Math.floor(at),hi=Math.ceil(at);return sorted[lo]+(sorted[hi]-sorted[lo])*(at-lo);};
export function runLatency(input,stations,baselines,progress=()=>{}){
  const ep=ephemeris(input),p=ep.config,sim=p.simulation,ph=p.physics,edges=candidates(p),n=ep.count;
  const baseline=baselines.routes[sim.route];if(!baseline)throw Error('未知航线');
  const spec=baseline.stations.map(name=>stations[name]),g=spec.map(ground),u=spec.map(up);
  const ref=sim.baseline_rtt_ms??baseline.rtt_ms,proc=ph.satellite_processing_us*1e-6,frames=[];
  let previous=null,changes=0,onlineWeight=0,totalWeight=0,weightedRtt=0,outage=0,longest=0;
  for(let time=0,k=0;time<sim.duration_s;time+=sim.step_s,k++){
    const re=ep.positions(time),adj=Array.from({length:n+2},()=>[]),add=(a,b,w)=>{adj[a].push([b,w]);adj[b].push([a,w]);};
    let accepted=0;
    for(const [a,b] of edges){const distance=norm(sub(re[b],re[a]));if(distance<=ph.max_isl_range_km&&clearSegment(re[a],re[b],RE+ph.atmosphere_km)){add(a,b,distance/C+proc);accepted++;}}
    const visible=[0,0];for(let side=0;side<2;side++)for(let i=0;i<n;i++){const d=sub(re[i],g[side]),distance=norm(d);if(dot(d,u[side])/distance>=Math.sin(ph.min_elevation_deg*rad)){visible[side]++;add(n+side,i,distance/C+proc/2+ph.ground_modem_ms/1000);}}
    const best=shortest(adj,n,n+1),rtt=best?2*best.owtt*1000:null,path=best?best.path.join('>'):'',weight=Math.min(sim.step_s,sim.duration_s-time);
    const changed=previous!==null&&best!==null&&path!==previous;changes+=changed?1:0;previous=best?path:null;
    totalWeight+=weight;
    if(best){onlineWeight+=weight;weightedRtt+=rtt*weight;outage=0;}else{outage+=weight;longest=Math.max(longest,outage);}
    let length=null;if(best)length=best.path.slice(1).reduce((sum,b,j)=>{const a=best.path[j],pa=a<n?re[a]:g[a-n],pb=b<n?re[b]:g[b-n];return sum+norm(sub(pb,pa));},0);
    frames.push({time_s:time,sample_duration_s:weight,rtt_ms:rtt,owtt_ms:best?best.owtt*1000:null,delta_rtt_ms:best?ref-rtt:null,
      reference_rtt_ms:ref,satellite_relays:best?best.path.length-2:null,path_length_km:length,path,path_changed:changed,
      outage_reason:best?'connected':Math.min(...visible)===0?'no_visible_ground_satellite':'no_isl_route',source_visible:visible[0],destination_visible:visible[1],accepted_isl:accepted});
    if(k%Math.max(1,Math.floor(sim.duration_s/sim.step_s/50))===0)progress(time/sim.duration_s);
  }
  const values=frames.filter(f=>f.rtt_ms!==null).map(f=>f.rtt_ms).sort((a,b)=>a-b),availability=onlineWeight/totalWeight;
  const p1=percentile(values,.01),p99=percentile(values,.99);
  return {configuration:p,mode:'geometry',frames,summary:{samples:frames.length,online_samples:values.length,availability,
    mean_rtt_ms:values.length?weightedRtt/onlineWeight:null,p1_rtt_ms:p1,p99_rtt_ms:p99,p99_p1_jitter_ms:values.length?p99-p1:null,
    outage_s:totalWeight-onlineWeight,longest_outage_s:longest,path_changes:changes,handover_count:null,
    unconditional_p99_rtt_ms:availability<.99?'infinity_due_to_outage':percentile(values,Math.min(.99/availability,1))},
    conventions:{rtt:'2 × same-epoch symmetric OWTT',access:'Immediate access to all visible satellites',
      topology:p.topology==='grid'?'Shell-local four-neighbour graph':'Unlimited-terminal mesh',
      excluded:'PAT/FOV/slew/Doppler/acquisition/handover/traffic/weather/capacity',jitter:'Conditional online RTT P99−P1'}};
}
