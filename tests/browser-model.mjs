import fs from 'node:fs';
import assert from 'node:assert/strict';
import {ephemeris,runLatency,validateConfig} from '../viewer/shared/model.js';
const fixtures=JSON.parse(fs.readFileSync(new URL('./fixtures/browser-model.json',import.meta.url)));
const stations=JSON.parse(fs.readFileSync(new URL('../data/stations.json',import.meta.url))),baselines=JSON.parse(fs.readFileSync(new URL('../data/baselines.json',import.meta.url)));
let count=0,maxKm=0,maxMs=0;
for(const f of fixtures){const ep=ephemeris(f.config);
  for(const [time,expected] of Object.entries(f.positions)){const actual=ep.positions(Number(time));assert.equal(actual.length,expected.length);
    actual.forEach((r,i)=>{const error=Math.hypot(...r.map((v,j)=>v-expected[i][j]));maxKm=Math.max(maxKm,error);assert.ok(error<1e-7);count++;});}
  const result=runLatency(f.config,stations,baselines);assert.equal(result.frames.length,f.frames.length);
  result.frames.forEach((r,i)=>{const expected=f.frames[i];assert.equal(r.source_visible,expected.source_visible);assert.equal(r.destination_visible,expected.destination_visible);assert.equal(r.accepted_isl,expected.accepted_isl);
    if(expected.rtt_ms===null)assert.equal(r.rtt_ms,null);else{const error=Math.abs(r.rtt_ms-expected.rtt_ms);maxMs=Math.max(maxMs,error);assert.ok(error<1e-8);}});
}
assert.throws(()=>validateConfig({...fixtures[0].config,schema_version:2}));
console.log(JSON.stringify({positionChecks:count,maxPositionErrorKm:maxKm,maxLatencyErrorMs:maxMs,models:fixtures.length}));
