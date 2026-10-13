import {ephemeris,runLatency} from './model.js';
self.onmessage=async({data})=>{try{
  const progress=x=>postMessage({type:'progress',value:x});
  if(data.type==='latency'){postMessage({type:'result',result:runLatency(data.config,data.stations,data.baselines,progress)});return;}
  const ep=ephemeris(data.config),p=ep.config,sim=p.simulation,step=data.sampleStep||60;
  const times=[];for(let t=0;t<sim.duration_s;t+=step)times.push(t);times.push(sim.duration_s);
  const series=ep.elements.map(()=>[]);
  times.forEach((time,k)=>{ep.positions(time).forEach((r,i)=>series[i].push(time,...r.map(x=>Math.round(x*1e6)/1000)));if(k%40===0)progress(k/times.length);});
  const epoch=new Date(sim.epoch).toISOString(),stop=new Date(Date.parse(epoch)+sim.duration_s*1000).toISOString(),interval=epoch+'/'+stop;
  const packets=structuredClone(data.scene);
  const doc=packets.find(x=>x.id==='document');doc.name=p.name||'自定义星座';doc.clock={interval,currentTime:epoch,multiplier:120,range:'LOOP_STOP',step:'SYSTEM_CLOCK_MULTIPLIER'};
  const cfg=packets.find(x=>x.id==='configuration');cfg.properties={minElevationDeg:{number:p.physics.min_elevation_deg},planeCount:{number:p.shells.reduce((s,c)=>s+c.planes,0)},displayDescription:{string:p.name||'自定义星座'}};
  const colors=[[36,145,218,255],[230,126,45,255],[153,108,219,255]];
  let offset=0;const planeOffsets=p.shells.map(c=>{const old=offset;offset+=c.planes;return old;});
  ep.elements.forEach((e,i)=>{const plane=planeOffsets[e.shell]+e.plane+1,color=colors[(plane-1)%3],id=`custom-${e.shell+1}-${e.plane+1}-${e.slot+1}`;
    packets.push({id,name:id,availability:interval,properties:{satellite:{boolean:true},plane:{number:plane},shell:{number:e.shell+1}},
      position:{epoch,referenceFrame:'FIXED',cartesian:series[i],interpolationAlgorithm:'LAGRANGE',interpolationDegree:Math.min(5,times.length-1)},
      point:{pixelSize:7,color:{rgba:color},outlineColor:{rgba:[255,255,255,255]},outlineWidth:1},
      path:{show:true,leadTime:0,trailTime:1800,resolution:60,width:1,material:{solidColor:{color:{rgba:color}}}}});});
  postMessage({type:'result',result:{packets,configuration:p}});
}catch(error){postMessage({type:'error',message:error.message});}};
