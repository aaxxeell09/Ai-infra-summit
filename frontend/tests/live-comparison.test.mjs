import test from 'node:test';
import assert from 'node:assert/strict';
import {createLiveComparisonProvider} from '../public/live-comparison.mjs';
const cfg = {cell_id:'cpu-t10',model_sha256:'weights',runtime_sha256:'exe',requested_device:'cpu',params:{n_threads:10,n_ctx:4096}};
const request = {request_id:'req-1',comparison:'speed',baseline:{...cfg,cell_id:'cpu-t0',params:{n_threads:0,n_ctx:4096}},selected:cfg};
function lane(c=cfg) {return {status:'completed',answer:'Actual answer',configuration_applied:true,effective_configuration:{cell_id:c.cell_id,model_sha256:'weights',runtime_sha256:'exe',device:'cpu',threads:c.params.n_threads,context:4096},ttft_ms:20,total_time_s:2,output_tokens:5,native_decode_tps:50};}
const final = () => ({request_id:'req-1',state:'completed',events:[],result:{schema_version:'local-turbo.comparison-result.v1',request_id:'req-1',mode:'live',lanes:{default:lane(request.baseline),turbo:lane()},winner:null,speedup:null}});
const reply = value => ({ok:true,json:async()=>value});
function memory() {const m=new Map();return {getItem:k=>m.get(k),setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};}
test('live returns device text and measured results without a scripted fallback', async()=>{
 const p=createLiveComparisonProvider({storage:memory(),fetcher:async(_,o)=>reply(o.method?{}:final())});
 const r=await p.execute(request);assert.equal(r.lanes.turbo.answer,'Actual answer');assert.equal(r.lanes.turbo.total_time_s,2);assert.equal(r.winner,null);assert.equal(p.pendingRequest(),null);
});
test('wrong applied configuration blocks success and keeps reconciliation state', async()=>{
 const state=final();state.result.lanes.turbo.effective_configuration.threads=6;
 const p=createLiveComparisonProvider({storage:memory(),fetcher:async(_,o)=>reply(o.method?{}:state)});
 await assert.rejects(p.execute(request),/acknowledge/);assert.equal(p.pendingRequest().request_id,'req-1');
});
test('second-lane failure preserves first-lane evidence',async()=>{
 const state=final();state.state='failed';state.error='Native load failed';state.result.lanes.turbo={status:'failed',answer:''};
 const p=createLiveComparisonProvider({storage:memory(),fetcher:async(_,o)=>reply(o.method?{}:state)});
 const r=await p.execute(request);assert.equal(r.status,'failed');assert.equal(r.lanes.default.answer,'Actual answer');assert.equal(p.pendingRequest(),null);
});
test('cancel is requested and polled through terminal cleanup, not treated as instant completion',async()=>{
 const controller=new AbortController();let cancelled=false;let polls=0;
 const state=final();state.state='cancelled';state.result.lanes={};
 const p=createLiveComparisonProvider({storage:memory(),interval:0,fetcher:async(url,o)=>{
  if(url.endsWith('/cancel')){cancelled=true;return reply({});}
  if(o.method){controller.abort();return reply({});}
  polls++;return reply(polls===1?{request_id:'req-1',state:'running',events:[]}:state);
 }});
 const r=await p.execute(request,{signal:controller.signal});assert.ok(cancelled);assert.equal(polls,2);assert.equal(r.status,'cancelled');assert.equal(p.pendingRequest(),null);
});
test('network failure retains the same ID across reload for reconciliation',async()=>{
 const storage=memory();const p=createLiveComparisonProvider({storage,fetcher:async()=>{throw new Error('offline');}});
 await assert.rejects(p.execute(request),/offline/);
 const calls=[];const next=createLiveComparisonProvider({storage,fetcher:async(url,o)=>{calls.push(o.method);return reply(final());}});
 await next.execute(request);assert.deepEqual(calls,[undefined]);assert.equal(next.pendingRequest(),null);
});
