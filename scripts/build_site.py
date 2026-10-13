"""Build the complete public static toolkit; no new coverage/routing scans."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import shutil
from dataclasses import replace
from hftsim.tools import parse_config
from hftsim.czml import export_shells_czml

ROOT=Path(__file__).resolve().parents[1]
def build(out):
    out=Path(out).resolve()
    if out==ROOT or out==ROOT/'viewer':raise ValueError('Output must be a build directory')
    out.mkdir(parents=True,exist_ok=True);data=out/'data';data.mkdir(exist_ok=True)
    for name in ['index.html','lab.css','latency.html','latency.js']:shutil.copyfile(ROOT/'viewer'/name,out/name)
    shutil.copyfile(ROOT/'viewer/cesium/index.html',out/'coverage.html')
    for name in ['style.css','viewer.js','custom.js']:shutil.copyfile(ROOT/'viewer/cesium'/name,out/name)
    shutil.copytree(ROOT/'viewer/shared',out/'shared',dirs_exist_ok=True)
    shutil.copytree(ROOT/'viewer/docs',out/'docs',dirs_exist_ok=True)
    shutil.copytree(ROOT/'configs',data/'configs',dirs_exist_ok=True)
    for name in ['catalog.json','stations.json','baselines.json']:shutil.copyfile(ROOT/'data'/name,data/name)
    presets=json.loads((ROOT/'data/preset-metrics.json').read_text())
    scene=None
    for item in presets['scenarios']:
        cfg=json.loads((ROOT/'configs'/f"{item['id']}.json").read_text());sim,shells,physics=parse_config(cfg)
        step=120 if item['id']=='lightspeed298' else 60 if item['id'].startswith('globalstar') else 30
        packets,meta=export_shells_czml(shells,replace(sim,step_s=step),physics.min_elevation_deg,cfg['name'])
        if scene is None:scene=[p for p in packets if not p.get('properties',{}).get('satellite')]
        if item['id']=='lightspeed298':
            for packet in packets:
                if packet.get('properties',{}).get('satellite'):packet['path']['trailTime']=240
        path=data/f"{item['id']}.json";path.write_text(json.dumps(packets,ensure_ascii=False,separators=(',',':')))
        item['url']=f"./data/{item['id']}.json";item['bytes']=path.stat().st_size
    (data/'scenarios.json').write_text(json.dumps(presets,ensure_ascii=False,indent=2))
    (data/'scene.json').write_text(json.dumps(scene,ensure_ascii=False,separators=(',',':')))
    js=(out/'viewer.js').read_text().replace("load('/data/walker-delta.czml')","load('./data/baseline18.json')")
    (out/'viewer.js').write_text(js)
    print(f'Built two tools and {len(presets["scenarios"])} cached presets at {out}')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='build/site');args=parser.parse_args();build(args.out)
