"""Two reusable tools with one versioned JSON configuration contract."""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx
from .config import Constellation, Simulation, Physics
from .orbits import CompositeEphemeris
from .optics import candidate_edges
from .geometry import geodetic_ecef, ground_up, elevation_deg, segment_min_radius
from .config import RE_KM, C_KM_S
from .benchmarks import load_data
from .czml import export_shells_czml, visible_counts
from .engine import simulate, build_graph, save_result
from .phase3 import availability_metrics
from .plots import comparison_plot, jitter_boxplot


def parse_config(payload):
    if payload.get('schema_version') != 1:
        raise ValueError('Require schema_version=1')
    sim=Simulation(**payload.get('simulation',{}))
    physics=Physics(**payload.get('physics',{}))
    shells=[]
    for row in payload.get('shells',[]):
        row=dict(row);pattern=row.pop('pattern','delta');p=row.get('planes',1)
        if pattern=='delta':row['raan_span_deg']=360
        elif pattern=='star':row['raan_span_deg']=180*(p-1)/p if p>1 else 360
        elif pattern!='partial':raise ValueError('pattern must be delta, star or partial')
        c=Constellation(**row)
        if not 0<=c.walker_f<c.planes:raise ValueError('Walker F must be between 0 and P-1')
        shells.append(c)
    if not shells:raise ValueError('At least one shell is required')
    return sim,tuple(shells),physics


def topology_edges(shells,topology='grid'):
    count=sum(c.count for c in shells)
    if topology=='complete':
        if count>150:raise ValueError('Unlimited-terminal mesh limited to 150 satellites')
        return np.column_stack(np.triu_indices(count,1))
    if topology!='grid':raise ValueError('topology must be grid or complete')
    edges=[];offset=0
    for c in shells:
        edges.extend((candidate_edges(replace(c,topology='grid'))+offset).tolist());offset+=c.count
    return np.asarray(edges,dtype=int).reshape(-1,2)


def geometry_latency(payload,progress=None):
    """Geometric graph with immediate access to every visible satellite."""
    sim,shells,p=parse_config(payload);ep=CompositeEphemeris(shells,sim.epoch_datetime)
    edges=topology_edges(shells,payload.get('topology','grid'))
    stations,baselines=load_data();baseline=baselines['routes'][sim.route]
    ground=[geodetic_ecef(stations[n]['lat_deg'],stations[n]['lon_deg'],stations[n]['height_km']) for n in baseline['stations']]
    normals=[ground_up(stations[n]['lat_deg'],stations[n]['lon_deg']) for n in baseline['stations']]
    reference=sim.baseline_rtt_ms or baseline['rtt_ms'];rows=[];previous=None
    times=np.arange(0,sim.duration_s,sim.step_s)
    for k,t in enumerate(times):
        re=ep.state(float(t))[2];a,b=edges.T
        distance=np.linalg.norm(re[b]-re[a],axis=-1)
        usable=(distance<=p.max_isl_range_km)&(segment_min_radius(re[a],re[b])>=RE_KM+p.atmosphere_km)
        gd=[np.linalg.norm(re-g,axis=-1) for g in ground]
        ready=[np.flatnonzero(elevation_deg(re,g,u)>=p.min_elevation_deg).tolist() for g,u in zip(ground,normals)]
        graph=build_graph(ep.count,edges,usable,distance,ready,gd,p)
        rtt=owtt=length=hops=np.nan;path=None
        try:
            owtt,seq=nx.single_source_dijkstra(graph,ep.count,ep.count+1,weight='weight')
            path=tuple(seq);rtt=2*owtt*1000;hops=len(path)-2
            length=sum(graph[x][y]['distance_km'] for x,y in zip(path,path[1:]))
            reason='connected'
        except nx.NetworkXNoPath:reason='no_visible_ground_satellite' if min(map(len,ready))==0 else 'no_isl_route'
        changed=previous is not None and path is not None and previous!=path
        rows.append(dict(time_s=float(t),sample_duration_s=float(min(sim.step_s,sim.duration_s-t)),
            rtt_ms=rtt,owtt_ms=owtt*1000,delta_rtt_ms=reference-rtt,reference_rtt_ms=reference,
            satellite_relays=hops,path_length_km=length,path='>'.join(map(str,path)) if path else '',
            path_changed=changed,outage_reason=reason,source_visible=len(ready[0]),destination_visible=len(ready[1]),accepted_isl=int(usable.sum())))
        previous=path
        if progress and k%max(1,len(times)//20)==0:progress(k/len(times))
    metadata=dict(configuration=payload,mode='geometry',shells=[asdict(c) for c in shells],
        benchmark=baseline,excluded='PAT/FOV/slew/Doppler/acquisition/handover/traffic/weather/capacity',
        convention='2 × same-epoch symmetric OWTT; every visible ground link ready immediately; grid has no cross-shell edges; complete has unlimited terminals')
    return pd.DataFrame(rows),pd.DataFrame(columns=['station','time_s','kind']),metadata


def engineering_latency(payload):
    sim,shells,p=parse_config(payload);count=sum(c.count for c in shells)
    ep=CompositeEphemeris(shells,sim.epoch_datetime)
    topology=topology_edges(shells,payload.get('topology','grid'))
    # Node-count carrier only; the explicitly supplied edges define all links.
    carrier=Constellation(planes=1,sats_per_plane=count,label=payload.get('name','Configured shells'))
    frame,events,meta=simulate(sim,carrier,p,ephemeris=ep,edges=topology)
    meta.update(configuration=payload,mode='engineering',shells=[asdict(c) for c in shells],
                topology_note='Explicit grid is shell-local; complete is an unlimited-terminal counterfactual')
    return frame,events,meta


def coverage_main():
    parser=argparse.ArgumentParser(description='Tool 1: geometric coverage CZML and access audit')
    parser.add_argument('--config',required=True);parser.add_argument('--out',default='outputs/coverage')
    parser.add_argument('--ephemeris-step',type=float,default=60)
    args=parser.parse_args();payload=json.loads(Path(args.config).read_text());sim,shells,p=parse_config(payload)
    if args.ephemeris_step<=0 or args.ephemeris_step>sim.duration_s:raise ValueError('Invalid ephemeris step')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    packets,meta=export_shells_czml(shells,replace(sim,step_s=args.ephemeris_step),p.min_elevation_deg,payload.get('name','Custom constellation'))
    (out/'constellation.czml').write_text(json.dumps(packets,ensure_ascii=False,separators=(',',':')))
    stations,_=load_data();names=['LD4','NY4','TOKYO'];ep=CompositeEphemeris(shells,sim.epoch_datetime)
    ground=np.array([geodetic_ecef(stations[n]['lat_deg'],stations[n]['lon_deg'],stations[n]['height_km']) for n in names])
    up=np.array([ground_up(stations[n]['lat_deg'],stations[n]['lon_deg']) for n in names])
    times=np.arange(0,sim.duration_s,sim.step_s);counts=[]
    for start in range(0,len(times),240):counts.append(visible_counts(ep.state(times[start:start+240,None])[2],ground,up,p.min_elevation_deg))
    counts=np.concatenate(counts);weights=np.minimum(sim.step_s,sim.duration_s-times)
    pd.DataFrame(dict(time_s=times,**{n:counts[:,j] for j,n in enumerate(names)})).to_csv(out/'coverage.csv',index=False)
    summary=dict(joint=availability_metrics((counts>0).all(axis=1),weights),
                 joint_dual=float(np.average((counts>=2).all(axis=1),weights=weights)),
                 stations={n:availability_metrics(counts[:,j]>0,weights) for j,n in enumerate(names)})
    meta.update(configuration=payload,geometry_only=True)
    (out/'metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))


def latency_main():
    parser=argparse.ArgumentParser(description='Tool 2: geometry or engineering snapshot latency')
    parser.add_argument('--config',required=True);parser.add_argument('--mode',choices=['geometry','engineering'],default='engineering')
    parser.add_argument('--out',default='outputs/latency');args=parser.parse_args()
    payload=json.loads(Path(args.config).read_text())
    frame,events,meta=(geometry_latency if args.mode=='geometry' else engineering_latency)(payload)
    save_result(args.out,frame,events,meta)
    comparison_plot({payload.get('name','Custom'):frame},Path(args.out)/'latency.png')
    jitter_boxplot({payload.get('name','Custom'):frame},Path(args.out)/'jitter.png')
    print((Path(args.out)/'summary.json').read_text())
