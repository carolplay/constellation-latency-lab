/* Baseline rendering diagnosis; does not change the site or orbital model. */
const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const req=process.env.BROWSER_NODE_MODULES?createRequire(path.join(process.env.BROWSER_NODE_MODULES,'entry.cjs')):require;
const {chromium}=req('playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||undefined,args:['--use-angle=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
  const page=await browser.newPage({viewport:{width:390,height:844},ignoreHTTPSErrors:true});
  const origin=process.env.WALKER_PREVIEW_URL||'http://127.0.0.1:8766/';
  const response=await page.goto(origin,{waitUntil:'domcontentloaded',timeout:90000});
  if(await page.locator('.card').count()!==2)throw Error('Public homepage not accessible');
  await page.goto(new URL('coverage.html',origin).href,{waitUntil:'domcontentloaded',timeout:90000});
  await page.waitForFunction(()=>window.walkerApp?.ready,{},{timeout:90000});
  await page.locator('#scenario').selectOption('candidate72');await page.waitForFunction(()=>walkerApp.ready&&walkerApp.satelliteEntities.length===72,{},{timeout:90000});
  const results=[];
  for(const [name,footprints,paths] of [['full',true,true],['no_footprints',false,true],['points_only',false,false]]){
    const result=await page.evaluate(async({name,footprints,paths})=>{
      const a=walkerApp,C=Cesium;a.viewer.clock.shouldAnimate=false;
      const checkbox=document.getElementById('footprints');checkbox.checked=footprints;checkbox.dispatchEvent(new Event('change'));
      for(const e of a.satelliteEntities)e.path.show=paths;
      a.viewer.clock.currentTime=C.JulianDate.addSeconds(a.viewer.clock.startTime,3600,new C.JulianDate());
      const times=[];
      for(let i=0;i<25;i++){const t=C.JulianDate.addSeconds(a.viewer.clock.startTime,3600+i*10,new C.JulianDate()),start=performance.now();a.update(t,true);if(i>=5)times.push(performance.now()-start);}
      const avg=times.reduce((s,x)=>s+x,0)/times.length;
      a.viewer.clock.shouldAnimate=true;const deltas=[];let previous=null,start=null;
      await new Promise(resolve=>{function tick(now){if(start===null)start=now;if(previous!==null)deltas.push(now-previous);previous=now;if(now-start>=2500)resolve();else requestAnimationFrame(tick);}requestAnimationFrame(tick);});
      a.viewer.clock.shouldAnimate=false;deltas.sort((a,b)=>a-b);const mean=deltas.reduce((s,x)=>s+x,0)/deltas.length;
      return {name,footprints,paths,meanUpdateMs:avg,meanAnimationFrameMs:mean,observedFps:1000/mean,p99FrameMs:deltas[Math.floor((deltas.length-1)*.99)],frames:deltas.length};
    },{name,footprints,paths});results.push(result);
  }
  const out='outputs/release-verification';fs.mkdirSync(out,{recursive:true});
  const result={publicHomepageStatus:response.status(),unauthenticatedContext:true,viewport:'390x844',satellites:72,
    renderer:'Headless Chromium with SwiftShader; software-rendered baseline, not measured phone FPS',results};
  fs.writeFileSync(path.join(out,'performance-baseline.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));await browser.close();
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
