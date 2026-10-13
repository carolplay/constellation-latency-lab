/* Standalone Cesium core viewer; no ion SDK or access token required. */
(async()=>{
  const status=document.getElementById('status');
  const fail=error=>{status.textContent='无法载入：'+error.message;status.className='error';};
  try{
    if(!window.Cesium)throw new Error('CesiumJS 下载失败；请检查网络连接');
    const C=window.Cesium,A=6378137,B=6356752.314245;
    let baseLayer;
    try{
      baseLayer=new C.ImageryLayer(await C.TileMapServiceImageryProvider.fromUrl(C.buildModuleUrl('Assets/Textures/NaturalEarthII')));
    }catch(_){baseLayer=new C.ImageryLayer(new C.GridImageryProvider());}
    const viewer=new C.Viewer('globe',{baseLayer,terrainProvider:new C.EllipsoidTerrainProvider(),
      baseLayerPicker:false,geocoder:false,homeButton:false,sceneModePicker:true,navigationHelpButton:false,
      fullscreenButton:false,animation:true,timeline:true,selectionIndicator:true,infoBox:false,
      shouldAnimate:false,contextOptions:{webgl:{alpha:false}}});
    viewer.scene.globe.depthTestAgainstTerrain=true;
    viewer.scene.globe.enableLighting=false;
    viewer.scene.globe.baseColor=C.Color.fromCssColorString('#344e64');
    const app=window.walkerApp={viewer,ready:false,lastStats:null};
    let satellites=[],cones=[],footprints=[],route=[],stations=[],epsilon=20,lastWall=0,lastTime=null;
    const planeColors=['#2491da','#e67e2d','#996cdb'].map(color=>C.Color.fromCssColorString(color));
    const green=C.Color.fromCssColorString('#55c589'),red=C.Color.fromCssColorString('#ef776c');
    const dot=(a,b)=>a.x*b.x+a.y*b.y+a.z*b.z;
    function visible(sat,ground,normal){
      const dx=sat.x-ground.x,dy=sat.y-ground.y,dz=sat.z-ground.z;
      return (dx*normal.x+dy*normal.y+dz*normal.z)/Math.hypot(dx,dy,dz)>=Math.sin(epsilon*Math.PI/180);
    }
    function surfacePoint(entity,time,zeroHeight){
      const position=entity.position.getValue(time);
      let ground=position;
      if(zeroHeight){const ll=C.Cartographic.fromCartesian(position);ground=C.Cartesian3.fromRadians(ll.longitude,ll.latitude,0);}
      return {entity,ground,normal:C.Ellipsoid.WGS84.geodeticSurfaceNormal(ground,new C.Cartesian3())};
    }
    function boundary(satellite,vertices=window.matchMedia('(max-width:600px)').matches?32:64){
      const z=C.Cartesian3.normalize(satellite,new C.Cartesian3());
      const ref=Math.abs(z.z)<.95?C.Cartesian3.UNIT_Z:C.Cartesian3.UNIT_X;
      const x=C.Cartesian3.normalize(C.Cartesian3.cross(ref,z,new C.Cartesian3()),new C.Cartesian3());
      const y=C.Cartesian3.cross(z,x,new C.Cartesian3()),points=[];
      for(let j=0;j<vertices;j++){
        const az=2*Math.PI*j/vertices,tx=Math.cos(az)*x.x+Math.sin(az)*y.x,
          ty=Math.cos(az)*x.y+Math.sin(az)*y.y,tz=Math.cos(az)*x.z+Math.sin(az)*y.z;
        let lo=0,hi=Math.PI/2,g;
        for(let k=0;k<32;k++){
          const theta=(lo+hi)/2,c=Math.cos(theta),s=Math.sin(theta);
          const rx=c*z.x+s*tx,ry=c*z.y+s*ty,rz=c*z.z+s*tz;
          const radius=1/Math.sqrt((rx*rx+ry*ry)/(A*A)+rz*rz/(B*B));
          g=new C.Cartesian3(radius*rx,radius*ry,radius*rz);
          const n=C.Cartesian3.normalize(new C.Cartesian3(g.x/(A*A),g.y/(A*A),g.z/(B*B)),new C.Cartesian3());
          if(visible(satellite,g,n))lo=theta;else hi=theta;
        }
        points.push(g);
      }
      return points;
    }
    app.boundary=boundary;app.visible=visible;
    function syncLayers(){
      const footprintShown=document.getElementById('footprints').checked;
      for(const f of footprints)f.entity.show=footprintShown;
      for(const cone of cones)cone.show=document.getElementById('cones').checked;
    }
    function update(time,force=false){
      if(!app.ready)return;
      const wall=performance.now();
      if(!force&&wall-lastWall<180)return;
      if(!force&&lastTime&&Math.abs(C.JulianDate.secondsDifference(time,lastTime))<.2)return;
      lastWall=wall;lastTime=C.JulianDate.clone(time);
      const positions=satellites.map(e=>e.position.getValue(time)).filter(Boolean);
      for(let i=0;i<satellites.length;i++){
        const position=satellites[i].position.getValue(time);
        if(!position)continue;
        if(document.getElementById('footprints').checked){
          const ring=boundary(position);
          footprints[i].hierarchy=new C.PolygonHierarchy(ring);
          footprints[i].outline=[...ring,ring[0]];
        }
      }
      const stationCounts={};
      for(const s of stations){
        const count=positions.filter(p=>visible(p,s.ground,s.normal)).length;
        const name=s.entity.id.replace('station-','');stationCounts[name]=count;
        const label=document.getElementById(name);
        if(label){label.textContent=(name==='TOKYO'?'东京':name)+' '+count+' 星';label.style.color=count?green.toCssColorString():red.toCssColorString();}
        s.entity.point.color=count?green:red;
      }
      let covered=0;
      const routeCounts=[];
      for(const target of route){
        const count=positions.filter(p=>visible(p,target.ground,target.normal)).length;
        target.entity.point.color=count?green:red;covered+=count>0?1:0;routeCounts.push(count);
      }
      const label=document.getElementById('corridor');label.textContent='航线 '+covered+'/'+route.length+' 点覆盖';
      label.style.color=covered===route.length?green.toCssColorString():red.toCssColorString();
      app.lastStats={time:C.JulianDate.toIso8601(time,0),stationCounts,routeCounts,covered,total:route.length};
      status.textContent=app.lastStats.time.replace('T',' ').replace('Z',' UTC')+' · 红点表示当前无仰角 ≥'+epsilon+'° 的卫星';
    }
    app.update=update;
    function routeCamera(){viewer.camera.flyTo({destination:C.Cartesian3.fromDegrees(65,57,23000000),duration:.8});}
    document.getElementById('route-view').onclick=routeCamera;
    document.getElementById('global-view').onclick=()=>viewer.camera.flyTo({destination:C.Cartesian3.fromDegrees(30,25,38000000),duration:.8});
    for(const id of ['footprints','cones'])document.getElementById(id).onchange=()=>{syncLayers();update(viewer.clock.currentTime,true);};
    async function load(input,preserveTime=false){
      const previousTime=preserveTime&&app.ready?C.JulianDate.clone(viewer.clock.currentTime):null;
      const wasPlaying=viewer.clock.shouldAnimate;viewer.clock.shouldAnimate=false;
      app.ready=false;status.textContent='正在解析轨迹…';status.className='';
      viewer.entities.removeAll();viewer.dataSources.removeAll(true);
      const ds=await C.CzmlDataSource.load(input);
      const cfg=ds.entities.getById('configuration');
      const property=name=>cfg?.properties?.[name]?.getValue(ds.clock.currentTime);
      epsilon=property('minElevationDeg')??20;
      document.getElementById('footprint-label').textContent=epsilon+'° 足印';
      satellites=ds.entities.values.filter(e=>e.properties?.satellite?.getValue(ds.clock.currentTime));
      cones=ds.entities.values.filter(e=>e.properties?.cone?.getValue(ds.clock.currentTime));
      if(!satellites.length)throw new Error('星历中未找到 satellite 标记');
      // Thin mobile CZML contains ephemeris only. Derive sphere-approximation
      // cones at playback time instead of downloading a second ephemeris/quaternion stream.
      if(!cones.length){
        for(const satellite of satellites){
          const plane=satellite.properties.plane.getValue(ds.clock.currentTime),color=planeColors[(plane-1)%3];
          let cachedTime=null,cachedPose=null;
          function pose(time){
            if(cachedTime&&C.JulianDate.equals(cachedTime,time))return cachedPose;
            const r=satellite.position.getValue(time);if(!r)return null;
            const radius=C.Cartesian3.magnitude(r),radial=C.Cartesian3.normalize(r,new C.Cartesian3());
            const eps=epsilon*Math.PI/180,beta=Math.acos(A/radius*Math.cos(eps))-eps;
            const length=radius-A*Math.cos(beta),base=A*Math.sin(beta);
            const center=C.Cartesian3.subtract(r,C.Cartesian3.multiplyByScalar(radial,length/2,new C.Cartesian3()),new C.Cartesian3());
            let rotation;
            const axis=C.Cartesian3.cross(C.Cartesian3.UNIT_Z,radial,new C.Cartesian3());
            if(C.Cartesian3.magnitude(axis)<1e-10)rotation=radial.z>=0?C.Quaternion.IDENTITY:C.Quaternion.fromAxisAngle(C.Cartesian3.UNIT_X,Math.PI);
            else rotation=C.Quaternion.fromAxisAngle(C.Cartesian3.normalize(axis,axis),Math.acos(Math.max(-1,Math.min(1,radial.z))));
            cachedTime=C.JulianDate.clone(time);cachedPose={center,rotation,length,base};return cachedPose;
          }
          cones.push(ds.entities.add({id:'cone-'+satellite.id,name:satellite.id+' spherical cone (approx.)',
            position:new C.CallbackPositionProperty(time=>pose(time)?.center,false,C.ReferenceFrame.FIXED),
            orientation:new C.CallbackProperty(time=>pose(time)?.rotation,false),
            cylinder:{length:new C.CallbackProperty(time=>pose(time)?.length,false),topRadius:0,
              bottomRadius:new C.CallbackProperty(time=>pose(time)?.base,false),slices:48,material:color.withAlpha(.11)}}));
        }
      }
      footprints=[];
      for(const sat of satellites){
        const plane=sat.properties.plane.getValue(ds.clock.currentTime),color=planeColors[(plane-1)%3];
        const f={hierarchy:new C.PolygonHierarchy([]),outline:[],entity:null};
        f.entity=viewer.entities.add({id:'footprint-'+sat.id,name:sat.id+' WGS84 elevation footprint',
          polygon:{hierarchy:new C.CallbackProperty(()=>f.hierarchy,false),height:30,material:color.withAlpha(.14),arcType:C.ArcType.GEODESIC},
          polyline:{positions:new C.CallbackProperty(()=>f.outline,false),width:1.2,material:color.withAlpha(.7),clampToGround:false}});
        footprints.push(f);
      }
      stations=ds.entities.values.filter(e=>e.properties?.station?.getValue(ds.clock.currentTime)).map(e=>surfacePoint(e,ds.clock.currentTime,false));
      for(const s of stations)if(s.entity.label)s.entity.label.disableDepthTestDistance=0;
      route=ds.entities.values.filter(e=>e.properties?.routeSample?.getValue(ds.clock.currentTime)).map(e=>surfacePoint(e,ds.clock.currentTime,true));
      syncLayers();await viewer.dataSources.add(ds);
      Object.assign(viewer.clock,{startTime:C.JulianDate.clone(ds.clock.startTime),stopTime:C.JulianDate.clone(ds.clock.stopTime),
        currentTime:previousTime&&C.JulianDate.greaterThanOrEquals(previousTime,ds.clock.startTime)&&C.JulianDate.lessThanOrEquals(previousTime,ds.clock.stopTime)?previousTime:C.JulianDate.clone(ds.clock.currentTime),
        clockRange:C.ClockRange.LOOP_STOP,multiplier:120,shouldAnimate:preserveTime&&wasPlaying});
      viewer.timeline.zoomTo(viewer.clock.startTime,viewer.clock.stopTime);
      const planes=property('planeCount')??new Set(satellites.map(e=>e.properties.plane.getValue(ds.clock.currentTime))).size;
      document.getElementById('configuration').textContent=property('displayDescription')?
        property('displayDescription')+' · 最低仰角 '+epsilon+'°':
        property('inclinationDeg')+'° · '+satellites.length+'/'+planes+'/'+property('walkerF')+' · '+property('altitudeKm')+' km · 最低仰角 '+epsilon+'°';
      app.satelliteEntities=satellites;app.coneEntities=cones;app.routePoints=route;app.footprints=footprints;app.ready=true;
      update(viewer.clock.currentTime,true);if(!preserveTime||!previousTime)routeCamera();
    }
    app.load=load;
    document.getElementById('file').onchange=async e=>{const file=e.target.files[0];if(file){try{await load(JSON.parse(await file.text()));document.getElementById('study-summary').hidden=true;}catch(error){fail(error);}}};
    viewer.clock.onTick.addEventListener(clock=>update(clock.currentTime));
    if(location.protocol==='file:')status.textContent='请选择导出的 walker-delta.czml 文件；时间轴可播放 24 小时';
    else {
      let presets=null;
      try{const response=await fetch('./data/scenarios.json');if(response.ok)presets=await response.json();}catch(_){}
      if(presets?.scenarios?.length){
        const selector=document.getElementById('scenario'),study=document.getElementById('study-summary');
        for(const preset of presets.scenarios){const option=document.createElement('option');option.value=preset.id;option.textContent=preset.label;selector.appendChild(option);}
        document.getElementById('scenario-control').hidden=false;
        async function choose(){
          selector.disabled=true;
          try{const preset=presets.scenarios.find(x=>x.id===selector.value);await load(preset.url,true);
            study.hidden=false;study.textContent='24h/'+preset.step_s+'s 几何采样：三站同时有星 '+(preset.joint*100).toFixed(2)+'% · 三站均有至少2星 '+(preset.dual*100).toFixed(2)+'%（非网络SLA）'+(preset.note?' · '+preset.note:'');
          }catch(error){fail(error);}finally{selector.disabled=false;}
        }
        selector.onchange=choose;await choose();
      }else await load('/data/walker-delta.czml');
    }
  }catch(error){fail(error);}
})();
